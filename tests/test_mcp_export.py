from __future__ import annotations

import hashlib
import json

import pytest

from quant_research_engine.mcp_server.client import AgentAPIClient, AgentAPIConfig, AgentAPIError
from quant_research_engine.mcp_server.export import export_backtest
from test_mcp_server import FakeResponse, FakeSession


class ExportClient:
    def __init__(self):
        self.result = {
            "ok": True,
            "result": {
                "status": "completed", "summary": {"run_id": "run-test"},
                "artifacts": [
                    {"name": "summary.md", "sha256": hashlib.sha256(b"summary").hexdigest()},
                    {"name": "equity_curve.csv", "sha256": hashlib.sha256(b"curve").hexdigest()},
                    {"name": "600519.SH/trades.csv", "sha256": "not-selected"},
                ],
            },
        }
        self.downloads = []

    def request(self, method, path):
        return self.result

    def download_artifact(self, job_id, name):
        self.downloads.append(name)
        return {"summary.md": b"summary", "equity_curve.csv": b"curve"}[name]


def test_compact_export_writes_manifest_and_verified_files(tmp_path):
    client = ExportClient()
    result = export_backtest(client, 360, tmp_path)
    out = tmp_path / "job_360"
    assert (out / "result.json").is_file()
    assert (out / "summary.md").read_bytes() == b"summary"
    assert (out / "equity_curve.csv").read_bytes() == b"curve"
    assert not (out / "600519.SH").exists()
    assert result["file_count"] == 4
    manifest = json.loads((out / "local_manifest.json").read_text())
    assert manifest["schema_version"] == "qre-local-export-v1"
    assert manifest["profile"] == "compact"
    assert not (tmp_path / ".job_360.partial").exists()
    with pytest.raises(FileExistsError):
        export_backtest(client, 360, tmp_path)


def test_export_hash_mismatch_removes_partial(tmp_path):
    client = ExportClient()
    client.result["result"]["artifacts"][0]["sha256"] = "bad"
    with pytest.raises(ValueError, match="SHA-256"):
        export_backtest(client, 360, tmp_path)
    assert not (tmp_path / "job_360").exists()
    assert not (tmp_path / ".job_360.partial").exists()


def test_download_rejects_nested_or_traversing_name():
    session = FakeSession(FakeResponse(b"data"))
    client = AgentAPIClient(
        AgentAPIConfig(base_url="https://example.test/api/agent/v1", token="test"), session=session
    )
    with pytest.raises(AgentAPIError, match="不合法"):
        client.download_artifact(1, "../secret")
    assert session.calls == []
    assert client.download_artifact(1, "summary.md") == b"data"


def test_admin_console_shows_account_result_visibility_from_policy_source():
    from pathlib import Path
    app_source = Path("src/quant_research_engine/gui/saas/app.py").read_text(encoding="utf-8")
    console = Path("src/quant_research_engine/gui/saas/templates/console.html").read_text(encoding="utf-8")
    assert '"result_visibility": _agent.JOB_RESULT_VISIBILITY' in app_source
    assert "ag.result_visibility === 'account'" in console
