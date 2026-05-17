from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from quant_research_engine.data.catalog import FactorFieldRequest


@dataclass(frozen=True)
class StrategySpec:
    name: str
    signal_expression: str
    market_fields: list[str]
    factor_fields: list[FactorFieldRequest]
    forward_horizons: list[int]
    quantiles: int | None
    holding_days: int
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    weight_model: str | None = None
    score_column: str | None = None
    volatility_column: str | None = None
    rebalance_interval_days: int | None = None
    exclude_st: bool = False
    exclude_suspended: bool = False
    exclude_risk_warning: bool = False
    min_listing_days: int | None = None
    min_amount: float | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StrategySpec":
        with Path(path).open("r", encoding="utf-8") as file:
            raw = yaml.safe_load(file)
        if not isinstance(raw, dict):
            raise ValueError(f"Strategy YAML must contain a mapping: {path}")
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "StrategySpec":
        experiment = _mapping(raw, "experiment")
        data = _mapping(raw, "data")
        signal = _mapping(raw, "signal")
        evaluation = _mapping(raw, "evaluation")
        holding = _mapping(raw, "holding")
        risk = raw.get("risk", {})
        if risk is None:
            risk = {}
        if not isinstance(risk, dict):
            raise ValueError("risk section must be a mapping when provided")
        portfolio = raw.get("portfolio", {})
        if portfolio is None:
            portfolio = {}
        if not isinstance(portfolio, dict):
            raise ValueError("portfolio section must be a mapping when provided")
        universe = raw.get("universe", {})
        if universe is None:
            universe = {}
        if not isinstance(universe, dict):
            raise ValueError("universe section must be a mapping when provided")

        factor_fields_raw = data.get("factor_fields", {})
        if not isinstance(factor_fields_raw, dict):
            raise ValueError("data.factor_fields must be a mapping of logical_name -> factors.table.column")

        market_fields = data.get("market_fields", ["open", "high", "low", "close", "pre_close", "vol", "amount"])
        if not isinstance(market_fields, list) or not all(isinstance(field, str) for field in market_fields):
            raise ValueError("data.market_fields must be a list of column names")

        horizons = evaluation.get("forward_return_horizons", [1, 3, 5])
        if not isinstance(horizons, list) or not all(isinstance(horizon, int) for horizon in horizons):
            raise ValueError("evaluation.forward_return_horizons must be a list of integers")

        return cls(
            name=str(experiment.get("name", "unnamed_experiment")),
            signal_expression=str(signal["entry"]),
            market_fields=market_fields,
            factor_fields=[
                FactorFieldRequest.from_target(str(logical_name), str(target))
                for logical_name, target in factor_fields_raw.items()
            ],
            forward_horizons=horizons,
            quantiles=_optional_int(evaluation, "quantiles"),
            holding_days=int(holding.get("max_holding_days", 1)),
            stop_loss_pct=_optional_float(risk, "stop_loss_pct"),
            take_profit_pct=_optional_float(risk, "take_profit_pct"),
            trailing_stop_pct=_optional_float(risk, "trailing_stop_pct"),
            weight_model=_optional_str(portfolio, "weight_model"),
            score_column=_optional_str(portfolio, "score_column"),
            volatility_column=_optional_str(portfolio, "volatility_column"),
            rebalance_interval_days=_optional_int(portfolio, "rebalance_interval_days"),
            exclude_st=bool(universe.get("exclude_st", False)),
            exclude_suspended=bool(universe.get("exclude_suspended", False)),
            exclude_risk_warning=bool(universe.get("exclude_risk_warning", False)),
            min_listing_days=_optional_int(universe, "min_listing_days"),
            min_amount=_optional_float(universe, "min_amount"),
        )


def _mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} section is required")
    return value


def _optional_float(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    return float(value)


def _optional_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    return str(value)


def _optional_int(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    return int(value)
