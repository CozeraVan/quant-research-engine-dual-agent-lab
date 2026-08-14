"""Alpha191 面板因子赚钱效应评估（R-QRE-009 评估口径：先小样本后全期）。

逐因子装配（close + 单因子列，全市场）→ EvaluationEngine.evaluate →
提取 mean_rank_ic / ICIR / IC 一致率 / 五分位多空价差，输出 leaderboard。

口径约定：
- 主排序键 / 主指标 horizon = 5 日（PRIMARY_HORIZON）。
- 分位语义沿用引擎 ``_build_quantile_summary``：日频 qcut，quantile=1 为因子值
  最低组、quantile=5 为最高组；``top_minus_bottom`` = Q5 − Q1（做多高因子组、
  做空低因子组的远期收益差），与 mean_rank_ic 同号为方向一致。
- ic_win_rate 为方向一致率：mean_rank_ic >= 0 时取 rank_ic>0 的日期占比，
  否则取 rank_ic<0 的占比（负向因子按反向计）。
- ICIR = 日频 rank IC 均值 / 标准差（ddof=1）；日频序列与引擎 ic_summary
  同一公式（逐日 Spearman），仅引擎不落盘 std，故在此重算。
- 显著性标注 significant=★：|mean_rank_ic| >= 0.05 且 ic_win_rate >= 0.55。
"""

from __future__ import annotations

import gc
from dataclasses import dataclass
from datetime import date

import pandas as pd

from quant_research_engine.data.assembler import ResearchFrameAssembler
from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.evaluation.engine import EvaluationEngine
from quant_research_engine.evaluation.models import EvaluationRequest, EvaluationResult

ALPHA191_TABLE = "stock_daily_alpha191"
ALL_ALPHA_FACTORS: list[str] = [f"alpha{i:03d}" for i in range(1, 192)]

FORWARD_HORIZONS: list[int] = [1, 3, 5, 10, 20]
PRIMARY_HORIZON = 5
QUANTILES = 5
DEFAULT_BATCH_SIZE = 10

SIGNIFICANT_IC_THRESHOLD = 0.05
SIGNIFICANT_WIN_RATE_THRESHOLD = 0.55

# 事件流对本评估无意义（赚钱效应看 IC/分层，不看事件），always-true 占位。
_SIGNAL_EXPRESSION = "close > 0"

LEADERBOARD_COLUMNS = [
    "factor",
    "mean_rank_ic",
    "icir",
    "ic_win_rate",
    "top_minus_bottom",
    "observation_dates",
    "significant",
]


@dataclass(frozen=True)
class AlphaEvalConfig:
    start: date
    end: date
    price_column: str = "close"
    batch_size: int = DEFAULT_BATCH_SIZE


def daily_rank_ic(
    frame: pd.DataFrame,
    factor: str,
    horizon: int = PRIMARY_HORIZON,
    price_column: str = "close",
) -> pd.Series:
    """逐日 Spearman rank IC 序列（因子 vs horizon 日前向收益），用于 ICIR。

    与 EvaluationEngine._build_ic_summary 同一公式；引擎只输出均值/胜率，
    ICIR 需要的日频 std 在此重算。
    """
    ordered = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    future = ordered.groupby("ts_code")[price_column].shift(-horizon)
    working = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(ordered["trade_date"]),
            "factor": ordered[factor],
            "forward": future / ordered[price_column] - 1,
        }
    ).dropna()
    values = {}
    for trade_date, group in working.groupby("trade_date", sort=True):
        if len(group) < 2:
            continue
        ic = group["factor"].rank(method="average").corr(group["forward"].rank(method="average"))
        if pd.notna(ic):
            values[trade_date] = float(ic)
    return pd.Series(values)


def _row_at_horizon(summary: pd.DataFrame, horizon: int) -> pd.Series | None:
    if summary.empty or "horizon" not in summary.columns:
        return None
    matched = summary.loc[summary["horizon"] == horizon]
    if matched.empty:
        return None
    return matched.iloc[0]


def summarize_factor_result(
    factor: str,
    frame: pd.DataFrame,
    result: EvaluationResult,
    config: AlphaEvalConfig,
) -> dict[str, object]:
    """从单次 EvaluationResult 提取 leaderboard 行（主 horizon = 5）。"""
    row: dict[str, object] = {
        "factor": factor,
        "mean_rank_ic": None,
        "icir": None,
        "ic_win_rate": None,
        "top_minus_bottom": None,
        "observation_dates": 0,
        "significant": "",
    }

    ic_row = _row_at_horizon(result.ic_summary, PRIMARY_HORIZON)
    mean_rank_ic = None
    positive_rate = None
    if ic_row is not None:
        mean_rank_ic = ic_row.get("mean_rank_ic")
        positive_rate = ic_row.get("rank_ic_positive_rate")
        row["observation_dates"] = int(ic_row.get("observation_dates") or 0)
    if mean_rank_ic is not None and pd.notna(mean_rank_ic):
        mean_rank_ic = float(mean_rank_ic)
        row["mean_rank_ic"] = mean_rank_ic

    if positive_rate is not None and pd.notna(positive_rate) and mean_rank_ic is not None:
        positive_rate = float(positive_rate)
        # 方向一致率：负向因子取 rank_ic<0 的占比
        row["ic_win_rate"] = positive_rate if mean_rank_ic >= 0 else 1.0 - positive_rate

    q = result.quantile_summary
    if not q.empty:
        q_rows = q.loc[q["horizon"] == PRIMARY_HORIZON]
        top = q_rows.loc[q_rows["quantile"] == QUANTILES, "mean_forward_return"]
        bottom = q_rows.loc[q_rows["quantile"] == 1, "mean_forward_return"]
        top_value = top.iloc[0] if not top.empty else None
        bottom_value = bottom.iloc[0] if not bottom.empty else None
        if top_value is not None and bottom_value is not None and pd.notna(top_value) and pd.notna(bottom_value):
            row["top_minus_bottom"] = float(top_value) - float(bottom_value)

    daily = daily_rank_ic(frame, factor, PRIMARY_HORIZON, config.price_column)
    if len(daily) >= 2:
        std = float(daily.std(ddof=1))
        if std > 0:
            row["icir"] = float(daily.mean()) / std

    if (
        row["mean_rank_ic"] is not None
        and row["ic_win_rate"] is not None
        and abs(row["mean_rank_ic"]) >= SIGNIFICANT_IC_THRESHOLD
        and row["ic_win_rate"] >= SIGNIFICANT_WIN_RATE_THRESHOLD
    ):
        row["significant"] = "★"
    return row


def build_leaderboard(rows: list[dict[str, object]]) -> pd.DataFrame:
    """按 |mean_rank_ic| 降序（NaN 垫底）生成 leaderboard DataFrame。"""
    board = pd.DataFrame(rows, columns=LEADERBOARD_COLUMNS)
    if board.empty:
        return board
    board["_abs_ic"] = board["mean_rank_ic"].astype("float64").abs()
    board = board.sort_values("_abs_ic", ascending=False, na_position="last").drop(columns=["_abs_ic"])
    return board.reset_index(drop=True)


def evaluate_alpha_factors(
    store,
    factors: list[str],
    config: AlphaEvalConfig,
    engine: EvaluationEngine | None = None,
) -> list[dict[str, object]]:
    """分批装配 + 逐因子评估。每批 batch_size 个因子一次取数，批后释放。"""
    engine = engine or EvaluationEngine()
    assembler = ResearchFrameAssembler(store)
    rows: list[dict[str, object]] = []
    for start_idx in range(0, len(factors), config.batch_size):
        batch = factors[start_idx : start_idx + config.batch_size]
        requests = [
            FactorFieldRequest.from_target(factor, f"factors.{ALPHA191_TABLE}.{factor}")
            for factor in batch
        ]
        frame = assembler.build(
            ts_codes=None,
            start=config.start,
            end=config.end,
            market_fields=[config.price_column],
            factor_fields=requests,
        )
        for factor in batch:
            try:
                sub = frame[["ts_code", "trade_date", config.price_column, factor]].copy()
                request = EvaluationRequest(
                    signal_expression=_SIGNAL_EXPRESSION,
                    forward_horizons=list(FORWARD_HORIZONS),
                    price_column=config.price_column,
                    factor_columns=[factor],
                    quantiles=QUANTILES,
                )
                result = engine.evaluate(sub, request)
                rows.append(summarize_factor_result(factor, sub, result, config))
            except Exception as exc:  # noqa: BLE001 — 单因子失败不阻断整批
                print(f"  [warn] {factor} 评估失败：{exc}")
                rows.append(
                    {
                        "factor": factor,
                        "mean_rank_ic": None,
                        "icir": None,
                        "ic_win_rate": None,
                        "top_minus_bottom": None,
                        "observation_dates": 0,
                        "significant": "",
                    }
                )
        del frame
        gc.collect()
        done = min(start_idx + config.batch_size, len(factors))
        print(f"  [batch] {done}/{len(factors)} factors evaluated")
    return rows
