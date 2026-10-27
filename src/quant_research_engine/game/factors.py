"""游戏技术因子目录：元数据白名单，不含任何时间序列。"""

from __future__ import annotations

import re

from quant_research_engine.game.engine import GameRuleError
from quant_research_engine.gui.factor_registry import (
    FactorRegistry, MIXED_FAMILY_PRICE_PREFIXES, NON_PRICE_FAMILIES,
    PRICE_SCALED_FAMILIES, is_price_scaled, load_registry,
)

TECHNICAL_CATEGORIES = (
    "overlap", "momentum", "volatility", "volume", "trend",
    "performance", "statistics", "candle", "risk", "liquidity",
)
GROUP_ORDER = (*TECHNICAL_CATEGORIES, "alpha")
GROUP_LABELS = {
    "overlap": "均线/轨道", "momentum": "动量", "volatility": "波动率",
    "volume": "量能", "trend": "趋势", "performance": "表现",
    "statistics": "统计", "candle": "K线形态", "risk": "风险",
    "liquidity": "流动性", "alpha": "Alpha 因子",
}
DEFAULT_CANONICALS = (
    "factors.stock_daily_overlap_close.ema_5",
    "factors.stock_daily_overlap_close.ema_20",
    "factors.stock_daily_overlap_close.ema_60",
    "factors.stock_daily_overlap_close.ema_250",
    "factors.stock_daily_momentum_close.macd_12_26_9",
    "factors.stock_daily_momentum_close.macds_12_26_9",
    "factors.stock_daily_momentum_close.macdh_12_26_9",
    "factors.stock_daily_momentum_close.rsi_14",
    "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
    "factors.stock_daily_volatility_close.bbm_20_2_0_2_0",
    "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
)
# 因子表按 hfq 口径（原始价 × adj_factor）落库，游戏 K 线按固定锚点前复权；
# 下列族的输出是价格或价格差，必须除以会话锚点才能与 K 线同尺度。
# 分类单一来源：gui.factor_registry（GUI 呈现层与游戏共用，避免两处漂移）。
# 证据：.tmp/trading-game-terminal/scan_all_families*.csv、verify_*.txt。
# 同一族内混合口径：只有下列列前缀是价格（psaraf/psarr 是加速度与比率，zigzag 全为 NaN）。
_OVERLAY_RE = re.compile(
    r"^(?:ema|ma|sma|wma|dema|tema|hma|kama|alma|rma|trima|jma|vidya|swma|fwma|pwma|"
    r"sinwma|zl_ema|zlma)_?\d*$"
    r"|^(?:bbl|bbm|bbu|dcl|dcm|dcu|kcl|kcb|kcu|kcbe|kcle|kcue|accbl|accbm|accbu|"
    r"psarl|psars|supert)_|^(?:boll|bb)_(?:upper|mid|lower)|^boll"
    r"|^(?:hl2|hlc3|ohlc4|wcp|vwap_d|midpoint_?\d*|midprice_?\d*)$",
    re.IGNORECASE,
)


def _group_of(entry) -> str | None:
    if entry.table == "stock_daily_risk":
        return "risk"
    if entry.table == "stock_daily_liquidity":
        return "liquidity"
    if entry.table.startswith("stock_daily_alpha"):
        return "alpha"
    return entry.category if entry.category in TECHNICAL_CATEGORIES else None


def is_overlay(entry) -> bool:
    return "overlap" in entry.table.lower() or bool(_OVERLAY_RE.match(entry.column))


def factor_catalog(registry: FactorRegistry | None = None) -> list[dict]:
    reg = registry or load_registry()
    result = []
    for entry in reg.entries.values():
        group = _group_of(entry)
        if group is None:
            continue
        result.append({
            "canonical": entry.canonical,
            "column": entry.column,
            "table": entry.table,
            "category": entry.category,
            "group": group,
            "label": entry.zh or entry.column,
            "family": entry.family,
            "output": entry.output,
            "price_basis": entry.price_basis,
            "params": dict(entry.params),
            "is_overlay": is_overlay(entry),
        })
    order = {name: index for index, name in enumerate(GROUP_ORDER)}
    result.sort(key=lambda item: (order[item["group"]], item["label"], item["canonical"]))
    return result


def price_scaled_canonicals(canonicals) -> dict[str, bool]:
    """canonical → 是否需要价格换算；目录里查不到的按不换算处理。"""
    wanted = set(canonicals)
    result: dict[str, bool] = {}
    for item in factor_catalog():
        if item["canonical"] in wanted:
            result[item["canonical"]] = is_price_scaled(item["family"], item["column"])
    for canonical in canonicals:
        result.setdefault(canonical, False)
    return result


def resolve_selection(canonicals) -> tuple[str, ...]:
    allowed = {item["canonical"] for item in factor_catalog()}
    selected = []
    seen = set()
    for canonical in canonicals:
        if not isinstance(canonical, str) or canonical not in allowed:
            raise GameRuleError(f"未知技术因子：{canonical}")
        if canonical not in seen:
            seen.add(canonical)
            selected.append(canonical)
    return tuple(selected)
