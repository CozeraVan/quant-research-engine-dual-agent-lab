import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "classic_catalog" / "report.py"
_SPEC = importlib.util.spec_from_file_location("classic_catalog_report", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_smoke_audit_counts_failures_zero_trades_and_anomalies():
    rows = [
        {"strategy_id": "ok", "entry_mode": "yaml", "status": "completed",
         "summary": {"total_trade_count": 1, "strategy_total_return": 0.01}},
        {"strategy_id": "zero", "entry_mode": "nl", "status": "completed",
         "summary": {"total_trade_count": 0}},
        {"strategy_id": "bad", "entry_mode": "wizard", "status": "failed", "error": "boom"},
        {"strategy_id": "nan", "entry_mode": "yaml", "status": "completed",
         "summary": {"strategy_total_return": float("inf")}},
    ]

    summary = _MODULE.audit(rows)
    assert summary["total"] == 4 and summary["status"]["completed"] == 3
    assert summary["zero_trades"] == ["zero"]
    assert summary["failed"][0]["strategy_id"] == "bad"
    assert summary["anomalies"] == [{"strategy_id": "nan", "field": "strategy_total_return", "issue": "nonfinite"}]
    assert "小样本收益不是策略有效性结论" in _MODULE.render(rows, summary)


def test_current_smoke_report_has_118_unique_strategies_and_no_numeric_anomalies():
    results = Path(".tmp/classic-catalog-public-smoke/results.jsonl")
    if not results.exists():
        return
    import json
    rows = [json.loads(line) for line in results.read_text().splitlines()]
    rows = list({row["strategy_id"]: row for row in rows}.values())
    summary = _MODULE.audit(rows)
    assert summary["total"] == summary["unique_strategies"] == 118
    assert summary["anomalies"] == []
