"""NL 中文股票语义层：穿越事件判定、canonical 术语表、确定性 YAML 规范化。

CR-2026-11-03（NL 语义优化与转义项目）的确定性底座。定位：

- **纯函数、零 DB 零 IO**：只读 YAML mapping 与用户文本，供
  ``gui/nl_compiler.py`` 编译后处理与 ``gui/engine.py::validate_yaml`` 复用；
- **不替代表达式引擎**：本模块只判定「用户说的是不是穿越事件」与「编译产物
  有没有写成穿越事件」，不重写表达式（避免误伤持续状态语义）；
- **语义正确性是硬闸**：用户文本含「上穿/下穿/金叉/死叉」而 entry/exit 完全
  没有 ``.shift(1)`` 时，调用方必须修复回路或明确报错，**不允许静默降级**
  成当日状态（CR-2026-11-02/03 记录的错误：信号持续为真时长开/长平）。

穿越 canonical 模式（与向导 ``crosses_above/crosses_below`` 的编译产物一致）：
  上穿 ``(A > B) and (A.shift(1) <= B.shift(1))``
  下穿 ``(A < B) and (A.shift(1) >= B.shift(1))``
"""

from __future__ import annotations

import ast
from typing import Any, Iterable

import yaml

# ---------------------------------------------------------------------------
# 穿越语义词（用户文本侧）
# ---------------------------------------------------------------------------
# 只收「无歧义就是穿越事件」的说法。「突破/跌破/站上/跌回」在不同语境下既可能是
# 事件也可能是状态，不进硬闸词表（避免误伤「只要股价在均线上方就持有」这类
# 持续状态描述）；这类词交由 prompt 的语义字典引导。
CROSS_WORDS: tuple[str, ...] = (
    "上穿", "下穿", "金叉", "死叉",
    "crosses above", "crosses below", "cross above", "cross below",
    "golden cross", "dead cross", "cross up", "cross down",
)

# 持续状态词：出现这些词说明用户要的是当日状态，不是穿越事件（提示用）。
STATE_WORDS: tuple[str, ...] = (
    "大于", "小于", "高于", "低于", "超过", "跌破", "站上", "处于", "位于",
    "只要", "持续", "一直", "始终",
)

CROSS_CANONICAL = {
    "above": "(A > B) and (A.shift(1) <= B.shift(1))",
    "below": "(A < B) and (A.shift(1) >= B.shift(1))",
}

ISSUE_CROSS_WITHOUT_LAG = "cross_without_lag"
ISSUE_CROSS_PARTIAL_LAG = "cross_partial_lag"


def has_cross_semantics(description: str | None) -> bool:
    """用户文本是否含穿越语义词（上穿/下穿/金叉/死叉…）。"""
    text = (description or "").lower()
    return any(word in text for word in CROSS_WORDS)


def has_state_semantics(description: str | None) -> bool:
    """用户文本是否含持续状态词（大于/小于/只要…一直）。"""
    text = (description or "").lower()
    return any(word in text for word in STATE_WORDS)


def _signal_sides(mapping: dict[str, Any] | None) -> list[tuple[str, str]]:
    """返回 [("entry", expr), ("exit", expr)]（表达式为字符串的非空边）。"""
    signal = (mapping or {}).get("signal") or {}
    if not isinstance(signal, dict):
        return []
    sides: list[tuple[str, str]] = []
    for key in ("entry", "exit"):
        value = signal.get(key)
        if isinstance(value, str) and value.strip():
            sides.append((key, value))
    return sides


def _has_lag(expression: str) -> bool:
    """表达式是否引用上一周期（``.shift(n)`` 方法链）。"""
    return ".shift(" in (expression or "")


def _compares_two_series(expression: str) -> bool:
    """表达式里是否存在「两个序列互比」的比较（如 ``macd < macds``）。

    与常量比较（``rsi_14 > 70``）天然是当日状态，不参与单边缺 shift 的判定。
    解析失败保守返回 False（不产生猜测性告警）。
    """
    try:
        tree = ast.parse(expression or "", mode="eval")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        if all(isinstance(op, ast.Name) for op in operands):
            return True
    return False


def cross_semantic_issues(
    mapping: dict[str, Any] | None,
    description: str | None,
) -> list[dict[str, Any]]:
    """编译产物 vs 用户语义的穿越一致性校验。

    返回 issue 列表（空 = 一致）：
    - ``cross_without_lag``（error）：用户说穿越事件，而 entry/exit **都没有**
      ``.shift(1)``——就是被降级成当日状态的静默错误；
    - ``cross_partial_lag``（warning）：一侧有 shift、另一侧没有，且缺 shift 那侧
      是两个序列互比（可能是单边漏写）。只告警不阻断，避免误伤
      「金叉买入，RSI>70 卖出」这类合法混搭。
    """
    if not has_cross_semantics(description):
        return []
    sides = _signal_sides(mapping)
    if not sides:
        return []
    lagged = [(name, expr) for name, expr in sides if _has_lag(expr)]
    if not lagged:
        return [{
            "code": ISSUE_CROSS_WITHOUT_LAG,
            "severity": "error",
            "message": (
                "用户描述含「上穿/下穿/金叉/死叉」等穿越语义，但编译出的入场/出场条件"
                "完全没有引用上一周期（.shift(1)），已被降级为当日状态：信号在区间内"
                "持续为真时会重复触发，而不是只在穿越当日触发一次。"
            ),
            "hint": (
                "穿越事件必须写成：上穿 (A > B) and (A.shift(1) <= B.shift(1))；"
                "下穿 (A < B) and (A.shift(1) >= B.shift(1))。"
                "若你要的是持续状态（不是穿越事件），请把描述改成「大于/小于」后重新编译。"
            ),
        }]
    issues: list[dict[str, Any]] = []
    for name, expr in sides:
        if _has_lag(expr):
            continue
        if _compares_two_series(expr):
            issues.append({
                "code": ISSUE_CROSS_PARTIAL_LAG,
                "severity": "warning",
                "side": name,
                "message": (
                    f"{name} 条件没有引用上一周期（.shift(1)），且是两个指标互比："
                    "若这一侧也是穿越语义，需要补 .shift(1)。"
                ),
                "hint": CROSS_CANONICAL["above"] + " / " + CROSS_CANONICAL["below"],
            })
    return issues


def cross_semantic_issues_from_yaml(
    yaml_text: str,
    description: str | None,
) -> list[dict[str, Any]]:
    """YAML 文本版入口（解析失败返回空，由调用方的结构校验负责报错）。"""
    try:
        mapping = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return []
    if not isinstance(mapping, dict):
        return []
    return cross_semantic_issues(mapping, description)


def cross_fix_prompt(
    description: str,
    yaml_text: str,
    issues: Iterable[dict[str, Any]] | None = None,
) -> str:
    """穿越语义修复回路的回喂提示（与 ``nl_compiler._fixup_prompt`` 同风格）。"""
    lines = [
        "用户需求：" + description,
        "",
        "你上次输出的 YAML 把穿越事件写成了当日状态（没有用 .shift(1) 引用上一周期）。",
    ]
    for issue in issues or []:
        lines.append(f"- {issue.get('message', '')}")
        if issue.get("hint"):
            lines.append(f"  正确写法：{issue['hint']}")
    lines += [
        "",
        "规则重申：",
        "- 「大于/小于/高于/低于」= 当日状态，不要加 .shift(1)；",
        "- 「上穿/下穿/金叉/死叉」= 穿越事件，必须用 .shift(1)：",
        f"  上穿：{CROSS_CANONICAL['above']}",
        f"  下穿：{CROSS_CANONICAL['below']}",
        "- MACD 金叉 = DIF 上穿 DEA（macd_12_26_9 上穿 macds_12_26_9）；"
        "死叉 = DIF 下穿 DEA。",
        "",
        "上次输出：",
        yaml_text,
        "",
        "请只输出修正后的完整 YAML（只改 signal.entry/exit 的穿越条件，"
        "因子名、持仓、风控等其余部分不变；禁止编造列名）。",
    ]
    return "\n".join(lines)


def format_semantic_error(issues: Iterable[dict[str, Any]]) -> str:
    """语义校验失败的中文报错（提交前可见，绝不静默降级）。"""
    lines = ["该策略未通过语义校验："]
    for issue in issues or []:
        lines.append(f"- {issue.get('message', '')}")
        if issue.get("hint"):
            lines.append(f"  {issue['hint']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# canonical 中文语义字典（CR-2026-11-03 §4）
# ---------------------------------------------------------------------------
# 原则：因子命名仍走 configs/factor_aliases.json 与 factor_registry.json 的既有
# 别名解析；本字典只补「表达式级」语义（穿越/位置/形态），不重复造因子命名。
# 每条: (中文说法, 语义, canonical 写法/说明)
SEMANTIC_DICTIONARY: tuple[dict[str, str], ...] = (
    {"term": "上穿 / 金叉", "meaning": "穿越事件：本周期在上方，上一周期不在上方",
     "canonical": "(A > B) and (A.shift(1) <= B.shift(1))"},
    {"term": "下穿 / 死叉", "meaning": "穿越事件：上穿的镜像",
     "canonical": "(A < B) and (A.shift(1) >= B.shift(1))"},
    {"term": "快线（MACD 语境）", "meaning": "DIF",
     "canonical": "factors.stock_daily_momentum_close.macd_12_26_9"},
    {"term": "慢线 / 信号线 / DEA（MACD 语境）", "meaning": "DEA（信号线）",
     "canonical": "factors.stock_daily_momentum_close.macds_12_26_9"},
    {"term": "N 日均线", "meaning": "简单移动平均（用户说「指数」时才用 EMA）",
     "canonical": "factors.stock_daily_overlap_close.sma_N（如 sma_5、sma_20、sma_200）"},
    {"term": "N 日指数均线 / EMA", "meaning": "指数移动平均",
     "canonical": "factors.stock_daily_overlap_close.ema_N"},
    {"term": "大于 / 小于 / 高于 / 低于", "meaning": "当日状态（不是穿越事件，禁止加 .shift(1)）",
     "canonical": "A > B / A < B"},
    {"term": "回调 X%", "meaning": "相对近 N 日高点回撤达到 X%",
     "canonical": "close <= close.rolling(N).max() * (1 - X)"},
    {"term": "支撑 / 支撑位", "meaning": "价格守在近 N 日低点之上",
     "canonical": "close >= low.rolling(N).min()"},
    {"term": "压力 / 压力位", "meaning": "价格被近 N 日高点压住",
     "canonical": "close <= high.rolling(N).max()"},
    {"term": "放量", "meaning": "成交量相对近 N 日均量放大",
     "canonical": "vol > vol.rolling(N).mean() * X"},
    {"term": "缩量", "meaning": "成交量相对近 N 日均量缩小",
     "canonical": "vol < vol.rolling(N).mean() * X"},
    {"term": "突破（近 N 日高点）", "meaning": "价格上穿近 N 日高点（穿越事件）",
     "canonical": "close > high.rolling(N).max().shift(1)"},
)

# 形态类语义可用的预计算因子列（库内已落库，优先引用；没有的周期才用
# rolling 方法链，且**禁止编造列名**——写不出来的登记为缺因子申请）。
PRECOMPUTED_PATTERN_COLUMNS: tuple[dict[str, str], ...] = (
    {"semantic": "近 N 日最高价（区间最高）", "column": "factors.stock_daily_volatility_close.hhv_N",
     "example": "hhv_20"},
    {"semantic": "近 N 日最低价（区间最低）", "column": "factors.stock_daily_volatility_close.llv_N",
     "example": "llv_20"},
    {"semantic": "近 N 日成交量均线", "column": "factors.stock_daily_volume_close.vol_sma_N",
     "example": "vol_sma_20"},
)


def render_semantic_dictionary() -> str:
    """渲染进 prompt 的 canonical 语义字典块（紧凑、确定性）。"""
    lines = ["中文语义词典（canonical → 写法；因子列名仍以真实因子目录为准，禁止编造）："]
    for item in SEMANTIC_DICTIONARY:
        lines.append(f"- {item['term']}：{item['meaning']} → {item['canonical']}")
    lines.append("形态类可用预计算列：" + "；".join(
        f"{p['semantic']}={p['column']}（例 {p['example']}）" for p in PRECOMPUTED_PATTERN_COLUMNS))
    lines.append(
        "DSL 能力边界：不支持裸函数调用（如 rolling_max(close, N) 非法）；"
        "滚动统计只许用方法链 close.rolling(N).max() / low.rolling(N).min() / "
        "vol.rolling(N).mean()，或直接引用上表的预计算列。"
    )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# canonical YAML 规范化（确定性输出）
# ---------------------------------------------------------------------------

CANONICAL_TOP_ORDER: tuple[str, ...] = (
    "experiment", "data", "universe", "signal", "holding", "risk", "portfolio", "evaluation",
)
_CANONICAL_SUBORDER: dict[str, tuple[str, ...]] = {
    "experiment": ("name", "market_profile", "frequency"),
    "data": ("market_fields", "factor_fields"),
    "universe": ("exclude_st", "exclude_suspended", "exclude_risk_warning",
                 "min_listing_days", "min_amount"),
    "signal": ("entry", "exit"),
    "holding": ("max_holding_days",),
    "risk": ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct"),
    "portfolio": ("weight_model", "score_column", "volatility_column",
                  "rebalance_interval_days"),
    "evaluation": ("forward_return_horizons", "quantiles"),
}
MARKET_FIELDS_ORDER: tuple[str, ...] = (
    "open", "high", "low", "close", "pre_close", "vol", "amount",
)


class _CanonicalDumper(yaml.SafeDumper):
    """标量列表走 flow 风格（``[open, high, …]``），与 few-shot 输出一致。"""

    def represent_sequence(self, tag: str, sequence: Any, flow_style: bool | None = None):
        scalar_only = all(
            isinstance(item, (str, int, float, bool)) for item in sequence
        )
        return super().represent_sequence(tag, sequence, flow_style=scalar_only or flow_style)


def _ordered(mapping: dict[str, Any], order: Iterable[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in order:
        if key in mapping:
            out[key] = mapping[key]
    for key in sorted(k for k in mapping if k not in out):
        out[key] = mapping[key]
    return out


def canonical_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """键序稳定化 + market_fields/factor_fields 规范化（就地返回新 mapping）。"""
    result = _ordered(mapping, CANONICAL_TOP_ORDER)
    for section, order in _CANONICAL_SUBORDER.items():
        value = result.get(section)
        if isinstance(value, dict):
            result[section] = _ordered(value, order)
    data = result.get("data")
    if isinstance(data, dict):
        market = data.get("market_fields")
        if isinstance(market, list):
            known = [f for f in MARKET_FIELDS_ORDER if f in market]
            extra = sorted(f for f in market if f not in MARKET_FIELDS_ORDER)
            data["market_fields"] = known + extra
        factors = data.get("factor_fields")
        if isinstance(factors, dict):
            data["factor_fields"] = {k: factors[k] for k in sorted(factors)}
    return result


def canonical_yaml_text(mapping: dict[str, Any]) -> str:
    """确定性 YAML 序列化：键序稳定、无注释、无 Markdown 围栏、标量列表 flow 风格。

    同一份 mapping 重复调用产出逐字节一致；同一句中文描述即使 LLM 每次的键序/
    列表风格略有差异，规范化后也收敛到同一形态（CR-2026-11-03 DoD 3）。
    """
    return yaml.dump(
        canonical_mapping(mapping),
        Dumper=_CanonicalDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )


def canonicalize_strategy_yaml(yaml_text: str) -> str:
    """YAML 文本 → canonical YAML 文本（解析失败原样返回，交给结构校验报错）。"""
    try:
        mapping = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return yaml_text
    if not isinstance(mapping, dict):
        return yaml_text
    return canonical_yaml_text(mapping)
