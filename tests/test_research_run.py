from __future__ import annotations

import json
from datetime import date

from quant_research_engine.orchestration.research_run import (
    ResearchRunRequest,
    ResearchRunResult,
    _write_research_manifest,
)


def _make_request(tmp_path, **overrides):
    defaults = {
        "strategy_path": tmp_path / "strategy.yaml",
        "start": date(2024, 1, 1),
        "end": date(2024, 2, 1),
        "output_dir": tmp_path / "run_output",
    }
    defaults.update(overrides)
    return ResearchRunRequest(**defaults)


class TestResearchRunRequest:
    def test_minimal_construction(self, tmp_path):
        req = _make_request(tmp_path)
        assert req.backtest_mode == "batch"
        assert req.initial_cash == 1_000_000
        assert req.min_factor_coverage == 0.8
        assert req.skip_preflight is False
        assert req.skip_eval is False
        assert req.run_id is None

    def test_full_construction(self, tmp_path):
        req = ResearchRunRequest(
            strategy_path=tmp_path / "strategy.yaml",
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            output_dir=tmp_path / "output",
            run_id="my-run-001",
            db_url="postgresql://localhost/test",
            codes=["000001.SZ", "000002.SZ"],
            market_profile_path=tmp_path / "profile.yaml",
            skip_preflight=True,
            skip_eval=True,
            backtest_mode="shared",
            initial_cash=500_000,
            min_factor_coverage=0.9,
            group_by=["board"],
            random_baseline_seed=42,
            round_trip_cost_rate=0.005,
            metadata_columns=["industry"],
            window_size=20,
        )
        assert req.run_id == "my-run-001"
        assert req.backtest_mode == "shared"
        assert req.skip_preflight is True
        assert req.skip_eval is True
        assert req.group_by == ["board"]
        assert req.random_baseline_seed == 42
        assert req.metadata_columns == ["industry"]
        assert req.window_size == 20


class TestResearchRunResult:
    def test_default_construction(self, tmp_path):
        result = ResearchRunResult(
            run_id="abc123",
            output_dir=tmp_path / "output",
            preflight_status="skipped",
            eval_status="skipped",
            backtest_status="ok",
        )
        assert result.run_id == "abc123"
        assert result.preflight_status == "skipped"
        assert result.eval_status == "skipped"
        assert result.backtest_status == "ok"
        assert result.error_message is None
        assert result.backtest_paths == {}

    def test_error_state(self, tmp_path):
        result = ResearchRunResult(
            run_id="abc123",
            output_dir=tmp_path / "output",
            preflight_status="error",
            eval_status="skipped",
            backtest_status="error",
            error_message="Preflight failed (status=error)",
        )
        assert result.preflight_status == "error"
        assert result.error_message == "Preflight failed (status=error)"


class TestWriteResearchManifest:
    def test_writes_valid_json(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        (output_dir / "summary.csv").write_text("")
        request = _make_request(tmp_path, output_dir=output_dir, run_id="test-run-001")
        result = ResearchRunResult(
            run_id="test-run-001",
            output_dir=output_dir,
            preflight_status="ok",
            eval_status="ok",
            backtest_status="ok",
            backtest_paths={"summary_csv": output_dir / "summary.csv"},
        )
        manifest_path = _write_research_manifest(result, request)
        assert manifest_path.exists()
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["kind"] == "research_run_manifest"
        assert payload["command"] == "research-run"
        assert payload["run_id"] == "test-run-001"
        assert payload["strategy_path"] == str(request.strategy_path)
        assert payload["stages"]["preflight"] == "ok"
        assert payload["stages"]["eval"] == "ok"
        assert payload["stages"]["backtest"] == "ok"
        assert "summary_csv" in payload["backtest_artifacts"]
        assert "summary_csv" in payload["artifacts"]

    def test_error_manifest_includes_error(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        request = _make_request(tmp_path, output_dir=output_dir, run_id="test-run-002")
        result = ResearchRunResult(
            run_id="test-run-002",
            output_dir=output_dir,
            preflight_status="error",
            eval_status="skipped",
            backtest_status="error",
            error_message="Preflight failed",
        )
        manifest_path = _write_research_manifest(result, request)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["error"] == "Preflight failed"
        assert payload["kind"] == "research_run_manifest"
        assert payload["stages"]["preflight"] == "error"
        assert payload["stages"]["eval"] == "skipped"
        assert payload["artifacts"] == []

    def test_skipped_stages(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        request = _make_request(tmp_path, output_dir=output_dir, run_id="test-run-003")
        result = ResearchRunResult(
            run_id="test-run-003",
            output_dir=output_dir,
            preflight_status="skipped",
            eval_status="skipped",
            backtest_status="ok",
        )
        manifest_path = _write_research_manifest(result, request)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["kind"] == "research_run_manifest"
        assert payload["command"] == "research-run"
        assert payload["stages"]["preflight"] == "skipped"
        assert payload["stages"]["eval"] == "skipped"
