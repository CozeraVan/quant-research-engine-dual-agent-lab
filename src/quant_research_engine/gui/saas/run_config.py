"""标准化回测复现配置：原始输入、实际执行范围与版本合同。"""

from __future__ import annotations

import json
from typing import Any

from quant_research_engine import __version__
from quant_research_engine.factor_basis import FACTOR_BASIS_QFQ_ANCHOR_V1
from quant_research_engine.gui.saas.result_contract import RESULT_CONTRACT_VERSION


def _actual_codes(params: dict[str, Any], artifacts: list[dict[str, Any]]) -> list[str]:
    codes = {
        str(item.get("name", "")).rsplit("/", 1)[-1].removesuffix(".json.gz")
        for item in artifacts
        if str(item.get("name", "")).startswith("_symbol_details/")
        and str(item.get("name", "")).endswith(".json.gz")
    }
    if codes:
        return sorted(codes)
    original = params.get("codes") or []
    if isinstance(original, str):
        original = [original]
    return sorted(str(code) for code in original)


def build_run_config(
    *,
    job_id: int,
    params: dict[str, Any],
    input_snapshot: dict[str, Any],
    strategy_name: str | None,
    result_summary: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    data_until: Any = None,
    result_contract_version: str | None = None,
) -> dict[str, Any]:
    """生成可下载、可恢复的稳定 JSON；不改变 worker 输入。"""
    summary = result_summary or {}
    files = artifacts or []
    sampled_codes = _actual_codes(params, files)
    original = params.get("codes") or []
    if isinstance(original, str):
        original = [original]
    reported_count = summary.get("symbol_count")
    complete = not files or reported_count is None or reported_count == len(sampled_codes)
    # 全量结果只采样部分个股详情时，绝不能把样本误标为实际全股票池。
    actual_codes = sampled_codes if complete else []
    excluded = sorted(set(map(str, original)) - set(actual_codes)) if files and complete else []
    return {
        "schema_version": 1,
        "job_id": job_id,
        "strategy": {"name": strategy_name},
        "input": dict(input_snapshot),
        "params": json.loads(json.dumps(params, ensure_ascii=False)),
        "execution": {
            "run_id": summary.get("run_id"),
            "actual_codes": actual_codes,
            "actual_codes_complete": complete,
            "sampled_codes": [] if complete else sampled_codes,
            "excluded_codes": excluded,
            "symbol_count": summary.get("symbol_count", len(actual_codes)),
        },
        "versions": {
            "engine": __version__,
            "factor_basis": FACTOR_BASIS_QFQ_ANCHOR_V1,
            "result_contract": result_contract_version or RESULT_CONTRACT_VERSION,
        },
        "data_until": data_until.isoformat() if hasattr(data_until, "isoformat") else data_until,
    }
