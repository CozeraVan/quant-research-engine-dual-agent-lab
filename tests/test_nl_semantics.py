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
import yaml

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
    tables = {"factors.stock_daily_momentum_close": set(POOL)}
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
