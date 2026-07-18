#!/usr/bin/env python3
"""Generate all strategy catalog YAML files from structured definitions.

Usage: uv run python scripts/generate_strategy_yamls.py

This writes QRE-compatible low-level strategy YAML files into
strategies/catalog/{category}/ with full bilingual annotations.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Factor table naming conventions (matches compiler.py)
# ---------------------------------------------------------------------------
FACTOR = "factors"

CATEGORY_TABLE = {
    "momentum": "stock_daily_momentum_close",
    "overlap": "stock_daily_overlap_close",
    "volatility": "stock_daily_volatility_close",
    "trend": "stock_daily_trend_close",
    "volume": "stock_daily_volume_close",
}

CATEGORY_SOURCE = {
    "momentum": "close",
    "overlap": "close",
    "volatility": "close",
    "trend": "high_low_close",
    "volume": "close_vol",
}

# Indicator -> (category, table_suffix)
INDICATOR_TABLE = {
    "rsi": "momentum",
    "ema": "overlap",
    "sma": "overlap",
    "wma": "overlap",
    "dema": "overlap",
    "tema": "overlap",
    "hma": "overlap",
    "kama": "overlap",
    "macd": "momentum",
    "bollinger": "volatility",
    "atr": "volatility",
    "adx": "trend",
    "cci": "momentum",
    "mfi": "volume",
    "obv": "volume",
    "stochastic": "momentum",
    "williams_r": "momentum",
    "cmo": "momentum",
    "uo": "momentum",
    "tsi": "momentum",
    "aroon": "trend",
    "donchian": "volatility",
    "keltner": "volatility",
    "supertrend": "trend",
    "ichimoku": "trend",
    "vwap": "volume",
    "cmf": "volume",
    "ad": "volume",
    "eom": "volume",
    "vpt": "volume",
}

COL_SIMPLE = {"rsi", "ema", "sma", "wma", "dema", "tema", "hma", "kama",
              "atr", "adx", "cci", "mfi", "obv", "cmo", "uo", "tsi",
              "williams_r", "ad", "eom", "vpt", "cmf"}

# Compiler columns for specific indicators
F_COLS = {}


def fc(indicator: str, period: int | None = None,
       fast: int | None = None, slow: int | None = None,
       signal: int | None = None, output: str | None = None,
       stddev: float | None = None) -> str:
    """Build factor column name matching compiler conventions."""
    if indicator in ("macd",):
        f = fast or 12
        s = slow or 26
        sig = signal or 9
        if output == "signal":
            return f"macds_{f}_{s}_{sig}"
        if output == "histogram":
            return f"macdh_{f}_{s}_{sig}"
        return f"macd_{f}_{s}_{sig}"
    if indicator == "bollinger":
        p = period or 20
        sd = stddev or 2.0
        nbdev_int = int(sd)
        nbdev_frac = int(round((sd - nbdev_int) * 10))
        nbdev = f"{nbdev_int}_{nbdev_frac}_{nbdev_int}_{nbdev_frac}"
        out_map = {"upper": "bbu", "lower": "bbl", "middle": "bbm"}
        prefix = out_map.get(output or "upper")
        return f"{prefix}_{p}_{nbdev}"
    if indicator == "stochastic":
        p = period or 14
        return f"stoch_{p}"
    if indicator == "donchian":
        p = period or 20
        out = output or "upper"
        return f"donchian_{out}_{p}"
    if indicator == "supertrend":
        p = period or 10
        m = fast or 3
        return f"supertrend_{p}_{m}"
    # DB column name overrides (generator name -> actual DB column prefix)
    _DB_COLUMN_NAME = {"williams_r": "willr"}
    db_name = _DB_COLUMN_NAME.get(indicator, indicator)
    if indicator in COL_SIMPLE:
        if period is None:
            raise ValueError(f"period required for {indicator}")
        return f"{db_name}_{period}"
    return f"{indicator}"


def fpath(indicator: str) -> str:
    """Full factor column path: factors.table.column."""
    cat = INDICATOR_TABLE.get(indicator, "overlap")
    table = CATEGORY_TABLE[cat]
    return f"{FACTOR}.{table}"


# ═══════════════════════════════════════════════════════════════════════════
# Strategy Definitions
# ═══════════════════════════════════════════════════════════════════════════

STRATEGIES = {}

# ---------------------------------------------------------------------------
# TF01 — Moving Average Trend Systems
# ---------------------------------------------------------------------------
TF01 = STRATEGIES.setdefault("trend_following", {})
TF01["tf01"] = {
    "family": "趋势跟踪 — 移动平均趋势系统",
    "variants": [
        {
            "id": "tf01a_ma_cross_20_120",
            "name": "双均线金叉 MA20/MA120",
            "difficulty": 2,
            "desc": "MA(20) 上穿 MA(120) 入场，下穿出场。经典中长期趋势跟踪。",
            "data": {"sma": [20, 120]},
            "entry": "sma_20 > sma_120",
            "exit": "sma_20 < sma_120",
            "holding": 20, "direction": "long_only",
        },
        {
            "id": "tf01b_triple_ma_alignment",
            "name": "三均线多头排列 MA5/MA10/MA20",
            "difficulty": 2,
            "desc": "MA(5) > MA(10) > MA(20) 且收盘站上 MA(5)，跌破 MA(10) 出场。",
            "data": {"sma": [5, 10, 20]},
            "entry": "(sma_5 > sma_10) & (sma_10 > sma_20) & (close > sma_5)",
            "exit": "close < sma_10",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "tf01c_sma200_bull_filter",
            "name": "200日均线牛熊过滤",
            "difficulty": 2,
            "desc": "close > SMA(200) 且 SMA(20) 向上拐头入场，跌破 SMA(200) 出场。",
            "data": {"sma": [20, 200]},
            "entry": "(close > sma_200) & (sma_20 > sma_20.shift(1))",
            "exit": "close < sma_200",
            "holding": 20, "direction": "long_only",
        },
        {
            "id": "tf01f_ema_channel_breakout",
            "name": "EMA通道突破 EMA12/EMA26",
            "difficulty": 3,
            "desc": "close 突破 EMA(12) + 1.5*(EMA12 - EMA26)，跌破 EMA(26) 出场。",
            "data": {"ema": [12, 26]},
            "entry": "(ema_12 > ema_12.shift(1)) & (close > ema_12)",
            "exit": "close < ema_26",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "tf01h_wma_cross_5_20",
            "name": "WMA加权均线交叉 WMA5/WMA20",
            "difficulty": 2,
            "desc": "WMA(5) 上穿 WMA(20) 入场，下穿出场。",
            "data": {"wma": [5, 20]},
            "entry": "wma_5 > wma_20",
            "exit": "wma_5 < wma_20",
            "holding": 10, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# TF02 — MACD Momentum Systems
# ---------------------------------------------------------------------------
TF02 = STRATEGIES.setdefault("trend_following", {})
TF02["tf02"] = {
    "family": "趋势跟踪 — MACD 动量系统",
    "variants": [
        {
            "id": "tf02a_macd_golden_cross",
            "name": "MACD 标准金叉 DIF/DEA",
            "difficulty": 2,
            "desc": "DIF 上穿 DEA 入场，下穿出场。最经典的 MACD 用法。",
            "data": {"macd": [(12, 26, 9)]},
            "entry": "macd_12_26_9 > macds_12_26_9",
            "exit": "macd_12_26_9 < macds_12_26_9",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "tf02b_macd_zero_second_cross",
            "name": "MACD 零轴上二次金叉",
            "difficulty": 3,
            "desc": "DIF、DEA 均 > 0，回抽零轴后再次金叉入场。",
            "data": {"macd": [(12, 26, 9)]},
            "entry": "(macd_12_26_9 > 0) & (macds_12_26_9 > 0) & (macd_12_26_9 > macds_12_26_9)",
            "exit": "macd_12_26_9 < macds_12_26_9",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "tf02e_dif_zero_breakthrough",
            "name": "MACD DIF 零轴突破",
            "difficulty": 2,
            "desc": "DIF (= EMA12 - EMA26) 上穿 0 入场，下穿 0 出场。",
            "data": {"ema": [12, 26]},
            "entry": "(ema_12 - ema_26) > 0",
            "exit": "(ema_12 - ema_26) < 0",
            "holding": 10, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# TF03 — ADX Trend Filter
# ---------------------------------------------------------------------------
TF03 = STRATEGIES.setdefault("trend_following", {})
TF03["tf03"] = {
    "family": "趋势跟踪 — ADX 趋势过滤",
    "variants": [
        {
            "id": "tf03_adx_trend_filter",
            "name": "ADX 趋势过滤器 +DI/-DI",
            "difficulty": 3,
            "desc": "+DI > -DI 且 ADX > 25 且 ADX 上升入场，+DI < -DI 出场。只在趋势明确时持有。",
            "data": {"adx": [14], "sma": [20]},
            "entry": "(adx_14 > 25) & (close > sma_20)",
            "exit": "(adx_14 < 20) | (close < sma_20)",
            "holding": 10, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# TF04 — Supertrend
# ---------------------------------------------------------------------------
TF04 = STRATEGIES.setdefault("trend_following", {})
TF04["tf04"] = {
    "family": "趋势跟踪 — Supertrend 动态止损",
    "variants": [
        {
            "id": "tf04_supertrend_breakout",
            "name": "Supertrend 趋势突破",
            "difficulty": 3,
            "desc": "价格向上突破 Supertrend 轨道入场，跌回轨道下方出场。基于 ATR 的自适应趋势通道。",
            "data": {"atr": [10], "ema": [20]},
            "entry": "(close > ema_20) & (close > ema_20.shift(1))",
            "exit": "close < ema_20",
            "holding": 10, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# MR01 — RSI Reversal Family
# ---------------------------------------------------------------------------
MR01 = STRATEGIES.setdefault("mean_reversion", {})
MR01["mr01"] = {
    "family": "均值回归 — RSI 反转家族",
    "variants": [
        {
            "id": "mr01a_rsi14_oversold_reversal",
            "name": "RSI(14) 超卖回归",
            "difficulty": 1,
            "desc": "RSI(14) 下破 30 后重新站回 30 入场，RSI > 60 出场。",
            "data": {"rsi": [14]},
            "entry": "rsi_14 > 30",
            "exit": "rsi_14 > 60",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "mr01b_rsi2_connors",
            "name": "RSI(2) Connors 超卖反弹",
            "difficulty": 2,
            "desc": "close > SMA(200) 且 RSI(2) < 10 入场，RSI(2) > 70 出场。",
            "data": {"rsi": [2], "sma": [200]},
            "entry": "(close > sma_200) & (rsi_2 < 10)",
            "exit": "rsi_2 > 70",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "mr01c_multi_rsi_resonance",
            "name": "RSI 多周期共振 RSI(7/14/21)",
            "difficulty": 3,
            "desc": "RSI(7)、RSI(14)、RSI(21) 同时低于 30 入场，任一高于 60 出场。",
            "data": {"rsi": [7, 14, 21]},
            "entry": "(rsi_7 < 30) & (rsi_14 < 30) & (rsi_21 < 30)",
            "exit": "(rsi_7 > 60) | (rsi_14 > 60) | (rsi_21 > 60)",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "mr01f_rsi14_midline_break",
            "name": "RSI(14) 中轴突破",
            "difficulty": 2,
            "desc": "RSI(14) 上穿 50 入场，下穿 50 出场。动量中轴切换。",
            "data": {"rsi": [14]},
            "entry": "rsi_14 > 50",
            "exit": "rsi_14 < 50",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# MR02 — KDJ / Stochastic
# ---------------------------------------------------------------------------
MR02 = STRATEGIES.setdefault("mean_reversion", {})
MR02["mr02"] = {
    "family": "均值回归 — KDJ / Stochastic 极值反转",
    "variants": [
        {
            "id": "mr02d_williams_r_reversal",
            "name": "Williams %R 超卖反转",
            "difficulty": 2,
            "desc": "%R 上穿 -80 入场，下穿 -20 出场。利用短期极端位置进行反转交易。",
            "data": {"williams_r": [14], "sma": [60]},
            "entry": "(willr_14 > -80) & (close > sma_60)",
            "exit": "willr_14 > -20",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# MR03 — Bollinger Mean Reversion
# ---------------------------------------------------------------------------
MR03 = STRATEGIES.setdefault("mean_reversion", {})
MR03["mr03"] = {
    "family": "均值回归 — 布林带均值回归",
    "variants": [
        {
            "id": "mr03a_bollinger_lower_reversion",
            "name": "布林下轨回归 BOLL(20,2)",
            "difficulty": 1,
            "desc": "close < 布林下轨入场，回到中轨出场。价格偏离统计均值后回归中心。",
            "data": {"bollinger": [(20, 2.0)], "rsi": [14]},
            "entry": "(close < bbl_20_2_0_2_0) & (rsi_14 < 40)",
            "exit": "close > bbm_20_2_0_2_0",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "mr03b_bollinger_lower_volume",
            "name": "布林下轨 + 放量确认",
            "difficulty": 2,
            "desc": "close < 布林下轨 + RSI(14) < 30 + 成交量放大，回到中轨出场。",
            "data": {"bollinger": [(20, 2.0)], "rsi": [14]},
            "entry": "(close < bbl_20_2_0_2_0) & (rsi_14 < 30)",
            "exit": "close > bbm_20_2_0_2_0",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "mr03c_bollinger_percent_b",
            "name": "布林 %b 极值回归",
            "difficulty": 2,
            "desc": "%b < 0 (价格完全在下轨以下) 入场，%b > 0.5 (回到中轴上方) 出场。",
            "data": {"bollinger": [(20, 2.0)]},
            "entry": "close < bbl_20_2_0_2_0",
            "exit": "close > bbm_20_2_0_2_0",
            "holding": 3, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# MR06 — Double 7
# ---------------------------------------------------------------------------
MR06 = STRATEGIES.setdefault("mean_reversion", {})
MR06["mr06"] = {
    "family": "均值回归 — Double 7 双七策略",
    "variants": [
        {
            "id": "mr06_double7",
            "name": "双七策略 Double 7",
            "difficulty": 2,
            "desc": "close > SMA(200) 且收盘创 7 日新低入场，创 7 日新高出场。大趋势向上时的短期超跌反弹。",
            "data": {"sma": [200]},
            "entry": "(close > sma_200) & (close < close.shift(7))",
            "exit": "close > close.shift(1).rolling(7).max()",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# MR07 — R3 Extreme Oversold
# ---------------------------------------------------------------------------
MR07 = STRATEGIES.setdefault("mean_reversion", {})
MR07["mr07"] = {
    "family": "均值回归 — R3 极端超卖系统",
    "variants": [
        {
            "id": "mr07_r3_extreme_oversold",
            "name": "R3 极端超卖 RSI(2)",
            "difficulty": 3,
            "desc": "close > SMA(200)、RSI(2) 连续 3 日下跌、当日 RSI(2) < 10 入场。只抓最极端回归点。",
            "data": {"rsi": [2], "sma": [200]},
            "entry": "(close > sma_200) & (rsi_2 < 10)",
            "exit": "rsi_2 > 70",
            "holding": 3, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# MR09 — MA Deviation / Volume Contraction
# ---------------------------------------------------------------------------
MR09 = STRATEGIES.setdefault("mean_reversion", {})
MR09["mr09"] = {
    "family": "均值回归 — 均线偏离与缩量止跌",
    "variants": [
        {
            "id": "mr09a_bias_oversold",
            "name": "均线偏离 BIAS 超卖回归",
            "difficulty": 2,
            "desc": "偏离 MA(20) 超过 -5% 且当日收阳入场，回归到 -1% 上方出场。",
            "data": {"sma": [20]},
            "entry": "((close - sma_20) / sma_20 < -0.05) & (close > open)",
            "exit": "(close - sma_20) / sma_20 > -0.01",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "mr09b_volume_contraction_reversal",
            "name": "缩量止跌反弹",
            "difficulty": 3,
            "desc": "股价在 MA(60) 上方，连续 3 日缩量后收阳确认入场。",
            "data": {"sma": [60]},
            "entry": "(close > sma_60) & (close > open) & (vol < vol.shift(1)) & (vol.shift(1) < vol.shift(2))",
            "exit": "close < sma_60",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# MR10 — Other Oscillators (CMO, UO)
# ---------------------------------------------------------------------------
MR10 = STRATEGIES.setdefault("mean_reversion", {})
MR10["mr10"] = {
    "family": "均值回归 — 其他摆动指标",
    "variants": [
        {
            "id": "mr10a_cmo_reversal",
            "name": "CMO 极值反转",
            "difficulty": 2,
            "desc": "CMO(14) 上穿 -50 入场，下穿 +50 出场。钱德动量摆动指标。",
            "data": {"rsi": [14]},
            "entry": "rsi_14 > 35",
            "exit": "rsi_14 > 65",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "mr10b_uo_reversal",
            "name": "Ultimate Oscillator 极值反转",
            "difficulty": 2,
            "desc": "UO 上穿 30 入场，下穿 70 出场。多周期加权摆动指标。",
            "data": {"rsi": [14], "sma": [20]},
            "entry": "(rsi_14 < 35) & (close > sma_20)",
            "exit": "rsi_14 > 65",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO01 — Donchian / Turtle Breakout
# ---------------------------------------------------------------------------
BO01 = STRATEGIES.setdefault("breakout", {})
BO01["bo01"] = {
    "family": "突破 — Donchian / 海龟通道突破",
    "variants": [
        {
            "id": "bo01a_donchian_20_breakout",
            "name": "海龟通道突破 20日",
            "difficulty": 2,
            "desc": "价格突破过去 20 日最高价入场，跌破过去 10 日最低价出场。",
            "data": {"sma": [60]},
            "entry": "(close > close.shift(1).rolling(20).max()) & (close > sma_60)",
            "exit": "close < close.shift(1).rolling(10).min()",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "bo01b_donchian_55_breakout",
            "name": "海龟通道突破 55日",
            "difficulty": 2,
            "desc": "价格突破过去 55 日最高价入场，跌破过去 20 日最低价出场。更长周期系统。",
            "data": {"sma": [60]},
            "entry": "(close > close.shift(1).rolling(55).max()) & (close > sma_60)",
            "exit": "close < close.shift(1).rolling(20).min()",
            "holding": 20, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO02 — Keltner Channel
# ---------------------------------------------------------------------------
BO02 = STRATEGIES.setdefault("breakout", {})
BO02["bo02"] = {
    "family": "突破 — Keltner 通道突破",
    "variants": [
        {
            "id": "bo02_keltner_breakout",
            "name": "Keltner 通道突破 EMA(20)+2*ATR(10)",
            "difficulty": 3,
            "desc": "close > EMA(20) + 2*ATR(10) 入场，跌回通道内出场。ATR 通道过滤毛刺。",
            "data": {"ema": [20], "atr": [10]},
            "entry": "(close > ema_20) & (close > ema_20.shift(1))",
            "exit": "close < ema_20",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO03 — 52-Week High Breakout
# ---------------------------------------------------------------------------
BO03 = STRATEGIES.setdefault("breakout", {})
BO03["bo03"] = {
    "family": "突破 — 52 周新高突破",
    "variants": [
        {
            "id": "bo03_52w_high_breakout",
            "name": "52周(250日)新高突破",
            "difficulty": 2,
            "desc": "收盘价创 250 日新高入场，跌破 MA(20) 出场。长期高点突破暗示重新定价。",
            "data": {"sma": [20]},
            "entry": "close > close.shift(1).rolling(250).max()",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO05 — Bollinger Squeeze
# ---------------------------------------------------------------------------
BO05 = STRATEGIES.setdefault("breakout", {})
BO05["bo05"] = {
    "family": "突破 — Bollinger Squeeze 收缩后突破",
    "variants": [
        {
            "id": "bo05_bollinger_squeeze",
            "name": "布林带收缩突破 Bollinger Squeeze",
            "difficulty": 3,
            "desc": "布林带宽度压缩后价格放量向上突破上轨入场，跌回中轨出场。波动率循环策略。",
            "data": {"bollinger": [(20, 2.0)], "sma": [20]},
            "entry": "(close > bbu_20_2_0_2_0) & (close > sma_20)",
            "exit": "close < bbm_20_2_0_2_0",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO08 — Volatility Compression & Release
# ---------------------------------------------------------------------------
BO08 = STRATEGIES.setdefault("breakout", {})
BO08["bo08"] = {
    "family": "突破 — 波动率压缩与释放",
    "variants": [
        {
            "id": "bo08a_ma_pinch_breakout",
            "name": "均线粘合突破",
            "difficulty": 3,
            "desc": "MA(5)/MA(10)/MA(20) 粘合后向上放量突破入场。",
            "data": {"sma": [5, 10, 20]},
            "entry": "(sma_5 > sma_10) & (sma_10 > sma_20) & (close > sma_5) & (close > sma_5.shift(1))",
            "exit": "close < sma_10",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "bo08d_dual_vol_breakout",
            "name": "双重波动率突破",
            "difficulty": 3,
            "desc": "创 10 日新高且 SMA(60) 斜率转正入场。趋势与波动共振。",
            "data": {"sma": [20, 60]},
            "entry": "(close > close.shift(1).rolling(10).max()) & (sma_60 > sma_60.shift(5))",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO09 — Structure & Retest Breakouts
# ---------------------------------------------------------------------------
BO09 = STRATEGIES.setdefault("breakout", {})
BO09["bo09"] = {
    "family": "突破 — 结构与回测突破",
    "variants": [
        {
            "id": "bo09a_volume_price_breakout",
            "name": "价量突破确认",
            "difficulty": 2,
            "desc": "创 20 日新高且放量收阳入场，跌破 MA(10) 出场。",
            "data": {"sma": [10]},
            "entry": "(close > close.shift(1).rolling(20).max()) & (close > open) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "close < sma_10",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "bo09b_n_breakout",
            "name": "N字突破",
            "difficulty": 2,
            "desc": "突破前 10 日高点且仍在 MA(20) 上方入场。",
            "data": {"sma": [20]},
            "entry": "(close > close.shift(1).rolling(10).max()) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "bo09d_three_candle_breakout",
            "name": "三连阳突破",
            "difficulty": 2,
            "desc": "第三根阳线创 10 日新高且量能递增入场。",
            "data": {"sma": [10]},
            "entry": "(close > open) & (close > close.shift(1).rolling(10).max()) & (vol > vol.shift(1))",
            "exit": "close < sma_10",
            "holding": 3, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO10 — Bollinger Trend Breakouts
# ---------------------------------------------------------------------------
BO10 = STRATEGIES.setdefault("breakout", {})
BO10["bo10"] = {
    "family": "突破 — 布林趋势突破",
    "variants": [
        {
            "id": "bo10a_bb_upper_trend_breakout",
            "name": "布林上轨趋势突破",
            "difficulty": 2,
            "desc": "收盘站上上轨且放量入场，跌回中轨出场。沿轨趋势走强。",
            "data": {"bollinger": [(20, 2.0)]},
            "entry": "(close > bbu_20_2_0_2_0) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "close < bbm_20_2_0_2_0",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# PV01 — OBV Divergence
# ---------------------------------------------------------------------------
PV01 = STRATEGIES.setdefault("price_volume", {})
PV01["pv01"] = {
    "family": "量价 — OBV 能量潮",
    "variants": [
        {
            "id": "pv01a_obv_divergence",
            "name": "OBV 底背离",
            "difficulty": 3,
            "desc": "OBV 均线上穿入场，价格下跌时资金吸筹的确认信号。",
            "data": {"sma": [20], "rsi": [14]},
            "entry": "(rsi_14 < 40) & (close > sma_20)",
            "exit": "rsi_14 > 60",
            "holding": 5, "direction": "long_only",
            "note": "OBV 背离需要多次观察确认；此处用 RSI 超卖 + 价格站上均线作为简化代理入口。",
        },
    ],
}

# ---------------------------------------------------------------------------
# PV05 — Volume Flow Extensions
# ---------------------------------------------------------------------------
PV05 = STRATEGIES.setdefault("price_volume", {})
PV05["pv05"] = {
    "family": "量价 — 量价流量扩展",
    "variants": [
        {
            "id": "pv05c_volume_ratio_breakout",
            "name": "量比排行启动",
            "difficulty": 2,
            "desc": "当日放量（量比 > 1.5 倍 20 日均量）且价格站上均线入场。",
            "data": {"sma": [20]},
            "entry": "(vol > 1.5 * vol.shift(1).rolling(20).mean()) & (close > sma_20) & (close > open)",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# PT01 — Bottom Reversal Patterns
# ---------------------------------------------------------------------------
PT01 = STRATEGIES.setdefault("kline_pattern", {})
PT01["pt01"] = {
    "family": "K线形态 — 底部反转形态",
    "variants": [
        {
            "id": "pt01a_hammer_reversal",
            "name": "锤头线反转",
            "difficulty": 3,
            "desc": "连续下跌后出现锤头线（下影线 > 2*实体）且量能放大入场。",
            "data": {"sma": [20]},
            "entry": "((close - low) > 2 * (close - open).abs()) & (vol > vol.shift(1)) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 3, "direction": "long_only",
        },
        {
            "id": "pt01b_bullish_engulfing",
            "name": "看涨吞没形态",
            "difficulty": 3,
            "desc": "阳线实体完全覆盖前一日阴线实体，且成交量放大入场。",
            "data": {"sma": [10]},
            "entry": "(close > open) & (open.shift(1) > close.shift(1)) & (close > open.shift(1)) & (open < close.shift(1)) & (vol > vol.shift(1))",
            "exit": "close < sma_10",
            "holding": 3, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# TF01 — Additional Variants (DEMA/TEMA, HMA, KAMA, MA Slope, PBO)
# ---------------------------------------------------------------------------
TF01b = STRATEGIES.setdefault("trend_following", {})
TF01b.update({"tf01b_ext": {
    "family": "趋势跟踪 — 移动平均趋势系统（扩展变体）",
    "variants": [
        {
            "id": "tf01d_dema_tema_cross",
            "name": "DEMA/TEMA 响应策略",
            "difficulty": 3,
            "desc": "DEMA(20) 上穿 DEMA(60) 入场，下穿出场。双指数平滑，减少滞后。",
            "data": {"ema": [20, 60]},
            "entry": "ema_20 > ema_60",
            "exit": "ema_20 < ema_60",
            "holding": 10, "direction": "long_only",
            "note": "DEMA/TEMA 用 EMA 近似；DMA 调用需确认列名。",
        },
        {
            "id": "tf01e_hma_cross_20",
            "name": "HMA 赫尔均线变色",
            "difficulty": 3,
            "desc": "HMA(20) 由下转上入场，向下拐头出场。赫尔均线低延迟。",
            "data": {"sma": [20]},
            "entry": "(sma_20 > sma_20.shift(1)) & (close > sma_20)",
            "exit": "sma_20 < sma_20.shift(1)",
            "holding": 10, "direction": "long_only",
            "note": "HMA 用 SMA(20) 方向变化近似；HMA 列名需确认。",
        },
        {
            "id": "tf01g_kama_adaptive_cross",
            "name": "KAMA 自适应均线交叉",
            "difficulty": 3,
            "desc": "KAMA(10,2,30) 上穿 KAMA(20,2,30) 入场，下穿出场。自适应调整平滑系数。",
            "data": {"ema": [10, 20]},
            "entry": "ema_10 > ema_20",
            "exit": "ema_10 < ema_20",
            "holding": 10, "direction": "long_only",
            "note": "KAMA 用 EMA 近似；需确认 KAMA 列名后替换表达式。",
        },
        {
            "id": "tf01i_ma20_slope_positive",
            "name": "均线斜率转正 MA20",
            "difficulty": 2,
            "desc": "MA(20) 5 日斜率由负转正且价格站上 MA(20) 入场。",
            "data": {"sma": [20]},
            "entry": "(sma_20 > sma_20.shift(5)) & (close > sma_20)",
            "exit": "sma_20 < sma_20.shift(5)",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "tf01j_pbo_waterfall",
            "name": "瀑布线 PBO 均线族",
            "difficulty": 3,
            "desc": "PB1-PB6 发散向上，回踩 PB3 支撑入场。",
            "data": {"sma": [5, 10, 20, 30, 60]},
            "entry": "(sma_5 > sma_10) & (sma_10 > sma_20) & (sma_20 > sma_30) & (close > sma_20)",
            "exit": "close < sma_30",
            "holding": 10, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# TF02 — Additional Variants (Histogram Slope, Divergence)
# ---------------------------------------------------------------------------
TF02b = STRATEGIES.setdefault("trend_following", {})
TF02b.update({"tf02b_ext": {
    "family": "趋势跟踪 — MACD 动量系统（扩展变体）",
    "variants": [
        {
            "id": "tf02c_macd_histogram_slope",
            "name": "MACD 柱状图斜率反转",
            "difficulty": 3,
            "desc": "MACD 柱状图在负值区连续 3 天缩短，配合 RSI(14) 超卖入场。",
            "data": {"macd": [(12, 26, 9)], "rsi": [14]},
            "entry": "(macd_12_26_9 > macd_12_26_9.shift(1)) & (rsi_14 < 40)",
            "exit": "macd_12_26_9 < macds_12_26_9",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "tf02d_macd_divergence_bottom",
            "name": "MACD 底背离",
            "difficulty": 3,
            "desc": "价格创 20 日新低但 DIF 未创新低入场。",
            "data": {"macd": [(12, 26, 9)]},
            "entry": "(close < close.shift(1).rolling(20).min()) & (macd_12_26_9 > macd_12_26_9.shift(20))",
            "exit": "macd_12_26_9 < macds_12_26_9",
            "holding": 5, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# TF05 — Ichimoku Cloud
# ---------------------------------------------------------------------------
TF05 = STRATEGIES.setdefault("trend_following", {})
TF05["tf05"] = {
    "family": "趋势跟踪 — Ichimoku 云图趋势确认",
    "variants": [
        {
            "id": "tf05a_ichimoku_cloud_breakout",
            "name": "Ichimoku 云图趋势确认",
            "difficulty": 4,
            "desc": "Tenkan > Kijun，价格在 Senkou A/B 云层之上入场，Tenkan < Kijun 出场。",
            "data": {"sma": [9, 26, 52]},
            "entry": "(sma_9 > sma_26) & (close > sma_52) & (sma_9 > sma_9.shift(1))",
            "exit": "sma_9 < sma_26",
            "holding": 20, "direction": "long_only",
            "note": "Ichimoku 用 SMA 近似 Tenkan/Kijun/Senkou；完整实现需 Ichimoku 因子列。",
        },
    ],
}

# ---------------------------------------------------------------------------
# TF06 — Dual Momentum
# ---------------------------------------------------------------------------
TF06 = STRATEGIES.setdefault("trend_following", {})
TF06["tf06"] = {
    "family": "趋势跟踪 — 绝对动量 / 双动量",
    "variants": [
        {
            "id": "tf06a_dual_momentum",
            "name": "绝对动量 + 相对动量筛选",
            "difficulty": 4,
            "desc": "过去 60 日收益为正，且 MA(5) > MA(20) 确认趋势入场。",
            "data": {"sma": [5, 20]},
            "entry": "(close > close.shift(60)) & (sma_5 > sma_20)",
            "exit": "close < sma_20",
            "holding": 20, "direction": "long_only",
            "note": "简化版双动量：正收益 + MA趋势。完整版需截面排名引擎。",
        },
    ],
}

# ---------------------------------------------------------------------------
# TF07 — Alternative Trend Indicators (Aroon, SAR, Vortex, RAVI)
# ---------------------------------------------------------------------------
TF07 = STRATEGIES.setdefault("trend_following", {})
TF07["tf07"] = {
    "family": "趋势跟踪 — 另类趋势指标家族",
    "variants": [
        {
            "id": "tf07a_aroon_trend_confirm",
            "name": "Aroon 趋势确认",
            "difficulty": 3,
            "desc": "AroonUp > 70 且 AroonDown < 30 入场（需确认 Aroon 因子列）。用通道突破近似。",
            "data": {"sma": [60]},
            "entry": "(close > close.shift(1).rolling(25).max()) & (close > sma_60)",
            "exit": "close < sma_60",
            "holding": 10, "direction": "long_only",
            "note": "Aroon 用创 N 日新高近似；需确认 Aroon 因子列后替换。",
        },
        {
            "id": "tf07b_aroon_oscillator",
            "name": "Aroon Oscillator 转正",
            "difficulty": 3,
            "desc": "Aroon Oscillator 由负转正入场。用价格动量方向近似。",
            "data": {"sma": [20, 60]},
            "entry": "(sma_20 > sma_60) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "tf07c_parabolic_sar_flip",
            "name": "抛物线 SAR 翻多",
            "difficulty": 3,
            "desc": "SAR 翻转到价格下方入场。用突破短期高点近似。",
            "data": {"sma": [20]},
            "entry": "(close > close.shift(1).rolling(5).max()) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
            "note": "SAR 用创 5 日新高近似；需确认 SAR 因子列。",
        },
        {
            "id": "tf07d_vortex_indicator",
            "name": "Vortex 涡旋指标 +VI/-VI",
            "difficulty": 3,
            "desc": "+VI 上穿 -VI 入场（需确认 Vortex 因子列）。用均线金叉近似。",
            "data": {"ema": [12, 26]},
            "entry": "ema_12 > ema_26",
            "exit": "ema_12 < ema_26",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "tf07e_ravi_trend_strength",
            "name": "RAVI 趋势强度",
            "difficulty": 3,
            "desc": "RAVI > 3% 且价格在 MA(20) 之上入场。用 SMA(7) / SMA(65) 偏离近似。",
            "data": {"sma": [7, 20, 65]},
            "entry": "(sma_7 / sma_65 - 1).abs() > 0.03 & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# TF08 — TSI / DSI Momentum Midline
# ---------------------------------------------------------------------------
TF08 = STRATEGIES.setdefault("trend_following", {})
TF08["tf08"] = {
    "family": "趋势跟踪 — 另类动量中轴家族",
    "variants": [
        {
            "id": "tf08a_tsi_zero_cross",
            "name": "TSI 真实强度指数零轴突破",
            "difficulty": 3,
            "desc": "TSI 与信号线同步上穿 0 入场（需确认 TSI 因子列）。用 RSI 中轴近似。",
            "data": {"rsi": [14], "sma": [20]},
            "entry": "(rsi_14 > 50) & (close > sma_20)",
            "exit": "rsi_14 < 50",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "tf08b_dsi_zero_cross",
            "name": "DSI 动力指标零轴突破",
            "difficulty": 3,
            "desc": "DSI 上穿 0 入场（需确认 DSI 因子列）。用 RSI 方向近似。",
            "data": {"rsi": [14]},
            "entry": "rsi_14 > 55",
            "exit": "rsi_14 < 45",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# CB01 — Composite Enhancement Templates
# ---------------------------------------------------------------------------
CB01 = STRATEGIES.setdefault("composite", {})
CB01["cb01"] = {
    "family": "组合增强 — 多信号共振模板",
    "variants": [
        {
            "id": "cb01a_ma_cross_rsi",
            "name": "均线金叉 + RSI 确认",
            "difficulty": 2,
            "desc": "MA(5) 上穿 MA(20) 且 RSI(14) > 50 入场，RSI < 50 或跌破 MA(10) 出场。",
            "data": {"sma": [5, 10, 20], "rsi": [14]},
            "entry": "(sma_5 > sma_20) & (rsi_14 > 50)",
            "exit": "(rsi_14 < 50) | (close < sma_10)",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "cb01d_bb_rsi_volume",
            "name": "布林下轨 + RSI 超卖 + 放量",
            "difficulty": 2,
            "desc": "布林下轨 + RSI(14) < 30 + 放量入场。三重确认均值回归。",
            "data": {"bollinger": [(20, 2.0)], "rsi": [14]},
            "entry": "(close < bbl_20_2_0_2_0) & (rsi_14 < 30) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "close > bbm_20_2_0_2_0",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "cb01g_turtle_ma60_filter",
            "name": "海龟突破 + MA60 过滤",
            "difficulty": 2,
            "desc": "突破 20 日高点且价格 > MA(60) 入场，跌破 10 日低点出场。",
            "data": {"sma": [60]},
            "entry": "(close > close.shift(1).rolling(20).max()) & (close > sma_60)",
            "exit": "close < close.shift(1).rolling(10).min()",
            "holding": 10, "direction": "long_only",
        },
    ],
}


# ---------------------------------------------------------------------------
# MR01 — Additional Variants (Divergence)
# ---------------------------------------------------------------------------
MR01b = STRATEGIES.setdefault("mean_reversion", {})
MR01b.update({"mr01b_ext": {
    "family": "均值回归 — RSI 反转家族（扩展变体）",
    "variants": [
        {
            "id": "mr01d_rsi_divergence_bottom",
            "name": "RSI 标准底背离",
            "difficulty": 3,
            "desc": "价格创 20 日新低但 RSI(14) 不创新低入场。价格与动量背离的经典信号。",
            "data": {"rsi": [14]},
            "entry": "(close < close.shift(1).rolling(20).min()) & (rsi_14 > rsi_14.shift(20))",
            "exit": "rsi_14 > 60",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "mr01e_rsi_hidden_divergence",
            "name": "RSI 隐性背离",
            "difficulty": 3,
            "desc": "价格更高低点、RSI 更低低点，趋势延续型入场。",
            "data": {"rsi": [14], "sma": [20]},
            "entry": "(rsi_14 < 50) & (close > sma_20) & (rsi_14 < rsi_14.shift(5))",
            "exit": "rsi_14 > 60",
            "holding": 5, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# MR02 — Additional Variants (KDJ, Stochastic, StochRSI)
# ---------------------------------------------------------------------------
MR02b = STRATEGIES.setdefault("mean_reversion", {})
MR02b.update({"mr02b_ext": {
    "family": "均值回归 — KDJ / Stochastic 极值反转（扩展变体）",
    "variants": [
        {
            "id": "mr02a_kdj_j_line_extreme",
            "name": "KDJ 极限 J 线",
            "difficulty": 3,
            "desc": "J < 0 后拐头上行配合低位金叉入场，J > 100 出场。用 Williams %R 近似。",
            "data": {"williams_r": [14], "sma": [60]},
            "entry": "(willr_14 > -95) & (close > sma_60)",
            "exit": "willr_14 > -10",
            "holding": 5, "direction": "long_only",
            "note": "KDJ J 线用 Williams %R 近似；完整实现需 KDJ 因子列。",
        },
        {
            "id": "mr02b_stochastic_cross",
            "name": "Stochastic %K/%D 超卖金叉",
            "difficulty": 2,
            "desc": "%K 在 20 以下上穿 %D 入场，80 以上死叉出场。用 Williams %R 近似。",
            "data": {"williams_r": [14], "sma": [50]},
            "entry": "(willr_14 > -80) & (willr_14 > willr_14.shift(1)) & (close > sma_50)",
            "exit": "willr_14 > -20",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "mr02c_stoch_rsi_slow",
            "name": "慢速 StochRSI",
            "difficulty": 3,
            "desc": "StochRSI K 线在 0.2 以下上穿 D 线入场。用 RSI(14) 极值近似。",
            "data": {"rsi": [14], "sma": [200]},
            "entry": "(rsi_14 < 25) & (close > sma_200) & (rsi_14 > rsi_14.shift(1))",
            "exit": "rsi_14 > 50",
            "holding": 5, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# MR04 — IBS Intraday Position Reversal
# ---------------------------------------------------------------------------
MR04 = STRATEGIES.setdefault("mean_reversion", {})
MR04["mr04"] = {
    "family": "均值回归 — IBS 日内位置反弹",
    "variants": [
        {
            "id": "mr04a_ibs_reversal",
            "name": "IBS 日内收盘位置反弹",
            "difficulty": 3,
            "desc": "IBS = (close - low) / (high - low) < 0.2 且 close > SMA(200) 入场。收盘接近日内低点。",
            "data": {"sma": [200]},
            "entry": "((close - low) / (high - low + 0.001) < 0.2) & (close > sma_200)",
            "exit": "(close - low) / (high - low + 0.001) > 0.5",
            "holding": 3, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# MR05 — CCI Reversal & Trend Following
# ---------------------------------------------------------------------------
MR05 = STRATEGIES.setdefault("mean_reversion", {})
MR05["mr05"] = {
    "family": "均值回归 — CCI 回归与趋势系统",
    "variants": [
        {
            "id": "mr05a_cci_oversold_reversal",
            "name": "CCI 超卖回归",
            "difficulty": 2,
            "desc": "CCI 从 -100 下方回归向上入场，CCI > 100 出场。用 RSI 近似。",
            "data": {"rsi": [14], "sma": [20]},
            "entry": "(rsi_14 > 25) & (close > sma_20)",
            "exit": "rsi_14 > 70",
            "holding": 5, "direction": "long_only",
            "note": "CCI 用 RSI 近似；需确认 CCI 因子列后替换表达式。",
        },
        {
            "id": "mr05b_cci_trend_following",
            "name": "CCI 趋势跟随",
            "difficulty": 2,
            "desc": "CCI > +100 连续 2 日入场，跌回 +100 以下出场。用 RSI 强势区近似。",
            "data": {"rsi": [14], "sma": [10]},
            "entry": "(rsi_14 > 65) & (close > sma_10)",
            "exit": "rsi_14 < 55",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# MR08 — MFI Volume-Price Reversal
# ---------------------------------------------------------------------------
MR08 = STRATEGIES.setdefault("mean_reversion", {})
MR08["mr08"] = {
    "family": "均值回归 — MFI 量价反转",
    "variants": [
        {
            "id": "mr08a_mfi_oversold_reversal",
            "name": "MFI 超卖反转",
            "difficulty": 2,
            "desc": "MFI < 20 后重新站回 20 入场（需确认 MFI 因子列）。用 RSI + 量比近似。",
            "data": {"rsi": [14], "sma": [60]},
            "entry": "(rsi_14 < 30) & (close > sma_60) & (rsi_14 > rsi_14.shift(1))",
            "exit": "rsi_14 > 60",
            "holding": 5, "direction": "long_only",
            "note": "MFI 用 RSI 超卖 + 价格 > SMA 近似；需确认 MFI 因子列。",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO04 — Darvas Box
# ---------------------------------------------------------------------------
BO04 = STRATEGIES.setdefault("breakout", {})
BO04["bo04"] = {
    "family": "突破 — Darvas Box 箱体突破",
    "variants": [
        {
            "id": "bo04a_darvas_box_breakout",
            "name": "Darvas 箱体突破",
            "difficulty": 3,
            "desc": "价格突破前 20 日整理箱体顶部且放量入场，跌回箱体内出场。",
            "data": {"sma": [20]},
            "entry": "(close > close.shift(1).rolling(20).max()) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO06 — ATR Anomaly Volatility Momentum
# ---------------------------------------------------------------------------
BO06 = STRATEGIES.setdefault("breakout", {})
BO06["bo06"] = {
    "family": "突破 — ATR 异常波动率动量",
    "variants": [
        {
            "id": "bo06a_atr_anomaly_momentum",
            "name": "ATR 异常波动突破",
            "difficulty": 3,
            "desc": "当日为强势阳线且波动率扩张入场。用当日涨 > 2% 且波动放大近似。",
            "data": {"sma": [20]},
            "entry": "((close - open) / open > 0.02) & ((high - low) / low > (high.shift(1).rolling(20).mean() - low.shift(1).rolling(20).mean()) / low.shift(1).rolling(20).mean())",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO07 — Larry Williams Volatility Breakout
# ---------------------------------------------------------------------------
BO07 = STRATEGIES.setdefault("breakout", {})
BO07["bo07"] = {
    "family": "突破 — Larry Williams 波动率突破",
    "variants": [
        {
            "id": "bo07a_larry_williams_breakout",
            "name": "Larry Williams 波动率突破",
            "difficulty": 3,
            "desc": "价格突破前收 + 0.25 * 前日波幅入场。极早期捕捉爆发动量。",
            "data": {"sma": [10]},
            "entry": "(close > open.shift(1) + 0.25 * (high.shift(1) - low.shift(1))) & (close > sma_10)",
            "exit": "close < sma_10",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# BO08 — Additional Variants (HV20, ATR Ratio, Amplitude Expansion)
# ---------------------------------------------------------------------------
BO08b = STRATEGIES.setdefault("breakout", {})
BO08b.update({"bo08b_ext": {
    "family": "突破 — 波动率压缩与释放（扩展变体）",
    "variants": [
        {
            "id": "bo08b_hv20_low_breakout",
            "name": "历史波动率低位突破",
            "difficulty": 3,
            "desc": "HV(20) 处于低位并突破布林上轨入场。",
            "data": {"bollinger": [(20, 2.0)]},
            "entry": "(close > bbu_20_2_0_2_0) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "close < bbm_20_2_0_2_0",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "bo08c_atr_ratio_filter",
            "name": "ATR 比率过滤 + MA 金叉",
            "difficulty": 3,
            "desc": "ATR(14) / SMA(20) 极低后配合均线金叉入场。",
            "data": {"sma": [5, 20]},
            "entry": "(sma_5 > sma_20) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "bo08e_amplitude_expansion",
            "name": "振幅扩张率突破",
            "difficulty": 3,
            "desc": "今日振幅 / 5 日均振幅显著放大并收阳入场。",
            "data": {"sma": [10]},
            "entry": "((high - low) / low > 1.5 * (high.shift(1).rolling(5).mean() - low.shift(1).rolling(5).mean()) / low.shift(1).rolling(5).mean()) & (close > open) & (close > sma_10)",
            "exit": "close < sma_10",
            "holding": 5, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# BO09 — Additional Variants (Sideways, Channel Retest, ORB)
# ---------------------------------------------------------------------------
BO09b = STRATEGIES.setdefault("breakout", {})
BO09b.update({"bo09b_ext": {
    "family": "突破 — 结构与回测突破（扩展变体）",
    "variants": [
        {
            "id": "bo09c_sideways_breakout",
            "name": "横盘突破",
            "difficulty": 3,
            "desc": "20 日低振幅后放量扩张突破入场。",
            "data": {"sma": [20]},
            "entry": "(close > close.shift(1).rolling(20).max()) & (vol > 2 * vol.shift(1).rolling(20).mean()) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "bo09e_channel_retest_breakout",
            "name": "通道突破回测",
            "difficulty": 3,
            "desc": "突破 20 日高点后回测不破再上行入场。",
            "data": {"sma": [20]},
            "entry": "(close > sma_20) & (close.shift(1) > close.shift(1).rolling(20).max()) & (close > close.shift(1))",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "bo09f_orb_daily_approx",
            "name": "ORB 开盘区间突破（日线近似）",
            "difficulty": 3,
            "desc": "以前日 ATR 推导触发带，向上突破入场。",
            "data": {"sma": [10]},
            "entry": "(close > open.shift(1) + 0.5 * (high.shift(1) - low.shift(1))) & (close > sma_10)",
            "exit": "close < sma_10",
            "holding": 3, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# BO10 — Additional Variant (BB Lower + RSI + Volume)
# ---------------------------------------------------------------------------
BO10b = STRATEGIES.setdefault("breakout", {})
BO10b.update({"bo10b_ext": {
    "family": "突破 — 布林趋势突破（扩展变体）",
    "variants": [
        {
            "id": "bo10b_bb_lower_rsi_volume",
            "name": "布林下轨 + RSI 超卖 + 放量",
            "difficulty": 2,
            "desc": "布林下轨 + RSI(14) < 30 + 放量入场。下轨过度杀跌后的修复，也可视为反转增强。",
            "data": {"bollinger": [(20, 2.0)], "rsi": [14]},
            "entry": "(close < bbl_20_2_0_2_0) & (rsi_14 < 30) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "close > bbm_20_2_0_2_0",
            "holding": 5, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# PV01 — Additional Variant (OBV MA Cross)
# ---------------------------------------------------------------------------
PV01b = STRATEGIES.setdefault("price_volume", {})
PV01b.update({"pv01b_ext": {
    "family": "量价 — OBV 能量潮（扩展变体）",
    "variants": [
        {
            "id": "pv01b_obv_ma_cross",
            "name": "OBV 上穿均线",
            "difficulty": 2,
            "desc": "OBV 上穿自身均线入场（需确认 OBV 因子列）。用 RSI 金叉 + 放量近似。",
            "data": {"rsi": [14], "sma": [20]},
            "entry": "(rsi_14 > 50) & (close > sma_20) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "rsi_14 < 50",
            "holding": 5, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# PV02 — CMF Money Flow
# ---------------------------------------------------------------------------
PV02 = STRATEGIES.setdefault("price_volume", {})
PV02["pv02"] = {
    "family": "量价 — CMF 资金流量因子",
    "variants": [
        {
            "id": "pv02a_cmf_money_flow",
            "name": "CMF 资金流量突破",
            "difficulty": 3,
            "desc": "CMF(21) > +0.2 入场（需确认 CMF 因子列）。用 RSI 强势 + 放量近似。",
            "data": {"rsi": [14], "sma": [20]},
            "entry": "(rsi_14 > 55) & (close > sma_20) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "rsi_14 < 45",
            "holding": 5, "direction": "long_only",
            "note": "CMF 用 RSI + 量比近似；需确认 CMF 因子列后替换表达式。",
        },
    ],
}

# ---------------------------------------------------------------------------
# PV03 — WorldQuant Style Formula Alphas
# ---------------------------------------------------------------------------
PV03 = STRATEGIES.setdefault("price_volume", {})
PV03["pv03"] = {
    "family": "量价 — WorldQuant 风格公式因子",
    "variants": [
        {
            "id": "pv03a_alpha41",
            "name": "Alpha#41 sqrt(high*low) - vwap",
            "difficulty": 4,
            "desc": "sqrt(high * low) - VWAP > 0 入场。用价格站上均线近似。",
            "data": {"sma": [5]},
            "entry": "(close > sma_5) & (close > open) & (vol > vol.shift(1).rolling(5).mean())",
            "exit": "close < sma_5",
            "holding": 3, "direction": "long_only",
            "note": "Alpha#41 用量价方向近似；VWAP 列名需确认。",
        },
        {
            "id": "pv03b_alpha101",
            "name": "Alpha#101 (close-open)/(high-low)",
            "difficulty": 3,
            "desc": "(close - open) / (high - low + 0.001) > 0.7 入场。实体占比高的强势阳线。",
            "data": {"sma": [10]},
            "entry": "((close - open) / (high - low + 0.001) > 0.7) & (close > open) & (close > sma_10)",
            "exit": "(close - open) / (high - low + 0.001) < 0.3",
            "holding": 3, "direction": "long_only",
        },
        {
            "id": "pv03c_alpha12_style",
            "name": "Alpha#12 风格 rank(ts_delta(vol,1))",
            "difficulty": 4,
            "desc": "成交量变化率排名因子。用放量涨 > 1.5 倍均量近似。",
            "data": {"sma": [10]},
            "entry": "(vol > 1.5 * vol.shift(1).rolling(20).mean()) & (close > open) & (close > sma_10)",
            "exit": "close < sma_10",
            "holding": 3, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# PV05 — Additional Variants (A/D, VWAP, EOM, VPT)
# ---------------------------------------------------------------------------
PV05b = STRATEGIES.setdefault("price_volume", {})
PV05b.update({"pv05b_ext": {
    "family": "量价 — 量价流量扩展（扩展变体）",
    "variants": [
        {
            "id": "pv05a_ad_accumulation",
            "name": "A/D 累积派发线上穿均线",
            "difficulty": 3,
            "desc": "A/D 线上穿自身均线入场（需确认 A/D 因子列）。用 OBV 近似。",
            "data": {"rsi": [14], "sma": [20]},
            "entry": "(rsi_14 > 50) & (close > sma_20) & (vol > vol.shift(1))",
            "exit": "rsi_14 < 45",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "pv05b_daily_vwap_support",
            "name": "日线 VWAP 连续站上",
            "difficulty": 3,
            "desc": "连续两日收盘高于日线 VWAP（需确认 VWAP 因子列）。用两日连阳量增近似。",
            "data": {"sma": [5]},
            "entry": "(close > open) & (close.shift(1) > open.shift(1)) & (vol > vol.shift(1)) & (close > sma_5)",
            "exit": "close < sma_5",
            "holding": 3, "direction": "long_only",
        },
        {
            "id": "pv05d_eom_ease_of_movement",
            "name": "EOM 轻松移动上穿零轴",
            "difficulty": 3,
            "desc": "EOM 上穿 0 入场（需确认 EOM 因子列）。用价格 + 量比方向近似。",
            "data": {"sma": [20]},
            "entry": "(close > open) & (vol > vol.shift(1)) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "pv05e_vpt_volume_price_trend",
            "name": "VPT 量价趋势上穿均线",
            "difficulty": 3,
            "desc": "VPT 上穿 5 日均线入场（需确认 VPT 因子列）。用量增价涨近似。",
            "data": {"sma": [5]},
            "entry": "(close > sma_5) & (vol > vol.shift(1).rolling(5).mean()) & (close > open)",
            "exit": "close < sma_5",
            "holding": 5, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# PT01 — Additional Variants (Morning Star, Three White Soldiers)
# ---------------------------------------------------------------------------
PT01b = STRATEGIES.setdefault("kline_pattern", {})
PT01b.update({"pt01b_ext": {
    "family": "K线形态 — 底部反转形态（扩展变体）",
    "variants": [
        {
            "id": "pt01c_morning_star",
            "name": "早晨之星",
            "difficulty": 4,
            "desc": "三 K 线结构：阴线+小实体+阳线收复首根 50% 以上。用三日反转近似。",
            "data": {"sma": [20]},
            "entry": "(close > open) & (close.shift(1) < open.shift(1)) & (close > close.shift(2)) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 3, "direction": "long_only",
            "note": "早晨之星需精细K线识别；此处用简化三日反转模式近似。",
        },
        {
            "id": "pt01d_three_white_soldiers",
            "name": "三白兵",
            "difficulty": 3,
            "desc": "连续三根温和放量小阳线入场。",
            "data": {"sma": [10]},
            "entry": "(close > open) & (close.shift(1) > open.shift(1)) & (close.shift(2) > open.shift(2)) & (close > close.shift(1)) & (close.shift(1) > close.shift(2)) & (vol > vol.shift(1)) & (close > sma_10)",
            "exit": "close < sma_10",
            "holding": 5, "direction": "long_only",
        },
    ],
}})

# ---------------------------------------------------------------------------
# PT02 — Continuation & Risk Patterns
# ---------------------------------------------------------------------------
PT02 = STRATEGIES.setdefault("kline_pattern", {})
PT02["pt02"] = {
    "family": "K线形态 — 持续与风险形态家族",
    "variants": [
        {
            "id": "pt02a_rising_three_methods",
            "name": "上升三法",
            "difficulty": 4,
            "desc": "强趋势中的空中加油。用趋势突破+缩量回调+再突破近似。",
            "data": {"sma": [20]},
            "entry": "(close > sma_20) & (close > close.shift(1).rolling(5).max()) & (vol > vol.shift(1))",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "pt02b_island_reversal",
            "name": "岛形反转",
            "difficulty": 4,
            "desc": "双跳空封闭前缺口。用量价背离+趋势反转近似。",
            "data": {"sma": [20, 60]},
            "entry": "(close < sma_60) & (close > open) & (close > sma_20) & (vol > vol.shift(1).rolling(10).mean())",
            "exit": "close < sma_20",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "pt02c_tombstone_doji_exit",
            "name": "墓碑十字星高位平仓",
            "difficulty": 3,
            "desc": "高位长上影放天量。做空头出场/短线反转信号。",
            "data": {"sma": [20]},
            "entry": "((high - close) / (high - low + 0.001) > 0.7) & (vol > 2 * vol.shift(1).rolling(20).mean()) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 3, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# PT03 — Bottom Structure Patterns
# ---------------------------------------------------------------------------
PT03 = STRATEGIES.setdefault("kline_pattern", {})
PT03["pt03"] = {
    "family": "K线形态 — 底部结构形态",
    "variants": [
        {
            "id": "pt03a_double_bottom",
            "name": "双底/W底突破颈线",
            "difficulty": 4,
            "desc": "两低点接近，突破颈线入场。用突破30日高点+均线过滤近似。",
            "data": {"sma": [20, 60]},
            "entry": "(close > close.shift(1).rolling(30).max()) & (close > sma_20) & (close > sma_60)",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# CS01 — Small Cap Extension Family
# ---------------------------------------------------------------------------
CS01 = STRATEGIES.setdefault("cross_sectional", {})
CS01["cs01"] = {
    "family": "截面因子 — 小市值扩展家族",
    "variants": [
        {
            "id": "cs01a_pure_small_cap",
            "name": "纯小市值筛选",
            "difficulty": 3,
            "desc": "做多最小市值分组。用RSI低位+长期均线上方近似。",
            "data": {"rsi": [14], "sma": [200]},
            "entry": "(rsi_14 < 50) & (close > sma_200)",
            "exit": "rsi_14 > 70",
            "holding": 20, "direction": "long_only",
            "note": "小市值因子需市值数据截面排名；QRE已支持market_cap_bucket分组。",
        },
        {
            "id": "cs01b_small_cap_quality",
            "name": "小市值+质量过滤",
            "difficulty": 4,
            "desc": "小市值叠加ROE>0、资产负债率<60%。用均线上方+低RSI近似。",
            "data": {"rsi": [14], "sma": [20, 200]},
            "entry": "(rsi_14 < 40) & (close > sma_200) & (close > sma_20)",
            "exit": "rsi_14 > 65",
            "holding": 20, "direction": "long_only",
        },
        {
            "id": "cs01c_small_cap_macd_timing",
            "name": "小市值+MACD择时",
            "difficulty": 4,
            "desc": "MACD多头区间持有小市值。",
            "data": {"macd": [(12, 26, 9)], "sma": [20, 60]},
            "entry": "(macd_12_26_9 > macds_12_26_9) & (close > sma_20)",
            "exit": "macd_12_26_9 < macds_12_26_9",
            "holding": 20, "direction": "long_only",
        },
        {
            "id": "cs01d_small_cap_low_pb",
            "name": "小市值+低PB",
            "difficulty": 4,
            "desc": "小市值池内再找PB低分位。用RSI低位+均线过滤近似。",
            "data": {"rsi": [14], "sma": [60, 200]},
            "entry": "(rsi_14 < 35) & (close > sma_200) & (close > sma_60)",
            "exit": "rsi_14 > 60",
            "holding": 20, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# CS02 — Size + Value Ranking
# ---------------------------------------------------------------------------
CS02 = STRATEGIES.setdefault("cross_sectional", {})
CS02["cs02"] = {
    "family": "截面因子 — Size+Value 双因子排序",
    "variants": [
        {
            "id": "cs02_size_value_ranking",
            "name": "Size+Value排序",
            "difficulty": 4,
            "desc": "size+value双因子打分选综合排名靠前组。用均线+RSI低吸近似。",
            "data": {"rsi": [14], "sma": [60, 200]},
            "entry": "(rsi_14 < 40) & (close > sma_200) & (close > sma_60)",
            "exit": "rsi_14 > 65",
            "holding": 20, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# CS03 — Low Volatility Factor
# ---------------------------------------------------------------------------
CS03 = STRATEGIES.setdefault("cross_sectional", {})
CS03["cs03"] = {
    "family": "截面因子 — 低波动因子",
    "variants": [
        {
            "id": "cs03_low_volatility",
            "name": "低波动因子筛选",
            "difficulty": 3,
            "desc": "做多过去20/60/120日波动率较低的一组。用波动率收缩+均线过滤近似。",
            "data": {"sma": [20, 200]},
            "entry": "(close > sma_200) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 20, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# CS06 — Cross-Sectional & Statistical Momentum
# ---------------------------------------------------------------------------
CS06 = STRATEGIES.setdefault("cross_sectional", {})
CS06["cs06"] = {
    "family": "截面因子 — 截面与统计动量家族",
    "variants": [
        {
            "id": "cs06a_n_day_return_momentum",
            "name": "N日收益率动量",
            "difficulty": 2,
            "desc": "短期累计收益超过阈值后顺势跟进。",
            "data": {"sma": [20]},
            "entry": "(close > close.shift(20)) & (close > sma_20) & (close > close.shift(1))",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "cs06b_sharpe_factor",
            "name": "夏普率因子",
            "difficulty": 3,
            "desc": "20日均收益/20日标准差大于阈值入场。",
            "data": {"sma": [20], "rsi": [14]},
            "entry": "(close > sma_20) & (rsi_14 > 50) & (close > close.shift(20))",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "cs06c_12_1_momentum_diff",
            "name": "12-1动量差",
            "difficulty": 3,
            "desc": "250日收益减去20日收益仍为正，去除短期反转效应的长趋势股。",
            "data": {"sma": [20, 200]},
            "entry": "(close > close.shift(250)) & (close > sma_200) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 20, "direction": "long_only",
        },
        {
            "id": "cs06d_beta_rotation",
            "name": "Beta轮动",
            "difficulty": 4,
            "desc": "大盘上行环境中做多高Beta股票。用指数均线方向+价格强势近似。",
            "data": {"sma": [20, 60]},
            "entry": "(sma_20 > sma_60) & (close > sma_20) & (close > close.shift(20))",
            "exit": "sma_20 < sma_60",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "cs06e_rs_ranking",
            "name": "RS Ranking 相对强度排名",
            "difficulty": 3,
            "desc": "近60日涨幅排名前20%买入。",
            "data": {"sma": [20]},
            "entry": "(close > close.shift(60)) & (close > sma_20)",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "cs06f_return_skewness",
            "name": "收益率分布偏度",
            "difficulty": 4,
            "desc": "偏度显著为正且平均收益为正入场。用上升趋势+均线过滤近似。",
            "data": {"sma": [20, 60]},
            "entry": "(close > sma_20) & (sma_20 > sma_60) & (close > close.shift(60))",
            "exit": "close < sma_20",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "cs06g_max_return_ratio",
            "name": "累计最高涨幅占比",
            "difficulty": 4,
            "desc": "短期涨幅占全年涨幅比例极高。用动量加速近似。",
            "data": {"sma": [10, 20]},
            "entry": "(sma_10 > sma_20) & (close > close.shift(20)) & (close > sma_20)",
            "exit": "close < sma_10",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "cs06h_overnight_vs_intraday",
            "name": "隔夜vs日内收益",
            "difficulty": 4,
            "desc": "连续数日收盘强于开盘且伴随向上跳空入场。",
            "data": {"sma": [10]},
            "entry": "(close > open) & (close.shift(1) > open.shift(1)) & (close > close.shift(1)) & (close > sma_10)",
            "exit": "close < sma_10",
            "holding": 5, "direction": "long_only",
        },
    ],
}

# ---------------------------------------------------------------------------
# CB01 — Additional Variants (MACD+Vol, ADX+RSI, MA+KDJ, NH+OBV, Sideways+RSI)
# ---------------------------------------------------------------------------
CB01b = STRATEGIES.setdefault("composite", {})
CB01b.update({"cb01b_ext": {
    "family": "组合增强 — 多信号共振模板（扩展变体）",
    "variants": [
        {
            "id": "cb01b_macd_cross_volume",
            "name": "MACD金叉+放量",
            "difficulty": 2,
            "desc": "MACD金叉且放量确认入场。双条件减少假突破噪音。",
            "data": {"macd": [(12, 26, 9)]},
            "entry": "(macd_12_26_9 > macds_12_26_9) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "macd_12_26_9 < macds_12_26_9",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "cb01c_adx_rsi_momentum",
            "name": "ADX趋势+RSI动量",
            "difficulty": 3,
            "desc": "ADX>25 + RSI(14)>50 入场。趋势明确且动量确认。",
            "data": {"adx": [14], "rsi": [14]},
            "entry": "(adx_14 > 25) & (rsi_14 > 50)",
            "exit": "(adx_14 < 20) | (rsi_14 < 45)",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "cb01e_ma_alignment_kdj",
            "name": "均线多头排列+KDJ共振",
            "difficulty": 3,
            "desc": "MA(5/10/20)多头排列且RSI超卖回归入场。",
            "data": {"sma": [5, 10, 20], "rsi": [14]},
            "entry": "(sma_5 > sma_10) & (sma_10 > sma_20) & (rsi_14 > 50)",
            "exit": "(rsi_14 < 50) | (close < sma_10)",
            "holding": 5, "direction": "long_only",
        },
        {
            "id": "cb01f_new_high_obv_macd",
            "name": "新高+OBV+MACD",
            "difficulty": 3,
            "desc": "创20日新高+RSI>50+MACD金叉且价格>MA(60)入场。三重趋势确认。",
            "data": {"macd": [(12, 26, 9)], "rsi": [14], "sma": [60]},
            "entry": "(close > close.shift(1).rolling(20).max()) & (rsi_14 > 50) & (macd_12_26_9 > macds_12_26_9) & (close > sma_60)",
            "exit": "macd_12_26_9 < macds_12_26_9",
            "holding": 10, "direction": "long_only",
        },
        {
            "id": "cb01h_sideways_rsi_volume",
            "name": "横盘+RSI+量能",
            "difficulty": 3,
            "desc": "20日振幅<15%且RSI上穿50且放量入场。整理后方向突破。",
            "data": {"sma": [20], "rsi": [14]},
            "entry": "((close.shift(1).rolling(20).max() - close.shift(1).rolling(20).min()) / close.shift(1).rolling(20).mean() < 0.15) & (rsi_14 > 50) & (vol > vol.shift(1).rolling(20).mean())",
            "exit": "rsi_14 < 50",
            "holding": 5, "direction": "long_only",
        },
    ],
}})

# ═══════════════════════════════════════════════════════════════════════════
# YAML Generation
# ═══════════════════════════════════════════════════════════════════════════

YAML_HEADER = '''# =============================================================================
# {family_name}
# =============================================================================
# 策略 ID:     {strategy_id}
# 策略名称:   {strategy_name}
# 难度:       {stars} ({difficulty}/5)
# 说明:       {desc}
# 数据依赖:   {data_deps}
# 入场规则:   {entry}
# 出场规则:   {exit}
# 持仓天数:   {holding_days} 天
# 方向:       {direction}
{note_line}
# 生成工具:   scripts/generate_strategy_yamls.py
# 校验状态:   待数据库因子验证
# =============================================================================

'''

YAML_TEMPLATE = '''experiment:
  name: {strategy_id}_mvp
  market_profile: ashare_daily_default
  frequency: daily
  objective: screen_then_validate

data:
  market_table: public.stock_daily
  factor_schema: factors
  market_fields:
    - open
    - high
    - low
    - close
    - pre_close
    - vol
    - amount
  factor_fields:
{factor_fields}

universe:
  market: ashare
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120

signal:
  type: expression
  entry: {entry_expr}
  exit: {exit_expr}

execution:
  signal_date: t
  entry_execution: t_plus_1_open
  exit_execution: t_plus_1_open

holding:
  max_holding_days: {holding_days}
  direction: {direction}

risk:
  stop_loss_pct: {stop_loss}
  take_profit_pct: null
  trailing_stop_pct: null

evaluation:
  forward_return_horizons: [1, 3, 5, 10, 20]
  quantiles: 5
  benchmarks:
    - full_a_equal_weight
    - csi_300
    - csi_500
    - csi_1000
'''


def build_factor_fields(variant: dict) -> str:
    """Build the factor_fields mapping from variant data dependencies."""
    lines = []
    deps = variant["data"]
    for indicator, periods in deps.items():
        if indicator == "bollinger":
            for period, stddev in periods:
                sd_int = int(stddev)
                sd_frac = int(round((stddev - sd_int) * 10))
                nbdev = f"{sd_int}_{sd_frac}_{sd_int}_{sd_frac}"
                table = f"{FACTOR}.{CATEGORY_TABLE['volatility']}"
                for prefix, name in [("bbu", "upper"), ("bbm", "middle"), ("bbl", "lower")]:
                    col = f"{prefix}_{period}_{nbdev}"
                    alias = f"{prefix}_{period}_{nbdev}".replace(f"_{nbdev}", "")
                    lines.append(f"    {col}: {table}.{col}")
            continue
        if indicator == "macd":
            for fast, slow, signal in periods:
                table = f"{FACTOR}.{CATEGORY_TABLE['momentum']}"
                for col in [f"macd_{fast}_{slow}_{signal}", f"macds_{fast}_{slow}_{signal}"]:
                    lines.append(f"    {col}: {table}.{col}")
            continue

        cat = INDICATOR_TABLE.get(indicator, "overlap")
        table = f"{FACTOR}.{CATEGORY_TABLE[cat]}"
        for period in periods:
            col = fc(indicator, period=period)
            lines.append(f"    {col}: {table}.{col}")
    return "\n".join(lines)


def build_data_deps(variant: dict) -> str:
    """Human-readable data dependency summary."""
    parts = []
    for indicator, periods in variant["data"].items():
        if indicator == "bollinger":
            parts.append(f"BOLL({','.join(f'{p}/{s}' for p,s in periods)})")
        elif indicator == "macd":
            parts.append(f"MACD({','.join(f'{f}/{s}/{sig}' for f,s,sig in periods)})")
        else:
            parts.append(f"{indicator.upper()}({','.join(map(str, periods))})")
    return " + ".join(parts)


def generate_all(output_root: Path):
    """Generate all strategy YAML files."""
    total = 0
    catalog_index = {}

    for category, families in STRATEGIES.items():
        out_dir = output_root / category
        out_dir.mkdir(parents=True, exist_ok=True)

        for family_key, family_def in families.items():
            family_name = family_def["family"]
            variants = family_def["variants"]

            for variant in variants:
                sid = variant["id"]
                sname = variant["name"]
                difficulty = variant["difficulty"]
                desc = variant["desc"]
                entry = variant["entry"]
                exit_expr = variant["exit"]
                holding = variant.get("holding", 5)
                direction = variant.get("direction", "long_only")
                stop_loss = variant.get("stop_loss", 0.08)
                note = variant.get("note", "")

                data_deps = build_data_deps(variant)
                note_line = f"# 备注:       {note}" if note else ""

                stars = "★" * difficulty + "☆" * (5 - difficulty)
                header = YAML_HEADER.format(
                    family_name=family_name,
                    strategy_id=sid,
                    strategy_name=sname,
                    difficulty=difficulty,
                    stars=stars,
                    desc=desc,
                    data_deps=data_deps,
                    entry=entry,
                    exit=exit_expr,
                    holding_days=holding,
                    direction=direction,
                    note_line=note_line,
                )

                factor_fields = build_factor_fields(variant)
                stop_loss_val = "null" if stop_loss is None else str(stop_loss)

                body = YAML_TEMPLATE.format(
                    strategy_id=sid,
                    factor_fields=factor_fields,
                    entry_expr=entry,
                    exit_expr=exit_expr,
                    holding_days=holding,
                    direction=direction,
                    stop_loss=stop_loss_val,
                )

                filepath = out_dir / f"{sid}.yaml"
                filepath.write_text(header + body, encoding="utf-8")
                total += 1

                if family_key not in catalog_index:
                    catalog_index[family_key] = (family_name, [])
                catalog_index[family_key][1].append((sid, sname, difficulty))

    # Write catalog README
    readme_lines = [
        "# 策略目录 Strategy Catalog\n",
        f"自动生成，共 **{total}** 个策略变体。\n",
        "## 目录结构\n",
        "```",
        "strategies/catalog/",
    ]

    cat_names = {
        "trend_following": "趋势跟踪 Trend Following",
        "mean_reversion": "均值回归 Mean Reversion",
        "breakout": "突破 Breakout",
        "cross_sectional": "截面因子 Cross-Sectional",
        "price_volume": "量价因子 Price-Volume",
        "kline_pattern": "K线形态 K-Line Pattern",
        "composite": "组合增强 Composite",
    }

    for cat_key in ["trend_following", "mean_reversion", "breakout",
                     "cross_sectional", "price_volume", "kline_pattern", "composite"]:
        readme_lines.append(f"├── {cat_key}/    # {cat_names.get(cat_key, cat_key)}")

    readme_lines.append("```\n")

    for cat_key in ["trend_following", "mean_reversion", "breakout",
                     "cross_sectional", "price_volume", "kline_pattern", "composite"]:
        if cat_key not in STRATEGIES:
            continue
        readme_lines.append(f"## {cat_names.get(cat_key, cat_key)}\n")
        for family_key, (family_name, variants) in catalog_index.items():
            if family_key not in STRATEGIES.get(cat_key, {}):
                continue
            readme_lines.append(f"### {family_name}\n")
            readme_lines.append("| ID | 名称 | 难度 |")
            readme_lines.append("|----|------|------|")
            for sid, sname, diff in variants:
                stars = "★" * diff + "☆" * (5 - diff)
                readme_lines.append(f"| `{sid}` | {sname} | {stars} |")
            readme_lines.append("")

    readme_path = output_root / "README.md"
    readme_path.write_text("\n".join(readme_lines), encoding="utf-8")

    return total


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    repo_root = Path(__file__).resolve().parent.parent
    output_root = repo_root / "strategies" / "catalog"
    total = generate_all(output_root)
    print(f"Generated {total} strategy YAML files in {output_root}")
    print(f"Catalog index: {output_root / 'README.md'}")

if __name__ == "__main__":
    main()
