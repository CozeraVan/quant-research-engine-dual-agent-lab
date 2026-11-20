from __future__ import annotations

import json
from pathlib import Path

from quant_research_engine.smoke_cleanup import cleanup_smoke_run, cleanup_smoke_upload


def _run(tmp_path: Path, *, smoke=True, status="completed"):
    run_id = "20261120T000000000001"
    run_dir = tmp_path / "runs" / run_id
    output = run_dir / "artifacts" / run_id
    output.mkdir(parents=True)
    (output / "result.csv").write_text("x")
    (run_dir / "strategy.yaml").write_text("experiment: {}")
    record = {"run_id": run_id, "status": status, "output_dir": str(output)}
    if smoke:
        record["precheck"] = True
    (run_dir / "status.json").write_text(json.dumps(record))
    return run_id, run_dir, output


def test_terminal_smoke_run_and_output_are_deleted(tmp_path):
    run_id, run_dir, output = _run(tmp_path)
    assert cleanup_smoke_run(run_id, runs_dir=tmp_path / "runs") is True
    assert not run_dir.exists() and not output.exists()


def test_full_or_running_run_is_not_deleted(tmp_path):
    full = _run(tmp_path, smoke=False)
    running = _run(tmp_path / "other", status="running")
    assert cleanup_smoke_run(full[0], runs_dir=tmp_path / "runs") is False
    assert cleanup_smoke_run(running[0], runs_dir=tmp_path / "other" / "runs") is False
    assert full[1].exists() and running[1].exists()


def test_smoke_upload_directory_is_deleted_but_full_is_preserved(tmp_path):
    smoke = tmp_path / "job_10"
    full = tmp_path / "job_11"
    smoke.mkdir()
    full.mkdir()
    (smoke / "x.csv").write_text("x")
    (full / "x.csv").write_text("x")
    assert cleanup_smoke_upload(tmp_path, 10, kind="smoke") is True
    assert cleanup_smoke_upload(tmp_path, 11, kind="full") is False
    assert not smoke.exists() and full.exists()


def test_lab_history_excludes_existing_smoke_runs(monkeypatch):
    from quant_research_engine.gui import engine
    from quant_research_engine.gui.lab_result import build_lab_runs_list
    rows = [
        {"run_id": "full", "status": "completed", "codes": []},
        {"run_id": "smoke-old", "status": "completed", "codes": ["000001.SZ"], "precheck": True},
        {"run_id": "smoke-sandbox", "status": "completed", "codes": ["000001.SZ"], "purpose": "smoke"},
    ]
    monkeypatch.setattr(engine, "list_runs", lambda: rows)
    assert [row["run_id"] for row in build_lab_runs_list()] == ["full"]
