from __future__ import annotations

import json

import yaml

from quant_research_engine.gui.factor_correction import (
    COMMON_FACTOR_TARGETS,
    auto_fix_column,
    correct_factor_fields,
    format_corrections_note,
    format_unresolved_hint,
    suggest_similar_columns,
)
from quant_research_engine.gui.nl_compiler import build_system_prompt, compile_nl

# --- pure helpers ---


def test_auto_fix_normalized_equal_underscore():
    # DeepSeek 编造 rsi14；库中存在 rsi_14 → 自动纠正
    assert auto_fix_column("rsi14", {"rsi_14", "rsi_6"}) == "rsi_14"


def test_auto_fix_case_difference():
    assert auto_fix_column("MACD_12_26_9", {"macd_12_26_9"}) == "macd_12_26_9"


def test_auto_fix_unique_prefix():
    assert auto_fix_column("macd", {"macd_12_26_9"}) == "macd_12_26_9"


def test_auto_fix_ambiguous_prefix_not_fixed():
    # macd 系列三列并列 → 不自动纠正，宁给候选
    pool = {"macd_12_26_9", "macd_signal_12_26_9", "macd_histogram_12_26_9"}
    assert auto_fix_column("macd", pool) is None


def test_auto_fix_ambiguous_edit_distance_not_fixed():
    # rsi_9 与 rsi_6 距离 1，但 rsi_14 距离 2 差距不够 → 不纠正
    assert auto_fix_column("rsi_9", {"rsi_6", "rsi_14"}) is None


def test_auto_fix_unique_close_edit_distance():
    # 唯一候选且归一化编辑距离为 1（多打一位数字）→ 纠正
    assert auto_fix_column("rsi_144", {"rsi_14"}) == "rsi_14"


def test_auto_fix_exact_match_untouched():
    assert auto_fix_column("rsi_14", {"rsi_14"}) is None
    assert auto_fix_column("rsi_14", set()) is None


def test_suggest_similar_columns_ranked():
    pool = {"rsi_14", "rsi_6", "sma_20", "macd_12_26_9"}
    suggestions = suggest_similar_columns("rsi14", pool)
    assert suggestions[0] == "rsi_14"
    assert "sma_20" in suggestions
    assert len(suggestions) <= 5


# --- correct_factor_fields on parsed mapping ---


def _mapping_with(target: str) -> dict:
    return {
        "experiment": {"name": "demo", "market_profile": "ashare_daily_default", "frequency": "daily"},
        "data": {"market_fields": ["close"], "factor_fields": {"rsi": target}},
        "signal": {"entry": "rsi > 30"},
        "holding": {"max_holding_days": 5},
        "evaluation": {"forward_return_horizons": [1, 3, 5]},
    }


def test_correct_factor_fields_exact_untouched():
    mapping = _mapping_with("factors.stock_daily_momentum_close.rsi_14")
    report = correct_factor_fields(mapping, lambda table: {"rsi_14"})
    assert report["corrections"] == []
    assert report["unresolved"] == []
    assert mapping["data"]["factor_fields"]["rsi"] == "factors.stock_daily_momentum_close.rsi_14"


def test_correct_factor_fields_fabricated_auto_fixed():
    mapping = _mapping_with("factors.stock_daily_momentum_close.rsi14")
    report = correct_factor_fields(mapping, lambda table: {"rsi_14", "rsi_6"})
    assert report["corrections"] == [
        {"alias": "rsi", "table": "factors.stock_daily_momentum_close", "from": "rsi14", "to": "rsi_14"}
    ]
    assert mapping["data"]["factor_fields"]["rsi"] == "factors.stock_daily_momentum_close.rsi_14"
    assert report["unresolved"] == []


def test_correct_factor_fields_no_match_gives_candidates():
    mapping = _mapping_with("factors.stock_daily_momentum_close.rsi_99")
    pool = {"rsi_14": None, "rsi_6": None, "sma_20": None}
    report = correct_factor_fields(mapping, lambda table: set(pool))
    assert report["corrections"] == []
    assert len(report["unresolved"]) == 1
    item = report["unresolved"][0]
    assert item["column"] == "rsi_99"
    assert item["suggestion_scope"] == "same_table"
    assert item["suggestions"]  # Top-N 候选非空


def test_correct_factor_fields_wrong_table_cross_table_fix():
    # LLM 把 rsi 放进了 overlap 表 → 跨表兜底找到 momentum 表并改写
    mapping = _mapping_with("factors.stock_daily_overlap_close.rsi_14")

    def lookup(table: str) -> set[str]:
        if table == "factors.stock_daily_momentum_close":
            return {"rsi_14"}
        return set()

    report = correct_factor_fields(mapping, lookup)
    assert report["corrections"][0]["to"] == "rsi_14"
    assert mapping["data"]["factor_fields"]["rsi"] == "factors.stock_daily_momentum_close.rsi_14"


def test_format_hints_actionable_chinese():
    note = format_corrections_note([{"alias": "r", "table": "t", "from": "rsi14", "to": "rsi_14"}])
    assert "已自动纠正" in note and "rsi14→rsi_14" in note
    hint = format_unresolved_hint([
        {"alias": "r", "table": "t", "column": "rsi_99", "suggestions": ["rsi_14"], "suggestion_scope": "same_table"}
    ])
    assert "库中相似候选" in hint and "rsi_14" in hint and "常用已落库因子" in hint


# --- prompt 注入真实因子目录 ---


def test_system_prompt_injects_common_columns_and_no_fabrication_rule():
    prompt = build_system_prompt()
    assert "严禁编造因子名" in prompt
    assert "常用已落库列" in prompt
    for target in COMMON_FACTOR_TARGETS:
        assert target in prompt


# --- compile_nl 集成（http_post 桩 + 内存 column_lookup） ---


def _llm_env() -> dict[str, str]:
    return {
        "QRE_NL_LLM_BASE_URL": "http://llm.local/v1",
        "QRE_NL_LLM_API_KEY": "test-key",
        "QRE_NL_LLM_MODEL": "test-model",
    }


def _http_ok(content: str):
    def http_post(url, headers, payload, timeout):
        return {"choices": [{"message": {"content": content}}]}

    return http_post


_FABRICATED_YAML = (
    "experiment:\n  name: nl_fab\n  market_profile: ashare_daily_default\n  frequency: daily\n"
    "data:\n  market_fields: [open, high, low, close]\n"
    "  factor_fields:\n    rsi14: factors.stock_daily_momentum_close.rsi14\n"
    "signal:\n  entry: rsi14 > 30\n"
    "holding:\n  max_holding_days: 5\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5]\n"
)


def test_compile_nl_fabricated_factor_auto_corrected(tmp_path):
    result = compile_nl(
        "RSI 站回 30 买入",
        env=_llm_env(),
        http_post=_http_ok(_FABRICATED_YAML),
        column_lookup=lambda table: {"rsi_14", "rsi_6"},
        queue_path=tmp_path / "q.json",
    )
    assert result["ok"] is True
    # 纠正落进 YAML（target 换列名，alias 不变，信号表达式不受影响）
    parsed = yaml.safe_load(result["yaml"])
    assert parsed["data"]["factor_fields"]["rsi14"] == "factors.stock_daily_momentum_close.rsi_14"
    assert parsed["signal"]["entry"] == "rsi14 > 30"
    assert result["corrections"][0]["from"] == "rsi14"
    assert result["corrections"][0]["to"] == "rsi_14"
    assert any("已自动纠正" in w and "rsi14→rsi_14" in w for w in result["warnings"])
    # 全部纠正成功 → 不入补因子队列
    assert not (tmp_path / "q.json").exists()


def test_compile_nl_exact_factor_untouched(tmp_path):
    valid = _FABRICATED_YAML.replace("rsi14", "rsi_14")
    result = compile_nl(
        "x",
        env=_llm_env(),
        http_post=_http_ok(valid),
        column_lookup=lambda table: {"rsi_14"},
        queue_path=tmp_path / "q.json",
    )
    assert result["ok"] is True
    assert "corrections" not in result
    assert result["yaml"] == valid.rstrip("\n")  # 原样保留，未经 dump 重写


def test_compile_nl_unmatchable_factor_returns_candidates(tmp_path):
    queue_path = tmp_path / "handoff" / "queue.json"
    result = compile_nl(
        "x",
        env=_llm_env(),
        http_post=_http_ok(_FABRICATED_YAML.replace("rsi14", "rsi_99")),
        column_lookup=lambda table: {"rsi_14", "rsi_6", "sma_20"},
        queue_path=queue_path,
    )
    assert result["ok"] is False
    assert result["code"] == "missing_factors"
    assert "库中相似候选" in result["error"]
    assert "rsi_14" in result["error"]
    assert "常用已落库因子" in result["error"]
    assert result["suggestions"][0]["suggestions"]
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert queue[0]["expected_column"] == "rsi_99"
