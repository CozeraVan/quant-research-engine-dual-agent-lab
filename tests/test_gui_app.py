from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    """Create a Flask test client with isolated engine directories."""
    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# --- page routes ---


def test_index_returns_200(app_client):
    resp = app_client.get("/")
    assert resp.status_code == 200
    assert b"Backtest Console" in resp.data
    assert b"ema200_bollinger_reversal_mvp" in resp.data
    assert b"bb_upper" in resp.data
    assert b"bb_lower" in resp.data


def test_runs_page_returns_200(app_client):
    resp = app_client.get("/runs")
    assert resp.status_code == 200
    assert b"Run History" in resp.data


def test_runs_page_with_data(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "test001"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps({
            "run_id": "test001",
            "mode": "batch",
            "start": "2026-01-05",
            "end": "2026-03-31",
            "codes": ["000001.SZ"],
            "status": "completed",
            "created_at": "2026-05-21T12:00:00",
        }),
        encoding="utf-8",
    )

    resp = app_client.get("/runs")
    assert resp.status_code == 200
    assert b"test001" in resp.data


def test_run_detail_not_found(app_client):
    resp = app_client.get("/runs/nonexistent")
    assert resp.status_code == 404
    assert b"Error" in resp.data


def test_run_detail_found(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "detail001"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps({
            "run_id": "detail001",
            "mode": "shared",
            "start": "2026-01-05",
            "end": "2026-01-06",
            "codes": ["000001.SZ"],
            "status": "completed",
            "error": None,
        }),
        encoding="utf-8",
    )
    (run_dir / "stdout.log").write_text("strategy=test\norders=5\n", encoding="utf-8")

    resp = app_client.get("/runs/detail001")
    assert resp.status_code == 200
    assert b"detail001" in resp.data
    assert b"orders=5" in resp.data


# --- API: validate ---


def test_api_validate_valid(app_client):
    yaml = (
        "experiment:\n  name: default\n  engine:\n    kind: single\n"
        "data:\n  factor_fields:\n    f: factors.t.c\n"
        "signal:\n  entry: x < 0\n"
        "evaluation:\n  forward_return_horizons: [1]\n"
        "holding:\n  max_holding_days: 1\n"
    )
    resp = app_client.post(
        "/api/validate",
        data=json.dumps({"yaml": yaml}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["valid"] is True


def test_api_validate_invalid(app_client):
    resp = app_client.post(
        "/api/validate",
        data=json.dumps({"yaml": "not valid yaml: : ["}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["valid"] is False


# --- API: run ---


def test_api_run_missing_fields(app_client):
    resp = app_client.post(
        "/api/run",
        data=json.dumps({"yaml": "x"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = json.loads(resp.data)
    assert data["status"] == "error"
    assert "Missing fields" in data["error"]


def test_api_run_success(monkeypatch, app_client, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    def fake_run_via_module(**kwargs):
        kwargs["stdout_path"].write_text("strategy=test\norders=0\n", encoding="utf-8")
        kwargs["stderr_path"].write_text("", encoding="utf-8")

    monkeypatch.setattr("quant_research_engine.gui.engine._run_via_module", fake_run_via_module)

    resp = app_client.post(
        "/api/run",
        data=json.dumps({
            "yaml": "experiment:\n  name: default\n  engine:\n    kind: single\ndata:\n  factor_fields:\n    f: factors.t.c\nsignal:\n  entry: x < 0\nevaluation:\n  forward_return_horizons: [1]\nholding:\n  max_holding_days: 1\n",
            "mode": "single",
            "start": "2026-01-05",
            "end": "2026-01-06",
            "codes": "000001.SZ",
        }),
        content_type="application/json",
    )

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["status"] == "completed"
    assert data["mode"] == "single"


# --- API: templates ---


def test_api_template_save_and_list(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")

    save_resp = app_client.post(
        "/api/templates",
        data=json.dumps({"name": "api-test", "yaml": "name: t\nsignal_expression: x<0\n"}),
        content_type="application/json",
    )
    assert save_resp.status_code == 200
    assert json.loads(save_resp.data)["saved"] == "api-test"

    list_resp = app_client.get("/api/templates")
    assert list_resp.status_code == 200
    names = json.loads(list_resp.data)
    assert "api-test" in names


def test_api_template_save_empty_name(app_client):
    resp = app_client.post(
        "/api/templates",
        data=json.dumps({"name": "", "yaml": "x"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_api_template_load(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    (tmp_path / "templates").mkdir(parents=True, exist_ok=True)
    (tmp_path / "templates" / "load-test.yaml").write_text(
        "name: lt\nsignal_expression: x > 0\n", encoding="utf-8",
    )

    resp = app_client.get("/api/templates/load-test")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["name"] == "load-test"
    assert "x > 0" in data["yaml"]


def test_api_template_load_not_found(app_client):
    resp = app_client.get("/api/templates/nonexistent-xyz")
    assert resp.status_code == 404


# --- API: runs ---


def test_api_runs_list(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "api-run"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps({"run_id": "api-run", "mode": "batch", "status": "completed"}),
        encoding="utf-8",
    )

    resp = app_client.get("/api/runs")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert any(r["run_id"] == "api-run" for r in data)


def test_api_run_detail_not_found(app_client):
    resp = app_client.get("/api/runs/nonexistent")
    assert resp.status_code == 404


def test_api_run_strategy(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "strat-run"
    run_dir.mkdir(parents=True)
    (run_dir / "strategy.yaml").write_text("name: s\nsignal_expression: x < 0\n", encoding="utf-8")

    resp = app_client.get("/api/runs/strat-run/strategy")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "x < 0" in data["yaml"]


# --- API: artifact ---


def test_api_run_artifact_csv(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "art-run"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps({"run_id": "art-run", "artifacts": {"summary.csv": str(run_dir / "summary.csv")}}),
        encoding="utf-8",
    )
    (run_dir / "summary.csv").write_text("col_a,col_b\n1,2\n3,4\n", encoding="utf-8")

    resp = app_client.get("/api/runs/art-run/artifact/summary.csv")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["type"] == "csv"
    assert data["headers"] == ["col_a", "col_b"]
    assert data["rows"] == [["1", "2"], ["3", "4"]]


def test_api_run_artifact_not_found(app_client):
    resp = app_client.get("/api/runs/nonexistent/artifact/summary.csv")
    assert resp.status_code == 404


def test_api_run_artifact_json(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "json-run"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        json.dumps({"run_id": "json-run", "artifacts": {"report_manifest.json": str(run_dir / "report_manifest.json")}}),
        encoding="utf-8",
    )
    (run_dir / "report_manifest.json").write_text('{"kind": "test", "files": []}', encoding="utf-8")

    resp = app_client.get("/api/runs/json-run/artifact/report_manifest.json")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["type"] == "json"
    assert data["data"]["kind"] == "test"


# --- rerun restoration ---


def test_rerun_strategy_endpoint(app_client, monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "rerun-test"
    run_dir.mkdir(parents=True)
    (run_dir / "strategy.yaml").write_text(
        "experiment:\n  name: rerun\n  engine:\n    kind: single\n"
        "data:\n  factor_fields:\n    f: factors.t.c\n"
        "signal:\n  entry: x < 0\n"
        "evaluation:\n  forward_return_horizons: [1]\n"
        "holding:\n  max_holding_days: 1\n",
        encoding="utf-8",
    )

    resp = app_client.get("/api/runs/rerun-test/strategy")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "rerun" in data["yaml"]


# --- gui CLI integration ---


def test_gui_subcommand_help():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "quant_research_engine.apps.cli", "gui", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--host" in result.stdout
    assert "--port" in result.stdout


# --- Builder API: compile ---

BUILDER_ENTRY = {
    "strategy": {
        "id": "rsi2_test",
        "name": "RSI2 Test",
        "family": "mean_reversion",
        "direction": "long_only",
        "description": "Test strategy.",
    },
    "rules": {
        "entry": {
            "all": [
                {"alias": "rsi_fast", "operator": "<", "value": 10}
            ]
        }
    },
    "factor_requirements": [
        {
            "alias": "rsi_fast",
            "indicator": "rsi",
            "source": "close",
            "period": 2,
            "reason": "Signal",
        }
    ],
    "experiment": {
        "id": "rsi2-test",
        "frequency": "daily",
        "market": "ashare",
        "start": "2026-01-01",
        "end": "2026-03-31",
        "universe": {
            "include": "all_a",
            "exclude_st": True,
            "exclude_suspended": True,
            "exclude_risk_warning": True,
            "min_listing_days": 120,
        },
        "execution": {"market_profile": "ashare_daily_default"},
        "capital": {"initial_cash": 100000, "max_positions": 10},
    },
}


def test_builder_compile_valid(app_client):
    resp = app_client.post(
        "/api/builder/compile",
        data=json.dumps(BUILDER_ENTRY),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    assert "yaml" in data
    assert "rsi_fast" in data["yaml"]


def test_builder_compile_invalid(app_client):
    resp = app_client.post(
        "/api/builder/compile",
        data=json.dumps({"strategy": {}, "rules": {}, "factor_requirements": [], "experiment": {}}),
        content_type="application/json",
    )
    assert resp.status_code == 422
    data = json.loads(resp.data)
    assert data["ok"] is False
    assert len(data["issues"]) > 0


def test_builder_compile_with_exit_rules(app_client):
    entry = dict(BUILDER_ENTRY)
    entry["rules"]["exit"] = {"any": [{"alias": "rsi_fast", "operator": ">", "value": 70}]}
    resp = app_client.post(
        "/api/builder/compile",
        data=json.dumps(entry),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    assert "exit" in data["yaml"].lower()


def test_builder_compile_with_risk(app_client):
    entry = dict(BUILDER_ENTRY)
    entry["rules"]["risk"] = {"stop_loss_pct": 0.05, "max_holding_days": 20}
    resp = app_client.post(
        "/api/builder/compile",
        data=json.dumps(entry),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    assert "stop_loss" in data["yaml"]


# --- Builder API: indicator-catalog ---


def test_builder_indicator_catalog(app_client):
    resp = app_client.get("/api/builder/indicator-catalog")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "indicators" in data
    assert "sources" in data
    assert "rsi" in data["indicators"]
    assert data["indicators"]["rsi"]["category"] == "momentum"
    assert "macd" in data["indicators"]
    assert "bollinger" in data["indicators"]
    assert "close" in data["sources"]


# --- Builder API: validate ---


def test_builder_validate_valid(app_client):
    resp = app_client.post(
        "/api/builder/validate",
        data=json.dumps(BUILDER_ENTRY),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["valid"] is True


def test_builder_validate_invalid(app_client):
    resp = app_client.post(
        "/api/builder/validate",
        data=json.dumps({"strategy": {}, "rules": {}, "factor_requirements": [], "experiment": {}}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["valid"] is False
    assert len(data["issues"]) > 0


# --- Builder: index page includes builder tab ---


def test_index_includes_builder_tab(app_client):
    resp = app_client.get("/")
    assert resp.status_code == 200
    assert b"Strategy Builder" in resp.data
    assert b"YAML Editor" in resp.data
    assert b"builder-layout" in resp.data
