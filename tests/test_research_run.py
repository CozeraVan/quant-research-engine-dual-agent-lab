from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from quant_research_engine.evaluation.models import EvaluationResult
from quant_research_engine.orchestration.research_run import (
    ResearchRunRequest,
    ResearchRunResult,
    _write_research_manifest,
    _write_research_report_manifest,
    _write_preflight_artifact,
    _write_eval_artifacts,
    _run_eval,
    run_research_run,
)
from quant_research_engine.preflight import FactorCoverage, PreflightReport
from quant_research_engine.strategies.spec import StrategySpec


def _make_request(tmp_path, **overrides):
    defaults = {
        "strategy_path": tmp_path / "strategy.yaml",
        "start": date(2024, 1, 1),
        "end": date(2024, 2, 1),
        "output_dir": tmp_path / "run_output",
    }
    defaults.update(overrides)
    return ResearchRunRequest(**defaults)


def _make_fake_spec() -> StrategySpec:
    return StrategySpec(
        name="test_strategy",
        signal_expression="close > 0",
        exit_signal_expression=None,
        market_fields=["close"],
        factor_fields=[],
        forward_horizons=[1, 3, 5],
        holding_days=5,
        quantiles=None,
    )


def _make_fake_eval_result() -> EvaluationResult:
    df = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [pd.Timestamp("2024-01-05")]})
    empty = pd.DataFrame()
    return EvaluationResult(
        events=df,
        summary=empty,
        ic_summary=empty,
        quantile_summary=empty,
        group_summary=empty,
        random_baseline_summary=empty,
        factor_decay_summary=empty,
        regime_summary=empty,
    )


class FakeStore:
    def __init__(self, settings):
        self.settings = settings

    def ping(self):
        return True


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
        assert result.preflight_paths == {}
        assert result.eval_paths == {}
        assert result.report_manifest_path is None

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


class TestWritePreflightArtifact:
    def test_writes_preflight_json_with_to_dict(self, tmp_path):
        """Regression: real PreflightReport.to_dict() fields survive in the JSON."""
        output_dir = tmp_path / "run_output"
        report = PreflightReport(
            status="ok",
            market_rows=1000,
            latest_market_date="2024-02-01",
            requested_symbols=["000001.SZ", "000002.SZ"],
            loaded_symbols=["000001.SZ", "000002.SZ"],
            missing_symbols=[],
            factor_coverages={
                "ema_200": FactorCoverage(
                    logical_name="ema_200",
                    table="stock_daily_overlap_typical_price",
                    column="ema_200",
                    rows=950,
                    non_null_rows=900,
                    coverage_ratio=0.95,
                ),
            },
            joined_rows=900,
            join_coverage_ratio=0.9,
            metadata_rows=2,
            universe_total_symbols=5000,
            universe_eligible_symbols=["000001.SZ", "000002.SZ"],
            universe_excluded_symbols={},
            benchmark_rows=1000,
            benchmark_non_null_rows=995,
            checks=[],
        )

        path = _write_preflight_artifact(report, output_dir)
        assert path.exists()
        assert path.parent.name == "preflight"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert payload["market_rows"] == 1000
        assert payload["latest_market_date"] == "2024-02-01"
        assert payload["requested_symbols"] == ["000001.SZ", "000002.SZ"]
        assert payload["loaded_symbols"] == ["000001.SZ", "000002.SZ"]
        assert payload["missing_symbols"] == []
        assert "ema_200" in payload["factor_coverages"]
        assert payload["joined_rows"] == 900
        assert payload["join_coverage_ratio"] == 0.9
        assert payload["metadata_rows"] == 2
        assert payload["universe_total_symbols"] == 5000
        assert payload["benchmark_rows"] == 1000
        assert payload["benchmark_non_null_rows"] == 995
        assert payload["checks"] == []

    def test_writes_preflight_json_with_fake_fallback(self, tmp_path):
        """Fake reports without to_dict() still serialize via attribute fallback."""
        output_dir = tmp_path / "run_output"

        class FakeReport:
            status = "ok"
            summary = "All checks passed"
            missing_factor_requests = []
            missing_factors = None
            details = {"code_count": 100}
            market_fields_available = ["open", "close"]
            factor_fields_available = ["factors.stock_daily_basic.ema_200"]
            universe_size = 5000
            factor_coverage = 0.95
            calendar_range = "2024-01-01 to 2024-02-01"

        report = FakeReport()

        path = _write_preflight_artifact(report, output_dir)
        assert path.exists()
        assert path.parent.name == "preflight"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["status"] == "ok"
        assert payload["summary"] == "All checks passed"
        assert payload["universe_size"] == 5000
        assert payload["factor_coverage"] == 0.95


class TestWriteEvalArtifacts:
    def test_writes_eval_artifacts_under_eval_subdir(self, tmp_path):
        output_dir = tmp_path / "run_output"
        request = _make_request(tmp_path, output_dir=output_dir, run_id="eval-test-001")
        result = _make_fake_eval_result()
        paths = _write_eval_artifacts(result, request)
        assert "events" in paths
        assert "run_manifest" in paths
        assert "report_manifest" in paths
        for p in paths.values():
            assert p.parent == output_dir / "eval"
        assert (output_dir / "eval" / "events.csv").exists()
        assert (output_dir / "eval" / "run_manifest.json").exists()
        assert (output_dir / "eval" / "report_manifest.json").exists()


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
        assert "backtest:summary_csv" in payload["artifacts"]

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

    def test_manifest_with_preflight_artifacts(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        preflight_dir = output_dir / "preflight"
        preflight_dir.mkdir(parents=True)
        preflight_path = preflight_dir / "preflight_report.json"
        preflight_path.write_text("{}")
        request = _make_request(tmp_path, output_dir=output_dir, run_id="test-run-004")
        result = ResearchRunResult(
            run_id="test-run-004",
            output_dir=output_dir,
            preflight_status="ok",
            eval_status="skipped",
            backtest_status="ok",
            preflight_paths={"preflight_report": preflight_path},
        )
        manifest_path = _write_research_manifest(result, request)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "preflight_report" in payload["preflight_artifacts"]
        assert "preflight:preflight_report" in payload["artifacts"]

    def test_manifest_with_eval_artifacts(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        eval_dir = output_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "events.csv").write_text("")
        (eval_dir / "run_manifest.json").write_text("{}")
        (eval_dir / "report_manifest.json").write_text("{}")
        request = _make_request(tmp_path, output_dir=output_dir, run_id="test-run-005")
        result = ResearchRunResult(
            run_id="test-run-005",
            output_dir=output_dir,
            preflight_status="skipped",
            eval_status="ok",
            backtest_status="ok",
            eval_paths={
                "events": eval_dir / "events.csv",
                "run_manifest": eval_dir / "run_manifest.json",
                "report_manifest": eval_dir / "report_manifest.json",
            },
        )
        manifest_path = _write_research_manifest(result, request)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "events" in payload["eval_artifacts"]
        assert "run_manifest" in payload["eval_artifacts"]
        assert "report_manifest" in payload["eval_artifacts"]
        assert "eval:events" in payload["artifacts"]
        assert "eval:run_manifest" in payload["artifacts"]
        assert "eval:report_manifest" in payload["artifacts"]
        assert payload["eval_artifacts"]["report_manifest"] == "eval/report_manifest.json"

    def test_manifest_with_all_stage_artifacts(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        preflight_dir = output_dir / "preflight"
        preflight_dir.mkdir(parents=True)
        preflight_path = preflight_dir / "preflight_report.json"
        preflight_path.write_text("{}")
        eval_dir = output_dir / "eval"
        eval_dir.mkdir(parents=True)
        eval_rm = eval_dir / "report_manifest.json"
        eval_rm.write_text("{}")
        backtest_dir = output_dir / "backtest"
        backtest_dir.mkdir(parents=True)
        summary_csv = backtest_dir / "summary.csv"
        summary_csv.write_text("")
        backtest_rm = backtest_dir / "report_manifest.json"
        backtest_rm.write_text("{}")
        request = _make_request(tmp_path, output_dir=output_dir, run_id="test-run-006")
        result = ResearchRunResult(
            run_id="test-run-006",
            output_dir=output_dir,
            preflight_status="ok",
            eval_status="ok",
            backtest_status="ok",
            preflight_paths={"preflight_report": preflight_path},
            eval_paths={"report_manifest": eval_rm},
            backtest_paths={"summary_csv": summary_csv, "report_manifest": backtest_rm},
        )
        manifest_path = _write_research_manifest(result, request)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "preflight_report" in payload["preflight_artifacts"]
        assert "report_manifest" in payload["eval_artifacts"]
        assert "summary_csv" in payload["backtest_artifacts"]
        assert "report_manifest" in payload["backtest_artifacts"]
        # Stage-qualified in top-level artifacts; no duplicates across stages
        assert payload["artifacts"] == sorted(payload["artifacts"])
        assert "backtest:report_manifest" in payload["artifacts"]
        assert "backtest:summary_csv" in payload["artifacts"]
        assert "eval:report_manifest" in payload["artifacts"]
        assert "preflight:preflight_report" in payload["artifacts"]
        # All stage-qualified keys are unique
        assert len(payload["artifacts"]) == len(set(payload["artifacts"]))
        assert len(payload["artifacts"]) == 4

    def test_research_manifest_records_benchmark_inputs(self, tmp_path):
        """_write_research_manifest records benchmark_table/code/value_column."""
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        request = _make_request(
            tmp_path,
            output_dir=output_dir,
            run_id="test-run-benchmark",
            benchmark_table="public.index_daily",
            benchmark_code="000300.SH",
            benchmark_value_column="close",
        )
        result = ResearchRunResult(
            run_id="test-run-benchmark",
            output_dir=output_dir,
            preflight_status="skipped",
            eval_status="ok",
            backtest_status="ok",
        )
        manifest_path = _write_research_manifest(result, request)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["benchmark_table"] == "public.index_daily"
        assert payload["benchmark_code"] == "000300.SH"
        assert payload["benchmark_value_column"] == "close"

    def test_research_manifest_benchmark_fields_null_when_omitted(self, tmp_path):
        """_write_research_manifest writes null benchmark fields when not provided."""
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        request = _make_request(
            tmp_path,
            output_dir=output_dir,
            run_id="test-run-no-benchmark",
        )
        result = ResearchRunResult(
            run_id="test-run-no-benchmark",
            output_dir=output_dir,
            preflight_status="skipped",
            eval_status="ok",
            backtest_status="ok",
        )
        manifest_path = _write_research_manifest(result, request)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["benchmark_table"] is None
        assert payload["benchmark_code"] is None
        assert payload["benchmark_value_column"] == "close"


class TestRunEvalReal:
    """Regression: tests that exercise the real _run_eval() without monkeypatching it."""

    def test_run_eval_passes_benchmark_params_to_assembler(self, monkeypatch):
        """_run_eval() passes benchmark params through to ResearchFrameAssembler.build()."""
        spec = StrategySpec(
            name="test",
            signal_expression="close > 5",
            exit_signal_expression=None,
            market_fields=["close"],
            factor_fields=[],
            forward_horizons=[1, 3, 5],
            holding_days=5,
            quantiles=None,
        )

        dates = pd.to_datetime([
            "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
        ])
        bars = pd.DataFrame({
            "ts_code": ["000001.SZ"] * 5,
            "trade_date": dates,
            "close": [10.0, 10.5, 11.0, 10.8, 11.2],
        })

        assembler_build_calls: list[dict] = []

        class RealFakeStore:
            def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
                return bars

            def load_factor_history(self, ts_codes, field_requests, start, end):
                return pd.DataFrame(columns=["ts_code", "trade_date"])

            def load_benchmark_bars(self, table_name, ts_codes, start, end, fields=None, limit=None):
                assembler_build_calls.append(
                    {
                        "table_name": table_name,
                        "ts_codes": ts_codes,
                        "fields": fields,
                    }
                )
                return pd.DataFrame(
                    {
                        "ts_code": [ts_codes[0], ts_codes[0]],
                        "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                        "close": [100.0, 101.0],
                    }
                )

        store = RealFakeStore()
        request = ResearchRunRequest(
            strategy_path=Path("dummy.yaml"),
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            output_dir=Path("/tmp/dummy"),
            benchmark_table="public.index_daily",
            benchmark_code="000300.SH",
            benchmark_value_column="close",
        )

        status, result = _run_eval(store, spec, request)
        assert status == "ok"
        assert result is not None
        # Verify benchmark params were threaded to the assembler
        assert len(assembler_build_calls) == 1
        assert assembler_build_calls[0]["table_name"] == "public.index_daily"
        assert assembler_build_calls[0]["ts_codes"] == ["000300.SH"]
        assert assembler_build_calls[0]["fields"] == ["close"]
        # Evaluation ran successfully and produced forward returns
        assert not result.events.empty
        assert "forward_return_1" in result.events.columns

    def test_run_eval_with_correct_evaluation_request_shape(self, monkeypatch):
        """_run_eval() constructs a valid EvaluationRequest and calls evaluate()."""
        spec = StrategySpec(
            name="test",
            signal_expression="close > 5",
            exit_signal_expression=None,
            market_fields=["close"],
            factor_fields=[],
            forward_horizons=[1, 3, 5],
            holding_days=5,
            quantiles=None,
        )

        dates = pd.to_datetime([
            "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
        ])
        bars = pd.DataFrame({
            "ts_code": ["000001.SZ"] * 5,
            "trade_date": dates,
            "close": [10.0, 10.5, 11.0, 10.8, 11.2],
        })

        class RealFakeStore:
            def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
                return bars

            def load_factor_history(self, ts_codes, field_requests, start, end):
                return pd.DataFrame(columns=["ts_code", "trade_date"])

        store = RealFakeStore()
        request = ResearchRunRequest(
            strategy_path=Path("dummy.yaml"),
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            output_dir=Path("/tmp/dummy"),
        )

        status, result = _run_eval(store, spec, request)
        assert status == "ok"
        assert result is not None
        assert not result.events.empty
        # Verify forward returns were computed
        assert "forward_return_1" in result.events.columns


    def test_run_eval_passes_metadata_as_of_to_assembler(self, monkeypatch):
        """_run_eval() passes metadata_as_of through to ResearchFrameAssembler.build()."""
        from quant_research_engine.data.assembler import ResearchFrameAssembler

        spec = StrategySpec(
            name="test",
            signal_expression="close > 5",
            exit_signal_expression=None,
            market_fields=["close"],
            factor_fields=[],
            forward_horizons=[1, 3, 5],
            holding_days=5,
            quantiles=None,
        )

        dates = pd.to_datetime([
            "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08",
        ])
        bars = pd.DataFrame({
            "ts_code": ["000001.SZ"] * 5,
            "trade_date": dates,
            "close": [10.0, 10.5, 11.0, 10.8, 11.2],
        })

        build_kwargs: list[dict] = []
        original_build = ResearchFrameAssembler.build

        def capture_build(self, **kwargs):
            build_kwargs.append(kwargs)
            return original_build(self, **kwargs)

        monkeypatch.setattr(ResearchFrameAssembler, "build", capture_build)

        class RealFakeStore:
            def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
                return bars

            def load_factor_history(self, ts_codes, field_requests, start, end):
                return pd.DataFrame(columns=["ts_code", "trade_date"])

            def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
                return pd.DataFrame(columns=["ts_code"])

        store = RealFakeStore()
        as_of_date = date(2025, 12, 31)
        request = ResearchRunRequest(
            strategy_path=Path("dummy.yaml"),
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            output_dir=Path("/tmp/dummy"),
            metadata_as_of=as_of_date,
        )

        status, result = _run_eval(store, spec, request)
        assert status == "ok"
        assert result is not None
        assert len(build_kwargs) == 1
        assert build_kwargs[0].get("metadata_as_of") == as_of_date


class TestRunResearchRunOrchestration:
    def test_preflight_error_short_circuits(self, tmp_path, monkeypatch):
        """Preflight error should stop pipeline before eval/backtest."""
        spec = _make_fake_spec()
        strat_path = tmp_path / "strategy.yaml"
        strat_path.write_text("name: test\nsignal:\n  entry: close > 0\n")
        output_dir = tmp_path / "run_output"

        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._build_db_store",
            lambda db_url=None: FakeStore(None),
        )
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run.StrategySpec",
            type("FakeSpec", (), {"from_yaml": staticmethod(lambda path: spec)}),
        )

        called_eval = []
        called_backtest = []
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_eval",
            lambda *a, **kw: called_eval.append(1) or ("ok", None),
        )
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_backtest",
            lambda *a, **kw: called_backtest.append(1) or ("ok", {}),
        )
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_preflight",
            lambda *a, **kw: ("error", MagicMock(status="error")),
        )

        result = run_research_run(
            ResearchRunRequest(
                strategy_path=strat_path,
                start=date(2024, 1, 1),
                end=date(2024, 2, 1),
                output_dir=output_dir,
                run_id="err-run-001",
                db_url="postgresql://localhost/test",
            )
        )
        assert result.preflight_status == "error"
        assert result.eval_status == "skipped"
        assert result.backtest_status == "error"
        assert result.error_message is not None
        assert "Preflight failed" in result.error_message
        assert len(called_eval) == 0
        assert len(called_backtest) == 0
        assert result.manifest_path is not None
        assert result.manifest_path.exists()
        assert result.report_manifest_path is not None
        assert result.report_manifest_path.exists()

    def test_eval_error_short_circuits(self, tmp_path, monkeypatch):
        """Eval error should stop pipeline before backtest."""
        spec = _make_fake_spec()
        strat_path = tmp_path / "strategy.yaml"
        strat_path.write_text("name: test\nsignal:\n  entry: close > 0\n")
        output_dir = tmp_path / "run_output"

        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._build_db_store",
            lambda db_url=None: FakeStore(None),
        )
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run.StrategySpec",
            type("FakeSpec", (), {"from_yaml": staticmethod(lambda path: spec)}),
        )

        called_backtest = []
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_preflight",
            lambda *a, **kw: ("ok", MagicMock(status="ok")),
        )
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_eval",
            lambda *a, **kw: ("error", None),
        )
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_backtest",
            lambda *a, **kw: called_backtest.append(1) or ("ok", {}),
        )

        result = run_research_run(
            ResearchRunRequest(
                strategy_path=strat_path,
                start=date(2024, 1, 1),
                end=date(2024, 2, 1),
                output_dir=output_dir,
                run_id="eval-err-001",
                db_url="postgresql://localhost/test",
            )
        )
        assert result.preflight_status == "ok"
        assert result.eval_status == "error"
        assert result.backtest_status == "error"
        assert result.error_message == "Evaluation failed"
        assert len(called_backtest) == 0
        assert result.report_manifest_path is not None
        assert result.report_manifest_path.exists()

    def test_full_success_writes_all_stage_artifacts(self, tmp_path, monkeypatch):
        """Full successful run writes preflight, eval, backtest artifacts."""
        spec = _make_fake_spec()
        strat_path = tmp_path / "strategy.yaml"
        strat_path.write_text("name: test\nsignal:\n  entry: close > 0\n")
        output_dir = tmp_path / "run_output"

        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._build_db_store",
            lambda db_url=None: FakeStore(None),
        )
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run.StrategySpec",
            type("FakeSpec", (), {"from_yaml": staticmethod(lambda path: spec)}),
        )

        # Preflight mock
        preflight_report = MagicMock()
        preflight_report.status = "ok"
        preflight_report.summary = "All good"
        for attr in ("missing_factor_requests", "missing_factors", "details",
                      "market_fields_available", "factor_fields_available",
                      "universe_size", "factor_coverage", "calendar_range"):
            setattr(preflight_report, attr, None)
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_preflight",
            lambda *a, **kw: ("ok", preflight_report),
        )

        # Eval mock
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_eval",
            lambda *a, **kw: ("ok", _make_fake_eval_result()),
        )

        # Backtest mock
        backtest_dir = output_dir / "backtest"
        backtest_dir.mkdir(parents=True)
        summary_csv = backtest_dir / "summary.csv"
        summary_csv.write_text("col1,col2\n1,2")
        backtest_rm = backtest_dir / "report_manifest.json"
        backtest_rm.write_text("{}")
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_backtest",
            lambda *a, **kw: ("ok", {"summary_csv": summary_csv, "report_manifest": backtest_rm}),
        )

        result = run_research_run(
            ResearchRunRequest(
                strategy_path=strat_path,
                start=date(2024, 1, 1),
                end=date(2024, 2, 1),
                output_dir=output_dir,
                run_id="full-ok-001",
                db_url="postgresql://localhost/test",
            )
        )
        assert result.preflight_status == "ok"
        assert result.eval_status == "ok"
        assert result.backtest_status == "ok"
        assert result.error_message is None

        assert "preflight_report" in result.preflight_paths
        preflight_path = result.preflight_paths["preflight_report"]
        assert preflight_path.exists()
        assert preflight_path.parent.name == "preflight"

        assert "events" in result.eval_paths
        assert "run_manifest" in result.eval_paths
        assert "report_manifest" in result.eval_paths
        for p in result.eval_paths.values():
            assert p.exists()
            assert p.parent.name == "eval"

        assert result.backtest_paths
        for p in result.backtest_paths.values():
            assert p.exists()

        assert result.manifest_path is not None
        assert result.manifest_path.exists()
        payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert "preflight_report" in payload["preflight_artifacts"]
        assert "events" in payload["eval_artifacts"]
        assert "report_manifest" in payload["eval_artifacts"]

        # report_manifest.json should exist and be loadable
        assert result.report_manifest_path is not None
        assert result.report_manifest_path.exists()
        rm_payload = json.loads(result.report_manifest_path.read_text(encoding="utf-8"))
        assert rm_payload["kind"] == "research_run_report_manifest"
        assert rm_payload["schema_version"] == 1
        file_keys = {f["key"] for f in rm_payload["files"]}
        assert "research_run_manifest" in file_keys
        assert "preflight_report" in file_keys
        assert "eval_report_manifest" in file_keys
        assert "backtest_report_manifest" in file_keys

    def test_skip_preflight_and_eval_still_runs_backtest(self, tmp_path, monkeypatch):
        """When preflight and eval are skipped, backtest still runs."""
        spec = _make_fake_spec()
        strat_path = tmp_path / "strategy.yaml"
        strat_path.write_text("name: test\nsignal:\n  entry: close > 0\n")
        output_dir = tmp_path / "run_output"

        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._build_db_store",
            lambda db_url=None: FakeStore(None),
        )
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run.StrategySpec",
            type("FakeSpec", (), {"from_yaml": staticmethod(lambda path: spec)}),
        )

        backtest_dir = output_dir / "backtest"
        backtest_dir.mkdir(parents=True)
        summary_csv = backtest_dir / "summary.csv"
        summary_csv.write_text("col1\n1")

        called = []
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_backtest",
            lambda *a, **kw: called.append(1) or ("ok", {"summary_csv": summary_csv}),
        )

        result = run_research_run(
            ResearchRunRequest(
                strategy_path=strat_path,
                start=date(2024, 1, 1),
                end=date(2024, 2, 1),
                output_dir=output_dir,
                run_id="skip-run-001",
                db_url="postgresql://localhost/test",
                skip_preflight=True,
                skip_eval=True,
            )
        )
        assert result.preflight_status == "skipped"
        assert result.eval_status == "skipped"
        assert result.backtest_status == "ok"
        assert len(called) == 1
        assert result.preflight_paths == {}
        assert result.eval_paths == {}
        # report manifest should exist but not include preflight/eval entries
        assert result.report_manifest_path is not None
        assert result.report_manifest_path.exists()
        rm_payload = json.loads(result.report_manifest_path.read_text(encoding="utf-8"))
        rm_keys = {f["key"] for f in rm_payload["files"]}
        assert "research_run_manifest" in rm_keys
        assert "preflight_report" not in rm_keys
        assert "eval_report_manifest" not in rm_keys

    def test_backtest_artifacts_in_subdirectory(self, tmp_path, monkeypatch):
        """Backtest artifacts are written under backtest/ not the run root."""
        spec = _make_fake_spec()
        strat_path = tmp_path / "strategy.yaml"
        strat_path.write_text("name: test\nsignal:\n  entry: close > 0\n")
        output_dir = tmp_path / "run_output"

        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._build_db_store",
            lambda db_url=None: FakeStore(None),
        )
        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run.StrategySpec",
            type("FakeSpec", (), {"from_yaml": staticmethod(lambda path: spec)}),
        )

        backtest_dir = output_dir / "backtest"
        backtest_dir.mkdir(parents=True)
        summary_csv = backtest_dir / "summary.csv"
        summary_csv.write_text("col1\n1")

        captured_backtest_dir = []

        def _fake_backtest(store, s, request):
            captured_backtest_dir.append(request.output_dir)
            return ("ok", {"summary_csv": summary_csv})

        monkeypatch.setattr(
            "quant_research_engine.orchestration.research_run._run_backtest",
            _fake_backtest,
        )

        result = run_research_run(
            ResearchRunRequest(
                strategy_path=strat_path,
                start=date(2024, 1, 1),
                end=date(2024, 2, 1),
                output_dir=output_dir,
                run_id="bt-dir-001",
                db_url="postgresql://localhost/test",
                skip_preflight=True,
                skip_eval=True,
            )
        )
        assert result.backtest_status == "ok"
        assert len(captured_backtest_dir) == 1
        assert captured_backtest_dir[0] == output_dir


class TestWriteResearchReportManifest:
    def test_writes_report_manifest_with_research_run_manifest(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        (output_dir / "research_run_manifest.json").write_text(
            json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                         "run_id": "r1", "command": "research-run",
                         "strategy_path": "s.yaml", "artifacts": []}),
            encoding="utf-8",
        )
        request = _make_request(tmp_path, output_dir=output_dir, run_id="r1")
        result = ResearchRunResult(
            run_id="r1", output_dir=output_dir,
            preflight_status="ok", eval_status="ok", backtest_status="ok",
            manifest_path=output_dir / "research_run_manifest.json",
        )
        path = _write_research_report_manifest(result, request)
        assert path.name == "report_manifest.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["kind"] == "research_run_report_manifest"
        assert payload["schema_version"] == 1
        file_keys = {f["key"] for f in payload["files"]}
        assert "research_run_manifest" in file_keys
        run_entry = next(f for f in payload["files"] if f["key"] == "research_run_manifest")
        assert run_entry["role"] == "run_manifest"
        assert run_entry["path"] == "research_run_manifest.json"

    def test_includes_preflight_report_when_present(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        (output_dir / "research_run_manifest.json").write_text(
            json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                         "run_id": "r2", "command": "research-run",
                         "strategy_path": "s.yaml", "artifacts": []}),
            encoding="utf-8",
        )
        preflight_dir = output_dir / "preflight"
        preflight_dir.mkdir()
        preflight_path = preflight_dir / "preflight_report.json"
        preflight_path.write_text("{}")
        request = _make_request(tmp_path, output_dir=output_dir, run_id="r2")
        result = ResearchRunResult(
            run_id="r2", output_dir=output_dir,
            preflight_status="ok", eval_status="skipped", backtest_status="ok",
            manifest_path=output_dir / "research_run_manifest.json",
            preflight_paths={"preflight_report": preflight_path},
        )
        path = _write_research_report_manifest(result, request)
        payload = json.loads(path.read_text(encoding="utf-8"))
        file_keys = {f["key"] for f in payload["files"]}
        assert "preflight_report" in file_keys
        pf_entry = next(f for f in payload["files"] if f["key"] == "preflight_report")
        assert pf_entry["role"] == "preflight_report"
        assert pf_entry["path"] == "preflight/preflight_report.json"

    def test_includes_eval_report_manifest_when_present(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        (output_dir / "research_run_manifest.json").write_text(
            json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                         "run_id": "r3", "command": "research-run",
                         "strategy_path": "s.yaml", "artifacts": []}),
            encoding="utf-8",
        )
        eval_dir = output_dir / "eval"
        eval_dir.mkdir()
        eval_rm = eval_dir / "report_manifest.json"
        eval_rm.write_text("{}")
        request = _make_request(tmp_path, output_dir=output_dir, run_id="r3")
        result = ResearchRunResult(
            run_id="r3", output_dir=output_dir,
            preflight_status="skipped", eval_status="ok", backtest_status="ok",
            manifest_path=output_dir / "research_run_manifest.json",
            eval_paths={"report_manifest": eval_rm},
        )
        path = _write_research_report_manifest(result, request)
        payload = json.loads(path.read_text(encoding="utf-8"))
        file_keys = {f["key"] for f in payload["files"]}
        assert "eval_report_manifest" in file_keys

    def test_includes_backtest_report_manifest_when_present(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        (output_dir / "research_run_manifest.json").write_text(
            json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                         "run_id": "r4", "command": "research-run",
                         "strategy_path": "s.yaml", "artifacts": []}),
            encoding="utf-8",
        )
        bt_dir = output_dir / "backtest"
        bt_dir.mkdir()
        bt_rm = bt_dir / "report_manifest.json"
        bt_rm.write_text("{}")
        request = _make_request(tmp_path, output_dir=output_dir, run_id="r4")
        result = ResearchRunResult(
            run_id="r4", output_dir=output_dir,
            preflight_status="skipped", eval_status="skipped", backtest_status="ok",
            manifest_path=output_dir / "research_run_manifest.json",
            backtest_paths={"report_manifest": bt_rm},
        )
        path = _write_research_report_manifest(result, request)
        payload = json.loads(path.read_text(encoding="utf-8"))
        file_keys = {f["key"] for f in payload["files"]}
        assert "backtest_report_manifest" in file_keys

    def test_skipped_preflight_not_included(self, tmp_path):
        output_dir = tmp_path / "run_output"
        output_dir.mkdir()
        (output_dir / "research_run_manifest.json").write_text(
            json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                         "run_id": "r5", "command": "research-run",
                         "strategy_path": "s.yaml", "artifacts": []}),
            encoding="utf-8",
        )
        request = _make_request(tmp_path, output_dir=output_dir, run_id="r5")
        result = ResearchRunResult(
            run_id="r5", output_dir=output_dir,
            preflight_status="skipped", eval_status="skipped", backtest_status="ok",
            manifest_path=output_dir / "research_run_manifest.json",
            preflight_paths={},
            eval_paths={},
        )
        path = _write_research_report_manifest(result, request)
        payload = json.loads(path.read_text(encoding="utf-8"))
        file_keys = {f["key"] for f in payload["files"]}
        assert "research_run_manifest" in file_keys
        assert "preflight_report" not in file_keys
        assert "eval_report_manifest" not in file_keys
