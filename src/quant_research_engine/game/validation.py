"""用游戏侧已复权 OHLC 独立重算价格型因子，逐点校验因子表换算结果。

本模块不读取因子表、不依赖任何经验常数，只按 TA-Lib 口径（EMA 用 SMA 种子、
BOLL 用 ddof=1 的标准差）从会话 K 线重算，供落库值与展示值对账。
"""

from __future__ import annotations

import math
import re

from quant_research_engine.game.factors import factor_catalog

ABS_TOLERANCE = 0.02
REL_TOLERANCE = 2e-3
# 全历史 EMA 与窗口首根 SMA 种子存在几何衰减差；只豁免 4×span 的暖机段，
# 之后的任何单点异常仍逐项计数，避免把真实错位/缺数据一并隐藏。
EMA_SEED_WARMUP_MULTIPLIER = 4

_EMA_RE = re.compile(r"^ema_(\d+)$")
_SMA_RE = re.compile(r"^sma_(\d+)$")
_BOLL_RE = re.compile(r"^(bbl|bbm|bbu)_(\d+)_([0-9.]+)")


def recompute_ema(closes, span: int) -> list[float | None]:
    values = [float(value) for value in closes]
    result: list[float | None] = [None] * len(values)
    if span <= 0 or len(values) < span:
        return result
    seed = sum(values[:span]) / span
    result[span - 1] = seed
    alpha = 2.0 / (span + 1.0)
    for index in range(span, len(values)):
        seed = values[index] * alpha + seed * (1.0 - alpha)
        result[index] = seed
    return result


def recompute_sma(closes, period: int) -> list[float | None]:
    values = [float(value) for value in closes]
    result: list[float | None] = [None] * len(values)
    if period <= 0:
        return result
    window = 0.0
    for index, value in enumerate(values):
        window += value
        if index >= period:
            window -= values[index - period]
        if index >= period - 1:
            result[index] = window / period
    return result


def recompute_boll(closes, period: int, mult: float = 2.0,
                   ddof: int = 1) -> dict[str, list[float | None]]:
    values = [float(value) for value in closes]
    count = len(values)
    mid: list[float | None] = [None] * count
    lower: list[float | None] = [None] * count
    upper: list[float | None] = [None] * count
    if period <= ddof or period <= 0:
        return {"bbl": lower, "bbm": mid, "bbu": upper}
    for index in range(period - 1, count):
        window = values[index - period + 1:index + 1]
        mean = sum(window) / period
        variance = sum((value - mean) ** 2 for value in window) / (period - ddof)
        deviation = math.sqrt(max(variance, 0.0))
        mid[index] = mean
        lower[index] = mean - mult * deviation
        upper[index] = mean + mult * deviation
    return {"bbl": lower, "bbm": mid, "bbu": upper}


def _expected_series(column: str, closes, cache: dict):
    match = _EMA_RE.match(column)
    if match:
        key = ("ema", match.group(1))
        if key not in cache:
            cache[key] = recompute_ema(closes, int(match.group(1)))
        return cache[key]
    match = _SMA_RE.match(column)
    if match:
        key = ("sma", match.group(1))
        if key not in cache:
            cache[key] = recompute_sma(closes, int(match.group(1)))
        return cache[key]
    match = _BOLL_RE.match(column)
    if match:
        prefix, period, mult = match.group(1), int(match.group(2)), float(match.group(3))
        key = ("boll", period, mult)
        if key not in cache:
            cache[key] = recompute_boll(closes, period, mult)
        return cache[key][prefix]
    return None


def audit_price_factors(bars, factors: dict, canonicals) -> dict:
    """逐点比对因子表值与按游戏 K 线重算的值；只审计可重算的价格型列。

    重算输入按 canonical 所属口径表选择（close / typical_price / average_price），
    每个口径独立缓存：_expected_series 的内层缓存键只含公式与参数（如
    ("ema", "5")），跨口径共用同一个 cache 时，先审计的 close 会把 typical /
    average 的同名列误配到收盘价序列——2026-11-14 样本 typical 691 处误报的
    根因即此（checked=11383 中 691 处全部落在 typical.ema_5，非暖机、非上游异常）。
    """
    closes = [float(bar.close) for bar in bars]
    catalog = {item["canonical"]: item for item in factor_catalog()}
    cache: dict = {}
    summary = {
        "checked": 0, "mismatches": 0,
        "max_abs_diff": 0.0, "max_rel_diff": 0.0,
        "canonicals": {},
    }
    for canonical in canonicals:
        item = catalog.get(canonical)
        if item is None:
            summary["canonicals"][canonical] = {"checked": 0, "mismatches": 0, "skipped": True}
            continue
        table = item.get("table", "")
        if table.endswith("_average_price"):
            # 先求 VWAP（Bar.average_price 已按会话复权比率换算），再按该因子
            # 的公式计算；不能直接把所有 average_price 口径列都当成 VWAP 本体
            # （EMA/MACD/BOLL 等会被误判 100%）。
            series = [bar.average_price for bar in bars]
            if any(value is None for value in series):
                # 缺 vol/amount 的 bar 还原不了均价，整列不做猜测性重算。
                summary["canonicals"][canonical] = {"checked": 0, "mismatches": 0, "skipped": True}
                continue
            basis = "average_price"
        elif table.endswith("_typical_price"):
            series = [(bar.high + bar.low + bar.close) / 3 for bar in bars]
            basis = "typical_price"
        elif table.endswith("_close"):
            series = closes
            basis = "close"
        else:
            # 未登记价格口径不做猜测性重算，显式 skipped。
            summary["canonicals"][canonical] = {"checked": 0, "mismatches": 0, "skipped": True}
            continue
        expected = _expected_series(item["column"], series, cache.setdefault(basis, {}))
        if expected is None:
            summary["canonicals"][canonical] = {"checked": 0, "mismatches": 0, "skipped": True}
            continue
        ema_match = _EMA_RE.match(item["column"])
        warmup = int(ema_match.group(1)) * EMA_SEED_WARMUP_MULTIPLIER if ema_match else 0
        stats = {"checked": 0, "mismatches": 0, "max_abs_diff": 0.0}
        for index, values in factors.items():
            actual = values.get(canonical)
            if actual is None or index >= len(expected) or index < warmup:
                continue
            reference = expected[index]
            if reference is None:
                continue
            diff = abs(float(actual) - reference)
            relative = diff / max(abs(reference), 1e-9)
            stats["checked"] += 1
            stats["max_abs_diff"] = max(stats["max_abs_diff"], diff)
            summary["max_abs_diff"] = max(summary["max_abs_diff"], diff)
            summary["max_rel_diff"] = max(summary["max_rel_diff"], relative)
            if diff > ABS_TOLERANCE and relative > REL_TOLERANCE:
                stats["mismatches"] += 1
        summary["checked"] += stats["checked"]
        summary["mismatches"] += stats["mismatches"]
        summary["canonicals"][canonical] = stats
    return summary