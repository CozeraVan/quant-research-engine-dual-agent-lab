"""Alpha191 截面 rank 策略模板；只生成既有 StrategySpec 配置。"""

from __future__ import annotations

import math
import re
from typing import Any

_ALPHA_RE = re.compile(r"^alpha\d{3}$")


def _number(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数值") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} 必须是有限数值")
    return result


def build_alpha191_rank_strategy(
    alpha: str,
    *,
    direction: str = "high",
    entry_threshold: float | None = None,
    exit_threshold: float | None = None,
    holding_days: int = 10,
    stop_loss_pct: float = 0.08,
    name: str | None = None,
) -> dict[str, Any]:
    """生成高/低秩 Alpha191 日线策略；参数异常在生成阶段直接拒绝。"""
    if not _ALPHA_RE.fullmatch(str(alpha)) or not 1 <= int(str(alpha)[5:]) <= 191:
        raise ValueError("alpha 编号须为 alpha001…alpha191")
    if direction not in {"high", "low"}:
        raise ValueError("direction 只允许 high/low")
    entry = _number(
        (-0.2 if direction == "high" else 0.2) if entry_threshold is None else entry_threshold,
        "entry_threshold",
    )
    exit_ = _number(
        (-0.5 if direction == "high" else 0.5) if exit_threshold is None else exit_threshold,
        "exit_threshold",
    )
    if direction == "high" and not entry > exit_:
        raise ValueError("高秩策略要求 entry_threshold > exit_threshold")
    if direction == "low" and not entry < exit_:
        raise ValueError("低秩策略要求 entry_threshold < exit_threshold")
    holding_days = int(holding_days)
    if holding_days < 0:
        raise ValueError("holding_days 不能为负数")
    stop_loss = _number(stop_loss_pct, "stop_loss_pct")
    if stop_loss < 0:
        raise ValueError("stop_loss_pct 不能为负数")
    entry_operator, exit_operator = (">", "<") if direction == "high" else ("<", ">")
    return {
        "experiment": {
            "name": name or f"{alpha}_{direction}_rank",
            "market_profile": "ashare_daily_default",
            "frequency": "daily",
        },
        "data": {
            "market_fields": ["open", "high", "low", "close", "pre_close", "vol", "amount"],
            "factor_fields": {str(alpha): f"factors.stock_daily_alpha191.{alpha}"},
        },
        "universe": {
            "exclude_st": True, "exclude_suspended": True,
            "exclude_risk_warning": True, "min_listing_days": 120,
        },
        "signal": {
            "entry": f"{alpha} {entry_operator} {entry}",
            "exit": f"{alpha} {exit_operator} {exit_}",
        },
        "holding": {"max_holding_days": holding_days},
        "risk": {
            "stop_loss_pct": stop_loss, "take_profit_pct": None, "trailing_stop_pct": None,
        },
        "evaluation": {"forward_return_horizons": [1, 3, 5, 10, 20], "quantiles": 5},
    }
