from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Indicator catalog: indicator name -> (category, column_builder)
# ---------------------------------------------------------------------------

def _col_simple(indicator: str, source: str, period: int | None, params: dict[str, Any], output: str | None) -> str:
    """Build column name for simple indicators: {indicator}_{period}."""
    if period is None:
        raise ValueError(f"period is required for indicator '{indicator}'")
    return f"{indicator}_{period}"


def _col_macd(indicator: str, source: str, period: int | None, params: dict[str, Any], output: str | None) -> str:
    """Build column name for MACD: macd_{fast}_{slow}_{signal} or macd_{output}_{fast}_{slow}_{signal}."""
    fast = params.get("fast")
    slow = params.get("slow")
    signal = params.get("signal")
    if fast is None or slow is None or signal is None:
        raise ValueError(
            f"MACD requires params.fast, params.slow, params.signal; got {params}"
        )
    if output and output not in ("macd", "signal", "histogram"):
        raise ValueError(f"MACD output must be macd, signal, or histogram; got {output}")
    if output and output != "macd":
        return f"macd_{output}_{fast}_{slow}_{signal}"
    return f"macd_{fast}_{slow}_{signal}"


def _col_bollinger(indicator: str, source: str, period: int | None, params: dict[str, Any], output: str | None) -> str:
    """Build column name for Bollinger Bands: bb{u|l|m}_{period}_{nbdev}_{nbdev}.

    nbdev 2.0 is encoded as 2_0_2_0 (two int.frac pairs).
    """
    if period is None:
        raise ValueError("period is required for Bollinger Bands")
    stddev = params.get("stddev", 2.0)
    nbdev_int = int(stddev)
    nbdev_frac = int(round((stddev - nbdev_int) * 10))
    nbdev_part = f"{nbdev_int}_{nbdev_frac}_{nbdev_int}_{nbdev_frac}"
    output_map = {"upper": "bbu", "lower": "bbl", "middle": "bbm"}
    prefix = output_map.get(output or "upper")
    return f"{prefix}_{period}_{nbdev_part}"


_INDICATOR_CATALOG: dict[str, tuple[str, object]] = {
    "rsi": ("momentum", _col_simple),
    "ema": ("overlap", _col_simple),
    "sma": ("overlap", _col_simple),
    "wma": ("overlap", _col_simple),
    "macd": ("momentum", _col_macd),
    "bollinger": ("volatility", _col_bollinger),
    "atr": ("volatility", _col_simple),
    "adx": ("trend", _col_simple),
    "cci": ("momentum", _col_simple),
    "mfi": ("volume", _col_simple),
    "obv": ("volume", _col_simple),
    "stochastic": ("momentum", _col_simple),
    "williams_r": ("momentum", _col_simple),
}


_SOURCE_TO_TABLE_SUFFIX: dict[str, str] = {"typical": "typical_price"}


def _build_table_name(category: str, source: str) -> str:
    suffix = _SOURCE_TO_TABLE_SUFFIX.get(source, source)
    return f"stock_daily_{category}_{suffix}"


# ---------------------------------------------------------------------------
# Parsed entry types
# ---------------------------------------------------------------------------

@dataclass
class FactorRequirement:
    alias: str
    indicator: str
    source: str
    period: int | None
    params: dict[str, Any]
    output: str | None
    required: bool
    reason: str


@dataclass
class CompileIssue:
    level: str  # "error" or "warning"
    message: str


@dataclass
class CompiledEntry:
    strategy_id: str
    name: str
    family: str
    direction: str
    version: str | None
    factor_targets: dict[str, str]  # alias -> "factors.table.column"
    signal_expression: str | None
    exit_signal_expression: str | None
    experiment: dict[str, Any]
    rules: dict[str, Any] | None = None
    issues: list[CompileIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# Built-in aliases that don't need factor requirements.
_BUILTIN_ALIASES = frozenset({"close", "open", "high", "low", "pre_close", "vol", "amount"})


def parse_high_level_entry(path: str | Path) -> dict[str, Any]:
    """Parse and validate a high-level strategy entry YAML file.

    Returns the raw parsed dict.  Structural validation is performed
    inside `compile_entry`.
    """
    with Path(path).open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"Strategy entry must be a YAML mapping: {path}")
    return raw


def compile_entry(raw: dict[str, Any]) -> CompiledEntry:
    """Compile a high-level strategy entry into a linkable intermediate form.

    Validates the three required sections (strategy, factor_requirements,
    experiment), resolves factor aliases to low-level table.column targets,
    and builds signal expressions from rules.
    """
    issues: list[CompileIssue] = []

    # --- strategy section ---
    strategy = raw.get("strategy")
    if not isinstance(strategy, dict):
        raise ValueError("entry must contain a 'strategy' mapping")
    strategy_id = _require_str(strategy, "id", "strategy")
    name = _require_str(strategy, "name", "strategy")
    family = _require_str(strategy, "family", "strategy")
    direction = _require_str(strategy, "direction", "strategy")
    version = strategy.get("version")

    # --- factor_requirements section ---
    factor_reqs_raw = raw.get("factor_requirements")
    if not isinstance(factor_reqs_raw, list):
        raise ValueError("entry must contain a 'factor_requirements' list")
    factor_reqs: list[FactorRequirement] = []
    seen_aliases: set[str] = set()
    for i, item in enumerate(factor_reqs_raw):
        if not isinstance(item, dict):
            issues.append(CompileIssue("error", f"factor_requirements[{i}] must be a mapping"))
            continue
        alias = _require_str(item, "alias", f"factor_requirements[{i}]")
        if alias in seen_aliases:
            issues.append(CompileIssue("error", f"duplicate alias '{alias}' in factor_requirements"))
        seen_aliases.add(alias)
        if alias in _BUILTIN_ALIASES:
            issues.append(CompileIssue("error", f"alias '{alias}' shadows a built-in market field"))
        indicator = _require_str(item, "indicator", f"factor_requirements[{i}]")
        source = _require_str(item, "source", f"factor_requirements[{i}]")
        period = item.get("period")
        if period is not None and not isinstance(period, int):
            issues.append(CompileIssue("error", f"factor_requirements[{i}].period must be an integer"))
        params = item.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            issues.append(CompileIssue("error", f"factor_requirements[{i}].params must be a mapping"))
            params = {}
        output = item.get("output")
        if output is not None and not isinstance(output, str):
            issues.append(CompileIssue("error", f"factor_requirements[{i}].output must be a string"))
        required = item.get("required", True)
        if not isinstance(required, bool):
            required = True
        reason = _require_str(item, "reason", f"factor_requirements[{i}]")
        factor_reqs.append(FactorRequirement(
            alias=alias,
            indicator=indicator,
            source=source,
            period=period,
            params=params,
            output=output,
            required=required,
            reason=reason,
        ))

    # --- Resolve factor targets ---
    factor_targets: dict[str, str] = {}
    for req in factor_reqs:
        if req.indicator not in _INDICATOR_CATALOG:
            issues.append(CompileIssue(
                "error",
                f"unknown indicator '{req.indicator}' for alias '{req.alias}'. "
                f"Known indicators: {', '.join(sorted(_INDICATOR_CATALOG))}",
            ))
            continue
        category, builder = _INDICATOR_CATALOG[req.indicator]
        try:
            col = builder(req.indicator, req.source, req.period, req.params, req.output)  # type: ignore[operator]
        except ValueError as exc:
            issues.append(CompileIssue("error", f"cannot build column for alias '{req.alias}': {exc}"))
            continue
        table = _build_table_name(category, req.source)
        factor_targets[req.alias] = f"factors.{table}.{col}"

    # --- rules section → signal expressions ---
    rules = raw.get("rules")
    signal_expr = None
    exit_signal_expr = None
    if isinstance(rules, dict):
        signal_expr = _compile_expression(rules.get("entry"), factor_targets, issues)
        exit_signal_expr = _compile_expression(rules.get("exit"), factor_targets, issues)
    elif rules is not None:
        issues.append(CompileIssue("error", "rules must be a mapping"))

    # --- experiment section ---
    experiment = raw.get("experiment")
    if not isinstance(experiment, dict):
        raise ValueError("entry must contain an 'experiment' mapping")

    return CompiledEntry(
        strategy_id=strategy_id,
        name=name,
        family=family,
        direction=direction,
        version=version,
        factor_targets=factor_targets,
        signal_expression=signal_expr,
        exit_signal_expression=exit_signal_expr,
        experiment=experiment,
        rules=rules if isinstance(rules, dict) else None,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Expression compiler
# ---------------------------------------------------------------------------

_COMPARISON_OPS: dict[str, str] = {
    "<": "<",
    ">": ">",
    "<=": "<=",
    ">=": ">=",
    "==": "==",
    "!=": "!=",
}

_CROSSOVER_OPS = {"crosses_above", "crosses_below"}


def _compile_expression(
    rule_block: Any,
    factor_targets: dict[str, str],
    issues: list[CompileIssue],
) -> str | None:
    """Compile a rules block (entry or exit) into a pandas-evaluable expression string.

    Returns None if the block is empty or missing.
    """
    if rule_block is None:
        return None
    if not isinstance(rule_block, dict):
        return None

    combinator = None
    conditions = None
    if "all" in rule_block:
        combinator = "and"
        conditions = rule_block["all"]
    elif "any" in rule_block:
        combinator = "or"
        conditions = rule_block["any"]
    else:
        return None

    if not isinstance(conditions, list) or len(conditions) == 0:
        return None

    parts: list[str] = []
    for i, cond in enumerate(conditions):
        if not isinstance(cond, dict):
            issues.append(CompileIssue("error", f"condition {i} in rule block must be a mapping"))
            continue
        alias = cond.get("alias")
        operator = cond.get("operator")
        if not alias or not operator:
            issues.append(CompileIssue("error", f"condition {i} must have 'alias' and 'operator'"))
            continue

        # Validate alias exists in factor_targets or built-in aliases
        if alias not in factor_targets and alias not in _BUILTIN_ALIASES:
            issues.append(CompileIssue("warning", f"alias '{alias}' in condition {i} is not a declared factor or built-in field"))

        left = alias
        right: str | None = None
        if "alias_b" in cond:
            alias_b = cond["alias_b"]
            if alias_b not in factor_targets and alias_b not in _BUILTIN_ALIASES:
                issues.append(CompileIssue("warning", f"alias_b '{alias_b}' in condition {i} is not a declared factor or built-in field"))
            right = alias_b
        elif "value" in cond:
            right = str(cond["value"])

        if right is None:
            issues.append(CompileIssue("error", f"condition {i} must have 'value' or 'alias_b'"))
            continue

        if operator in _CROSSOVER_OPS:
            issues.append(CompileIssue(
                "warning",
                f"crossover operator '{operator}' has no direct low-level equivalent; "
                f"emitted as simple comparison. The compiler will support crossovers "
                f"when the runtime engine adds lagged-comparison support.",
            ))
            if operator == "crosses_above":
                operator = ">"
            else:
                operator = "<"

        if operator in _COMPARISON_OPS:
            py_op = _COMPARISON_OPS[operator]
            parts.append(f"({left} {py_op} {right})")
        else:
            issues.append(CompileIssue("error", f"unknown operator '{operator}' in condition {i}"))

    if not parts:
        return None
    return f" {combinator} ".join(parts)


# ---------------------------------------------------------------------------
# StrategySpec bridge
# ---------------------------------------------------------------------------

def compile_to_strategy_spec_dict(entry: CompiledEntry) -> dict[str, Any]:
    """Convert a CompiledEntry to the low-level StrategySpec-compatible mapping.

    This dict can be passed to StrategySpec.from_mapping() for use with
    existing preflight, backtest, and evaluation commands.
    """
    experiment = entry.experiment
    universe = experiment.get("universe", {}) or {}
    capital = experiment.get("capital", {}) or {}
    rules = entry.rules or {}
    risk_raw = rules.get("risk") or experiment.get("risk")
    if risk_raw is None:
        risk_raw = {}

    holding_max = rules.get("max_holding_days") or experiment.get("max_holding_days")
    if holding_max is None and isinstance(risk_raw, dict):
        holding_max = risk_raw.get("max_holding_days", 1)

    return {
        "experiment": {
            "name": entry.strategy_id,
        },
        "data": {
            "factor_fields": entry.factor_targets,
            "market_fields": [
                "open", "high", "low", "close", "pre_close", "vol", "amount",
            ],
        },
        "signal": {
            "entry": entry.signal_expression or "close > 0",
            "exit": entry.exit_signal_expression,
        },
        "evaluation": {
            "forward_return_horizons": [1, 3, 5, 10, 20],
        },
        "holding": {
            "max_holding_days": holding_max if isinstance(holding_max, int) else 1,
        },
        "risk": {
            "stop_loss_pct": risk_raw.get("stop_loss_pct") if isinstance(risk_raw, dict) else None,
            "take_profit_pct": risk_raw.get("take_profit_pct") if isinstance(risk_raw, dict) else None,
            "trailing_stop_pct": risk_raw.get("trailing_stop_pct") if isinstance(risk_raw, dict) else None,
        },
        "universe": {
            "exclude_st": universe.get("exclude_st", True),
            "exclude_suspended": universe.get("exclude_suspended", True),
            "exclude_risk_warning": universe.get("exclude_risk_warning", True),
            "min_listing_days": universe.get("min_listing_days", 120),
            "min_amount": universe.get("min_amount"),
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_str(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{context}.{key} is required and must be a string")
    return value


def _optional_str(mapping: dict[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    return str(value)
