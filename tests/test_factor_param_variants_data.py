"""R3-3（TV_ROUND3 §4）：T5 参数网格的**数据侧**验收。

ROUND2 给 T5 打 60 分，理由是"数据侧未开工 = 功能实质未上线（线上仍单参数组）"。
R3-3 实测**推翻了这个判断的一半**：

- **数据侧早就完工**：`factors.stock_daily_momentum_close` 里 MACD 有 4 组参数
  （12,26,9 / 6,13,5 / 15,35,10 / 24,52,18）× 3 列，RSI 有 9 个周期。
- **真正缺的是产物侧**：per-symbol 产物只下发策略自己那一组参数
  （`_strategy_factor_specs` 读 strategy.yaml 的 `factor_fields`），
  所以前端 `applyParamChoices` 没有可切的东西。

本测试锁**数据质量**这一半：用**纯 pandas 独立实现**（不 import pandas_ta，
避免与管线共用同一份代码而失去交叉验证意义）对全量历史重算 MACD 多组参数，
与库里逐值比对。这正是 ROUND2 T5 验收第 2 条
（"同一产物切 3 组参数，因子值与离线重算一致"）在数据层的闭环。

口径要点（实测确认，勿凭记忆）：
- 因子表是 **hfq**（原始价 × adj_factor），重算必须同口径；
- warm-up 必须用**全量历史**（截窗口会让 EMA 初值不同，diff 大到几十）；
- pandas_ta 的 MACD 柱 = `dif - dea`（**不是** A 股软件常见的 `(dif-dea)*2`），
  实测 `(dif-dea)*2` 与库值差到 52，而 `dif-dea` 差 0.005。

无数据库时 skip（CI/无库环境不阻塞）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")

REPO = Path(__file__).resolve().parents[1]
# 家用机因子库（indicators_tushare 的 config/db_cfg.yaml）：本地 tushare_data。
# CI / 无库环境：连不上直接 skip，不阻塞。
DSN = os.environ.get(
    "QRE_FACTOR_DSN", "host=localhost port=5432 user=van password=211589 dbname=tushare_data"
)


def _connect():
    import psycopg

    try:
        return psycopg.connect(DSN)
    except psycopg.OperationalError as exc:  # 无库环境：跳过而非失败
        pytest.skip(f"连不上因子库（{DSN}）：{exc}")
TS_CODE = "000001.SZ"
# 与 configs/factors.yaml 的 macd params 对齐（close 口径 4 组）
MACD_PARAMS = [(12, 26, 9), (6, 13, 5), (15, 35, 10), (24, 52, 18)]
# DB numeric_precision=2。MACD 三列都是**导出量**（dif/dea/hist 由两个 EMA 相减得到），
# 最坏情况下要经过两次 2 位小数舍入，故误差上界为 2×0.005=0.01（留 1e-6 余量）。
# 实测 12/26/9、6/13/5、15/35/10 三组 max≈0.005，24/52/18 组 0.0069——都在界内。
TOL = 0.01 + 1e-6


def _load():
    with _connect() as conn:
        market = pd.read_sql_query(
            "SELECT trade_date, close, adj_factor FROM public.stock_daily "
            "WHERE ts_code = %s ORDER BY trade_date",
            conn,
            params=(TS_CODE,),
        )
        cols = ", ".join(
            c for f, s, g in MACD_PARAMS
            for c in (f"macd_{f}_{s}_{g}", f"macds_{f}_{s}_{g}", f"macdh_{f}_{s}_{g}")
        )
        fac = pd.read_sql_query(
            f"SELECT trade_date, {cols} FROM factors.stock_daily_momentum_close "
            "WHERE ts_code = %s ORDER BY trade_date",
            conn,
            params=(TS_CODE,),
        )
    return market, fac


def test_macd_param_variants_match_offline_recompute() -> None:
    """MACD 多组参数变体：库里值 vs pandas_ta 全量历史重算，逐值一致（舍入内）。"""
    market, fac = _load()
    assert len(market) > 500, f"样本太少（{len(market)} 行），不足以验 warm-up"
    m = market.merge(fac, on="trade_date", how="inner")
    m = m.sort_values("trade_date").reset_index(drop=True)

    # 因子表是 hfq（原始价 × adj_factor）——这是管线口径，重算必须同口径
    vals = (m["close"].astype(float) * m["adj_factor"].astype(float)).to_numpy(dtype=float)

    def _ema(values: "np.ndarray", n: int) -> "np.ndarray":
        """TA-Lib / pandas-ta 口径的 EMA：前 n 个有效值用 SMA 播种，之后递归。

        刻意不用 `Series.ewm(adjust=False)`——那是"从第一个值就递归"的口径，
        与因子管线（pandas_ta → ta.ema）差几十（实测 max_abs_diff=15.5），
        会在 warm-up 段给出假阳性。首段 NaN 跳过再播种。
        """
        out = np.full(len(values), np.nan)
        first = next((i for i, v in enumerate(values) if v == v), None)
        if first is None or len(values) - first < n:
            return out
        prev = float(np.mean(values[first:first + n]))
        out[first + n - 1] = prev
        a = 2.0 / (n + 1)
        for i in range(first + n, len(values)):
            v = values[i]
            prev = prev if v != v else a * v + (1 - a) * prev
            out[i] = prev
        return out

    def _macd(vals, fast: int, slow: int, signal: int):
        """纯 numpy 独立实现：dif = EMA(f)-EMA(s)；dea = EMA(dif, signal)；
        hist = dif - dea（**不是** A 股软件常见的 (dif-dea)*2，实测差到 52）。"""
        dif = _ema(vals, fast) - _ema(vals, slow)
        dea = _ema(dif, signal)
        return dif, dea, dif - dea

    checked = 0
    for fast, slow, signal in MACD_PARAMS:
        dif, dea, hist = _macd(vals, fast, slow, signal)
        for name, mine, theirs in (
            ("dif", dif, m[f"macd_{fast}_{slow}_{signal}"]),
            ("dea", dea, m[f"macds_{fast}_{slow}_{signal}"]),
            ("hist", hist, m[f"macdh_{fast}_{slow}_{signal}"]),
        ):
            theirs_v = theirs.astype(float).to_numpy(dtype=float)
            d = np.abs(mine - theirs_v)
            d = d[~np.isnan(d)]
            assert d.size, f"macd_{fast}_{slow}_{signal}.{name} 无可比样本"
            checked += 1
            assert float(d.max()) <= TOL, (
                f"macd_{fast}_{slow}_{signal}.{name} 与离线重算不一致: "
                f"max_abs_diff={float(d.max()):.6f} > {TOL}"
            )
    assert checked == len(MACD_PARAMS) * 3, f"应校验 {len(MACD_PARAMS)*3} 列，实际 {checked}"


def test_macd_variant_columns_exist() -> None:
    """4 组 MACD 参数变体必须都在库里（数据侧"已完工"的硬证据）。"""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='factors' AND table_name='stock_daily_momentum_close' "
            "AND column_name ~ '^macd[hds]?_' ORDER BY column_name"
        )
        cols = {r[0] for r in cur.fetchall()}
    missing = [
        f"{p}_{f}_{s}_{g}"
        for f, s, g in MACD_PARAMS
        for p in ("macd", "macds", "macdh")
        if f"{p}_{f}_{s}_{g}" not in cols
    ]
    assert not missing, f"缺 MACD 参数变体列: {missing}"
    assert len(cols) >= len(MACD_PARAMS) * 3, f"MACD 变体列不足: {sorted(cols)}"
