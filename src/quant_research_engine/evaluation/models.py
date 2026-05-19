from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class EvaluationRequest:
    signal_expression: str
    forward_horizons: list[int]
    price_column: str = "close"
    factor_columns: list[str] | None = None
    quantiles: int | None = None
    round_trip_cost_rate: float | None = None
    group_by: list[str] | None = None


@dataclass(frozen=True)
class EvaluationResult:
    events: pd.DataFrame
    summary: pd.DataFrame
    ic_summary: pd.DataFrame
    quantile_summary: pd.DataFrame
    group_summary: pd.DataFrame
