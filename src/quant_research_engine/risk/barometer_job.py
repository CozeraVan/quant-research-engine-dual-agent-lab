"""大盘/板块风险风向标数据装配层（CR_2026-08-23_market_risk_barometer §4 M2）。

本模块是 risk 包**唯一允许读写 DB 的层**：业务表只读
（public.stock_daily / reference.daily_basic / reference.stock_basic /
cluster.daily_tags / reference.trade_calendar），只写自有结果表
market_risk.daily。计算 100% 委托 M1 纯函数内核（cross_section/barometer）。

口径（披露）：
- 收益 = stock_daily.pct_chg / 100（tushare 前收盘口径，与 cluster-ashare
  tags_daily 一致；复权一致的日收益）。
- 市值权重 = reference.daily_basic.total_mv 当日截面内归一化。
- 行业分组 = reference.stock_basic.industry（静态映射）。
- 动态簇分组 = cluster.daily_tags 当日 tag → 成员（逐日变动；簇内 <5 只
  跳过）。簇行只输出当日截面指标 + 预警；252 日滚动分数需要固定成员
  历史序列，M2 对簇不计算分数（scores=None + note 披露）。行业与全市场
  计算完整分数。
- 组合法 ES99（expanding 历史模拟）为逐日序列，入 indicators；组合法
  EWMA/VaR/ES 汇总为整段统计，只入单日模式 JSON 产物的 portfolio 节。

存储（决策记录于 08_IMPLEMENTATION_BRIEF M2 节）：
- 独立 schema market_risk（QRE 产出与 cluster schema 分空间）；
  表 market_risk.daily，PK (trade_date, scope)，scope ∈
  market / industry:<行业> / cluster:<tag>；
  ON CONFLICT 行级幂等 upsert（结果行少，非千万级长表，无需窗口
  DELETE+INSERT）。
- JSON 产物 outputs/market_risk/<date>.json（引擎与结果分空间原则；
  QRE_OUTPUT_DIR 覆盖根目录）。

回填分块：区间按 chunk（默认 year）切块，每块前补
SCORE_WINDOW+CORR_WINDOW=312 交易日 buffer（分位窗口 + 相关窗口
warmup），块内计算后只写块区间日期；块间结果与整段一致
（EWMA/相关/分位均为 trailing 窗口统计，buffer 覆盖最大窗口）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from quant_research_engine.risk import barometer, cross_section
from quant_research_engine.risk.constants import (
    BAROMETER_CORR_WINDOW,
    BAROMETER_SCORE_WINDOW,
    Z_99,
)

log = logging.getLogger(__name__)

#: 默认库连接（本机 socket；QRE_MARKET_RISK_DB_URL > QRE_MARKET_DB_URL 覆盖）
DEFAULT_DB_URL = "postgresql+psycopg:///tushare_data"

RESULT_SCHEMA = "market_risk"
RESULT_TABLE = "daily"

#: 回填 buffer（交易日）：分位窗口 252 + 相关窗口 60
BUFFER_TRADE_DAYS = BAROMETER_SCORE_WINDOW + BAROMETER_CORR_WINDOW

#: 簇/行业最小成员数（CR §3：簇内 <5 只跳过；行业同口径对齐）
MIN_GROUP_MEMBERS = 5

DDL = (
    f"CREATE SCHEMA IF NOT EXISTS {RESULT_SCHEMA}",
    f"""
    CREATE TABLE IF NOT EXISTS {RESULT_SCHEMA}.{RESULT_TABLE} (
        trade_date date NOT NULL,
        scope text NOT NULL,
        n_stocks integer,
        indicators jsonb NOT NULL,
        scores jsonb,
        alert jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (trade_date, scope)
    )
    """,
)

UPSERT_SQL = f"""
INSERT INTO {RESULT_SCHEMA}.{RESULT_TABLE}
    (trade_date, scope, n_stocks, indicators, scores, alert)
VALUES (:trade_date, :scope, :n_stocks, CAST(:indicators AS jsonb),
        CAST(:scores AS jsonb), CAST(:alert AS jsonb))
ON CONFLICT (trade_date, scope) DO UPDATE SET
    n_stocks = EXCLUDED.n_stocks,
    indicators = EXCLUDED.indicators,
    scores = EXCLUDED.scores,
    alert = EXCLUDED.alert
"""


def resolve_db_url() -> str:
    return (
        os.environ.get("QRE_MARKET_RISK_DB_URL", "").strip()
        or os.environ.get("QRE_MARKET_DB_URL", "").strip()
        or DEFAULT_DB_URL
    )


def get_engine(url: str | None = None):
    return create_engine(url or resolve_db_url(), pool_pre_ping=True)


def output_dir() -> str:
    root = os.environ.get("QRE_OUTPUT_DIR", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "outputs"
    )
    path = os.path.abspath(os.path.join(root, "market_risk"))
    os.makedirs(path, exist_ok=True)
    return path


# ── 取数（业务表只读）──


def fetch_trade_dates(engine, d0: dt.date, d1: dt.date) -> list[dt.date]:
    """交易日历（reference.trade_calendar，is_open=1，cal_date 升序）。"""
    frame = pd.read_sql(
        text(
            "SELECT cal_date FROM reference.trade_calendar "
            "WHERE is_open = 1 AND cal_date BETWEEN :d0 AND :d1 ORDER BY cal_date"
        ),
        engine,
        params={"d0": d0, "d1": d1},
    )
    return [d if isinstance(d, dt.date) else d.date() for d in frame["cal_date"]]


def _pivot(frame: pd.DataFrame, value_col: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    wide = frame.pivot(index="trade_date", columns="ts_code", values=value_col)
    wide.index = pd.to_datetime(wide.index)  # date/Timestamp 统一为 datetime64
    return wide.sort_index()


def fetch_returns_panel(engine, d0: dt.date, d1: dt.date) -> pd.DataFrame:
    """收益面板（dates × ts_code）：pct_chg/100（前收盘口径）。"""
    frame = pd.read_sql(
        text(
            "SELECT ts_code, trade_date, pct_chg / 100.0 AS ret "
            "FROM public.stock_daily WHERE trade_date BETWEEN :d0 AND :d1"
        ),
        engine,
        params={"d0": d0, "d1": d1},
    )
    return _pivot(frame, "ret")


def fetch_market_cap_panel(engine, d0: dt.date, d1: dt.date) -> pd.DataFrame:
    """市值面板（total_mv）；缺失列为 NaN（加权函数行内归一化时剔除）。"""
    frame = pd.read_sql(
        text(
            "SELECT ts_code, trade_date, total_mv::float8 AS mv "
            "FROM reference.daily_basic WHERE trade_date BETWEEN :d0 AND :d1"
        ),
        engine,
        params={"d0": d0, "d1": d1},
    )
    return _pivot(frame, "mv")


def fetch_industry_groups(engine) -> dict[str, list[str]]:
    """行业分组（reference.stock_basic.industry，静态映射）。"""
    frame = pd.read_sql(
        text(
            "SELECT ts_code, industry FROM reference.stock_basic "
            "WHERE industry IS NOT NULL AND industry <> ''"
        ),
        engine,
    )
    groups: dict[str, list[str]] = {}
    for industry, sub in frame.groupby("industry"):
        groups[str(industry)] = sorted(sub["ts_code"].astype(str))
    return groups


def fetch_cluster_groups(engine, trade_date: dt.date) -> dict[str, list[str]]:
    """当日标签簇分组（cluster.daily_tags，tag → 成员）。"""
    frame = pd.read_sql(
        text(
            "SELECT ts_code, tag FROM cluster.daily_tags WHERE trade_date = :d"
        ),
        engine,
        params={"d": trade_date},
    )
    groups: dict[str, list[str]] = {}
    for tag, sub in frame.groupby("tag"):
        groups[str(tag)] = sorted(sub["ts_code"].astype(str).unique())
    return groups


# ── 结果表读写（唯一写库点）──


def ensure_storage(engine) -> None:
    with engine.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))


def upsert_daily(engine, rows: list[dict[str, Any]]) -> int:
    """幂等 upsert（ON CONFLICT (trade_date, scope)），返回写入行数。"""
    if not rows:
        return 0
    params = []
    for r in rows:
        params.append(
            {
                "trade_date": r["trade_date"],
                "scope": r["scope"],
                "n_stocks": r["n_stocks"],
                "indicators": json.dumps(_jsonable(r["indicators"]), ensure_ascii=False),
                "scores": json.dumps(_jsonable(r["scores"]), ensure_ascii=False),
                "alert": json.dumps(_jsonable(r["alert"]), ensure_ascii=False),
            }
        )
    with engine.begin() as conn:
        conn.execute(text(UPSERT_SQL), params)
    return len(params)


def _jsonable(value: Any) -> Any:
    """递归转 JSON 可序列化（NaN/inf → None，numpy 标量 → python，日期 → ISO）。"""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
        return value.isoformat()
    return value


def write_json_product(date: dt.date, payload: dict[str, Any]) -> str:
    path = os.path.join(output_dir(), f"{date.isoformat()}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_jsonable(payload), fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


# ── 分块（纯函数，供测试）──


def chunk_ranges(dates: list[dt.date], chunk: str = "year") -> list[tuple[dt.date, dt.date]]:
    """把交易日序列按 chunk（year/month/all）切成 [首, 末] 区间。"""
    if not dates:
        return []
    if chunk == "all":
        return [(dates[0], dates[-1])]
    if chunk not in {"year", "month"}:
        raise ValueError(f"chunk must be year/month/all, got {chunk}")
    key = (lambda d: d.year) if chunk == "year" else (lambda d: (d.year, d.month))
    ranges: list[tuple[dt.date, dt.date]] = []
    start = prev = dates[0]
    for d in dates[1:]:
        if key(d) != key(prev):
            ranges.append((start, prev))
            start = d
        prev = d
    ranges.append((start, prev))
    return ranges


def buffer_start(engine, d0: dt.date, buffer_days: int = BUFFER_TRADE_DAYS) -> dt.date:
    """d0 前第 buffer_days 个交易日（不足则取最早可用）。"""
    frame = pd.read_sql(
        text(
            "SELECT cal_date FROM reference.trade_calendar "
            "WHERE is_open = 1 AND cal_date < :d0 ORDER BY cal_date DESC LIMIT :n"
        ),
        engine,
        params={"d0": d0, "n": int(buffer_days)},
    )
    if frame.empty:
        return d0
    earliest = frame["cal_date"].iloc[-1]
    return earliest if isinstance(earliest, dt.date) else earliest.date()


# ── 组装（计算全委托 M1 内核）──


def _series_at(series: pd.Series, date: Any) -> float | None:
    try:
        v = series.loc[date]
    except KeyError:
        return None
    if isinstance(v, pd.Series):
        v = v.iloc[-1]
    return float(v) if pd.notna(v) else None


def _score_at(score_df: pd.DataFrame, date: Any) -> tuple[float | None, bool]:
    try:
        row = score_df.loc[date]
    except KeyError:
        return None, True
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    warm = bool(row["warmup"])
    return (None if warm else float(row["score"])), warm


def _universe_rows(
    result: dict[str, Any],
    scope: str,
    dates: list[pd.Timestamp],
) -> list[dict[str, Any]]:
    """把 build_barometer 单宇宙结果展开为逐日行（dates 限块区间）。"""
    ind = result["indicator_series"]
    scores = result["score_series"]
    corr_s = ind["avg_pairwise_corr"]
    breach_s = ind["breach_ratio"]
    n_s = ind["n_stocks"]
    es99_s = ind.get("portfolio_es99")
    rows = []
    for d in dates:
        comp_scores: dict[str, float | None] = {}
        warm = False
        for k, sc in scores.items():
            val, w = _score_at(sc, d)
            comp_scores[k] = val
            warm = warm or w
        valid = [v for v in comp_scores.values() if v is not None]
        total = float(np.mean(valid)) if valid else None
        alert = barometer.evaluate_alert(corr_s.loc[:d], breach_s.loc[:d])
        indicators = {
            "median_sigma": _series_at(ind["median_sigma"], d),
            "sigma_q90": _series_at(ind["sigma_q_high"], d),
            "dispersion_equal_weight": _series_at(ind["dispersion"], d),
            "avg_pairwise_corr_equal_weight": _series_at(corr_s, d),
            "var_breach_ratio": _series_at(breach_s, d),
            "portfolio_es99": _series_at(es99_s, d) if es99_s is not None else None,
        }
        n_val = _series_at(n_s, d)
        rows.append(
            {
                "trade_date": d.date() if hasattr(d, "date") else d,
                "scope": scope,
                "n_stocks": int(n_val) if n_val is not None else None,
                "indicators": indicators,
                "scores": {"components": comp_scores, "total_score": total, "warmup": warm},
                "alert": alert,
            }
        )
    return rows


def _cluster_rows(
    returns: pd.DataFrame,
    sigma_forecast: pd.DataFrame,
    var99: pd.DataFrame,
    dates: list[pd.Timestamp],
    cluster_groups_by_date: dict[pd.Timestamp, dict[str, list[str]]],
) -> list[dict[str, Any]]:
    """动态簇逐日行：当日成员截面指标 + 预警（簇分数 M2 不算，披露）。

    sigma_forecast/var99 为全市场预算面板，簇内只取成员列（不重算 EWMA，
    与全市场同口径）。
    """
    rows: list[dict[str, Any]] = []
    for d in dates:
        groups = cluster_groups_by_date.get(d, {})
        for tag, codes in groups.items():
            cols = [c for c in codes if c in returns.columns]
            if len(cols) < MIN_GROUP_MEMBERS:
                continue
            r_row = returns.loc[d, cols]
            sig_row = sigma_forecast.loc[d, cols]
            var_row = var99.loc[d, cols]
            valid = r_row.notna()
            n = int(valid.sum())
            if n < MIN_GROUP_MEMBERS:
                continue
            sigma_vals = sig_row[cols].dropna()
            # 簇当日突破占比（用簇成员）
            pair = pd.DataFrame({"r": r_row, "v": var_row}).dropna()
            br = float((pair["r"] < -pair["v"]).mean()) if len(pair) else None
            indicators = {
                "median_sigma": float(sigma_vals.median()) if len(sigma_vals) else None,
                "sigma_q90": float(sigma_vals.quantile(0.90)) if len(sigma_vals) else None,
                "dispersion_equal_weight": (
                    float(r_row[valid].std(ddof=1)) if n >= 2 else None
                ),
                "avg_pairwise_corr_equal_weight": None,
                "var_breach_ratio": br,
                "portfolio_es99": None,
            }
            alert = {
                "alert": None,
                "note": "cluster 簇 M2 不判预警（预警在全市场口径）；分数不计算（成员逐日变动）",
            }
            rows.append(
                {
                    "trade_date": d.date() if hasattr(d, "date") else d,
                    "scope": f"cluster:{tag}",
                    "n_stocks": n,
                    "indicators": indicators,
                    "scores": None,
                    "alert": alert,
                }
            )
    return rows


def compute_chunk(
    returns: pd.DataFrame,
    weights: pd.DataFrame | None,
    industry_groups: dict[str, list[str]],
    cluster_groups_by_date: dict[pd.Timestamp, dict[str, list[str]]],
    write_dates: list[pd.Timestamp],
) -> list[dict[str, Any]]:
    """块内计算：全市场 + 行业（build_barometer 完整分数）+ 簇（当日指标）。"""
    rows: list[dict[str, Any]] = []
    # 全市场
    market = barometer.build_barometer(returns, weights=weights)["market"]
    rows.extend(_universe_rows(market, "market", write_dates))
    # 行业（静态映射，完整分数）
    for industry, codes in sorted(industry_groups.items()):
        cols = [c for c in codes if c in returns.columns]
        if len(cols) < MIN_GROUP_MEMBERS:
            continue
        sub_w = weights.reindex(columns=cols) if weights is not None else None
        res = barometer.build_barometer(returns[cols], weights=sub_w)["market"]
        rows.extend(_universe_rows(res, f"industry:{industry}", write_dates))
    # 动态簇（当日成员，轻量指标）
    if cluster_groups_by_date:
        var_panel = cross_section.ewma_variance_panel(returns)
        sigma_forecast = np.sqrt(var_panel).shift(1)
        var99 = sigma_forecast * Z_99
        rows.extend(
            _cluster_rows(returns, sigma_forecast, var99, write_dates, cluster_groups_by_date)
        )
    return rows


def run_range(
    engine,
    d0: dt.date,
    d1: dt.date,
    chunk: str = "year",
    write_json: bool = True,
    fetch_cluster: bool = True,
) -> dict[str, Any]:
    """区间回填：分块取数（含 buffer）→ 计算 → 幂等 upsert + JSON 产物。"""
    ensure_storage(engine)
    dates = fetch_trade_dates(engine, d0, d1)
    if not dates:
        raise ValueError(f"no trade dates in [{d0}, {d1}]")
    industry_groups = fetch_industry_groups(engine)
    chunks = chunk_ranges(dates, chunk=chunk)
    total_rows = 0
    for c0, c1 in chunks:
        b0 = buffer_start(engine, c0)
        log.info("chunk [%s, %s]（buffer 自 %s）取数…", c0, c1, b0)
        returns = fetch_returns_panel(engine, b0, c1)
        weights = fetch_market_cap_panel(engine, b0, c1)
        log.info("收益面板 %d 日 × %d 股", *returns.shape)
        write_dates = [pd.Timestamp(d) for d in dates if c0 <= d <= c1]
        cluster_groups_by_date: dict[pd.Timestamp, dict[str, list[str]]] = {}
        if fetch_cluster:
            for d in write_dates:
                cluster_groups_by_date[d] = fetch_cluster_groups(engine, d.date())
        log.info("chunk [%s, %s] 计算…", c0, c1)
        rows = compute_chunk(returns, weights, industry_groups, cluster_groups_by_date, write_dates)
        written = upsert_daily(engine, [_jsonable(r) for r in rows])
        total_rows += written
        log.info("chunk [%s, %s] 写入 %d 行", c0, c1, written)
        if write_json:
            by_date: dict[dt.date, list[dict[str, Any]]] = {}
            for r in rows:
                by_date.setdefault(r["trade_date"], []).append(r)
            for d, day_rows in by_date.items():
                write_json_product(
                    d,
                    {
                        "trade_date": d.isoformat(),
                        "chunk": [c0.isoformat(), c1.isoformat()],
                        "buffer_start": b0.isoformat(),
                        "rows": day_rows,
                    },
                )
    return {"range": [d0.isoformat(), d1.isoformat()], "chunks": len(chunks), "rows_written": total_rows}


def run_date(
    engine,
    date: dt.date,
    write_json: bool = True,
    fetch_cluster: bool = True,
) -> dict[str, Any]:
    """单日模式（日更）：buffer 312 交易日 → 计算 → 写当日。"""
    summary = run_range(engine, date, date, chunk="all", write_json=write_json, fetch_cluster=fetch_cluster)
    return summary


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="market_risk_daily 装配/回填")
    parser.add_argument("--date", help="单日模式（日更），如 2026-08-20")
    parser.add_argument("--d0", help="区间起点 YYYY-MM-DD")
    parser.add_argument("--d1", help="区间终点 YYYY-MM-DD")
    parser.add_argument("--chunk", default="year", choices=["year", "month", "all"])
    parser.add_argument("--no-json", action="store_true", help="不写 JSON 产物")
    parser.add_argument("--no-cluster", action="store_true", help="不取动态簇分组")
    parser.add_argument("--db-url", default=None)
    args = parser.parse_args(argv)

    engine = get_engine(args.db_url)
    if args.date:
        d = dt.date.fromisoformat(args.date)
        summary = run_date(engine, d, write_json=not args.no_json, fetch_cluster=not args.no_cluster)
    elif args.d0 and args.d1:
        summary = run_range(
            engine,
            dt.date.fromisoformat(args.d0),
            dt.date.fromisoformat(args.d1),
            chunk=args.chunk,
            write_json=not args.no_json,
            fetch_cluster=not args.no_cluster,
        )
    else:
        parser.error("give --date or --d0/--d1")
    log.info("done: %s", summary)


if __name__ == "__main__":
    main()
