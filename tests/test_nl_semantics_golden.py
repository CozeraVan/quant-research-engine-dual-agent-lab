"""CR-2026-11-03 NL 语义 golden dataset 合同测试。

数据：``tests/fixtures/nl_semantics/golden_cases.yaml``（中文描述 → 模型输出 →
期望 YAML 结构）。每个用例走真实编译链路（stub LLM 回放模型输出 +
``configs/factor_catalog_llm.json`` 真实因子目录做存在性校验），断言：

- 穿越事件（上穿/下穿/金叉/死叉）的 entry/exit 必须含 ``.shift(1)``；
- 持续状态（大于/小于/水平位）全文不得出现 ``.shift(``；
- 因子列名必须与 golden 期望逐字一致（库内不存在 → 编译失败，测试红）；
- 输出是 canonical YAML（键序稳定、无围栏、幂等）。

这个文件同时是「禁止编造因子名」与「状态语义不得误加 shift」的回归闸门。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from quant_research_engine.gui.factor_catalog_llm import catalog_column_lookup
from quant_research_engine.gui.nl_compiler import compile_nl
from quant_research_engine.gui.nl_semantics import canonicalize_strategy_yaml

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nl_semantics" / "golden_cases.yaml"

ENV = {"QRE_NL_LLM_BASE_URL": "http://fake", "QRE_NL_LLM_API_KEY": "k",
       "QRE_NL_LLM_MODEL": "m"}


def _cases():
    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data, "golden dataset 不能为空"
    return data


CASES = _cases()


def _http(content):
    def http_post(url, headers, payload, timeout):
        return {"choices": [{"message": {"content": content}}]}

    return http_post


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden_case_contract(case, tmp_path):
    result = compile_nl(
        case["description"],
        env=ENV,
        http_post=_http(case["llm_output"]),
        column_lookup=catalog_column_lookup(),
        queue_path=tmp_path / "missing_factor_queue.json",
    )
    assert result["ok"] is True, result
    yaml_text = result["yaml"]
    parsed = yaml.safe_load(yaml_text)
    expect = case["expect"]

    entry = parsed["signal"]["entry"]
    exit_ = parsed["signal"].get("exit") or ""
    if expect.get("entry_has_shift"):
        assert ".shift(1)" in entry, (case["id"], entry)
    if expect.get("exit_has_shift"):
        assert ".shift(1)" in exit_, (case["id"], exit_)
    if expect.get("exit_has_shift") is False:
        assert ".shift(" not in exit_, (case["id"], exit_)
    if expect.get("no_shift_anywhere"):
        assert ".shift(" not in yaml_text, (case["id"], yaml_text)
    for needle in expect.get("entry_contains", []):
        assert needle in entry, (case["id"], needle, entry)
    for needle in expect.get("exit_contains", []):
        assert needle in exit_, (case["id"], needle, exit_)

    assert parsed["data"]["factor_fields"] == expect["factor_fields"], case["id"]
    if "holding_max_days" in expect:
        assert parsed["holding"]["max_holding_days"] == expect["holding_max_days"]
    for name in expect.get("corrections_from", []):
        assert any(c["from"] == name for c in result.get("corrections", [])), case["id"]

    # canonical 输出：幂等 + 无围栏 + 无注释
    assert "```" not in yaml_text
    assert canonicalize_strategy_yaml(yaml_text) == yaml_text


def test_golden_dataset_rejects_fabricated_factor_column():
    """反向合同：golden 期望里的列名必须真实存在于因子库快照。

    防止有人往 golden dataset 里写一个编造的列名还能让测试变绿。
    """
    lookup = catalog_column_lookup()
    assert lookup is not None, "因子目录快照缺失（configs/factor_catalog_llm.json）"
    referenced = set()
    for case in CASES:
        for target in case["expect"]["factor_fields"].values():
            table, column = str(target).rsplit(".", 1)
            referenced.add((table, column))
    assert referenced, "golden dataset 没有引用任何因子列"
    unknown = sorted(f"{t}.{c}" for t, c in referenced if c not in lookup(t))
    assert not unknown, f"golden dataset 引用了因子库中不存在的列：{unknown}"
