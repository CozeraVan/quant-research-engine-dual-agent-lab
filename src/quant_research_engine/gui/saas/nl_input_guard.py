"""QRE-SAAS-NL-A1：自然语言输入前置校验（规则层 + DeepSeek 裁判）。

职责边界（批准计划见 08_IMPLEMENTATION_BRIEF.md QRE-SAAS-NL-A1，DeepSeek 方向：
用户明确不配置 Jev/TypeSafe，改用现有 QRE_NL_LLM_* DeepSeek 通道）：
- 规则层是纯函数、零 IO：在 NL 编译的空输入检查之后、prompt/缓存/配额/LLM
  之前执行，输出 pass/review/reject 三态与中文缺失项/合法示例。
- DeepSeek 裁判是第二道防线，**复用现有编译通道**：`gui.nl_compiler.call_llm`
  注入独立裁判 system prompt，要求严格 JSON 三分类
  （strategy/not_strategy/unclear）；解析失败/超时/HTTP/结构错误一律降级
  规则层，绝不伪装裁判成功，不伪造置信度，不记录策略文本或密钥。
- 裁判只在缓存 miss 且配额计数后运行（成本控制由 app.py 编排保证）；
  裁判结论只把 pass 升级为 review，**从不硬拒**。
- 不改 YAML 编译、缓存 key、配额数值、worker、引擎。
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from quant_research_engine.gui import nl_compiler

GUARD_VERSION = "2026-10-26.2"

DECISION_PASS = "pass"
DECISION_REVIEW = "review"
DECISION_REJECT = "reject"

MIN_LENGTH = 6            # strip 后少于此长度直接拒（"买"、"abc" 类）
NO_SEMANTIC_MAX_LEN = 16  # 无任何交易语义的短文本直接拒；长文本降级 review
RECOGNIZABLE_RATIO = 0.6  # 可识别字符占比下限，低于则判乱码

# DeepSeek 裁判：独立 system prompt（与编译 prompt 完全不同），严格 JSON 三分类
REFEREE_SYSTEM_PROMPT = """你是交易策略描述的分类裁判。判断用户输入的文本是否是明确的股票交易策略描述（包含可执行的入场或出场条件、指标或规则）。
只输出一行严格 JSON（不要 Markdown 围栏、不要任何解释文字）：
{"label":"strategy"}、{"label":"not_strategy"} 或 {"label":"unclear"}
判定标准：
- strategy：明确的交易策略描述，包含入场或出场条件、指标或规则
- not_strategy：与交易策略无关的闲聊、乱码、纯数字或不含任何交易规则的文本
- unclear：可能是交易策略但信息不足或表述模糊，无法确定"""
REFEREE_TIMEOUT_SECONDS = 30  # 裁判只做分类，超时短于编译（60s）

# 入场语义词（中英文常见交易说法；指标别名不算乱码，单独一档）
ENTRY_WORDS = (
    "买入", "买进", "购入", "入场", "开仓", "做多", "建仓", "金叉", "上穿", "突破",
    "向上突破", "翻多", "加仓", "抄底", "低吸", "看涨", "进场", "买",
    "buy", "entry", "enter", "long", "golden cross", "cross above",
    "crosses above", "breakout", "break above", "buy signal", "go long",
)
# 出场语义词
EXIT_WORDS = (
    "卖出", "出售", "离场", "止盈", "止损", "死叉", "下穿", "跌破",
    "向下突破", "做空", "平仓", "减仓", "清仓", "高抛", "看跌", "出场", "卖",
    "sell", "exit", "close the position", "stop loss", "stop-loss",
    "take profit", "take-profit", "dead cross", "cross below",
    "crosses below", "breakdown", "break below", "sell signal", "go short",
)
# 指标/机制词：用于「无交易语义」判定，避免把含指标的非常规表述误杀
INDICATOR_WORDS = (
    "macd", "ema", "rsi", "kdj", "boll", "bollinger", "sma", "wma", "obv",
    "atr", "cci", "dmi", "sar", "均线", "移动平均", "布林", "动量", "波动",
    "成交量", "量价", "换手", "交叉", "背离", "趋势", "反转", "网格", "海龟",
    "指标", "因子", "信号", "策略", "股票", "股价", "大盘",
)
# 领域语境词：股票/价格/市场/交易度量语境。入出场词 + 领域语境才判 pass——
# 只有通用买卖动词（买房/买菜/买机票）不足以判定为交易策略。
DOMAIN_WORDS = (
    # 价格与K线
    "股价", "收盘", "开盘", "最高价", "最低价", "高价", "低点", "高点",
    "涨停", "跌停", "阳线", "阴线", "下影线", "上影线", "k线", "日线",
    "分时", "均价", "委托价", "成交价",
    # 市场与标的
    "股票", "a股", "大盘", "指数", "板块", "股市", "证券", "个股", "港股",
    "美股", "行情",
    # 交易与度量
    "交易日", "持仓", "仓位", "委托", "下单", "成交", "换手", "量比",
    "年化", "夏普", "回撤", "胜率", "盈亏", "收益", "估值", "基本面",
    "上涨", "下跌", "涨幅", "跌幅", "反弹", "回调",
)
# 强交易词：入出场词中本身即交易语境的（金叉/死叉/止损/做多…）
STRONG_TRADING_WORDS = (
    "金叉", "死叉", "上穿", "下穿", "突破", "跌破", "做多", "做空", "开仓",
    "平仓", "建仓", "抄底", "止盈", "止损", "加仓", "减仓", "清仓", "离场",
    "入场", "翻多", "高抛", "低吸", "看涨", "看跌",
    "golden cross", "dead cross", "stop loss", "stop-loss", "take profit",
    "take-profit", "breakout", "breakdown",
)

LEGAL_EXAMPLES = (
    "MACD 金叉买入，死叉卖出",
    "EMA 上穿 20 日均线时买入，下穿时卖出",
    "RSI 低于 30 买入，高于 70 卖出",
    "收盘价突破 20 日高点买入，跌破 10 日低点卖出",
)

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_DIGITS_ONLY = re.compile(r"^[\d\s.,+\-*/%]+$")
# 可识别字符 = 字母/数字（含中英文）+ 空白 + 常用中英文标点；表情/乱码符号不在内
_PUNCT = set(" \t\r\n，。！？、；：""''（）()【】[]<>《》%+-*/.,;:!?\"'`~@#$^&_|=")


def _recognizable_ratio(text: str) -> float:
    if not text:
        return 0.0
    ok = sum(1 for ch in text if ch.isalnum() or ch.isspace() or ch in _PUNCT)
    return ok / len(text)


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(w in low for w in words)


def _has_domain_context(text: str) -> bool:
    """股票/价格/指标/交易语境：领域词、指标词或强交易词任一命中。"""
    return (_has_any(text, DOMAIN_WORDS) or _has_any(text, INDICATOR_WORDS)
            or _has_any(text, STRONG_TRADING_WORDS))


def rule_check(description: str) -> dict[str, Any]:
    """纯规则三态校验。返回 decision/reasons/missing/examples/rule。"""
    text = (description or "").strip()
    reasons: list[str] = []
    missing: list[str] = []

    # --- 硬拒（不可绕过）---
    if len(text) < MIN_LENGTH:
        return _reject([f"输入过短（至少 {MIN_LENGTH} 个字符）"])
    if not _CJK.search(text) and not _LATIN.search(text):
        return _reject(["输入不包含任何中英文字符（疑似纯数字或符号）"])
    if _DIGITS_ONLY.match(text):
        return _reject(["输入是纯数字（疑似误输入数字或日期）"])
    if _recognizable_ratio(text) < RECOGNIZABLE_RATIO:
        return _reject(["输入包含大量无法识别的字符（疑似乱码）"])
    has_entry = _has_any(text, ENTRY_WORDS)
    has_exit = _has_any(text, EXIT_WORDS)
    has_indicator = _has_any(text, INDICATOR_WORDS)
    if not has_entry and not has_exit and not has_indicator and len(text) < NO_SEMANTIC_MAX_LEN:
        return _reject(["未识别到任何交易策略语义（既无入场/出场条件，也无指标或交易关键词）"])

    # --- 软复核（可 force 绕过）---
    if not has_entry:
        missing.append("entry")
        reasons.append("缺少入场条件（如：金叉 / 突破 / 买入 / buy）")
    if not has_exit:
        missing.append("exit")
        reasons.append("缺少出场条件（如：死叉 / 止损 / 止盈 / 卖出 / sell）")
    if has_entry and has_exit and not _has_domain_context(text):
        reasons.append("未识别到股票或交易语境（如：收盘价、均线、涨停、换手率、持仓等）——只有买卖动词不足以判定为交易策略")
    if not has_entry and not has_exit and not has_indicator:
        reasons.append("未识别到指标或交易关键词，请补充具体规则")

    if reasons:
        return {
            "decision": DECISION_REVIEW,
            "rule": DECISION_REVIEW,
            "reasons": reasons,
            "missing": missing,
            "examples": list(LEGAL_EXAMPLES),
        }
    return {"decision": DECISION_PASS, "rule": DECISION_PASS,
            "reasons": [], "missing": [], "examples": []}


def _reject(reasons: list[str]) -> dict[str, Any]:
    return {"decision": DECISION_REJECT, "rule": DECISION_REJECT,
            "reasons": reasons, "missing": [], "examples": list(LEGAL_EXAMPLES)}


# ---------------------------------------------------------------- DeepSeek 裁判
def build_referee(config: dict[str, str] | None) -> Callable[[str], dict[str, Any]] | None:
    """返回裁判 callable；LLM 未配置（config 为 None）时返回 None。"""
    if not config:
        return None
    return lambda description: referee_classify(description, config)


def _parse_referee_label(raw: str) -> str:
    """稳健解析裁判输出：去 fenced block → 截取 JSON 对象 → 校验三分类。"""
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no json object")
    data = json.loads(text[start:end + 1])
    label = data.get("label")
    if label not in ("strategy", "not_strategy", "unclear"):
        raise ValueError(f"bad label: {label!r}")
    return label


def referee_classify(description: str, config: dict[str, str], *,
                     call_llm_fn: Callable[..., Any] | None = None) -> dict[str, Any]:
    """调用 DeepSeek 裁判（复用 nl_compiler.call_llm，注入独立裁判 prompt）。

    返回 {"ok": True, "label": strategy|not_strategy|unclear} 或
    {"ok": False, "status": "llm_error"|"bad_structure"}。
    任何故障都由调用方降级为规则层，绝不伪装裁判成功、不伪造置信度。
    """
    fn = call_llm_fn or nl_compiler.call_llm
    try:
        raw = fn(description, config, system_prompt=REFEREE_SYSTEM_PROMPT,
                 timeout=REFEREE_TIMEOUT_SECONDS)
    except Exception:
        return {"ok": False, "status": "llm_error"}
    try:
        return {"ok": True, "label": _parse_referee_label(raw)}
    except Exception:
        return {"ok": False, "status": "bad_structure"}


def evaluate_input(description: str, *,
                   referee: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """规则层 + 可选 DeepSeek 裁判的组合决策。

    - 规则层硬拒（reject）直接返回，不再调用裁判；
    - 规则层 pass 时裁判可升级为 review；裁判故障/未配置则保持规则层结论；
    - 裁判任何结论都**不会**把输入变成 reject。
    """
    result = rule_check(description)
    if result["decision"] == DECISION_REJECT:
        result["referee"] = None
        return result
    referee_view: dict[str, Any] | None = None
    if referee is not None:
        try:
            outcome = referee(description)
        except Exception:
            outcome = {"ok": False, "status": "llm_error"}
        if outcome.get("ok"):
            label = outcome.get("label")
            referee_view = {"status": "ok", "label": label}
            if label == "not_strategy":
                result["decision"] = DECISION_REVIEW
                result["reasons"] = list(result["reasons"]) + [
                    "DeepSeek 校验认为这条描述与交易策略无关，请确认后继续"]
            elif label == "unclear":
                result["decision"] = DECISION_REVIEW
                result["reasons"] = list(result["reasons"]) + [
                    "DeepSeek 校验无法确定这是否是交易策略，请补充具体规则或确认后继续"]
            # label == "strategy"：维持规则层结论
        else:
            referee_view = {"status": outcome.get("status") or "llm_error"}
    result["referee"] = referee_view
    if result["decision"] == DECISION_REVIEW and not result.get("examples"):
        result["examples"] = list(LEGAL_EXAMPLES)
    return result
