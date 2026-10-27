#!/usr/bin/env python3
"""生成因子语义注册表 ``configs/factor_registry.json``（QRE-GUI-FACTOR-REGISTRY-001）。

权威设计：``docs/superpowers/specs/2026-10-25-factor-registry-design.md``。

采用「规则生成 + 特殊条目人工维护」：

- ``FAMILY_RULES``：按列名规律（``ema_<n>``、``macd_<f>_<s>_<g>`` …）生成
  中文名、参数与常用别名，覆盖技术指标族（均线/动量/波动/趋势/量能/统计/K线）；
- ``MANUAL_ENTRIES``：特殊财务、风险、流动性、估值条目与中文习惯名人工补全；
- 两者都没覆盖的列 ``zh`` 记 ``null``（展示回退 canonical，并进入覆盖报告），
  **不伪造中文翻译**。

产物是仓库内版本化 JSON，运行时只读加载（``gui/factor_registry.py``）。
因子库更新后重跑：

    QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data \\
        .venv/bin/python scripts/gen_factor_registry.py

新增列未注册时 ``validate_registry`` 会告警——不要静默放过。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_OUT = ROOT / "configs" / "factor_registry.json"
DEFAULT_SNAPSHOT = ROOT / "configs" / "factor_catalog_llm.json"

REGISTRY_VERSION = "1.0"

# 价格口径优先级与 factor_wizard.PRICE_BASIS_PREFERENCE 保持一致
PRICE_BASIS_PREFERENCE = ("close", "typical_price", "average_price")

PRICE_BASIS_ZH = {
    "close": "收盘价",
    "typical_price": "典型价",
    "average_price": "均价",
}

# ---------------------------------------------------------------------------
# 呈现合同（QRE-FACTOR-DISPLAY-CONTRACT，2026-10-27）
# ---------------------------------------------------------------------------
# 每个 canonical 固化 display 数据成员：chart_type / panel_id / role /
# series_type / axis / precision / color / price_basis / render_order。
# 页面（SaaS 目录 / symbol 静态图 / replay / factor-layout.js）只消费合同；
# 启发式仅旧数据回退。canonical 仍是唯一字段标识，本协议不改名。

# 均线/价格类族 → overlay 主图（与 factor-layout.js OVERLAY_RE 同族）
OVERLAY_MA_FAMILIES = {
    "ema", "sma", "wma", "dema", "tema", "hma", "kama", "alma", "fwma", "pwma",
    "sinwma", "swma", "zl_ema", "zlma", "trima", "jma", "vidya", "rma",
    "midpoint", "midprice", "wcp", "vwap_d", "hl2", "hlc3", "ohlc4",
}
# 轨道/区间类族 → overlay 主图（价格轨道）
OVERLAY_BAND_FAMILIES = {
    "bbl", "bbm", "bbu", "bbb", "dcl", "dcm", "dcu", "kcl", "kcb", "kcu",
    "kcbe", "kcle", "kcue", "accbl", "accbm", "accbu", "psarl", "psars",
    "supert",
}
# MACD/PPO/PVO 三元组：同表同参数同副图（family → (group, 固定 role)）
TRIPLE_FAMILY_MAP = {
    "macd": ("macd", None), "macds": ("macd", "signal"), "macdh": ("macd", "hist"),
    "ppo": ("ppo", "main"), "ppos": ("ppo", "signal"), "ppoh": ("ppo", "hist"),
    "pvo": ("pvo", "main"), "pvos": ("pvo", "signal"), "pvoh": ("pvo", "hist"),
}
TRIPLE_OUTPUT_ROLE = {"dif": "main", "signal": "signal", "hist": "hist"}
# 其他家族同副图（family → (group, role)）
FAMILY_PANEL_MAP = {
    "kdj_k": ("kdj", "k"), "kdj_d": ("kdj", "d"), "kdj_j": ("kdj", "j"),
    "stochk": ("stoch", "k"), "stochd": ("stoch", "d"), "stochh": ("stoch", "hist"),
    "stochrsik": ("stochrsi", "k"), "stochrsid": ("stochrsi", "d"),
    "aroond": ("aroon", "down"), "aroonu": ("aroon", "up"),
    "vtxp": ("vortex", "up"), "vtxm": ("vortex", "down"),
    "tsi": ("tsi", "main"), "tsis": ("tsi", "signal"),
    "rvgi": ("rvgi", "main"), "rvgis": ("rvgi", "signal"),
    "fishert": ("fisher", "main"), "fisherts": ("fisher", "signal"),
}
DISPLAY_ROLES = {"main", "signal", "hist", "k", "d", "j", "up", "down", "line", "band"}
ROLE_ORDER = {"main": 0, "k": 0, "up": 0, "signal": 1, "d": 1, "down": 1, "hist": 2, "j": 2}
OVERLAY_COLOR_CYCLE = ["#E8A33D", "#2A9D8F", "#6750A4"]  # 与 factor-layout.js 一致
TRIPLE_COLORS = {"main": "#6750A4", "signal": "#E8A33D", "hist": "#6750A4"}
MULTI_COLOR_CYCLE = ["#6750A4", "#E8A33D", "#2A9D8F"]   # 与 factor-layout.js 一致
DEFAULT_PANE_COLOR = "#6750A4"


def _params_suffix(params: dict[str, Any]) -> str:
    return "_".join(str(v) for v in params.values()) if params else ""


def _display_precision(table: str) -> int:
    return 4 if "alpha" in table else 2


def _display_for(*, table: str, column: str, family: str | None, output: str | None,
                 params: dict[str, Any], price_basis: str | None,
                 overlay_index: int) -> dict[str, Any]:
    """canonical → display 合同（安全默认 + 显式族规则）。"""
    basis = price_basis or "na"
    precision = _display_precision(table)
    if (family in OVERLAY_MA_FAMILIES or family in OVERLAY_BAND_FAMILIES
            or table.startswith("stock_daily_overlap")):
        role = "band" if family in OVERLAY_BAND_FAMILIES else "line"
        return {
            "chart_type": "overlay", "panel_id": None, "role": role,
            "series_type": "line", "axis": "price", "precision": precision,
            "color": OVERLAY_COLOR_CYCLE[overlay_index % len(OVERLAY_COLOR_CYCLE)],
            "price_basis": price_basis, "render_order": overlay_index,
        }
    if family in TRIPLE_FAMILY_MAP:
        group, fixed_role = TRIPLE_FAMILY_MAP[family]
        role = fixed_role or TRIPLE_OUTPUT_ROLE.get(output or "", "main")
        return {
            "chart_type": "pane",
            "panel_id": f"{group}:{table}:{_params_suffix(params)}:{basis}",
            "role": role,
            "series_type": "bar" if role == "hist" else "line",
            "axis": "value", "precision": precision,
            "color": TRIPLE_COLORS[role], "price_basis": price_basis,
            "render_order": ROLE_ORDER.get(role, 0),
        }
    if family in FAMILY_PANEL_MAP:
        group, role = FAMILY_PANEL_MAP[family]
        order = ROLE_ORDER.get(role, 0)
        return {
            "chart_type": "pane",
            "panel_id": f"{group}:{table}:{_params_suffix(params)}:{basis}",
            "role": role,
            "series_type": "bar" if role == "hist" else "line",
            "axis": "value", "precision": precision,
            "color": MULTI_COLOR_CYCLE[order % len(MULTI_COLOR_CYCLE)],
            "price_basis": price_basis, "render_order": order,
        }
    # 独立副图（RSI/风险/流动性/Alpha/其余全部）：panel_id 含表名列与价格口径
    return {
        "chart_type": "pane",
        "panel_id": f"pane:{table}:{column}:{basis}",
        "role": "line", "series_type": "line", "axis": "value",
        "precision": precision, "color": DEFAULT_PANE_COLOR,
        "price_basis": price_basis, "render_order": 0,
    }

# ---------------------------------------------------------------------------
# 行情字段（不进 factor_fields，由 market_fields 单独识别）
# ---------------------------------------------------------------------------

MARKET_FIELDS: dict[str, dict[str, Any]] = {
    "open": {"zh": "开盘价", "aliases": ["开盘", "今开", "open", "o"]},
    "high": {"zh": "最高价", "aliases": ["最高", "高点", "high", "h"]},
    "low": {"zh": "最低价", "aliases": ["最低", "低点", "low", "l"]},
    "close": {"zh": "收盘价", "aliases": ["收盘", "今收", "close", "c", "closing price"]},
    "pre_close": {"zh": "前收盘价", "aliases": ["前收盘", "昨收", "pre_close", "preclose", "prev close"]},
    "vol": {"zh": "成交量", "aliases": ["成交量", "vol", "volume", "量"]},
    "amount": {"zh": "成交额", "aliases": ["成交额", "amount", "turnover", "额"]},
}

# ---------------------------------------------------------------------------
# 族规则（列名规律 → 中文名 / 参数 / 别名）
# ---------------------------------------------------------------------------

FAMILY_RULES: list[dict[str, Any]] = [
    # ---- 均线 / 重叠 ----
    {"family": "ema", "abbr": "EMA", "zh_base": "指数移动均线",
     "pattern": r"^ema_(?P<period>\d+)$", "param_order": ["period"],
     "family_tokens": ["指数均线"],
     "aliases": ["ema", "指数均线", "指数移动平均", "指数移动均线", "指数平滑移动平均", "expma"],
     "default_params": {"period": 20}, "common_periods": [3, 5, 8, 10, 12, 13, 20, 21, 26, 34, 55, 60, 89, 120, 200, 250]},
    {"family": "sma", "abbr": "SMA", "zh_base": "简单移动均线",
     "pattern": r"^sma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["sma", "简单移动平均", "移动平均线", "均线"],
     "default_params": {"period": 20}, "common_periods": [5, 7, 9, 10, 20, 26, 30, 50, 52, 60, 65, 120, 200]},
    {"family": "wma", "abbr": "WMA", "zh_base": "加权移动均线",
     "pattern": r"^wma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["加权移动平均"], "default_params": {"period": 20}, "common_periods": [5, 10, 20]},
    {"family": "dema", "abbr": "DEMA", "zh_base": "双指数移动均线",
     "pattern": r"^dema_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["双指数移动平均"], "default_params": {"period": 20}, "common_periods": [10, 20, 60]},
    {"family": "tema", "abbr": "TEMA", "zh_base": "三指数移动均线",
     "pattern": r"^tema_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["三指数移动平均"], "default_params": {"period": 20}, "common_periods": [10, 20, 60]},
    {"family": "hma", "abbr": "HMA", "zh_base": "赫尔移动均线",
     "pattern": r"^hma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["船体移动平均", "hull moving average"], "default_params": {"period": 20}, "common_periods": [10, 20]},
    {"family": "rma", "abbr": "RMA", "zh_base": "威尔德移动均线",
     "pattern": r"^rma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["wilder移动平均"], "default_params": {"period": 14}, "common_periods": [10]},
    {"family": "trima", "abbr": "TRIMA", "zh_base": "三角移动均线",
     "pattern": r"^trima_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["三角移动平均"], "default_params": {"period": 20}, "common_periods": [10]},
    {"family": "kama", "abbr": "KAMA", "zh_base": "考夫曼自适应移动均线",
     "pattern": r"^kama_(?P<period>\d+)_(?P<fast>\d+)_(?P<slow>\d+)$",
     "param_order": ["period", "fast", "slow"], "aliases": ["考夫曼自适应移动平均"],
     "default_params": {"period": 10, "fast": 2, "slow": 30}, "common_params": [[10, 2, 30], [20, 2, 30]]},
    {"family": "vidya", "abbr": "VIDYA", "zh_base": "变量指数动态平均",
     "pattern": r"^vidya_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {"period": 20}, "common_periods": [20]},
    {"family": "pwma", "abbr": "PWMA", "zh_base": "帕斯卡加权移动均线",
     "pattern": r"^pwma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {"period": 10}, "common_periods": [10]},
    {"family": "fwma", "abbr": "FWMA", "zh_base": "斐波那契加权移动均线",
     "pattern": r"^fwma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {"period": 10}, "common_periods": [10]},
    {"family": "swma", "abbr": "SWMA", "zh_base": "对称加权移动均线",
     "pattern": r"^swma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {"period": 10}, "common_periods": [10]},
    {"family": "zl_ema", "abbr": "ZLEMA", "zh_base": "零滞后指数移动均线",
     "pattern": r"^zl_ema_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["零滞后ema"], "default_params": {"period": 10}, "common_periods": [10]},
    {"family": "alma", "abbr": "ALMA", "zh_base": "阿尔马斯移动均线", "zh_params": ["period"],
     "pattern": r"^alma_(?P<period>\d+)_(?P<offset>\d+)_(?P<sigma>[\d_]+)$",
     "param_order": ["period", "offset", "sigma"], "aliases": [],
     "default_params": {"period": 9, "offset": 6, "sigma": 0.85}, "common_params": [[9, 6, 0.85]]},
    {"family": "t3", "abbr": "T3", "zh_base": "三重指数移动均线",
     "pattern": r"^t3_(?P<period>\d+)_(?P<vfactor>[\d_]+)$",
     "param_order": ["period", "vfactor"], "aliases": [],
     "default_params": {"period": 10, "vfactor": 0.7}, "common_params": [[10, 0.7]]},
    {"family": "linreg", "abbr": "LINREG", "zh_base": "线性回归值",
     "pattern": r"^linreg_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["线性回归"], "default_params": {"period": 14}, "common_periods": [14]},
    {"family": "midpoint", "abbr": "MIDPOINT", "zh_base": "区间中点价",
     "pattern": r"^midpoint_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {"period": 2}, "common_periods": [2]},
    {"family": "midprice", "abbr": "MIDPRICE", "zh_base": "区间中价",
     "pattern": r"^midprice_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {"period": 2}, "common_periods": [2]},
    {"family": "vwma", "abbr": "VWMA", "zh_base": "成交量加权移动均线",
     "pattern": r"^vwma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["量价均线"], "default_params": {"period": 10}, "common_periods": [10]},
    {"family": "vwap_d", "abbr": "VWAP", "zh_base": "成交量加权平均价",
     "pattern": r"^vwap_d$", "param_order": [], "aliases": ["vwap", "成交量加权均价"],
     "default_params": {}, "common": True},
    {"family": "sinwma", "abbr": "SINWMA", "zh_base": "正弦加权移动均线",
     "pattern": r"^sinwma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {"period": 14}, "common_periods": [14]},
    {"family": "hl2", "abbr": "HL2", "zh_base": "高低价中值",
     "pattern": r"^hl2$", "param_order": [], "aliases": ["(最高+最低)/2"], "default_params": {}, "common": True},
    {"family": "hlc3", "abbr": "HLC3", "zh_base": "典型价",
     "pattern": r"^hlc3$", "param_order": [], "aliases": ["典型价", "(高+低+收)/3"], "default_params": {}, "common": True},
    {"family": "ohlc4", "abbr": "OHLC4", "zh_base": "四价均价",
     "pattern": r"^ohlc4$", "param_order": [], "aliases": ["(开+高+低+收)/4"], "default_params": {}, "common": True},
    {"family": "wcp", "abbr": "WCP", "zh_base": "加权收盘价",
     "pattern": r"^wcp$", "param_order": [], "aliases": ["加权收盘"], "default_params": {}, "common": True},
    {"family": "trix", "abbr": "TRIX", "zh_base": "三重指数平滑振荡指标",
     "pattern": r"^trix_(?P<period>\d+)_(?P<signal>\d+)$",
     "param_order": ["period", "signal"], "aliases": ["trix指标"],
     "default_params": {"period": 30, "signal": 9}, "common_params": [[30, 9]]},
    {"family": "trixs", "abbr": "TRIXS", "zh_base": "TRIX 信号线",
     "pattern": r"^trixs_(?P<period>\d+)_(?P<signal>\d+)$",
     "param_order": ["period", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "hilo", "abbr": "HILO", "zh_base": "高低价通道",
     "pattern": r"^hilo_(?P<high>\d+)_(?P<low>\d+)$", "param_order": ["high", "low"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "hilol", "abbr": "HILOL", "zh_base": "高低价通道下轨",
     "pattern": r"^hilol_(?P<high>\d+)_(?P<low>\d+)$", "param_order": ["high", "low"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "hilos", "abbr": "HILOS", "zh_base": "高低价通道上轨",
     "pattern": r"^hilos_(?P<high>\d+)_(?P<low>\d+)$", "param_order": ["high", "low"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "agj", "abbr": "AGJ", "zh_base": "阿伦·冈茨均线",
     "pattern": r"^agj_(?P<short>\d+)_(?P<long>\d+)_(?P<signal>\d+)$",
     "param_order": ["short", "long", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "agl", "abbr": "AGL", "zh_base": "阿伦·冈茨长线",
     "pattern": r"^agl_(?P<short>\d+)_(?P<long>\d+)_(?P<signal>\d+)$",
     "param_order": ["short", "long", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "agt", "abbr": "AGT", "zh_base": "阿伦·冈茨趋势线",
     "pattern": r"^agt_(?P<short>\d+)_(?P<long>\d+)_(?P<signal>\d+)$",
     "param_order": ["short", "long", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "ics", "abbr": "ICS", "zh_base": "即时趋势线",
     "pattern": r"^ics_26(_[\d_]+)?$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "iks", "abbr": "IKS", "zh_base": "即时趋势线（考夫曼）",
     "pattern": r"^iks_26(_[\d_]+)?$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "isa", "abbr": "ISA", "zh_base": "即时趋势长线",
     "pattern": r"^isa_9(_[\d_]+)?$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "isb", "abbr": "ISB", "zh_base": "即时趋势线（布林）",
     "pattern": r"^isb_26(_[\d_]+)?$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "its", "abbr": "ITS", "zh_base": "即时趋势线（三重）",
     "pattern": r"^its_9(_[\d_]+)?$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "jma", "abbr": "JMA", "zh_base": "Jurik 移动平均",
     "pattern": r"^jma_(?P<period>\d+)_(?P<phase>\d+)_(?P<power>[\d_]+)$",
     "param_order": ["period", "phase", "power"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "pbo", "abbr": "PBO", "zh_base": "价格突破带",
     "pattern": r"^pbo_(?P<band>pb\d)$", "param_order": ["band"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "supert", "abbr": "SUPERT", "zh_base": "超级趋势",
     "pattern": r"^supert_(?P<period>\d+)_(?P<mult>[\d_]+)$", "param_order": ["period", "mult"],
     "aliases": ["超级趋势线"], "default_params": {}, "common": True},
    {"family": "supertl", "abbr": "SUPERTL", "zh_base": "超级趋势下轨",
     "pattern": r"^supertl_(?P<period>\d+)_(?P<mult>[\d_]+)$", "param_order": ["period", "mult"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "supertd", "abbr": "SUPERTD", "zh_base": "超级趋势方向",
     "pattern": r"^supertd_(?P<period>\d+)_(?P<mult>[\d_]+)$", "param_order": ["period", "mult"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "superts", "abbr": "SUPERTS", "zh_base": "超级趋势信号",
     "pattern": r"^superts_(?P<period>\d+)_(?P<mult>[\d_]+)$",
     "param_order": ["period", "mult"], "aliases": [], "default_params": {}, "common": True},

    # ---- 动量 ----
    {"family": "rsi", "abbr": "RSI", "zh_base": "相对强弱指标",
     "pattern": r"^rsi_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["rsi", "相对强弱", "相对强弱指数", "rsi指标"],
     "default_params": {"period": 14}, "common_periods": [2, 6, 7, 9, 12, 14, 21, 24, 28]},
    {"family": "macd", "abbr": "MACD", "zh_base": "MACD", "output": "dif", "default_output": "dif",
     "pattern": r"^macd_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"],
     "aliases": ["macd", "macd指标", "macd快线", "dif", "快线", "dif线", "macd dif"],
     "default_params": {"fast": 12, "slow": 26, "signal": 9},
     "common_params": [[12, 26, 9], [6, 13, 5], [15, 35, 10], [24, 52, 18]]},
    {"family": "macd", "abbr": "MACDS", "zh_base": "MACD 信号线", "output": "signal",
     "pattern": r"^macds_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"],
     "aliases": ["dea", "dea线", "信号线", "慢线", "macd信号线", "macd dea", "macd_signal", "macd signal"],
     "default_params": {"fast": 12, "slow": 26, "signal": 9},
     "common_params": [[12, 26, 9], [6, 13, 5], [15, 35, 10], [24, 52, 18]]},
    {"family": "macd", "abbr": "MACDH", "zh_base": "MACD 柱", "output": "hist",
     "pattern": r"^macdh_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"],
     "aliases": ["柱", "macd柱", "柱状线", "柱状图", "hist", "macd_hist", "macd histogram"],
     "default_params": {"fast": 12, "slow": 26, "signal": 9},
     "common_params": [[12, 26, 9], [6, 13, 5], [15, 35, 10], [24, 52, 18]]},
    {"family": "macd_cn", "abbr": "MACD_CN", "zh_base": "MACD（中国口径）",
     "pattern": r"^macd_cn_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "cci", "abbr": "CCI", "zh_base": "顺势指标",
     "pattern": r"^cci_(?P<period>\d+)_(?P<c>[\d_]+)$", "param_order": ["period", "c"],
     "aliases": ["commodity channel index"], "default_params": {"period": 14, "c": 0.015},
     "common_params": [[14, 0.015], [20, 0.015]]},
    {"family": "willr", "abbr": "WR", "zh_base": "威廉指标",
     "pattern": r"^willr_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["wr", "威廉超买超卖"], "default_params": {"period": 14}, "common_periods": [14]},
    {"family": "mom", "abbr": "MOM", "zh_base": "动量",
     "pattern": r"^mom_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["momentum"], "default_params": {"period": 10}, "common_periods": [10]},
    {"family": "roc", "abbr": "ROC", "zh_base": "变动率",
     "pattern": r"^roc_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["rate of change"], "default_params": {"period": 10}, "common_periods": [10]},
    {"family": "cmo", "abbr": "CMO", "zh_base": "钱德动量摆动指标",
     "pattern": r"^cmo_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["chande momentum"], "default_params": {"period": 14}, "common_periods": [14]},
    {"family": "ao", "abbr": "AO", "zh_base": "动量震荡指标",
     "pattern": r"^ao_(?P<fast>\d+)_(?P<slow>\d+)$", "param_order": ["fast", "slow"],
     "aliases": ["awesome oscillator"], "default_params": {"fast": 5, "slow": 34},
     "common_params": [[5, 34]]},
    {"family": "apo", "abbr": "APO", "zh_base": "绝对价格振荡指标",
     "pattern": r"^apo_(?P<fast>\d+)_(?P<slow>\d+)$", "param_order": ["fast", "slow"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "ppo", "abbr": "PPO", "zh_base": "价格振荡百分比",
     "pattern": r"^ppo_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "ppos", "abbr": "PPOS", "zh_base": "PPO 信号线",
     "pattern": r"^ppos_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "ppoh", "abbr": "PPOH", "zh_base": "PPO 柱",
     "pattern": r"^ppoh_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "tsi", "abbr": "TSI", "zh_base": "真实强度指数",
     "pattern": r"^tsi_(?P<long>\d+)_(?P<short>\d+)_(?P<signal>\d+)$",
     "param_order": ["long", "short", "signal"], "aliases": ["true strength index"],
     "default_params": {}, "common": True},
    {"family": "tsis", "abbr": "TSIS", "zh_base": "TSI 信号线",
     "pattern": r"^tsis_(?P<long>\d+)_(?P<short>\d+)_(?P<signal>\d+)$",
     "param_order": ["long", "short", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "uo", "abbr": "UO", "zh_base": "终极振荡指标",
     "pattern": r"^uo_(?P<fast>\d+)_(?P<medium>\d+)_(?P<slow>\d+)$",
     "param_order": ["fast", "medium", "slow"], "aliases": ["ultimate oscillator"],
     "default_params": {}, "common": True},
    {"family": "rsx", "abbr": "RSX", "zh_base": "RSI 平滑值",
     "pattern": r"^rsx_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["rsi平滑"], "default_params": {"period": 14}, "common_periods": [14]},
    {"family": "rvgi", "abbr": "RVGI", "zh_base": "相对活力指数",
     "pattern": r"^rvgi_(?P<period>\d+)_(?P<signal>\d+)$", "param_order": ["period", "signal"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "rvgis", "abbr": "RVGIS", "zh_base": "RVGI 信号线",
     "pattern": r"^rvgis_(?P<period>\d+)_(?P<signal>\d+)$", "param_order": ["period", "signal"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "smi", "abbr": "SMI", "zh_base": "随机动量指数",
     "pattern": r"^smi_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)_(?P<median>[\d_]+)$",
     "param_order": ["fast", "slow", "signal", "median"], "aliases": ["stochastic momentum"],
     "default_params": {}, "common": True},
    {"family": "smis", "abbr": "SMIS", "zh_base": "SMI 信号线",
     "pattern": r"^smis_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)_(?P<median>[\d_]+)$",
     "param_order": ["fast", "slow", "signal", "median"], "aliases": [], "default_params": {}, "common": True},
    {"family": "smio", "abbr": "SMIO", "zh_base": "SMI 振荡值",
     "pattern": r"^smio_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)_(?P<median>[\d_]+)$",
     "param_order": ["fast", "slow", "signal", "median"], "aliases": [], "default_params": {}, "common": True},
    {"family": "stochk", "abbr": "STOCHK", "zh_base": "随机指标 K 值",
     "pattern": r"^stochk_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "stochd", "abbr": "STOCHD", "zh_base": "随机指标 D 值",
     "pattern": r"^stochd_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "stochh", "abbr": "STOCHH", "zh_base": "随机指标 H 值",
     "pattern": r"^stochh_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "stochrsik", "abbr": "STOCHRSIK", "zh_base": "StochRSI K 值",
     "pattern": r"^stochrsik_(?P<rsi>\d+)_(?P<stoch>\d+)_(?P<fast>\d+)_(?P<slow>\d+)$",
     "param_order": ["rsi", "stoch", "fast", "slow"], "aliases": [], "default_params": {}, "common": True},
    {"family": "stochrsid", "abbr": "STOCHRSID", "zh_base": "StochRSI D 值",
     "pattern": r"^stochrsid_(?P<rsi>\d+)_(?P<stoch>\d+)_(?P<fast>\d+)_(?P<slow>\d+)$",
     "param_order": ["rsi", "stoch", "fast", "slow"], "aliases": [], "default_params": {}, "common": True},
    {"family": "kdj_k", "abbr": "KDJ_K", "zh_base": "KDJ 指标 K 值",
     "pattern": r"^k_(?P<fast>\d+)_(?P<slow>\d+)$", "param_order": ["fast", "slow"],
     "aliases": ["kdj的k值", "k值"], "default_params": {"fast": 9, "slow": 3},
     "common_params": [[9, 3]]},
    {"family": "kdj_d", "abbr": "KDJ_D", "zh_base": "KDJ 指标 D 值",
     "pattern": r"^d_(?P<fast>\d+)_(?P<slow>\d+)$", "param_order": ["fast", "slow"],
     "aliases": ["kdj的d值", "d值"], "default_params": {"fast": 9, "slow": 3},
     "common_params": [[9, 3]]},
    {"family": "kdj_j", "abbr": "KDJ_J", "zh_base": "KDJ 指标 J 值",
     "pattern": r"^j_(?P<fast>\d+)_(?P<slow>\d+)$", "param_order": ["fast", "slow"],
     "aliases": ["kdj的j值", "j值"], "default_params": {"fast": 9, "slow": 3},
     "common_params": [[9, 3]]},
    {"family": "qqe", "abbr": "QQE", "zh_base": "QQE 指标",
     "pattern": r"^qqe_(?P<rsi>\d+)_(?P<sf>\d+)_(?P<wilders>[\d_]+)$",
     "param_order": ["rsi", "sf", "wilders"], "aliases": [], "default_params": {}, "common": True},
    {"family": "qqe_rsima", "abbr": "QQE_RSIMA", "zh_base": "QQE 参考均线",
     "pattern": r"^qqe_(?P<rsi>\d+)_(?P<sf>\d+)_(?P<wilders>[\d_]+)_rsima$",
     "param_order": ["rsi", "sf", "wilders"], "aliases": [], "default_params": {}, "common": True},
    {"family": "qqel", "abbr": "QQEL", "zh_base": "QQE 线",
     "pattern": r"^qqel_(?P<rsi>\d+)_(?P<sf>\d+)_(?P<wilders>[\d_]+)$",
     "param_order": ["rsi", "sf", "wilders"], "aliases": [], "default_params": {}, "common": True},
    {"family": "qqes", "abbr": "QQES", "zh_base": "QQE 信号线",
     "pattern": r"^qqes_(?P<rsi>\d+)_(?P<sf>\d+)_(?P<wilders>[\d_]+)$",
     "param_order": ["rsi", "sf", "wilders"], "aliases": [], "default_params": {}, "common": True},
    {"family": "stc", "abbr": "STC", "zh_base": "Schaff 趋势循环", "zh_params": ["fast"],
     "pattern": r"^stc_(?P<fast>\d+)_(?P<slow>\d+)_(?P<cycle>[\d_]+)$",
     "param_order": ["fast", "slow", "cycle"], "aliases": [], "default_params": {}, "common": True},
    {"family": "stcmacd", "abbr": "STCMACD", "zh_base": "Schaff 趋势循环（MACD）", "zh_params": ["fast"],
     "pattern": r"^stcmacd_(?P<fast>\d+)_(?P<slow>\d+)_(?P<cycle>[\d_]+)$",
     "param_order": ["fast", "slow", "cycle"], "aliases": [], "default_params": {}, "common": True},
    {"family": "stcstoch", "abbr": "STCSTOCH", "zh_base": "Schaff 趋势循环（Stoch）", "zh_params": ["fast"],
     "pattern": r"^stcstoch_(?P<fast>\d+)_(?P<slow>\d+)_(?P<cycle>[\d_]+)$",
     "param_order": ["fast", "slow", "cycle"], "aliases": [], "default_params": {}, "common": True},
    {"family": "sqz", "abbr": "SQZ", "zh_base": "挤压动量指标", "zh_params": ["period"],
     "pattern": r"^sqz_(?P<period>\d+)_(?P<mult>[\d_]+)_(?P<len>[\d_]+)$",
     "param_order": ["period", "mult", "len"], "aliases": ["squeeze momentum"],
     "default_params": {}, "common": True},
    {"family": "sqz_on", "abbr": "SQZ_ON", "zh_base": "挤压开启信号",
     "pattern": r"^sqz_on$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "sqz_off", "abbr": "SQZ_OFF", "zh_base": "挤压释放信号",
     "pattern": r"^sqz_off$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "sqz_no", "abbr": "SQZ_NO", "zh_base": "无挤压信号",
     "pattern": r"^sqz_no$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "fishert", "abbr": "FISHERT", "zh_base": "费舍尔变换",
     "pattern": r"^fishert_(?P<period>\d+)_(?P<signal>\d+)$", "param_order": ["period", "signal"],
     "aliases": ["fisher transform"], "default_params": {}, "common": True},
    {"family": "fisherts", "abbr": "FISHERTS", "zh_base": "费舍尔变换信号线",
     "pattern": r"^fisherts_(?P<period>\d+)_(?P<signal>\d+)$", "param_order": ["period", "signal"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "bias", "abbr": "BIAS", "zh_base": "乖离率",
     "pattern": r"^bias_sma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["乖离", "bias"], "default_params": {"period": 20}, "common_periods": [20, 26]},
    {"family": "psl", "abbr": "PSL", "zh_base": "心理线",
     "pattern": r"^psl_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["psychological line"], "default_params": {"period": 12}, "common_periods": [12]},
    {"family": "pgo", "abbr": "PGO", "zh_base": "PGO 振荡指标",
     "pattern": r"^pgo_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["pretty good oscillator"], "default_params": {}, "common": True},
    {"family": "cti", "abbr": "CTI", "zh_base": "相关性趋势指标",
     "pattern": r"^cti_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["correlation trend indicator"], "default_params": {"period": 12}, "common_periods": [12]},
    {"family": "er", "abbr": "ER", "zh_base": "效率比",
     "pattern": r"^er_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["efficiency ratio"], "default_params": {"period": 10}, "common_periods": [10]},
    {"family": "inertia", "abbr": "INERTIA", "zh_base": "趋势惯性",
     "pattern": r"^inertia_(?P<period>\d+)_(?P<rvi>\d+)$", "param_order": ["period", "rvi"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "bop", "abbr": "BOP", "zh_base": "均势指标",
     "pattern": r"^bop$", "param_order": [], "aliases": ["balance of power"],
     "default_params": {}, "common": True},
    {"family": "br", "abbr": "BR", "zh_base": "情绪指标 BR",
     "pattern": r"^br_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["意愿指标"], "default_params": {"period": 26}, "common_periods": [26]},
    {"family": "ar", "abbr": "AR", "zh_base": "人气指标 AR",
     "pattern": r"^ar_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["人气指标"], "default_params": {"period": 26}, "common_periods": [26]},
    {"family": "bullp", "abbr": "BULLP", "zh_base": "牛市力量",
     "pattern": r"^bullp_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "bearp", "abbr": "BEARP", "zh_base": "熊市力量",
     "pattern": r"^bearp_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "dmn", "abbr": "DMN", "zh_base": "下降动向值",
     "pattern": r"^dmn_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["-di"], "default_params": {}, "common": True},
    {"family": "dmp", "abbr": "DMP", "zh_base": "上升动向值",
     "pattern": r"^dmp_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["+di"], "default_params": {}, "common": True},
    {"family": "copc", "abbr": "COPC", "zh_base": "COPC 振荡指标",
     "pattern": r"^copc_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "cfo", "abbr": "CFO", "zh_base": "蔡金资金流",
     "pattern": r"^cfo_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["chaikin money flow"], "default_params": {}, "common": True},
    {"family": "cg", "abbr": "CG", "zh_base": "重心线",
     "pattern": r"^cg_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["center of gravity"], "default_params": {"period": 10}, "common_periods": [10]},
    {"family": "kst", "abbr": "KST", "zh_base": "确然指标",
     "pattern": r"^kst_(?P<roc1>\d+)_(?P<roc2>\d+)_(?P<roc3>\d+)_(?P<roc4>\d+)_(?P<s1>\d+)_(?P<s2>\d+)_(?P<s3>\d+)_(?P<s4>\d+)$",
     "param_order": ["roc1", "roc2", "roc3", "roc4", "s1", "s2", "s3", "s4"],
     "aliases": ["know sure thing"], "default_params": {}, "common": True},
    {"family": "ksts", "abbr": "KSTS", "zh_base": "KST 信号线",
     "pattern": r"^ksts_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "days_down_up", "abbr": "DAYS_DOWN_UP", "zh_base": "连续下跌天数",
     "pattern": r"^days_down_up$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "price_dist", "abbr": "PRICE_DIST", "zh_base": "价格距离",
     "pattern": r"^price_dist$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "price_position_ir", "abbr": "PRICE_POSITION_IR", "zh_base": "价格位置（信息比）",
     "pattern": r"^price_position_ir_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "rsrs", "abbr": "RSRS", "zh_base": "阻力支撑相对强度",
     "pattern": r"^rsrs_(?P<high>\d+)_(?P<low>\d+)$", "param_order": ["high", "low"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "small_cap_reversal", "abbr": "SMALL_CAP_REVERSAL", "zh_base": "小市值反转",
     "pattern": r"^small_cap_reversal_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},

    # ---- 波动率 ----
    {"family": "atr", "abbr": "ATR", "zh_base": "真实波幅",
     "pattern": r"^atr_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["average true range"], "default_params": {"period": 14}, "common_periods": [10, 14, 20]},
    {"family": "atrr", "abbr": "ATRR", "zh_base": "真实波幅百分比",
     "pattern": r"^atrr_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["atr%", "真实波幅率"], "default_params": {"period": 14}, "common_periods": [10, 14, 20]},
    {"family": "natr", "abbr": "NATR", "zh_base": "归一化真实波幅",
     "pattern": r"^natr_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {"period": 14}, "common_periods": [14]},
    {"family": "bbu", "abbr": "BBU", "zh_base": "布林带上轨", "zh_params": ["period"],
     "pattern": r"^bbu_(?P<period>\d+)_(?P<std>\d+)_(?P<nbdevup>\d+)_(?P<nbdevdn>[\d_]+)$",
     "param_order": ["period", "std", "nbdevup", "nbdevdn"],
     "aliases": ["布林上轨", "布林带上轨", "bollinger upper"],
     "default_params": {"period": 20, "std": 2, "nbdevup": 0, "nbdevdn": 2.0},
     "common_params": [[20, 2, 0, 2.0], [5, 2, 0, 2.0]]},
    {"family": "bbm", "abbr": "BBM", "zh_base": "布林带中轨", "zh_params": ["period"],
     "pattern": r"^bbm_(?P<period>\d+)_(?P<std>\d+)_(?P<nbdevup>\d+)_(?P<nbdevdn>[\d_]+)$",
     "param_order": ["period", "std", "nbdevup", "nbdevdn"],
     "aliases": ["布林中轨", "布林带中轨", "bollinger middle"],
     "default_params": {"period": 20, "std": 2, "nbdevup": 0, "nbdevdn": 2.0},
     "common_params": [[20, 2, 0, 2.0], [5, 2, 0, 2.0]]},
    {"family": "bbl", "abbr": "BBL", "zh_base": "布林带下轨", "zh_params": ["period"],
     "pattern": r"^bbl_(?P<period>\d+)_(?P<std>\d+)_(?P<nbdevup>\d+)_(?P<nbdevdn>[\d_]+)$",
     "param_order": ["period", "std", "nbdevup", "nbdevdn"],
     "aliases": ["布林下轨", "布林带下轨", "bollinger lower"],
     "default_params": {"period": 20, "std": 2, "nbdevup": 0, "nbdevdn": 2.0},
     "common_params": [[20, 2, 0, 2.0], [5, 2, 0, 2.0]]},
    {"family": "bbb", "abbr": "BBB", "zh_base": "布林带宽度（基础）", "zh_params": ["period"],
     "pattern": r"^bbb_(?P<period>\d+)_(?P<std>\d+)_(?P<nbdevup>\d+)_(?P<nbdevdn>[\d_]+)$",
     "param_order": ["period", "std", "nbdevup", "nbdevdn"],
     "aliases": ["布林带宽度"], "default_params": {}, "common": True},
    {"family": "bbp", "abbr": "BBP", "zh_base": "布林带百分比", "zh_params": ["period"],
     "pattern": r"^bbp_(?P<period>\d+)_(?P<std>\d+)_(?P<nbdevup>\d+)_(?P<nbdevdn>[\d_]+)$",
     "param_order": ["period", "std", "nbdevup", "nbdevdn"],
     "aliases": ["%b"], "default_params": {}, "common": True},
    {"family": "bb_width", "abbr": "BB_WIDTH", "zh_base": "布林带宽度", "zh_params": ["period"],
     "pattern": r"^bb_width_(?P<period>\d+)_(?P<std>\d+)_(?P<nbdevup>\d+)$",
     "param_order": ["period", "std", "nbdevup"],
     "aliases": ["布林宽度"], "default_params": {}, "common": True},
    {"family": "accbu", "abbr": "ACCBU", "zh_base": "加速布林带上轨",
     "pattern": r"^accbu_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "accbm", "abbr": "ACCBM", "zh_base": "加速布林带中轨",
     "pattern": r"^accbm_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "accbl", "abbr": "ACCBL", "zh_base": "加速布林带下轨",
     "pattern": r"^accbl_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "kcu", "abbr": "KCU", "zh_base": "肯特纳通道上轨",
     "pattern": r"^kcu_(?P<period>\d+)_(?P<mult>[\d_]+)_(?P<atr>[\d_]+)$",
     "param_order": ["period", "mult", "atr"], "aliases": ["肯特纳上轨"], "default_params": {}, "common": True},
    {"family": "kcb", "abbr": "KCB", "zh_base": "肯特纳通道中轨",
     "pattern": r"^kcb_(?P<period>\d+)_(?P<mult>[\d_]+)_(?P<atr>[\d_]+)$",
     "param_order": ["period", "mult", "atr"], "aliases": ["肯特纳中轨"], "default_params": {}, "common": True},
    {"family": "kcl", "abbr": "KCL", "zh_base": "肯特纳通道下轨",
     "pattern": r"^kcl_(?P<period>\d+)_(?P<mult>[\d_]+)_(?P<atr>[\d_]+)$",
     "param_order": ["period", "mult", "atr"], "aliases": ["肯特纳下轨"], "default_params": {}, "common": True},
    {"family": "kcbe", "abbr": "KCBE", "zh_base": "肯特纳通道外轨",
     "pattern": r"^kcbe_(?P<period>\d+)_(?P<mult>[\d_]+)$", "param_order": ["period", "mult"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "kcue", "abbr": "KCUE", "zh_base": "肯特纳通道上外轨",
     "pattern": r"^kcue_(?P<period>\d+)_(?P<mult>[\d_]+)$", "param_order": ["period", "mult"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "kcle", "abbr": "KCLE", "zh_base": "肯特纳通道下外轨",
     "pattern": r"^kcle_(?P<period>\d+)_(?P<mult>[\d_]+)$", "param_order": ["period", "mult"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "dcu", "abbr": "DCU", "zh_base": "唐奇安通道上轨",
     "pattern": r"^dcu_(?P<upper>\d+)_(?P<lower>\d+)$", "param_order": ["upper", "lower"],
     "aliases": ["唐奇安上轨", "donchian upper"], "default_params": {}, "common": True},
    {"family": "dcm", "abbr": "DCM", "zh_base": "唐奇安通道中轨",
     "pattern": r"^dcm_(?P<upper>\d+)_(?P<lower>\d+)$", "param_order": ["upper", "lower"],
     "aliases": ["唐奇安中轨", "donchian middle"], "default_params": {}, "common": True},
    {"family": "dcl", "abbr": "DCL", "zh_base": "唐奇安通道下轨",
     "pattern": r"^dcl_(?P<upper>\d+)_(?P<lower>\d+)$", "param_order": ["upper", "lower"],
     "aliases": ["唐奇安下轨", "donchian lower"], "default_params": {}, "common": True},
    {"family": "hhv", "abbr": "HHV", "zh_base": "区间最高价",
     "pattern": r"^hhv_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["最高值", "n日最高"], "default_params": {}, "common": True},
    {"family": "llv", "abbr": "LLV", "zh_base": "区间最低价",
     "pattern": r"^llv_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["最低值", "n日最低"], "default_params": {}, "common": True},
    {"family": "hv", "abbr": "HV", "zh_base": "历史波动率",
     "pattern": r"^hv_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["historical volatility"], "default_params": {}, "common": True},
    {"family": "massi", "abbr": "MASSI", "zh_base": "马萨伊指数",
     "pattern": r"^massi_(?P<fast>\d+)_(?P<slow>\d+)$", "param_order": ["fast", "slow"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "ui", "abbr": "UI", "zh_base": "溃疡指数",
     "pattern": r"^ui_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["ulcer index"], "default_params": {}, "common": True},
    {"family": "rvi", "abbr": "RVI", "zh_base": "相对波动率指数",
     "pattern": r"^rvi_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["relative volatility index"], "default_params": {}, "common": True},
    {"family": "amplitude", "abbr": "AMPLITUDE", "zh_base": "振幅",
     "pattern": r"^amplitude_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["当日振幅"], "default_params": {}, "common": True},
    {"family": "amplitude_expand", "abbr": "AMPLITUDE_EXPAND", "zh_base": "振幅扩张",
     "pattern": r"^amplitude_expand_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "amplitude_sma", "abbr": "AMPLITUDE_SMA", "zh_base": "振幅均线",
     "pattern": r"^amplitude_sma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "pdist", "abbr": "PDIST", "zh_base": "价格偏离度",
     "pattern": r"^pdist$", "param_order": [], "aliases": [], "default_params": {}, "common": True},

    # ---- 趋势 ----
    {"family": "adx", "abbr": "ADX", "zh_base": "平均趋向指数",
     "pattern": r"^adx_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["平均趋向指标", "adx指标"], "default_params": {"period": 14}, "common_periods": [14]},
    {"family": "adxr", "abbr": "ADXR", "zh_base": "平均趋向指数评估",
     "pattern": r"^adxr_(?P<period>\d+)_(?P<signal>\d+)$", "param_order": ["period", "signal"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "aroond", "abbr": "AROOND", "zh_base": "阿隆指标下行",
     "pattern": r"^aroond_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["aroon down"], "default_params": {"period": 14}, "common_periods": [14, 25]},
    {"family": "aroonu", "abbr": "AROONU", "zh_base": "阿隆指标上行",
     "pattern": r"^aroonu_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["aroon up"], "default_params": {"period": 14}, "common_periods": [14, 25]},
    {"family": "aroonosc", "abbr": "AROONOSC", "zh_base": "阿隆振荡",
     "pattern": r"^aroonosc_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["aroon oscillator"], "default_params": {"period": 14}, "common_periods": [14, 25]},
    {"family": "dpo", "abbr": "DPO", "zh_base": "区间震荡线",
     "pattern": r"^dpo_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["detrended price oscillator"], "default_params": {}, "common": True},
    {"family": "ht_tl", "abbr": "HT_TL", "zh_base": "希尔伯特瞬时趋势",
     "pattern": r"^ht_tl$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "lr", "abbr": "LR", "zh_base": "线性回归斜率",
     "pattern": r"^lr_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["linear regression"], "default_params": {}, "common": True},
    {"family": "ldecay", "abbr": "LDECAY", "zh_base": "线性衰减",
     "pattern": r"^ldecay_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "dec", "abbr": "DEC", "zh_base": "递减权重",
     "pattern": r"^dec_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "inc", "abbr": "INC", "zh_base": "递增权重",
     "pattern": r"^inc_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "qs", "abbr": "QS", "zh_base": "Qstick 指标",
     "pattern": r"^qs_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "ravi", "abbr": "RAVI", "zh_base": "RAVI 指标",
     "pattern": r"^ravi_(?P<fast>\d+)_(?P<slow>\d+)$", "param_order": ["fast", "slow"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "vhf", "abbr": "VHF", "zh_base": "垂直水平过滤",
     "pattern": r"^vhf_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["vertical horizontal filter"], "default_params": {}, "common": True},
    {"family": "ttm_trnd", "abbr": "TTM_TRND", "zh_base": "TTM 趋势",
     "pattern": r"^ttm_trnd_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "trendflex", "abbr": "TRENDFLEX", "zh_base": "趋势弹性",
     "pattern": r"^trendflex_(?P<period>\d+)_(?P<signal>\d+)_(?P<threshold>[\d_]+)$",
     "param_order": ["period", "signal", "threshold"], "aliases": [], "default_params": {}, "common": True},
    {"family": "chop", "abbr": "CHOP", "zh_base": "波动指数",
     "pattern": r"^chop_(?P<period>\d+)_(?P<low>\d+)_(?P<high>\d+)_(?P<mult>[\d_]+)$",
     "param_order": ["period", "low", "high", "mult"],
     "aliases": ["choppiness index"], "default_params": {}, "common": True},
    {"family": "psar", "abbr": "PSAR", "zh_base": "抛物线转向", "zh_params": ["acc"],
     "pattern": r"^psar(?P<suffix>[a-z]{1,2})_(?P<acc>\d+(?:_\d+)?)_(?P<max>\d+(?:_\d+)?)$",
     "param_order": ["acc", "max"], "aliases": ["sar", "抛物线指标"], "default_params": {}, "common": True},
    {"family": "zigzag", "abbr": "ZIGZAG", "zh_base": "ZigZag 指标",
     "pattern": r"^zigzag(?P<suffix>[a-z])_(?P<dev>[\d%_]+)_(?P<depth>\d+)$",
     "param_order": ["dev", "depth"], "aliases": ["之字转向"], "default_params": {}, "common": True},
    {"family": "ma_adhesion", "abbr": "MA_ADHESION", "zh_base": "均线粘合度",
     "pattern": r"^ma_adhesion_[\d_]+$", "param_order": [], "aliases": ["均线粘合"], "default_params": {}, "common": True},
    {"family": "sma_slope", "abbr": "SMA_SLOPE", "zh_base": "均线斜率",
     "pattern": r"^sma_slope_(?P<period>\d+)_(?P<lag>\d+)$", "param_order": ["period", "lag"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "ckspl", "abbr": "CKSPL", "zh_base": "却斯克通道下轨",
     "pattern": r"^ckspl_(?P<period>\d+)_(?P<fast>\d+)_(?P<slow>\d+)$",
     "param_order": ["period", "fast", "slow"], "aliases": [], "default_params": {}, "common": True},
    {"family": "cksps", "abbr": "CKSPS", "zh_base": "却斯克通道上轨",
     "pattern": r"^cksps_(?P<period>\d+)_(?P<fast>\d+)_(?P<slow>\d+)$",
     "param_order": ["period", "fast", "slow"], "aliases": [], "default_params": {}, "common": True},
    {"family": "rwih", "abbr": "RWIH", "zh_base": "随机行走指标高点",
     "pattern": r"^rwih_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "rwil", "abbr": "RWIL", "zh_base": "随机行走指标低点",
     "pattern": r"^rwil_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "amate_lr", "abbr": "AMATE_LR", "zh_base": "AMATE 长线",
     "pattern": r"^amate_lr_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "amate_sr", "abbr": "AMATE_SR", "zh_base": "AMATE 短线",
     "pattern": r"^amate_sr_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "vtxm", "abbr": "VTXM", "zh_base": "Vortex 负向",
     "pattern": r"^vtxm_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "vtxp", "abbr": "VTXP", "zh_base": "Vortex 正向",
     "pattern": r"^vtxp_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "sr", "abbr": "SR", "zh_base": "支撑压力位",
     "pattern": r"^sr_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},

    # ---- 量能 ----
    {"family": "obv", "abbr": "OBV", "zh_base": "能量潮",
     "pattern": r"^obv$", "param_order": [], "aliases": ["on balance volume"], "default_params": {}, "common": True},
    {"family": "ad", "abbr": "AD", "zh_base": "累积派发线",
     "pattern": r"^ad$", "param_order": [], "aliases": ["accumulation distribution"], "default_params": {}, "common": True},
    {"family": "adosc", "abbr": "ADOSC", "zh_base": "蔡金振荡指标",
     "pattern": r"^adosc_(?P<fast>\d+)_(?P<slow>\d+)$", "param_order": ["fast", "slow"],
     "aliases": ["chaikin oscillator"], "default_params": {}, "common": True},
    {"family": "cmf", "abbr": "CMF", "zh_base": "蔡金资金流量",
     "pattern": r"^cmf_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["chaikin money flow"], "default_params": {"period": 20}, "common_periods": [20]},
    {"family": "eom", "abbr": "EOM", "zh_base": "简易波动指标",
     "pattern": r"^eom_(?P<period>\d+)_(?P<divisor>\d+)$", "param_order": ["period", "divisor"],
     "aliases": ["ease of movement"], "default_params": {}, "common": True},
    {"family": "mfi", "abbr": "MFI", "zh_base": "资金流量指标",
     "pattern": r"^mfi_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["money flow index"], "default_params": {"period": 14}, "common_periods": [14]},
    {"family": "pvo", "abbr": "PVO", "zh_base": "成交量振荡指标",
     "pattern": r"^pvo_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": ["price volume oscillator"], "default_params": {}, "common": True},
    {"family": "pvos", "abbr": "PVOS", "zh_base": "PVO 信号线",
     "pattern": r"^pvos_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "pvoh", "abbr": "PVOH", "zh_base": "PVO 柱",
     "pattern": r"^pvoh_(?P<fast>\d+)_(?P<slow>\d+)_(?P<signal>\d+)$",
     "param_order": ["fast", "slow", "signal"], "aliases": [], "default_params": {}, "common": True},
    {"family": "pvt", "abbr": "PVT", "zh_base": "价量趋势",
     "pattern": r"^pvt$", "param_order": [], "aliases": ["price volume trend"], "default_params": {}, "common": True},
    {"family": "pvi", "abbr": "PVI", "zh_base": "正量指标",
     "pattern": r"^pvi$", "param_order": [], "aliases": ["positive volume index"], "default_params": {}, "common": True},
    {"family": "nvi", "abbr": "NVI", "zh_base": "负量指标",
     "pattern": r"^nvi_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["negative volume index"], "default_params": {}, "common": True},
    {"family": "pvie", "abbr": "PVIE", "zh_base": "正量指标指数",
     "pattern": r"^pvie_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "pvol", "abbr": "PVOL", "zh_base": "价量",
     "pattern": r"^pvol$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "vol_sma", "abbr": "VOL_SMA", "zh_base": "成交量均线",
     "pattern": r"^vol_sma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["量能均线"], "default_params": {}, "common": True},
    {"family": "volume_ratio", "abbr": "VOLUME_RATIO", "zh_base": "量比",
     "pattern": r"^volume_ratio_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["量比"], "default_params": {}, "common": True},
    {"family": "ad_sma", "abbr": "AD_SMA", "zh_base": "累积派发线均线",
     "pattern": r"^ad_sma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "obv_sma", "abbr": "OBV_SMA", "zh_base": "能量潮均线",
     "pattern": r"^obv_sma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "pvt_sma", "abbr": "PVT_SMA", "zh_base": "价量趋势均线",
     "pattern": r"^pvt_sma_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},

    # ---- 统计 ----
    {"family": "stdev", "abbr": "STDEV", "zh_base": "标准差",
     "pattern": r"^stdev_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["standard deviation"], "default_params": {}, "common": True},
    {"family": "skew", "abbr": "SKEW", "zh_base": "偏度",
     "pattern": r"^skew_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "kurt", "abbr": "KURT", "zh_base": "峰度",
     "pattern": r"^kurt_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "mad", "abbr": "MAD", "zh_base": "平均绝对偏差",
     "pattern": r"^mad_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "median", "abbr": "MEDIAN", "zh_base": "中位数",
     "pattern": r"^median_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "qtl", "abbr": "QTL", "zh_base": "分位数",
     "pattern": r"^qtl_(?P<period>\d+)_(?P<q>[\d_]+)$", "param_order": ["period", "q"],
     "aliases": ["quantile"], "default_params": {}, "common": True},
    {"family": "entp", "abbr": "ENTP", "zh_base": "谱熵",
     "pattern": r"^entp_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "zs", "abbr": "ZS", "zh_base": "Z 分数",
     "pattern": r"^zs_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["zscore", "z-score"], "default_params": {}, "common": True},
    {"family": "ibs", "abbr": "IBS", "zh_base": "内部 bar 强度",
     "pattern": r"^ibs_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["internal bar strength"], "default_params": {}, "common": True},
    {"family": "sharpe_stat", "abbr": "SHARPE", "zh_base": "夏普比率",
     "pattern": r"^sharpe_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["sharpe ratio"], "default_params": {}, "common": True},
    {"family": "slope", "abbr": "SLOPE", "zh_base": "斜率",
     "pattern": r"^slope_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "tos_stdevall", "abbr": "TOS_STDEVALL", "zh_base": "标准差带",
     "pattern": r"^tos_stdevall_(?P<band>[a-z]+)(_(?P<mult>\d+))?$", "param_order": ["band", "mult"],
     "aliases": [], "default_params": {}, "common": True},

    # ---- 绩效 ----
    {"family": "pctret", "abbr": "PCTRET", "zh_base": "区间收益率",
     "pattern": r"^pctret_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": ["收益率"], "default_params": {}, "common": True},
    {"family": "logret", "abbr": "LOGRET", "zh_base": "对数收益率",
     "pattern": r"^logret_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "dd", "abbr": "DD", "zh_base": "回撤",
     "pattern": r"^dd$", "param_order": [], "aliases": ["drawdown"], "default_params": {}, "common": True},
    {"family": "dd_pct", "abbr": "DD_PCT", "zh_base": "回撤比例",
     "pattern": r"^dd_pct$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "dd_log", "abbr": "DD_LOG", "zh_base": "对数回撤",
     "pattern": r"^dd_log$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "intraday_ret", "abbr": "INTRADAY_RET", "zh_base": "日内收益",
     "pattern": r"^intraday_ret_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "overnight_ret", "abbr": "OVERNIGHT_RET", "zh_base": "隔夜收益",
     "pattern": r"^overnight_ret_(?P<period>\d+)$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "mom_12_1", "abbr": "MOM_12_1", "zh_base": "12 个月动量",
     "pattern": r"^mom_12_1$", "param_order": [], "aliases": ["carry momentum"], "default_params": {}, "common": True},

    # ---- K 线 ----
    {"family": "cdl", "abbr": "CDL", "zh_base": "K 线形态",
     "pattern": r"^cdl_(?P<name>[a-z_]+)$", "param_order": [],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "ha", "abbr": "HA", "zh_base": "平均K线",
     "pattern": r"^ha_(?P<field>[a-z]+)$", "param_order": [],
     "aliases": ["heikin ashi"], "default_params": {}, "common": True},
    {"family": "z_score_price", "abbr": "Z", "zh_base": "价格 Z 分数",
     "pattern": r"^(?P<field>open|high|low|close)_z_(?P<period>\d+)_(?P<mult>\d+)$",
     "param_order": ["period", "mult"], "aliases": [], "default_params": {}, "common": True},

    # ---- 流动性 ----
    {"family": "avg_turnover", "abbr": "AVG_TURNOVER", "zh_base": "平均换手率",
     "pattern": r"^avg_turnover_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": ["换手率"], "default_params": {}, "common": True},
    {"family": "std_turnover", "abbr": "STD_TURNOVER", "zh_base": "换手率标准差",
     "pattern": r"^std_turnover_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "bias_turn", "abbr": "BIAS_TURN", "zh_base": "换手率乖离",
     "pattern": r"^bias_turn_(?P<short>\d+)d_(?P<long>\d+)d$", "param_order": ["short", "long"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "bias_std_turn", "abbr": "BIAS_STD_TURN", "zh_base": "换手率标准差乖离",
     "pattern": r"^bias_std_turn_(?P<short>\d+)d_(?P<long>\d+)d$", "param_order": ["short", "long"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "turnover_ma", "abbr": "TURNOVER_MA", "zh_base": "换手率均线",
     "pattern": r"^turnover_ma_(?P<short>\d+)d(_(?P<long>\d+)d)?$", "param_order": ["short", "long"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "amount_ma", "abbr": "AMOUNT_MA", "zh_base": "成交额均线",
     "pattern": r"^amount_ma_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "sum_abs_rtn_amount", "abbr": "SUM_ABS_RTN_AMOUNT", "zh_base": "绝对收益成交额",
     "pattern": r"^sum_abs_rtn_amount_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "volume_alpha", "abbr": "VOLUME_ALPHA", "zh_base": "量能 Alpha",
     "pattern": r"^volume_alpha_(?P<period>\d+)d_(?P<index>\d+)$", "param_order": ["period", "index"],
     "aliases": [], "default_params": {}, "common": True},

    # ---- 风险 ----
    {"family": "return_std", "abbr": "RETURN_STD", "zh_base": "收益标准差",
     "pattern": r"^return_std_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": ["收益率波动"], "default_params": {}, "common": True},
    {"family": "high_low", "abbr": "HIGH_LOW", "zh_base": "区间高低差",
     "pattern": r"^high_low_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "days_beyond", "abbr": "DAYS_BEYOND", "zh_base": "越界天数",
     "pattern": r"^days_beyond_upper_lower_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "sharpe_risk", "abbr": "SHARPE", "zh_base": "夏普比率",
     "pattern": r"^sharpe_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": ["sharpe"], "default_params": {}, "common": True},
    {"family": "adjusted_sharpe", "abbr": "ADJUSTED_SHARPE", "zh_base": "调整夏普比率",
     "pattern": r"^adjusted_sharpe_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "beta", "abbr": "BETA", "zh_base": "贝塔",
     "pattern": r"^beta_(?P<period>\d+)d_(?P<index>\d+)$", "param_order": ["period", "index"],
     "aliases": ["beta"], "default_params": {}, "common": True},
    {"family": "volume_beta", "abbr": "VOLUME_BETA", "zh_base": "量能贝塔",
     "pattern": r"^volume_beta_(?P<period>\d+)d_(?P<index>\d+)$", "param_order": ["period", "index"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "beta_consistency", "abbr": "BETA_CONSISTENCY", "zh_base": "贝塔一致性",
     "pattern": r"^beta_consistency_(?P<period>\d+)d_(?P<index>\d+)$", "param_order": ["period", "index"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "sigma", "abbr": "SIGMA", "zh_base": "年化波动率",
     "pattern": r"^sigma_(?P<period>\d+)d_(?P<index>\d+)$", "param_order": ["period", "index"],
     "aliases": [], "default_params": {}, "common": True},
    {"family": "log_price", "abbr": "LOG_PRICE", "zh_base": "对数价格",
     "pattern": r"^log_price$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "alpha_index", "abbr": "ALPHA_INDEX", "zh_base": "超额收益",
     "pattern": r"^alpha_(?P<period>\d+)d_(?P<index>\d+)$", "param_order": ["period", "index"],
     "aliases": ["alpha"], "default_params": {}, "common": True},

    # ---- 估值 / 成长 / 质量 / 规模（规则可判的） ----
    {"family": "size", "abbr": "SIZE", "zh_base": "市值",
     "pattern": r"^size$", "param_order": [], "aliases": ["市值"], "default_params": {}, "common": True},
    {"family": "float_size", "abbr": "FLOAT_SIZE", "zh_base": "流通市值",
     "pattern": r"^float_size$", "param_order": [], "aliases": ["流通市值"], "default_params": {}, "common": True},
    {"family": "nl_size", "abbr": "NL_SIZE", "zh_base": "非流通市值",
     "pattern": r"^nl_size$", "param_order": [], "aliases": [], "default_params": {}, "common": True},
    {"family": "peg", "abbr": "PEG", "zh_base": "PEG",
     "pattern": r"^peg_(?P<period>\d+)d$", "param_order": ["period"],
     "aliases": ["peg"], "default_params": {}, "common": True},
]

# ---------------------------------------------------------------------------
# 人工维护条目（特殊财务 / 风险 / 估值 / 中文习惯名；不伪造，逐条核对）
# key = "<table>.<column>"（table 不含 factors. 前缀）
# ---------------------------------------------------------------------------

MANUAL_ENTRIES: dict[str, dict[str, Any]] = {
    # 财务（PIT）
    "revenue": {"zh": "营业收入", "aliases": ["营收", "营业收入"], "common": True},
    "revenue_ttm": {"zh": "营业收入(TTM)", "aliases": ["营收ttm"], "common": True},
    "total_revenue": {"zh": "营业总收入", "aliases": ["总营收"], "common": True},
    "total_revenue_ttm": {"zh": "营业总收入(TTM)", "aliases": [], "common": True},
    "oper_cost": {"zh": "营业成本", "aliases": ["营业成本"], "common": True},
    "oper_cost_ttm": {"zh": "营业成本(TTM)", "aliases": [], "common": True},
    "total_cogs": {"zh": "营业总成本", "aliases": [], "common": True},
    "total_cogs_ttm": {"zh": "营业总成本(TTM)", "aliases": [], "common": True},
    "ebit": {"zh": "息税前利润", "aliases": ["ebit"], "common": True},
    "ebit_ttm": {"zh": "息税前利润(TTM)", "aliases": [], "common": True},
    "ebitda": {"zh": "息税折旧摊销前利润", "aliases": ["ebitda"], "common": True},
    "ebitda_ttm": {"zh": "息税折旧摊销前利润(TTM)", "aliases": [], "common": True},
    "n_income_attr_p": {"zh": "归母净利润", "aliases": ["归母净利润", "归属母公司净利润"], "common": True},
    "n_income_attr_p_ttm": {"zh": "归母净利润(TTM)", "aliases": [], "common": True},
    "n_income": {"zh": "净利润", "aliases": ["净利润"], "common": True},
    "n_income_ttm": {"zh": "净利润(TTM)", "aliases": [], "common": True},
    "rd_exp": {"zh": "研发费用", "aliases": ["研发费用"], "common": True},
    "rd_exp_ttm": {"zh": "研发费用(TTM)", "aliases": [], "common": True},
    "operate_profit": {"zh": "营业利润", "aliases": ["营业利润"], "common": True},
    "operate_profit_ttm": {"zh": "营业利润(TTM)", "aliases": [], "common": True},
    "total_profit": {"zh": "利润总额", "aliases": ["利润总额"], "common": True},
    "total_profit_ttm": {"zh": "利润总额(TTM)", "aliases": [], "common": True},
    "income_tax": {"zh": "所得税费用", "aliases": ["所得税"], "common": True},
    "income_tax_ttm": {"zh": "所得税费用(TTM)", "aliases": [], "common": True},
    "sell_exp": {"zh": "销售费用", "aliases": ["销售费用"], "common": True},
    "sell_exp_ttm": {"zh": "销售费用(TTM)", "aliases": [], "common": True},
    "admin_exp": {"zh": "管理费用", "aliases": ["管理费用"], "common": True},
    "admin_exp_ttm": {"zh": "管理费用(TTM)", "aliases": [], "common": True},
    "fin_exp": {"zh": "财务费用", "aliases": ["财务费用"], "common": True},
    "fin_exp_ttm": {"zh": "财务费用(TTM)", "aliases": [], "common": True},
    "int_exp": {"zh": "利息费用", "aliases": ["利息费用"], "common": True},
    "int_exp_ttm": {"zh": "利息费用(TTM)", "aliases": [], "common": True},
    "total_assets": {"zh": "总资产", "aliases": ["总资产"], "common": True},
    "total_assets_ttm": {"zh": "总资产(TTM)", "aliases": [], "common": True},
    "total_cur_assets": {"zh": "流动资产合计", "aliases": ["流动资产"], "common": True},
    "total_cur_liab": {"zh": "流动负债合计", "aliases": ["流动负债"], "common": True},
    "total_liab": {"zh": "负债合计", "aliases": ["总负债"], "common": True},
    "total_liab_ttm": {"zh": "负债合计(TTM)", "aliases": [], "common": True},
    "total_hldr_eqy_exc_min_int": {"zh": "股东权益合计(不含少数股东)", "aliases": ["股东权益", "净资产"], "common": True},
    "total_hldr_eqy_inc_min_int": {"zh": "股东权益合计(含少数股东)", "aliases": [], "common": True},
    "inventories": {"zh": "存货", "aliases": ["存货"], "common": True},
    "accounts_receiv": {"zh": "应收账款", "aliases": ["应收账款"], "common": True},
    "money_cap": {"zh": "货币资金", "aliases": ["货币资金"], "common": True},
    "fix_assets": {"zh": "固定资产", "aliases": ["固定资产"], "common": True},
    "intan_assets": {"zh": "无形资产", "aliases": ["无形资产"], "common": True},
    "goodwill": {"zh": "商誉", "aliases": ["商誉"], "common": True},
    "lt_borr": {"zh": "长期借款", "aliases": ["长期借款"], "common": True},
    "st_borr": {"zh": "短期借款", "aliases": ["短期借款"], "common": True},
    "basic_eps": {"zh": "基本每股收益", "aliases": ["基本每股收益", "eps"], "common": True},
    "eps_ttm": {"zh": "每股收益(TTM)", "aliases": ["每股收益ttm"], "common": True},
    "eps_y": {"zh": "每股收益(年度)", "aliases": [], "common": True},
    "eps_q": {"zh": "每股收益(单季)", "aliases": [], "common": True},
    "total_share": {"zh": "总股本", "aliases": ["总股本"], "common": True},
    "roe": {"zh": "净资产收益率", "aliases": ["roe", "净资产收益率"], "common": True},
    "roe_yearly": {"zh": "年化净资产收益率", "aliases": ["年化roe"], "common": True},
    "roe_ttm": {"zh": "净资产收益率(TTM)", "aliases": ["roe ttm"], "common": True},
    "roa": {"zh": "总资产收益率", "aliases": ["roa", "总资产收益率"], "common": True},
    "roa_ttm": {"zh": "总资产收益率(TTM)", "aliases": [], "common": True},
    "current_ratio": {"zh": "流动比率", "aliases": ["流动比率"], "common": True},
    "quick_ratio": {"zh": "速动比率", "aliases": ["速动比率"], "common": True},
    "debt_to_assets": {"zh": "资产负债率", "aliases": ["资产负债率", "负债率"], "common": True},
    "grossprofit_margin": {"zh": "毛利率", "aliases": ["毛利率"], "common": True},
    "netprofit_margin": {"zh": "净利率", "aliases": ["净利率"], "common": True},
    "free_cashflow": {"zh": "自由现金流", "aliases": ["自由现金流"], "common": True},
    "free_cashflow_ttm": {"zh": "自由现金流(TTM)", "aliases": [], "common": True},
    "n_cashflow_act": {"zh": "经营活动现金流净额", "aliases": ["经营现金流", "经营活动现金流"], "common": True},
    "n_cashflow_act_ttm": {"zh": "经营活动现金流净额(TTM)", "aliases": [], "common": True},
    "n_cash_flows_fnc_act": {"zh": "经营活动现金流入小计", "aliases": [], "common": True},
    "n_cash_flows_fnc_act_ttm": {"zh": "经营活动现金流入小计(TTM)", "aliases": [], "common": True},
    "n_cashflow_inv_act": {"zh": "投资活动现金流净额", "aliases": ["投资现金流"], "common": True},
    "n_cashflow_inv_act_ttm": {"zh": "投资活动现金流净额(TTM)", "aliases": [], "common": True},
    "c_pay_acq_const_fiolta": {"zh": "购建长期资产支付的现金", "aliases": [], "common": True},
    "c_paid_to_for_empl": {"zh": "支付给职工的现金", "aliases": [], "common": True},
    "c_inf_fr_operate_a": {"zh": "经营活动现金流入", "aliases": [], "common": True},
    "c_inf_fr_operate_a_ttm": {"zh": "经营活动现金流入(TTM)", "aliases": [], "common": True},
    "depr_fa_coga_dpba": {"zh": "固定资产折旧", "aliases": [], "common": True},
    "depr_fa_coga_dpba_ttm": {"zh": "固定资产折旧(TTM)", "aliases": [], "common": True},
    "amort_intang_assets": {"zh": "无形资产摊销", "aliases": [], "common": True},
    "amort_intang_assets_ttm": {"zh": "无形资产摊销(TTM)", "aliases": [], "common": True},
    "defer_tax_assets": {"zh": "递延所得税资产", "aliases": [], "common": True},
    "contract_liab": {"zh": "合同负债", "aliases": [], "common": True},
    "prepayment": {"zh": "预付款项", "aliases": ["预付账款"], "common": True},
    "lt_rec": {"zh": "长期应收款", "aliases": [], "common": True},
    "trad_asset": {"zh": "交易性金融资产", "aliases": [], "common": True},
    "assets_to_eqt": {"zh": "权益乘数", "aliases": [], "common": True},
    "biz_tax_surchg": {"zh": "营业税金及附加", "aliases": [], "common": True},
    "biz_tax_surchg_ttm": {"zh": "营业税金及附加(TTM)", "aliases": [], "common": True},
    "profit_dedt": {"zh": "扣非净利润", "aliases": ["扣非净利润"], "common": True},
    "profit_dedt_ttm": {"zh": "扣非净利润(TTM)", "aliases": [], "common": True},
    "grossprofit": {"zh": "毛利", "aliases": ["毛利"], "common": True},

    # 质量 / 成长 / 估值
    "npm_ttm": {"zh": "净利率(TTM)", "aliases": [], "common": True},
    "gpm_ttm": {"zh": "毛利率(TTM)", "aliases": [], "common": True},
    "opm_ttm": {"zh": "营业利润率(TTM)", "aliases": [], "common": True},
    "asset_turnover": {"zh": "总资产周转率", "aliases": ["资产周转率"], "common": True},
    "equity_turnover": {"zh": "权益周转率", "aliases": [], "common": True},
    "inventory_turnover": {"zh": "存货周转率", "aliases": ["存货周转率"], "common": True},
    "receivable_turnover": {"zh": "应收账款周转率", "aliases": ["应收账款周转率"], "common": True},
    "fixed_asset_turnover": {"zh": "固定资产周转率", "aliases": [], "common": True},
    "icr": {"zh": "利息保障倍数", "aliases": [], "common": True},
    "cfcr": {"zh": "现金流动负债比", "aliases": [], "common": True},
    "cash_ratio": {"zh": "现金比率", "aliases": ["现金比率"], "common": True},
    "de": {"zh": "产权比率", "aliases": [], "common": True},
    "debt_asset_ratio": {"zh": "资产负债率", "aliases": ["资产负债率"], "common": True},
    "financial_leverage": {"zh": "财务杠杆", "aliases": [], "common": True},
    "market_value_leverage": {"zh": "市值杠杆", "aliases": [], "common": True},
    "quality_composite": {"zh": "质量综合分", "aliases": [], "common": True},
    "yoy_revenue": {"zh": "营收同比增长率", "aliases": ["营收同比"], "common": True},
    "yoy_net_profit": {"zh": "净利润同比增长率", "aliases": ["净利润同比"], "common": True},
    "yoy_roe": {"zh": "ROE 同比增长率", "aliases": [], "common": True},
    "yoy_roa": {"zh": "ROA 同比增长率", "aliases": [], "common": True},
    "yoy_net_asset": {"zh": "净资产同比增长率", "aliases": [], "common": True},
    "yoy_total_asset": {"zh": "总资产同比增长率", "aliases": [], "common": True},
    "yoy_ocf": {"zh": "经营现金流同比增长率", "aliases": [], "common": True},
    "np_ttm_qoq": {"zh": "净利润TTM环比", "aliases": [], "common": True},
    "asset_growth_qoq": {"zh": "总资产环比增长率", "aliases": [], "common": True},
    "gross_margin_qoq": {"zh": "毛利率环比变动", "aliases": [], "common": True},
    "book_to_market": {"zh": "账面市值比", "aliases": ["bm", "市净率倒数"], "common": True},
    "earnings_to_price": {"zh": "盈利价格比", "aliases": ["ep", "市盈率倒数"], "common": True},
    "sales_to_market": {"zh": "营收市值比", "aliases": ["sp", "市销率倒数"], "common": True},
    "ocf_to_market": {"zh": "经营现金流市值比", "aliases": [], "common": True},
    "fcf_to_market": {"zh": "自由现金流市值比", "aliases": [], "common": True},
    "ncf_to_market": {"zh": "净现金流市值比", "aliases": [], "common": True},
    "ebitda_to_market": {"zh": "EBITDA 市值比", "aliases": [], "common": True},
    "earnings_cut_to_market": {"zh": "扣非盈利市值比", "aliases": [], "common": True},
    "dividend_yield_3y_avg": {"zh": "三年平均股息率", "aliases": ["股息率"], "common": True},
    "pegh5": {"zh": "PEG（五年）", "aliases": [], "common": True},
    "etp5": {"zh": "五年盈利价格比", "aliases": [], "common": True},
}

# 常用已落库因子清单（LLM prompt 只放少量示例，**不注入全量别名**）。
# COMMON_FACTOR_TARGETS 由本清单派生，消除手写漂移；每条都必须在因子库真实存在。
CORE_TARGETS: tuple[str, ...] = (
    "factors.stock_daily_momentum_close.rsi_6",
    "factors.stock_daily_momentum_close.rsi_12",
    "factors.stock_daily_momentum_close.rsi_14",
    "factors.stock_daily_momentum_close.rsi_24",
    "factors.stock_daily_momentum_close.macd_12_26_9",
    "factors.stock_daily_momentum_close.macds_12_26_9",
    "factors.stock_daily_momentum_close.macdh_12_26_9",
    "factors.stock_daily_momentum_close.k_9_3",
    "factors.stock_daily_momentum_close.d_9_3",
    "factors.stock_daily_momentum_close.j_9_3",
    "factors.stock_daily_momentum_close.cci_14_0_015",
    "factors.stock_daily_overlap_close.sma_5",
    "factors.stock_daily_overlap_close.sma_10",
    "factors.stock_daily_overlap_close.sma_20",
    "factors.stock_daily_overlap_close.sma_60",
    "factors.stock_daily_overlap_close.ema_5",
    "factors.stock_daily_overlap_close.ema_20",
    "factors.stock_daily_overlap_close.ema_12",
    "factors.stock_daily_overlap_close.ema_26",
    "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
    "factors.stock_daily_volatility_close.bbm_20_2_0_2_0",
    "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
    "factors.stock_daily_volatility_close.atrr_14",
    "factors.stock_daily_trend_close.adx_14",
    "factors.stock_daily_volume_close.mfi_14",
)

# 跨条目别名（一个别名天然指向多个字段 → 形成候选而非静默覆盖）
EXTRA_ALIASES: dict[str, list[str]] = {
    "布林带": [
        "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbm_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
    ],
    "布林线": [
        "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbm_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
    ],
    "bollinger": [
        "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbm_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
    ],
    "boll": [
        "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbm_20_2_0_2_0",
        "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
    ],
    "kdj": [
        "factors.stock_daily_momentum_close.k_9_3",
        "factors.stock_daily_momentum_close.d_9_3",
        "factors.stock_daily_momentum_close.j_9_3",
    ],
    "随机指标": [
        "factors.stock_daily_momentum_close.k_9_3",
        "factors.stock_daily_momentum_close.d_9_3",
        "factors.stock_daily_momentum_close.j_9_3",
    ],
    "随机kdj": [
        "factors.stock_daily_momentum_close.k_9_3",
        "factors.stock_daily_momentum_close.d_9_3",
        "factors.stock_daily_momentum_close.j_9_3",
    ],
    "dmi": [
        "factors.stock_daily_momentum_close.dmp_14",
        "factors.stock_daily_momentum_close.dmn_14",
    ],
}


# QRE-FACTOR-ZH-COVERAGE：按公式/官方定义维护的中文显示名。
# 只补 registry 中 zh 为空的条目（查表覆盖），不改名既有条目、不改别名与
# common/core 判定；命名依据 indicators_tushare 真实公式与官方 486 文档
# （docs/agent/change_requests/factor_specs_p1p3.md、factor_specs_p4p5p7.md）。
ALPHA191_ZH: dict[str, str] = {
    "alpha001": "量能变动与日内收益相关性（反向）",
    "alpha002": "收盘位置变化（反向）",
    "alpha003": "6日涨势强度累计",
    "alpha004": "均线带宽突破信号",
    "alpha005": "量高价时序秩相关峰值（反向）",
    "alpha006": "加权价变动方向（反向）",
    "alpha007": "VWAP偏离3日极值乘量变动",
    "alpha008": "混合价位4日变动（反向）",
    "alpha009": "中间价变动乘波幅平滑",
    "alpha010": "下跌波动/收盘平方5日峰值排名",
    "alpha011": "6日量价位置累计",
    "alpha012": "开盘偏离VWAP排名乘收盘偏离",
    "alpha013": "高低几何均价减VWAP",
    "alpha014": "5日价格变动",
    "alpha015": "开盘跳空幅度",
    "alpha016": "量VWAP排名相关5日峰值（反向）",
    "alpha017": "VWAP15日高点排名与5日价格变动幂次",
    "alpha018": "5日涨跌幅",
    "alpha019": "5日累计涨跌幅（条件）",
    "alpha020": "6日涨跌幅百分比",
    "alpha021": "6日收盘趋势斜率",
    "alpha022": "收盘偏离6日均值变化平滑",
    "alpha023": "上行日波动占比",
    "alpha024": "5日价格变动平滑",
    "alpha025": "7日量价变动排名乘长期收益",
    "alpha026": "7日均值偏离加长窗量价相关",
    "alpha027": "3/6日变动加权平滑",
    "alpha028": "9日RSV三重平滑",
    "alpha029": "6日涨跌幅乘成交量",
    "alpha030": "市场回归残差平方平滑（近似）",
    "alpha031": "收盘偏离12日均值百分比",
    "alpha032": "高价排名与量排名3日相关累计（反向）",
    "alpha033": "5日低点回升×长期动量排名×量时序秩",
    "alpha034": "12日均值比收盘",
    "alpha035": "开盘变动与量价相关排名小值（反向）",
    "alpha036": "量VWAP排名6日相关2日累计",
    "alpha037": "5日开盘收益积10日变动（反向）",
    "alpha038": "20日高点突破信号",
    "alpha039": "收盘变动排名与混合价量相关差（反向）",
    "alpha040": "26日上涨/下跌量比",
    "alpha041": "VWAP 3日变动5日峰值排名（反向）",
    "alpha042": "高价10日波动排名乘高价量相关（反向）",
    "alpha043": "6日带符号成交量累计",
    "alpha044": "低价量相关与VWAP变动时序秩和",
    "alpha045": "混合价1日变动排名乘VWAP长量相关",
    "alpha046": "多周期均线均值比收盘",
    "alpha047": "6日RSV 9日平滑",
    "alpha048": "3日连续同向天数排名乘短期量占比（反向）",
    "alpha049": "12日高低振幅占振幅和比（下行）",
    "alpha050": "12日高低振幅差比（下减上）",
    "alpha051": "12日高低振幅占振幅和比（上行）",
    "alpha052": "26日上行/下行典型价振幅比",
    "alpha053": "12日上涨天数占比",
    "alpha054": "日内波动+阴阳+开收相关复合（反向）",
    "alpha055": "20日多空力量累计",
    "alpha056": "开盘12日低点排名与量价相关幂次条件",
    "alpha057": "9日RSV 3日平滑",
    "alpha058": "20日上涨天数占比",
    "alpha059": "20日涨势强度累计",
    "alpha060": "20日量价位置累计",
    "alpha061": "VWAP变动与低价量相关排名大值（反向）",
    "alpha062": "高价与量排名5日相关（反向）",
    "alpha063": "6日上涨占比",
    "alpha064": "VWAP量与收盘量相关排名大值（反向）",
    "alpha065": "6日均值比收盘",
    "alpha066": "收盘偏离6日均值百分比",
    "alpha067": "24日上涨占比",
    "alpha068": "中间价变动乘波幅除量平滑",
    "alpha069": "20日DTM/DBM多空比",
    "alpha070": "6日成交额标准差",
    "alpha071": "收盘偏离24日均值百分比",
    "alpha072": "6日RSV 15日平滑",
    "alpha073": "收盘量相关双重衰减时序秩",
    "alpha074": "混合价量相关与VWAP量相关排名和",
    "alpha075": "50日个股涨指数跌天数占比",
    "alpha076": "20日单位量波动",
    "alpha077": "混合高价与VWAP差衰减排名小值",
    "alpha078": "典型价偏离12日均值",
    "alpha079": "12日上涨占比",
    "alpha080": "5日成交量变动百分比",
    "alpha081": "21日成交量SMA",
    "alpha082": "6日RSV 20日平滑",
    "alpha083": "高价排名与量排名5日协方差（反向）",
    "alpha084": "20日带符号成交量累计",
    "alpha085": "20日量比时序秩乘7日跌势时序秩",
    "alpha086": "20/10日前收盘差条件信号",
    "alpha087": "VWAP变动与低价开盘偏离衰减复合（反向）",
    "alpha088": "20日涨跌幅百分比",
    "alpha089": "13/27日SMA差二次平滑",
    "alpha090": "VWAP量排名5日相关（反向）",
    "alpha091": "收盘5日高点排名乘均量低价相关（反向）",
    "alpha092": "混合价变动与长量价相关衰减排名大值（反向）",
    "alpha093": "20日开盘下行振幅累计",
    "alpha094": "30日带符号成交量累计",
    "alpha095": "20日成交额标准差",
    "alpha096": "9日RSV双重3日平滑",
    "alpha097": "10日成交量标准差",
    "alpha098": "100日长期均线变动条件",
    "alpha099": "收盘排名与量排名5日协方差（反向）",
    "alpha100": "20日成交量标准差",
    "alpha101": "收盘长均量相关与混合价量相关排名比较（反向）",
    "alpha102": "6日成交量上涨占比",
    "alpha103": "20日低点出现时间倒数",
    "alpha104": "高价量相关变动乘收盘波动（反向）",
    "alpha105": "开盘排名与量排名10日相关（反向）",
    "alpha106": "20日价格变动",
    "alpha107": "开盘相对前日高收低排名积（反向）",
    "alpha108": "高价2日高点排名与VWAP长量相关幂次（反向）",
    "alpha109": "10日波幅SMA比",
    "alpha110": "20日上行/下行振幅比",
    "alpha111": "11日收盘位置乘量平滑",
    "alpha112": "12日涨跌幅力量比",
    "alpha113": "20日均价排名乘收盘短期量相关（反向）",
    "alpha114": "波幅比延迟2日排名乘量排名",
    "alpha115": "混合价量相关排名与价量时序秩相关幂次",
    "alpha116": "20日收盘趋势斜率",
    "alpha117": "32日量时序秩乘价位区间时序秩补数",
    "alpha118": "20日上行/下行开盘振幅比",
    "alpha119": "VWAP量相关与开盘量相关衰减排名差",
    "alpha120": "VWAP偏离收盘排名比",
    "alpha121": "VWAP 12日低点排名与量价相关条件",
    "alpha122": "对数收盘三重13日SMA",
    "alpha123": "中间价与均量60日相关20日累计9日",
    "alpha124": "收盘减VWAP除30日高点排名衰减",
    "alpha125": "VWAP与均量80日相关17日衰减20日",
    "alpha126": "典型价（高低收均值）",
    "alpha127": "12日高点偏离平方均值开方",
    "alpha128": "典型价上涨累计占比",
    "alpha129": "12日下跌幅度累计",
    "alpha130": "中间价与均量40日相关9日衰减10日",
    "alpha131": "VWAP变动排名与收盘长量相关时序秩幂次",
    "alpha132": "20日成交额均值",
    "alpha133": "20日高低点出现时间差",
    "alpha134": "12日涨跌幅乘成交量",
    "alpha135": "20日平滑的20日收益率延迟",
    "alpha136": "3日收益变动排名乘开盘量相关（反向）",
    "alpha137": "日内多空力量（16倍）",
    "alpha138": "混合低价变动与低价量相关衰减排名差（反向）",
    "alpha139": "开盘与量10日相关（反向）",
    "alpha140": "开低高收排名差衰减8日排名小值",
    "alpha141": "高价排名与均量15日相关9日（反向）",
    "alpha142": "收盘时序秩·二阶变动·量比时序秩（反向）",
    "alpha143": "条件涨跌幅乘累计",
    "alpha144": "20日下跌日单位额波动",
    "alpha145": "9/26/12日均量差百分比",
    "alpha146": "20日收益相对61日均值偏离比60日平方均值",
    "alpha147": "12日均值趋势斜率",
    "alpha148": "开盘与均量60日相关6日累计排名",
    "alpha149": "熊市beta（252日）",
    "alpha150": "典型价乘成交量",
    "alpha151": "20日价格变动平滑",
    "alpha152": "多重SMA复合（12日）",
    "alpha153": "多周期均线均值",
    "alpha154": "VWAP 16日低点与长量相关条件",
    "alpha155": "13/27日量SMA差二次平滑",
    "alpha156": "VWAP与混合低价变动衰减排名大值（反向）",
    "alpha157": "嵌套排名乘积与延迟收益时序秩小值",
    "alpha158": "高低相对15日SMA差比收盘",
    "alpha159": "三周期摆动合成",
    "alpha160": "下行日20日波动平滑",
    "alpha161": "12日真实波幅均值",
    "alpha162": "RSI12 12日区间分位",
    "alpha163": "负收益乘量乘VWAP乘上行振幅排名",
    "alpha164": "上涨日倒数平滑",
    "alpha165": "48日累计偏离极值差除标准差",
    "alpha166": "20日收益偏离放大（负）",
    "alpha167": "12日上涨幅度累计",
    "alpha168": "成交量相对20日均值（反向）",
    "alpha169": "9日价差SMA延迟12日平滑",
    "alpha170": "收盘倒数排名乘量比20日均值",
    "alpha171": "开盘^5加权价差（反向）",
    "alpha172": "14日多空力量均衡度",
    "alpha173": "13日SMA双重平滑",
    "alpha174": "上行日20日波动平滑",
    "alpha175": "6日真实波幅均值",
    "alpha176": "12日RSV排名与量排名相关",
    "alpha177": "20日高点出现时间倒数",
    "alpha178": "1日涨跌幅乘成交量",
    "alpha179": "VWAP量相关与低价量相关排名积",
    "alpha180": "成交量大于20日均值标记",
    "alpha181": "20日个股相对指数收益偏离平方和",
    "alpha182": "20日顺势天数占比",
    "alpha183": "24日累计偏离极值差除标准差",
    "alpha184": "前日开收与收盘200日相关排名加开收排名",
    "alpha185": "开盘收盘比平方排名（反向）",
    "alpha186": "ADX6与其6日延迟均值",
    "alpha187": "20日开盘上行振幅累计",
    "alpha188": "11日波幅偏离百分比",
    "alpha189": "6日收盘偏离绝对均值",
    "alpha190": "20日收益左尾对数似然",
    "alpha191": "均量与低价相关加中间价减收盘",
}

ALPHA101_ZH: dict[str, str] = {
    "alpha101_1": "下跌波动/收盘平方峰值时序参数排名",
    "alpha101_2": "量能变动与日内收益相关性（反向）",
    "alpha101_3": "开盘排名与量排名相关性（反向）",
    "alpha101_4": "低价排名9日时序秩（反向）",
    "alpha101_5": "开盘偏离VWAP排名乘收盘偏离绝对值（反向）",
    "alpha101_6": "开盘与量相关性（反向）",
    "alpha101_7": "放量时7日变动的60日时序秩（反向）",
    "alpha101_8": "5日开盘收益积10日变动（反向）",
    "alpha101_9": "5日价格变动条件累积",
    "alpha101_10": "4日价格变动条件累积排名",
    "alpha101_11": "VWAP偏离3日极值排名和乘量变动",
    "alpha101_12": "量变动符号乘价格变动（反向）",
    "alpha101_13": "收盘排名与量排名5日协方差（反向）",
    "alpha101_14": "3日收益变动排名乘开盘量相关（反向）",
    "alpha101_15": "高价排名与量排名3日相关3日累计（反向）",
    "alpha101_16": "高价排名与量排名5日协方差（反向）",
    "alpha101_17": "收盘10日时序秩·二阶变动·量比时序秩（反向）",
    "alpha101_18": "日内波幅+阴阳+开收相关复合（反向）",
    "alpha101_19": "7日动向符号乘长期收益排名与量价相关复合（反向）",
    "alpha101_20": "开盘相对前日高收低排名积（反向）",
    "alpha101_22": "高价量相关变动乘收盘波动（反向）",
    "alpha101_23": "20日高点突破信号",
    "alpha101_25": "收益乘量乘VWAP乘上行振幅（反向）",
    "alpha101_33": "开盘收盘比（反向）",
    "alpha101_34": "短长波动比与价格变动复合",
    "alpha101_41": "高低几何均价减VWAP",
    "alpha101_52": "5日低点回升×长期动量排名×量时序秩",
    "alpha101_53": "9日收盘位置变化（反向）",
    "alpha101_54": "开收位置五次幂比（反向）",
    "alpha101_57": "收盘偏离VWAP除30日高点排名衰减",
    "alpha101_101": "日内阴阳位置",
}

# quality / growth / _pit_financial_panel / candle / value：依据 compute_all 真实公式、
# 官方 486 文档表达式与 Tushare 标准字段语义。`_rank` 列为同名计算项的截面排名。
FINANCIAL_ZH: dict[str, str] = {
    # ---- quality（计算项 + 同名 _rank 截面排名）----
    "roe_ttm_lag63d": "净资产收益率(TTM，滞后63交易日)",
    "roe_y": "净资产收益率(年度)",
    "eps_ttm_rank": "每股收益(TTM)·排名",
    "financial_leverage_rank": "财务杠杆·排名",
    "gpm_ttm_rank": "毛利率(TTM)·排名",
    "icr_rank": "利息保障倍数·排名",
    "income_tax_yoy": "所得税费用(TTM)同比增长率",
    "income_tax_yoy_rank": "所得税费用(TTM)同比增长率·排名",
    "np_to_inventory_yoy": "净利润存货比同比",
    "np_to_inventory_yoy_rank": "净利润存货比同比·排名",
    "npm_q": "净利率(单季)",
    "npm_q_rank": "净利率(单季)·排名",
    "ar_ap_to_revenue": "预收预付净额/营业收入(TTM)",
    "ar_ap_to_revenue_rank": "预收预付净额/营业收入(TTM)·排名",
    "asset_turnover_rank": "总资产周转率·排名",
    "delta_current_ratio": "流动比率年度变化",
    "delta_current_ratio_rank": "流动比率年度变化·排名",
    "delta_de": "产权比率年度变化",
    "delta_de_rank": "产权比率年度变化·排名",
    "gpm_q": "毛利率(TTM口径)",
    "gpm_q_rank": "毛利率(TTM口径)·排名",
    "cash_profit_ratio": "现金利润偏离比",
    "cash_profit_ratio_rank": "现金利润偏离比·排名",
    "delta_opm": "营业利润率年度变化",
    "delta_opm_rank": "营业利润率年度变化·排名",
    "eps_q_rank": "每股收益(单季)·排名",
    "eps_y_rank": "每股收益(年度)·排名",
    "delta_npm": "净利率年度变化",
    "delta_npm_rank": "净利率年度变化·排名",
    "market_value_leverage_rank": "市值杠杆·排名",
    "npm_y": "净利率(年度)",
    "npm_y_rank": "净利率(年度)·排名",
    "opm_y": "营业利润率(年度)",
    "opm_y_rank": "营业利润率(年度)·排名",
    "delta_gpm": "毛利率年度变化",
    "delta_gpm_rank": "毛利率年度变化·排名",
    "gpm_y": "毛利率(年度)",
    "gpm_y_rank": "毛利率(年度)·排名",
    "np_to_total_expenses_yoy": "净利润三费比同比",
    "np_to_total_expenses_yoy_rank": "净利润三费比同比·排名",
    "np_to_deferred_tax_yoy": "净利润递延所得税资产比同比",
    "np_to_deferred_tax_yoy_rank": "净利润递延所得税资产比同比·排名",
    "roa_q": "总资产收益率(单季)",
    "roa_q_rank": "总资产收益率(单季)·排名",
    "gpm_qoq": "毛利率环比变动",
    "gpm_qoq_rank": "毛利率环比变动·排名",
    "delta_inventory_turnover": "存货周转率年度变化",
    "delta_inventory_turnover_rank": "存货周转率年度变化·排名",
    "delta_roa": "总资产收益率年度变化",
    "delta_roa_rank": "总资产收益率年度变化·排名",
    "fixed_asset_turnover_rank": "固定资产周转率·排名",
    "npm_ttm_rank": "净利率(TTM)·排名",
    "opm_ttm_rank": "营业利润率(TTM)·排名",
    "receivable_turnover_rank": "应收账款周转率·排名",
    "cfcr_rank": "现金流动负债比·排名",
    "delta_cash_ratio": "现金比率年度变化",
    "delta_cash_ratio_rank": "现金比率年度变化·排名",
    "lra_yoy": "长期应收款同比增长率",
    "lra_yoy_rank": "长期应收款同比增长率·排名",
    "np_to_fixed_assets_yoy": "净利润固定资产比同比",
    "np_to_fixed_assets_yoy_rank": "净利润固定资产比同比·排名",
    "np_to_salary_yoy": "净利润职工薪酬比同比",
    "np_to_salary_yoy_rank": "净利润职工薪酬比同比·排名",
    "npm_q_qoq": "净利率(单季)环比变化",
    "npm_q_qoq_rank": "净利率(单季)环比变化·排名",
    "npm_tsh": "归母净利润/平均总股本",
    "npm_tsh_rank": "归母净利润/平均总股本·排名",
    "npm_ttm_qoq": "净利率(TTM)环比变化",
    "npm_ttm_qoq_rank": "净利率(TTM)环比变化·排名",
    "cash_ratio_rank": "现金比率·排名",
    "delta_asset_turnover": "总资产周转率年度变化",
    "delta_asset_turnover_rank": "总资产周转率年度变化·排名",
    "delta_quick_ratio": "速动比率年度变化",
    "delta_quick_ratio_rank": "速动比率年度变化·排名",
    "delta_roe": "净资产收益率年度变化",
    "delta_roe_rank": "净资产收益率年度变化·排名",
    "inventory_turnover_rank": "存货周转率·排名",
    "roa_ttm_rank": "总资产收益率(TTM)·排名",
    "tax_surcharge_yoy": "税金及附加(TTM)同比增长率",
    "tax_surcharge_yoy_rank": "税金及附加(TTM)同比增长率·排名",
    "equity_turnover_rank": "权益周转率·排名",
    "expenses_to_equity_yoy": "三费权益比同比",
    "expenses_to_equity_yoy_rank": "三费权益比同比·排名",
    "roa_y": "总资产收益率(年度)",
    "roa_y_rank": "总资产收益率(年度)·排名",
    "opt_tpro": "营业利润/利润总额",
    "opt_tpro_rank": "营业利润/利润总额·排名",
    # ---- growth（计算项 + 同名 _rank 截面排名）----
    "sa": "每股收入增长加速度",
    "pa": "总资产收益率增长加速度",
    "eaa": "每股收益增长加速度",
    "eap": "每股收益增长价格标准化加速度",
    "np_ttm_qoq_rank": "净利润TTM环比·排名",
    "yoy_ocf_rank": "经营现金流同比增长率·排名",
    "sa_rank": "每股收入增长加速度·排名",
    "gross_margin_qoq_rank": "毛利率环比变动·排名",
    "pa_rank": "总资产收益率增长加速度·排名",
    "yoy_roa_rank": "ROA 同比增长率·排名",
    "yoy_net_asset_rank": "净资产同比增长率·排名",
    "yoy_roe_rank": "ROE 同比增长率·排名",
    "yoy_total_asset_rank": "总资产同比增长率·排名",
    "eaa_rank": "每股收益增长加速度·排名",
    "eap_rank": "每股收益增长价格标准化加速度·排名",
    "asset_growth_qoq_rank": "总资产环比增长率·排名",
    # ---- _pit_financial_panel（Tushare 标准字段）----
    "inc_end_date": "利润表报告期",
    "inc_ann_date": "利润表公告日",
    "bs_end_date": "资产负债表报告期",
    "bs_ann_date": "资产负债表公告日",
    "cf_end_date": "现金流量表报告期",
    "cf_ann_date": "现金流量表公告日",
    "fi_end_date": "财务指标报告期",
    "fi_ann_date": "财务指标公告日",
    "adv_receipts": "预收款项",
    "bond_payable": "应付债券",
    "c_pay_acq_const_fiolta_ttm": "购建固定资产等支付的现金(TTM)",
    "c_paid_to_for_empl_ttm": "支付给职工的现金(TTM)",
    "stot_inflows_inv_act": "投资活动现金流入小计",
    "stot_inflows_inv_act_ttm": "投资活动现金流入小计(TTM)",
    # ---- candle / value ----
    "cdl_doji_10_0_1": "CDLDOJI十字星形态",
    "etp5_rank": "五年盈利价格比·排名",
}


def _coverage_zh(table: str, column: str) -> str | None:
    """按表取中文显示名覆盖（仅用于补空，不覆盖既有条目）。"""
    if table == "stock_daily_alpha191":
        return ALPHA191_ZH.get(column)
    if table == "stock_daily_alpha101":
        return ALPHA101_ZH.get(column)
    return FINANCIAL_ZH.get(column)


def _fmt_params(template: str, params: dict[str, Any]) -> str:
    out = template
    for key, value in params.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def _to_number(raw: str) -> Any:
    text = raw.replace("_", ".")
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return raw


def _entry_params(match: re.Match, rule: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, raw in match.groupdict().items():
        if raw is None:
            continue
        params[key] = _to_number(raw.replace("_", "."))
    return params


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_common(rule: dict[str, Any], params: dict[str, Any]) -> bool:
    if rule.get("common"):
        return True
    if rule.get("common_params"):
        order = rule.get("param_order") or list(params)
        values = [_as_float(params.get(k)) for k in order]
        if any(v is None for v in values):
            return False
        for candidate in rule["common_params"]:
            if tuple(_as_float(v) for v in candidate) == tuple(values):
                return True
        return False
    if rule.get("common_periods"):
        return any(
            params.get("period") == p or params.get("long") == p or params.get("short") == p
            for p in rule["common_periods"]
        )
    return False


def _is_default_params(rule: dict[str, Any], params: dict[str, Any]) -> bool:
    default = rule.get("default_params") or {}
    if not default:
        return False
    for key, value in default.items():
        actual = _as_float(params.get(key))
        if actual is None or actual != float(value):
            return False
    return True


def _param_text(params: dict[str, Any], order: list[str]) -> str:
    return ",".join(str(params[k]) for k in order if k in params)


def _family_section() -> dict[str, dict[str, Any]]:
    """族规则摘要（按 family 合并）：加载层做结构化匹配与默认参数提示用。"""
    merged: dict[str, dict[str, Any]] = {}
    for rule in FAMILY_RULES:
        family = rule["family"]
        info = merged.setdefault(family, {
            "abbr": rule.get("abbr"),
            "zh_base": rule.get("zh_base"),
            "default_output": None,
            "default_params": {},
            "param_order": list(rule.get("param_order") or []),
            "aliases": [],
            "family_tokens": list(rule.get("family_tokens") or []),
        })
        info["default_output"] = info["default_output"] or rule.get("default_output")
        if rule.get("default_params"):
            info["default_params"] = dict(rule["default_params"])
        if rule.get("param_order"):
            info["param_order"] = list(rule["param_order"])
        for alias in rule.get("aliases", []):
            if alias not in info["aliases"]:
                info["aliases"].append(alias)
    return merged


def build_registry(tables_columns: dict[str, list[str]]) -> dict[str, Any]:
    """快照（{table: [columns]}）→ 注册表 dict。"""
    compiled = [
        (rule, re.compile(rule["pattern"])) for rule in FAMILY_RULES
    ]
    _CORE_SET = set(CORE_TARGETS)
    tables: dict[str, dict[str, Any]] = {}
    for table in sorted(tables_columns):
        parsed_category = None
        price_basis = None
        if table.startswith("stock_daily_") and table.endswith(
            ("_close", "_typical_price", "_average_price")
        ):
            body = table[len("stock_daily_"):]
            for basis in PRICE_BASIS_PREFERENCE:
                suffix = "_" + basis
                if body.endswith(suffix):
                    parsed_category = body[: -len(suffix)]
                    price_basis = basis
                    break
        tables[table] = {
            "category": parsed_category,
            "price_basis": price_basis,
            "price_basis_zh": PRICE_BASIS_ZH.get(price_basis) if price_basis else None,
            "columns": len(tables_columns[table]),
        }

    # overlay 序号预计算（同表内按列名排序，颜色/渲染序稳定且与策略引用无关）
    overlay_index: dict[tuple[str, str], int] = {}
    for table in sorted(tables_columns):
        idx = 0
        for column in sorted(tables_columns[table]):
            family = None
            for rule, regex in compiled:
                if regex.match(column):
                    family = rule["family"]
                    break
            if (family in OVERLAY_MA_FAMILIES or family in OVERLAY_BAND_FAMILIES
                    or table.startswith("stock_daily_overlap")):
                overlay_index[(table, column)] = idx
                idx += 1

    factors: list[dict[str, Any]] = []
    for table in sorted(tables_columns):
        for column in tables_columns[table]:
            if column in ("ts_code", "trade_date"):
                continue
            manual = MANUAL_ENTRIES.get(column, {})
            entry: dict[str, Any] = {
                "table": table,
                "column": column,
                "canonical": f"factors.{table}.{column}",
                "category": tables[table]["category"],
                "price_basis": tables[table]["price_basis"],
                "family": None,
                "output": None,
                "params": {},
                "zh": None,
                "aliases": [],
                "common": bool(manual.get("common")),
                "core": False,
            }
            matched_rule: dict[str, Any] | None = None
            for rule, regex in compiled:
                match = regex.match(column)
                if match is None:
                    continue
                params = _entry_params(match, rule)
                matched_rule = rule
                entry["family"] = rule["family"]
                entry["output"] = rule.get("output")
                entry["params"] = params
                entry["common"] = _is_common(rule, params) or bool(manual.get("common"))
                entry["core"] = entry["canonical"] in _CORE_SET
                if not manual.get("zh"):
                    shown = rule.get("zh_params")
                    if shown is None:
                        shown = rule.get("param_order") or list(params)
                    zh = _fmt_params(rule.get("zh") or rule["zh_base"], params)
                    if shown and rule.get("abbr"):
                        zh = f"{zh}({_param_text(params, shown)})"
                    entry["zh"] = zh
                break
            entry["core"] = entry["canonical"] in _CORE_SET
            if manual.get("zh"):
                entry["zh"] = manual["zh"]
            elif not entry["zh"]:
                # QRE-FACTOR-ZH-COVERAGE：族规则/手工条目未命中的列，按公式与
                # 官方定义查表补中文显示名（查不到仍为 null，不伪造）。
                entry["zh"] = _coverage_zh(table, column)
            # QRE-FACTOR-DISPLAY-CONTRACT：呈现属性作为因子数据成员（页面只消费，
            # 不各自猜指标）；安全默认 + 显式族规则，与因子库列一一对应。
            entry["display"] = _display_for(
                table=table, column=column, family=entry["family"],
                output=entry["output"], params=entry["params"],
                price_basis=tables[table]["price_basis"],
                overlay_index=overlay_index.get((table, column), 0),
            )
            # 别名：列名本身 + 参数写法（全部条目）；族别名只挂在「常用 + 默认参数」
            # 条目上，避免把全量别名塞进 JSON 与 LLM Prompt。
            aliases: list[str] = [column]
            if matched_rule is not None:
                params = entry["params"]
                order = matched_rule.get("param_order") or list(params)
                abbr = matched_rule.get("abbr")
                zh_base = matched_rule.get("zh_base")
                text = _param_text(params, order)
                if abbr and text:
                    aliases.append(f"{abbr}({text})")
                if zh_base and params.get("period") is not None:
                    aliases.append(f"{params['period']}日{zh_base}")
                if entry["common"] and _is_default_params(matched_rule, params):
                    for alias in matched_rule.get("aliases", []):
                        aliases.append(alias)
                        if text:
                            aliases.append(f"{alias}({text})")
                        if params.get("period") is not None:
                            aliases.append(f"{params['period']}日{alias}")
            aliases.extend(manual.get("aliases", []))
            seen: set[str] = set()
            entry["aliases"] = [a for a in aliases if a and not (a in seen or seen.add(a))]
            factors.append(entry)

    return {
        "version": REGISTRY_VERSION,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "source": "configs/factor_catalog_llm.json（因子库列快照）",
        "price_basis_preference": list(PRICE_BASIS_PREFERENCE),
        "market_fields": MARKET_FIELDS,
        "tables": tables,
        "families": _family_section(),
        "factors": factors,
        "extra_aliases": EXTRA_ALIASES,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成因子语义注册表")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT),
                        help="因子库列快照 JSON（{table: [columns]}）")
    args = parser.parse_args()
    data = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    registry = build_registry(data)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
    with_zh = sum(1 for f in registry["factors"] if f["zh"])
    common = sum(1 for f in registry["factors"] if f["common"])
    core = sum(1 for f in registry["factors"] if f["core"])
    missing_core = sorted(
        t for t in CORE_TARGETS
        if t not in {f["canonical"] for f in registry["factors"]}
    )
    if missing_core:
        print(f"[WARN] CORE_TARGETS 中有 {len(missing_core)} 条不在因子库：{missing_core}")
    # QRE-FACTOR-DISPLAY-CONTRACT：display 自校验（单一门禁见 factor_registry.validate）
    try:
        from quant_research_engine.gui.factor_registry import FactorRegistry

        issues = FactorRegistry(registry).validate(data)
        for issue in issues:
            print(f"[WARN] display 校验：{issue}")
    except Exception as exc:  # 校验失败不阻塞生成，但必须显式告警
        print(f"[WARN] display 校验器不可用：{exc}")
    overlays = sum(1 for f in registry["factors"] if f["display"]["chart_type"] == "overlay")
    panels = len(registry["factors"]) - overlays
    print(
        f"已生成 {out}：{len(registry['factors'])} 个字段"
        f"（中文名 {with_zh} / 常用 {common} / 核心示例 {core}；"
        f"display overlay {overlays} / pane {panels}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
