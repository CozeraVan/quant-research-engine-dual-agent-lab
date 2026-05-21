from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.preflight import PreflightReport, PreflightRequest


@dataclass(frozen=True)
class MissingFactorRequest:
    strategy_id: str
    alias: str
    indicator: str
    category: str | None
    source: str
    period: int | None
    params: dict[str, Any]
    output: str | None
    expected_table: str
    expected_column: str
    date_range: dict[str, str]
    reason: str
    required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "alias": self.alias,
            "indicator": self.indicator,
            "category": self.category,
            "source": self.source,
            "period": self.period,
            "params": self.params,
            "output": self.output,
            "expected_table": self.expected_table,
            "expected_column": self.expected_column,
            "date_range": self.date_range,
            "reason": self.reason,
            "required": self.required,
        }


def extract_missing_factors(
    report: PreflightReport,
    spec: object,  # StrategySpec — avoids circular import
    request: PreflightRequest,
) -> list[MissingFactorRequest]:
    missing: list[MissingFactorRequest] = []
    factor_by_name: dict[str, FactorFieldRequest] = {
        f.logical_name: f for f in spec.factor_fields
    }
    for check in report.checks:
        if not (check.name.startswith("factor_schema:") and check.status == "error"):
            continue
        logical_name = check.name.split(":", 1)[1]
        factor = factor_by_name.get(logical_name)
        if factor is None:
            continue
        missing.append(
            _build_missing_factor(
                strategy_id=spec.name,
                logical_name=logical_name,
                factor=factor,
                request=request,
            )
        )
    missing.sort(key=lambda r: (r.strategy_id, r.alias))
    return missing


def emit_missing_factor_requests(
    requests: list[MissingFactorRequest],
    output_dir: str | Path,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "missing_factor_requests.json"
    path.write_text(
        json.dumps(
            [r.to_dict() for r in requests],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _build_missing_factor(
    *,
    strategy_id: str,
    logical_name: str,
    factor: FactorFieldRequest,
    request: PreflightRequest,
) -> MissingFactorRequest:
    category = _parse_category(factor.source_table)
    source = _parse_source(factor.source_table)
    indicator, period, params, output = _parse_column(factor.source_column)

    return MissingFactorRequest(
        strategy_id=strategy_id,
        alias=logical_name,
        indicator=indicator,
        category=category,
        source=source,
        period=period,
        params=params,
        output=output,
        expected_table=factor.qualified_table,
        expected_column=factor.source_column,
        date_range={
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
        },
        reason=f"factor required by strategy '{strategy_id}'",
        required=True,
    )


def _parse_category(table_name: str) -> str | None:
    """Extract the semantic category from a factor table name.

    Table names follow the pattern stock_daily_{category}_{source}.
    """
    parts = table_name.split("_")
    if len(parts) >= 4 and parts[0] == "stock" and parts[1] == "daily":
        return parts[2]
    return None


def _parse_source(table_name: str) -> str:
    """Extract the price source from a factor table name."""
    parts = table_name.split("_")
    if len(parts) >= 4 and parts[0] == "stock" and parts[1] == "daily":
        return "_".join(parts[3:])
    return "close"


# Known multi-output indicator prefixes and their canonical indicator names.
_KNOWN_INDICATORS: dict[str, str] = {
    "rsi": "rsi",
    "ema": "ema",
    "sma": "sma",
    "wma": "wma",
    "macd": "macd",
    "bb": "bollinger",
    "bbu": "bollinger",
    "bbl": "bollinger",
    "bbm": "bollinger",
    "boll": "bollinger",
    "atr": "atr",
    "adx": "adx",
    "cci": "cci",
    "mfi": "mfi",
    "obv": "obv",
    "stoch": "stochastic",
    "willr": "williams_r",
}

# Multi-output indicator column suffixes -> output name.
_OUTPUT_SUFFIXES: dict[str, str] = {
    "u": "upper",
    "l": "lower",
    "m": "middle",
    "signal": "signal",
    "macd": "macd",
    "histogram": "histogram",
    "di_plus": "di_plus",
    "di_minus": "di_minus",
    "adx": "adx",
    "k": "k",
    "d": "d",
}


def _parse_column(column: str) -> tuple[str, int | None, dict[str, Any], str | None]:
    """Heuristically parse a factor column name into indicator metadata.

    Returns (indicator_name, period, params, output).

    Best-effort parsing. Not all indicators follow a regular pattern.
    For unparseable columns, the full column name is used as the indicator name.
    """
    parts = column.split("_")

    # Find the indicator prefix.
    indicator = column
    period: int | None = None
    params: dict[str, Any] = {}
    output: str | None = None

    if not parts:
        return indicator, period, params, output

    # Try to match known indicator prefixes.
    matched_indicator = None
    matched_prefix = ""
    prefix_len = 0
    for prefix, name in sorted(_KNOWN_INDICATORS.items(), key=lambda x: -len(x[0])):
        if parts[0] == prefix or column.startswith(prefix + "_"):
            matched_indicator = name
            matched_prefix = prefix
            prefix_len = len(prefix)
            break

    if matched_indicator is None:
        # Try to extract trailing numeric parts as period.
        numeric_parts = []
        for p in reversed(parts):
            try:
                numeric_parts.insert(0, int(p))
            except ValueError:
                break
        if numeric_parts:
            period = numeric_parts[0]
        return column, period, params, output

    indicator = matched_indicator
    remaining = column[prefix_len:].lstrip("_").split("_") if column[prefix_len:] else []

    if matched_indicator == "bollinger":
        # Pattern: bb{u|l|m}_{period}_{stddev}_{...}
        # Output may be in the prefix itself (e.g. bbu -> upper) or in remaining[0].
        if matched_prefix in ("bbu", "bbl", "bbm"):
            output = {"bbu": "upper", "bbl": "lower", "bbm": "middle"}[matched_prefix]
        elif remaining and remaining[0] in _OUTPUT_SUFFIXES:
            output = _OUTPUT_SUFFIXES[remaining[0]]
            remaining = remaining[1:]
        nums = _extract_numbers(remaining)
        if nums:
            period = nums[0]
            if len(nums) >= 2:
                params["stddev"] = float(nums[1])
        return indicator, period, params, output

    if matched_indicator == "macd":
        # Pattern: macd_{fast}_{slow}_{signal} or macd_signal_{fast}_{slow}_{signal}
        if remaining and remaining[0] in ("signal", "histogram", "macd"):
            output = remaining[0]
            remaining = remaining[1:]
        else:
            output = "macd"
        nums = _extract_numbers(remaining)
        if len(nums) >= 3:
            params["fast"] = nums[0]
            params["slow"] = nums[1]
            params["signal"] = nums[2]
        return indicator, None, params, output

    # Generic: try to extract trailing numbers as period.
    nums = _extract_numbers(remaining)
    if nums:
        period = nums[0]

    return indicator, period, params, output


def _extract_numbers(parts: list[str]) -> list[int]:
    nums: list[int] = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            break
    return nums
