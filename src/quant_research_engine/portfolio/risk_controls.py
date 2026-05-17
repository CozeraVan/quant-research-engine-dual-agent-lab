from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class RiskControlConfig:
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: str | None = None
    price: float | None = None


def evaluate_long_exit(
    *,
    entry_price: float,
    row: pd.Series,
    config: RiskControlConfig,
    trailing_anchor: float | None = None,
) -> ExitDecision:
    if config.stop_loss_pct is not None:
        stop_price = round(entry_price * (1 - config.stop_loss_pct), 10)
        if _optional_float(row, "low") <= stop_price:
            return ExitDecision(True, "stop_loss", stop_price)

    if config.trailing_stop_pct is not None and trailing_anchor is not None:
        trailing_stop_price = round(trailing_anchor * (1 - config.trailing_stop_pct), 10)
        if _optional_float(row, "low") <= trailing_stop_price:
            return ExitDecision(True, "trailing_stop", trailing_stop_price)

    if config.take_profit_pct is not None:
        take_profit_price = round(entry_price * (1 + config.take_profit_pct), 10)
        if _optional_float(row, "high") >= take_profit_price:
            return ExitDecision(True, "take_profit", take_profit_price)

    return ExitDecision(False)


def _optional_float(row: pd.Series, column: str) -> float:
    if column not in row.index or pd.isna(row[column]):
        return float("nan")
    return float(row[column])
