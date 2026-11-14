"""标准化 run_config：输入、实际执行范围与版本合同。"""

from quant_research_engine.gui.saas.run_config import build_run_config


def test_build_run_config_derives_actual_universe_and_versions():
    config = build_run_config(
        job_id=42,
        params={
            "start": "2021-01-01",
            "end": "2026-01-01",
            "codes": ["A.SZ", "B.SZ", "C.SZ"],
            "_factor_limits": {"max_fields": 20},
        },
        input_snapshot={"entry_mode": "nl", "nl_text": "原始输入", "yaml": "experiment: {}"},
        strategy_name="demo",
        result_summary={"symbol_count": 2, "run_id": "run-42"},
        artifacts=[
            {"name": "_symbol_details/A.SZ.json.gz"},
            {"name": "_symbol_details/B.SZ.json.gz"},
            {"name": "risk_report.json"},
        ],
        data_until="2025-12-31",
        result_contract_version="contract-test",
    )

    assert config["schema_version"] == 1
    assert config["job_id"] == 42
    assert config["strategy"]["name"] == "demo"
    assert config["input"]["nl_text"] == "原始输入"
    assert config["execution"]["actual_codes"] == ["A.SZ", "B.SZ"]
    assert config["execution"]["excluded_codes"] == ["C.SZ"]
    assert config["execution"]["symbol_count"] == 2
    assert config["execution"]["run_id"] == "run-42"
    assert config["versions"]["result_contract"] == "contract-test"
    assert config["versions"]["engine"]
    assert config["versions"]["factor_basis"] == "qfq_anchor_v1"
    assert config["data_until"] == "2025-12-31"
