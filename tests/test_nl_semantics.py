"""CR-2026-11-03 NL 语义优化与转义项目：穿越语义 + 语义字典 + canonical 输出。

覆盖四件事：
1. prompt 合同：`_DSL_DOC` 含「穿越事件必须用 .shift(1)」的 canonical 模式、
   不含旧「上穿请改写为当周期比较」的降级指令；few-shot 含 SMA/MACD 穿越示例；
2. 编译后语义硬闸：用户说上穿/下穿/金叉/死叉而 YAML 没有 .shift(1) → 回喂修复
   回路；仍不合法 → code=semantic_cross_missing 明确报错（绝不静默降级）；
3. 状态语义不误伤：rsi<20 / sma60>sma200 这类持续状态不得被加 .shift(1)；
4. canonical 输出确定性：同一 mapping / 乱序输入 → 逐字节一致，无 Markdown 围栏。

真实 DeepSeek 冒烟与信号级验证见 tests/test_nl_semantics_smoke.py（单独跑，
消耗真实额度）。
"""

from __future__ import annotations

import pytest
import pandas as pd
import yaml

from quant_research_engine.evaluation.signals import evaluate_expression_signal
from quant_research_engine.gui import nl_semantics as sem
from quant_research_engine.gui.nl_compiler import (
    MAX_FIX_RETRIES,
    build_system_prompt,
    compile_nl,
)

ENV = {"QRE_NL_LLM_BASE_URL": "http://fake", "QRE_NL_LLM_API_KEY": "k",
       "QRE_NL_LLM_MODEL": "m"}

POOL = {"macd_12_26_9", "macds_12_26_9", "macdh_12_26_9", "rsi_14"}


def _lookup(table_map=None):
    tables = {
        "factors.stock_daily_momentum_close": set(POOL),
        "factors.stock_daily_overlap_close": {"ema_5", "ema_20", "sma_5", "sma_20",
                                              "sma_60", "sma_200"},
        "factors.stock_daily_overlap_typical_price": {"ema_200"},
    }
    if table_map:
        tables.update(table_map)
    return lambda table: tables.get(table, set())


def _http(replies):
    """按顺序返回 replies 的 stub LLM；记录每次收到的 user prompt。"""
    calls: list[str] = []

    def http_post(url, headers, payload, timeout):
        calls.append(payload["messages"][-1]["content"])
        return {"choices": [{"message": {"content": replies[len(calls) - 1]}}]}

    return http_post, calls


def _spec(entry, exit_=None, **factors):
    factor_fields = factors or {
        "dif": "factors.stock_daily_momentum_close.macd_12_26_9",
        "dea": "factors.stock_daily_momentum_close.macds_12_26_9",
    }
    spec = {
        "experiment": {"name": "t", "market_profile": "ashare_daily_default",
                       "frequency": "daily"},
        "data": {"market_fields": ["open", "high", "low", "close", "pre_close", "vol", "amount"],
                 "factor_fields": factor_fields},
        "universe": {"exclude_st": True, "exclude_suspended": True,
                     "exclude_risk_warning": True, "min_listing_days": 120},
        "signal": {"entry": entry},
        "holding": {"max_holding_days": 0},
        "evaluation": {"forward_return_horizons": [1, 3, 5], "quantiles": 5},
    }
    if exit_ is not None:
        spec["signal"]["exit"] = exit_
    return spec


# --- prompt 合同 ---


def test_dsl_doc_drops_old_degradation_instruction():
    prompt = build_system_prompt()
    assert "上穿请改写为当周期比较" not in prompt
    assert "并明白这是当日状态而非穿越事件" not in prompt
    assert "不支持跨周期引用" not in prompt


def test_dsl_doc_states_cross_canonical_patterns():
    prompt = build_system_prompt()
    assert "上穿/下穿/金叉/死叉" in prompt
    assert "(A > B) and (A.shift(1) <= B.shift(1))" in prompt
    assert "(A < B) and (A.shift(1) >= B.shift(1))" in prompt
    # 大于/小于是当日状态，禁止乱加 shift
    assert "禁止加 .shift(1)" in prompt
    # MACD 金叉 = DIF 上穿 DEA，列名来自真实因子库
    assert "macd_12_26_9" in prompt and "macds_12_26_9" in prompt


def test_dsl_doc_documents_method_chain_capability():
    prompt = build_system_prompt()
    # 先核实过的 DSL 能力：裸函数调用非法，方法链合法
    assert "rolling_max(close, N) 非法" in prompt
    assert "close.rolling(N).max()" in prompt


def test_few_shot_contains_cross_examples():
    prompt = build_system_prompt()
    assert "示例 3" in prompt and "示例 4" in prompt
    assert "SMA5 上穿 SMA200" in prompt
    assert "MACD 金叉买入，死叉卖出" in prompt
    assert "nl_sma5_cross_sma200" in prompt
    assert "nl_macd_golden_dead_cross" in prompt


def test_semantic_dictionary_injected_without_fabricated_columns():
    prompt = build_system_prompt()
    assert "中文语义词典" in prompt
    for term in ("金叉", "死叉", "快线", "慢线", "支撑", "压力", "放量", "突破", "回调"):
        assert term in prompt
    # 形态类优先引用已落库的预计算列（hhv/llv/vol_sma 真实存在）
    assert "hhv_20" in prompt and "llv_20" in prompt and "vol_sma_20" in prompt


# --- 语义判定（纯函数） ---


@pytest.mark.parametrize("text", [
    "SMA5 上穿 SMA200 买入", "macd 金叉买入，死叉卖出", "EMA 下穿 20 日均线卖出",
    "golden cross buy", "dead cross sell", "快线 crosses above 慢线",
])
def test_has_cross_semantics_positive(text):
    assert sem.has_cross_semantics(text) is True


@pytest.mark.parametrize("text", [
    "RSI 小于 20 买入", "收盘价大于 20 日均线持有", "SMA60 大于 SMA200 时持股",
    "RSI 低于 30 买入，高于 70 卖出", "",
])
def test_has_cross_semantics_negative(text):
    assert sem.has_cross_semantics(text) is False


def test_state_semantics_without_cross_words_no_issue():
    mapping = _spec("rsi_14 < 20", "rsi_14 > 70")
    assert sem.cross_semantic_issues(mapping, "RSI 小于 20 买入，大于 70 卖出") == []


def test_cross_description_without_lag_is_error():
    issues = sem.cross_semantic_issues(_spec("dif > dea", "dif < dea"), "MACD 金叉买入，死叉卖出")
    assert len(issues) == 1
    assert issues[0]["code"] == sem.ISSUE_CROSS_WITHOUT_LAG
    assert issues[0]["severity"] == "error"
    assert ".shift(1)" in issues[0]["hint"]


def test_cross_description_with_lag_passes():
    mapping = _spec("(dif > dea) and (dif.shift(1) <= dea.shift(1))",
                    "(dif < dea) and (dif.shift(1) >= dea.shift(1))")
    assert sem.cross_semantic_issues(mapping, "MACD 金叉买入，死叉卖出") == []


def test_partial_lag_only_warns_on_series_vs_series():
    # 一侧穿越、一侧与常量比较（合法混搭）→ 无告警
    mapping = _spec("(dif > dea) and (dif.shift(1) <= dea.shift(1))", "rsi_14 > 70",
                    rsi_14="factors.stock_daily_momentum_close.rsi_14")
    assert sem.cross_semantic_issues(mapping, "MACD 金叉买入，RSI 大于 70 卖出") == []
    # 一侧穿越、另一侧两个序列互比且无 shift → warning（可能是单边漏写）
    mapping2 = _spec("(dif > dea) and (dif.shift(1) <= dea.shift(1))", "dea > macdh",
                     macdh="factors.stock_daily_momentum_close.macdh_12_26_9")
    issues = sem.cross_semantic_issues(mapping2, "MACD 金叉买入，DEA 上穿 MACD 柱卖出")
    assert [i["code"] for i in issues] == [sem.ISSUE_CROSS_PARTIAL_LAG]
    assert issues[0]["severity"] == "warning"


def test_cross_fix_prompt_carries_canonical_pattern():
    text = sem.cross_fix_prompt("MACD 金叉买入，死叉卖出", "entry: dif > dea",
                                [{"message": "m", "hint": "h"}])
    assert "用户需求" in text and "MACD 金叉买入，死叉卖出" in text
    assert sem.CROSS_CANONICAL["above"] in text and sem.CROSS_CANONICAL["below"] in text
    assert "禁止编造列名" in text


# --- 编译后语义硬闸（stub LLM） ---


def _cross_yaml(entry, exit_):
    return yaml.safe_dump(_spec(entry, exit_), allow_unicode=True, sort_keys=False)


def test_compile_cross_description_degraded_then_repaired():
    """第一轮把金叉写成当日状态 → 回喂修复回路 → 第二轮补上 .shift(1)。"""
    bad = _cross_yaml("dif > dea", "dif < dea")
    good = _cross_yaml("(dif > dea) and (dif.shift(1) <= dea.shift(1))",
                       "(dif < dea) and (dif.shift(1) >= dea.shift(1))")
    http, calls = _http([bad, good])
    result = compile_nl("MACD 金叉买入，死叉卖出", env=ENV, http_post=http,
                        column_lookup=_lookup())
    assert result["ok"] is True, result
    assert ".shift(1)" in result["yaml"]
    assert result["fix_attempts"] == 1
    assert len(calls) == 2
    assert ".shift(1)" in calls[1]  # 修复提示带 canonical 写法


def test_compile_cross_description_never_silently_degrades():
    """LLM 始终不写 .shift(1) → 明确报错，不返回降级 YAML 当成功。"""
    bad = _cross_yaml("dif > dea", "dif < dea")
    http, calls = _http([bad] * (1 + MAX_FIX_RETRIES))
    result = compile_nl("MACD 金叉买入，死叉卖出", env=ENV, http_post=http,
                        column_lookup=_lookup())
    assert result["ok"] is False
    assert result["code"] == "semantic_cross_missing"
    assert "穿越" in result["error"] and ".shift(1)" in result["error"]
    assert result["semantic_issues"][0]["code"] == sem.ISSUE_CROSS_WITHOUT_LAG
    assert result["yaml"]  # 草稿仍返回给用户编辑
    assert len(calls) == 1 + MAX_FIX_RETRIES


def test_compile_cross_gate_works_without_factor_lookup():
    """因子库不可用（lookup=None）时语义硬闸依然生效。"""
    bad = _cross_yaml("dif > dea", "dif < dea")
    http, _calls = _http([bad] * (1 + MAX_FIX_RETRIES))
    result = compile_nl("MACD 金叉买入，死叉卖出", env=ENV, http_post=http,
                        column_lookup=None)
    assert result["ok"] is False
    assert result["code"] == "semantic_cross_missing"


def test_compile_state_description_not_forced_to_lag():
    """持续状态描述：不得被加 .shift(1)，也不需要修复回路（一轮通过）。"""
    yaml_text = yaml.safe_dump(
        _spec("rsi_14 < 20", "rsi_14 > 70",
              rsi_14="factors.stock_daily_momentum_close.rsi_14"),
        allow_unicode=True, sort_keys=False)
    http, calls = _http([yaml_text])
    result = compile_nl("RSI 小于 20 买入，大于 70 卖出", env=ENV, http_post=http,
                        column_lookup=_lookup())
    assert result["ok"] is True, result
    assert ".shift(" not in result["yaml"]
    assert len(calls) == 1


def test_compile_mixed_cross_and_state_sides():
    """金叉买入 + 常量状态卖出：一侧 shift 即可通过，另一侧不被误加 shift。"""
    yaml_text = yaml.safe_dump(
        _spec("(dif > dea) and (dif.shift(1) <= dea.shift(1))", "rsi_14 > 70",
              rsi_14="factors.stock_daily_momentum_close.rsi_14"),
        allow_unicode=True, sort_keys=False)
    http, calls = _http([yaml_text])
    result = compile_nl("MACD 金叉买入，RSI 大于 70 卖出", env=ENV, http_post=http,
                        column_lookup=_lookup())
    assert result["ok"] is True, result
    assert len(calls) == 1


# --- canonical 输出 ---


def test_canonical_yaml_is_deterministic_and_fence_free():
    text = sem.canonical_yaml_text(_spec("dif > dea", "dif < dea"))
    assert "```" not in text and "#" not in text
    assert sem.canonical_yaml_text(yaml.safe_load(text)) == text


def test_canonical_yaml_normalizes_key_and_list_order():
    shuffled = _spec("dif > dea", "dif < dea")
    shuffled = dict(reversed(list(shuffled.items())))
    shuffled["data"]["factor_fields"] = dict(
        reversed(list(shuffled["data"]["factor_fields"].items())))
    shuffled["data"]["market_fields"] = ["vol", "close", "open", "high", "low",
                                         "pre_close", "amount"]
    assert sem.canonical_yaml_text(shuffled) == sem.canonical_yaml_text(
        _spec("dif > dea", "dif < dea"))
    dumped = sem.canonical_yaml_text(shuffled)
    assert "market_fields: [open, high, low, close, pre_close, vol, amount]" in dumped


def test_compile_output_is_canonicalized():
    """LLM 输出键序混乱 → 编译结果收敛到 canonical 形态。"""
    messy = ("evaluation:\n  quantiles: 5\n  forward_return_horizons: [1, 3, 5]\n"
             "signal:\n  entry: rsi_14 < 20\n"
             "data:\n  factor_fields:\n    rsi_14: factors.stock_daily_momentum_close.rsi_14\n"
             "  market_fields: [vol, close, open, high, low, pre_close, amount]\n"
             "experiment:\n  frequency: daily\n  market_profile: ashare_daily_default\n"
             "  name: t\nholding:\n  max_holding_days: 5\n")
    http, _calls = _http([messy])
    result = compile_nl("RSI 小于 20 买入", env=ENV, http_post=http,
                        column_lookup=_lookup())
    assert result["ok"] is True
    assert result["yaml"].startswith("experiment:\n")
    assert result["yaml"] == sem.canonicalize_strategy_yaml(result["yaml"])
    # 同一输入重复编译（stub 恒定输出）产出一致
    http2, _c2 = _http([messy])
    again = compile_nl("RSI 小于 20 买入", env=ENV, http_post=http2,
                       column_lookup=_lookup())
    assert again["yaml"] == result["yaml"]


# --- 语义字典（CR-2026-11-03 §4）---


def test_semantic_dictionary_covers_required_terms():
    terms = {item["term"] for item in sem.SEMANTIC_DICTIONARY}
    joined = " ".join(terms)
    for required in ("上穿", "下穿", "金叉", "死叉", "快线", "慢线", "支撑", "压力",
                     "放量", "缩量", "突破", "回调", "日均线", "指数均线"):
        assert required in joined, required
    by_term = {item["term"]: item for item in sem.SEMANTIC_DICTIONARY}
    # 快线=DIF / 慢线=DEA 的列名必须来自真实因子库（禁止编造）
    assert by_term["快线（MACD 语境）"]["canonical"].endswith("macd_12_26_9")
    assert by_term["慢线 / 信号线 / DEA（MACD 语境）"]["canonical"].endswith("macds_12_26_9")
    # 形态类语义只准用方法链（裸函数调用会被安全闸拒绝）
    for term in ("回调 X%", "支撑 / 支撑位", "压力 / 压力位", "放量", "缩量",
                 "突破（近 N 日高点）"):
        canonical = by_term[term]["canonical"]
        assert ".rolling(" in canonical, (term, canonical)
        assert "rolling_max(" not in canonical and "rolling_mean(" not in canonical


def test_precomputed_pattern_columns_exist_in_real_library():
    """字典推荐的预计算列必须真实存在于因子库快照（否则就是编造列名）。"""
    from quant_research_engine.gui.factor_catalog_llm import catalog_column_lookup

    lookup = catalog_column_lookup()
    assert lookup is not None
    for item in sem.PRECOMPUTED_PATTERN_COLUMNS:
        table, column = item["column"].rsplit(".", 1)
        assert item["example"] in lookup(table), item


def test_dsl_supports_rolling_method_chains_and_rejects_bare_calls():
    """先核实再写字典（CR-2026-11-03 §4 注）：滚动统计只能用方法链。

    ``close.rolling(20).max()`` 过安全闸且可被信号求值器执行；
    ``rolling_max(close, 20)`` 裸函数调用被拒——所以字典只给方法链写法。
    """
    import pandas as pd

    from quant_research_engine.evaluation.signals import evaluate_expression_signal
    from quant_research_engine.security.yaml_guard import validate_expression

    frame = pd.DataFrame({
        "close": [10.0, 11, 12, 13, 14, 15],
        "high": [10.0, 11, 12, 13, 14, 15],
        "low": [9.0, 10, 11, 12, 13, 14],
        "vol": [100.0, 110, 120, 130, 140, 150],
    })
    allowed = set(frame.columns)
    for expression in (
        "close > high.rolling(3).max().shift(1)",
        "close <= high.rolling(3).max() * 0.92",
        "close >= low.rolling(3).min()",
        "vol > vol.rolling(3).mean() * 1.5",
    ):
        assert validate_expression(expression, allowed_names=allowed) == [], expression
        signal = evaluate_expression_signal(frame, expression)
        assert signal.dtype == bool
    assert validate_expression("rolling_max(close, 3)", allowed_names=allowed)


def test_compiled_expression_survives_security_guard():
    """编译产物必须过安全闸（裸函数调用/属性访问会被拒）。"""
    from quant_research_engine.security.yaml_guard import validate_expression

    for expression in (
        "(sma_5 > sma_200) and (sma_5.shift(1) <= sma_200.shift(1))",
        "(dif < dea) and (dif.shift(1) >= dea.shift(1))",
        "close > high.rolling(20).max().shift(1)",
    ):
        names = {"sma_5", "sma_200", "dif", "dea", "close", "high"}
        assert validate_expression(expression, allowed_names=names) == [], expression


# --- 信号级验证（CR-2026-11-03 S4）---


def _synthetic_ema_cross_frame() -> pd.DataFrame:
    """EMA5 只上穿 EMA200 一次、也只下穿一次的合成序列（60 个交易日）。

    0–19 日在下方，20 日上穿，21–39 日在上方，40 日下穿，41–59 日在下方。
    """
    fast = [10.0 + 0.1 * i for i in range(20)]           # 10.0 → 11.9：全程在慢线下方
    fast += [12.0 + 0.1 * (i - 19) for i in range(20, 40)]  # 12.1 → 14.0：第 22 日上穿
    fast += [13.8 - 0.1 * (i - 39) for i in range(40, 60)]  # 13.7 → 12.0：第 54 日下穿
    slow = [12.0] * 20 + [12.2] * 20 + [12.4] * 20
    return pd.DataFrame({"ema_5": fast, "ema_200": slow})


def test_signal_level_single_cross_produces_single_entry():
    """编译出的穿越表达式在「只上穿一次」的序列上只产生 1 个入场信号。

    这是本次修复的核心验收：同样序列下，被降级成的当日状态表达式
    （``ema_5 > ema_200``）会在 20 个交易日持续为真（长开/重复触发），
    而正确的穿越表达式只在穿越当日触发一次。
    """
    frame = _synthetic_ema_cross_frame()
    entry = "(ema_5 > ema_200) and (ema_5.shift(1) <= ema_200.shift(1))"
    exit_ = "(ema_5 < ema_200) and (ema_5.shift(1) >= ema_200.shift(1))"
    entry_signal = evaluate_expression_signal(frame, entry)
    exit_signal = evaluate_expression_signal(frame, exit_)
    assert frame.index[entry_signal].tolist() == [22], frame.index[entry_signal].tolist()
    assert frame.index[exit_signal].tolist() == [54], frame.index[exit_signal].tolist()
    # 反证：当日状态写法会在上方区间全程为真（31 天），穿越只在当日为真
    state_signal = evaluate_expression_signal(frame, "ema_5 > ema_200")
    assert int(state_signal.sum()) == 31
    assert int(state_signal.sum()) > int(entry_signal.sum())


def test_compiled_ema_cross_yaml_signals_once_on_synthetic_series():
    """端到端：编译产物（含 canonical YAML）→ 信号求值 → 只 1 次入场。"""
    yaml_text = yaml.safe_dump(
        _spec("(ema_5 > ema_200) and (ema_5.shift(1) <= ema_200.shift(1))",
              "(ema_5 < ema_200) and (ema_5.shift(1) >= ema_200.shift(1))",
              ema_5="factors.stock_daily_overlap_close.ema_5",
              ema_200="factors.stock_daily_overlap_typical_price.ema_200"),
        allow_unicode=True, sort_keys=False)
    http, calls = _http([yaml_text])
    result = compile_nl("EMA5 上穿 EMA200 买入，下穿 EMA200 卖出", env=ENV,
                        http_post=http, column_lookup=_lookup())
    assert result["ok"] is True, result
    assert len(calls) == 1  # 合规产物不需要修复回路
    parsed = yaml.safe_load(result["yaml"])
    frame = _synthetic_ema_cross_frame()
    entry = evaluate_expression_signal(frame, parsed["signal"]["entry"])
    exit_ = evaluate_expression_signal(frame, parsed["signal"]["exit"])
    assert int(entry.sum()) == 1 and int(exit_.sum()) == 1
