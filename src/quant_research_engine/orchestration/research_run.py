from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from quant_research_engine.data.assembler import ResearchFrameAssembler
from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.settings import DatabaseSettings
from quant_research_engine.evaluation.engine import EvaluationEngine
from quant_research_engine.evaluation.io import write_evaluation_output
from quant_research_engine.evaluation.models import EvaluationRequest
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
from quant_research_engine.portfolio.io import write_batch_result
from quant_research_engine.preflight import PreflightRequest, PreflightRunner
from quant_research_engine.strategies.spec import StrategySpec


@dataclass
class ResearchRunRequest:
    strategy_path: Path
    start: date
    end: date
    output_dir: Path
    run_id: str | None = None
    db_url: str | None = None
    codes: list[str] | None = None
    market_profile_path: Path | None = None
    skip_preflight: bool = False
    skip_eval: bool = False
    backtest_mode: Literal["batch", "shared"] = "batch"
    initial_cash: float = 1_000_000
    min_factor_coverage: float = 0.8
    group_by: list[str] | None = None
    random_baseline_seed: int | None = None
    round_trip_cost_rate: float | None = None
    metadata_columns: list[str] | None = None
    window_size: int | None = None
    metadata_as_of: date | None = None
    benchmark_table: str | None = None
    benchmark_code: str | None = None
    benchmark_value_column: str = "close"
    compact: bool = False
    engine_impl: str = "simulator"
    position_sizing: str = "full_compound"
    profile_overrides: dict[str, float] | None = None
    universe_filter: bool = False


@dataclass
class ResearchRunResult:
    run_id: str
    output_dir: Path
    preflight_status: str  # "ok", "error", "skipped"
    eval_status: str  # "ok", "error", "skipped"
    backtest_status: str  # "ok", "error"
    backtest_paths: dict[str, Path] = field(default_factory=dict)
    eval_paths: dict[str, Path] = field(default_factory=dict)
    preflight_paths: dict[str, Path] = field(default_factory=dict)
    manifest_path: Path | None = None
    report_manifest_path: Path | None = None
    error_message: str | None = None
    stage_durations_s: dict[str, float] = field(default_factory=dict)


def _build_db_store(db_url: str | None = None) -> PostgresDataStore:
    settings = DatabaseSettings(market_db_url=db_url) if db_url else DatabaseSettings.from_env()
    store = PostgresDataStore(settings)
    store.ping()
    return store


def _run_preflight(
    store: PostgresDataStore,
    spec: StrategySpec,
    request: ResearchRunRequest,
) -> tuple[str, object | None]:
    """Run preflight. Returns (status, preflight_report_or_None)."""
    preflight_req = PreflightRequest(
        ts_codes=request.codes,
        start=request.start,
        end=request.end,
        market_fields=spec.market_fields,
        factor_fields=spec.factor_fields,
        min_factor_coverage=request.min_factor_coverage,
        exclude_st=spec.exclude_st,
        exclude_suspended=spec.exclude_suspended,
        exclude_risk_warning=spec.exclude_risk_warning,
        min_listing_days=spec.min_listing_days,
        min_amount=spec.min_amount,
        metadata_as_of=request.metadata_as_of,
    )
    report = PreflightRunner(store).run(preflight_req)
    status = report.status
    return status, report


def _write_preflight_artifact(report, output_dir: Path) -> Path:
    """Persist preflight report JSON. Returns the file path."""
    directory = output_dir / "preflight"
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "preflight_report.json"

    if hasattr(report, "to_dict"):
        payload: dict[str, object] = report.to_dict()
    else:
        # Fallback for test fakes that don't implement to_dict()
        payload = {"status": getattr(report, "status", "unknown")}
        for attr in ("summary", "missing_factor_requests", "missing_factors",
                      "details", "market_fields_available", "factor_fields_available",
                      "universe_size", "factor_coverage", "calendar_range"):
            val = getattr(report, attr, None)
            if val is not None:
                try:
                    json.dumps(val)
                    payload[attr] = val
                except (TypeError, ValueError):
                    payload[attr] = str(val)

    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, cls=_PreflightEncoder), encoding="utf-8")
    return report_path


class _PreflightEncoder(json.JSONEncoder):
    def default(self, o):
        try:
            return super().default(o)
        except TypeError:
            return str(o)


def _run_eval(
    store: PostgresDataStore,
    spec: StrategySpec,
    request: ResearchRunRequest,
    frame=None,
) -> tuple[str, object | None]:
    """Run evaluation. Returns (status, eval_result_or_None)."""
    if frame is None:
        assembler = ResearchFrameAssembler(store)
        frame = assembler.build(
            ts_codes=request.codes,
            start=request.start,
            end=request.end,
            market_fields=spec.market_fields,
            factor_fields=spec.factor_fields,
            metadata_as_of=request.metadata_as_of,
            benchmark_table=request.benchmark_table,
            benchmark_code=request.benchmark_code,
            benchmark_value_column=request.benchmark_value_column,
        )
    eval_req = EvaluationRequest(
        signal_expression=spec.signal_expression,
        forward_horizons=spec.forward_horizons,
        factor_columns=[f.logical_name for f in spec.factor_fields] if spec.factor_fields else None,
        quantiles=spec.quantiles,
        round_trip_cost_rate=request.round_trip_cost_rate,
        group_by=request.group_by,
        random_baseline_seed=request.random_baseline_seed,
    )
    result = EvaluationEngine().evaluate(frame, eval_req)
    return "ok", result


def _write_eval_artifacts(result, request: ResearchRunRequest) -> dict[str, Path]:
    """Persist evaluation artifacts under <output_dir>/eval/. Returns artifact paths dict."""
    eval_dir = request.output_dir / "eval"
    return write_evaluation_output(
        result=result,
        output_dir=eval_dir,
        run_id=request.run_id,
        strategy_path=str(request.strategy_path),
        start=str(request.start),
        end=str(request.end),
        codes=request.codes,
        round_trip_cost_rate=request.round_trip_cost_rate,
        market_profile=str(request.market_profile_path) if request.market_profile_path else None,
        group_by=request.group_by,
        random_baseline_seed=request.random_baseline_seed,
        benchmark_table=request.benchmark_table,
        benchmark_code=request.benchmark_code,
        benchmark_value_column=request.benchmark_value_column,
    )


def _run_backtest(
    store: PostgresDataStore,
    spec: StrategySpec,
    request: ResearchRunRequest,
    frame=None,
) -> tuple[str, dict[str, Path]]:
    """Run backtest. Returns (status, paths_dict)."""
    if frame is None:
        assembler = ResearchFrameAssembler(store)
        frame = assembler.build(
            ts_codes=request.codes,
            start=request.start,
            end=request.end,
            market_fields=spec.market_fields,
            factor_fields=spec.factor_fields,
            metadata_as_of=request.metadata_as_of,
        )
    market_profile = (
        __import__("quant_research_engine.config.loader", fromlist=["load_market_profile"]).load_market_profile(
            request.market_profile_path
        )
        if request.market_profile_path
        else AShareMarketProfile()
    )
    if request.profile_overrides:
        from dataclasses import replace

        from quant_research_engine.portfolio.universe import validate_profile_overrides

        validate_profile_overrides(request.profile_overrides)
        market_profile = replace(market_profile, **request.profile_overrides)

    universe_report = None
    if request.universe_filter:
        from quant_research_engine.portfolio.universe import (
            UniverseFilterSpec,
            apply_universe_filter,
            load_universe_metadata,
        )

        universe_spec = UniverseFilterSpec(
            exclude_st=spec.exclude_st,
            exclude_suspended=spec.exclude_suspended,
            exclude_risk_warning=spec.exclude_risk_warning,
            min_listing_days=spec.min_listing_days,
            min_amount=spec.min_amount,
        )
        if universe_spec.any_enabled():
            metadata = load_universe_metadata(store, request.codes, as_of=request.start)
            frame, universe_report = apply_universe_filter(
                frame, universe_spec, start=request.start, metadata=metadata
            )

    backtest_dir = request.output_dir / "backtest"
    backtest_dir.mkdir(parents=True, exist_ok=True)

    if universe_report is not None:
        universe_path = backtest_dir / "universe_report.json"
        universe_path.write_text(
            json.dumps(universe_report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    if request.backtest_mode == "batch":
        batch_req = BatchBacktestRequest(
            symbols=request.codes,
            initial_cash_per_symbol=request.initial_cash,
            entry_signal=spec.signal_expression,
            exit_signal=spec.exit_signal_expression,
            holding_days=spec.holding_days,
            summary_metadata_columns=request.metadata_columns,
            engine_impl=request.engine_impl,
            position_sizing=request.position_sizing,
        )
        result = BatchBacktestEngine(market_profile).run(frame, batch_req)
        run_request_payload: dict[str, object] = {
            "command": "backtest-batch",
            "strategy_path": str(request.strategy_path),
            "request": {
                "initial_cash": request.initial_cash,
                "entry_signal": spec.signal_expression,
                "exit_signal": spec.exit_signal_expression,
                "holding_days": spec.holding_days,
                "start": str(request.start),
                "end": str(request.end),
            },
        }
        paths = write_batch_result(result, backtest_dir, run_request=run_request_payload, run_id=request.run_id, compact=request.compact)
        if universe_report is not None:
            paths["universe_report"] = backtest_dir / "universe_report.json"
        return "ok", paths

    # shared-cash mode
    from quant_research_engine.portfolio.io import write_shared_cash_result
    from quant_research_engine.portfolio.shared import SharedCashBacktestEngine, SharedCashBacktestRequest

    shared_req = SharedCashBacktestRequest(
        symbols=request.codes,
        initial_cash=request.initial_cash,
        entry_signal=spec.signal_expression,
        exit_signal=spec.exit_signal_expression,
        holding_days=spec.holding_days,
        max_positions=50,
        metadata_columns=request.metadata_columns,
    )
    shared_result = SharedCashBacktestEngine(market_profile).run(frame, shared_req)
    run_request_payload = {
        "command": "backtest-shared",
        "strategy_path": str(request.strategy_path),
        "request": {
            "initial_cash": request.initial_cash,
            "entry_signal": spec.signal_expression,
            "exit_signal": spec.exit_signal_expression,
            "holding_days": spec.holding_days,
            "start": str(request.start),
            "end": str(request.end),
        },
    }
    paths = write_shared_cash_result(shared_result, backtest_dir, run_request=run_request_payload, run_id=request.run_id)
    if universe_report is not None:
        paths["universe_report"] = backtest_dir / "universe_report.json"
    return "ok", paths


def _write_research_manifest(result: ResearchRunResult, request: ResearchRunRequest) -> Path:
    """Write research_run_manifest.json and return its path."""
    manifest_path = result.output_dir / "research_run_manifest.json"

    def _rel_paths(paths: dict[str, Path], base: Path) -> dict[str, str]:
        return {key: str(path.relative_to(base)) for key, path in paths.items()}

    run_root = result.output_dir

    stages: dict[str, object] = {
        "preflight": result.preflight_status,
        "eval": result.eval_status,
        "backtest": result.backtest_status,
    }

    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "research_run_manifest",
        "run_id": result.run_id,
        "command": "research-run",
        "strategy_path": str(request.strategy_path),
        "output_dir": str(result.output_dir),
        "stages": stages,
        "benchmark_table": request.benchmark_table,
        "benchmark_code": request.benchmark_code,
        "benchmark_value_column": request.benchmark_value_column,
        "metadata_as_of": str(request.metadata_as_of) if request.metadata_as_of else None,
        "stage_durations_s": result.stage_durations_s,
        "profile_overrides": request.profile_overrides,
        "universe_filter": request.universe_filter,
    }

    if result.preflight_paths:
        payload["preflight_artifacts"] = _rel_paths(result.preflight_paths, run_root)
    if result.eval_paths:
        payload["eval_artifacts"] = _rel_paths(result.eval_paths, run_root)
    if result.backtest_paths:
        payload["backtest_artifacts"] = _rel_paths(result.backtest_paths, run_root)

    # Top-level artifacts: stage-qualified keys to avoid duplicates across stages
    all_keys: list[str] = []
    if result.preflight_paths:
        all_keys.extend(f"preflight:{k}" for k in result.preflight_paths.keys())
    if result.eval_paths:
        all_keys.extend(f"eval:{k}" for k in result.eval_paths.keys())
    if result.backtest_paths:
        all_keys.extend(f"backtest:{k}" for k in result.backtest_paths.keys())
    payload["artifacts"] = sorted(all_keys)

    if result.error_message:
        payload["error"] = result.error_message
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def _write_research_report_manifest(result: ResearchRunResult, request: ResearchRunRequest) -> Path:
    """Write a top-level report_manifest.json for the research-run bundle.

    This manifest uses kind ``research_run_report_manifest`` so that
    ``qre report-files`` and ``qre report-audit`` can discover and
    validate the whole run directory.
    """
    manifest_path = result.output_dir / "report_manifest.json"
    files: list[dict[str, str]] = []

    # research_run_manifest.json (always present when this is called)
    if result.manifest_path and result.manifest_path.exists():
        files.append({
            "key": "research_run_manifest",
            "path": "research_run_manifest.json",
            "filename": "research_run_manifest.json",
            "role": "run_manifest",
        })

    # Preflight stage entry point
    if "preflight_report" in result.preflight_paths:
        p = result.preflight_paths["preflight_report"]
        rel = str(p.relative_to(result.output_dir))
        files.append({
            "key": "preflight_report",
            "path": rel,
            "filename": p.name,
            "role": "preflight_report",
        })

    # Evaluation stage entry point
    if "report_manifest" in result.eval_paths:
        p = result.eval_paths["report_manifest"]
        rel = str(p.relative_to(result.output_dir))
        files.append({
            "key": "eval_report_manifest",
            "path": rel,
            "filename": p.name,
            "role": "eval_report_manifest",
        })

    # Backtest stage entry point
    if "report_manifest" in result.backtest_paths:
        p = result.backtest_paths["report_manifest"]
        rel = str(p.relative_to(result.output_dir))
        files.append({
            "key": "backtest_report_manifest",
            "path": rel,
            "filename": p.name,
            "role": "backtest_report_manifest",
        })

    payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "research_run_report_manifest",
        "files": files,
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path


def _build_research_frame(store: PostgresDataStore, spec: StrategySpec, request: ResearchRunRequest):
    """Build the shared market+factor frame for a run (eval and backtest stages
    use identical queries when no benchmark columns are requested)."""
    assembler = ResearchFrameAssembler(store)
    return assembler.build(
        ts_codes=request.codes,
        start=request.start,
        end=request.end,
        market_fields=spec.market_fields,
        factor_fields=spec.factor_fields,
        metadata_as_of=request.metadata_as_of,
    )


def run_research_run(request: ResearchRunRequest) -> ResearchRunResult:
    run_id = request.run_id or uuid.uuid4().hex[:12]
    result = ResearchRunResult(
        run_id=run_id,
        output_dir=request.output_dir,
        preflight_status="skipped",
        eval_status="skipped",
        backtest_status="error",
    )

    store = _build_db_store(request.db_url)
    try:
        # Shared frame: eval and backtest load the same market+factor frame
        # when no benchmark columns are requested; build it once per run.
        shared_frame = None

        def _shared_frame():
            nonlocal shared_frame
            if shared_frame is None:
                shared_frame = _build_research_frame(store, spec, request)
            return shared_frame

        shareable = (
            request.benchmark_table is None
            and request.benchmark_code is None
            and not request.skip_eval
        )

        # Stage 1: Preflight
        if not request.skip_preflight:
            spec = StrategySpec.from_yaml(request.strategy_path)
            t0 = time.perf_counter()
            status, report = _run_preflight(store, spec, request)
            result.stage_durations_s["preflight"] = round(time.perf_counter() - t0, 3)
            result.preflight_status = status
            if status == "ok":
                result.preflight_paths["preflight_report"] = _write_preflight_artifact(report, request.output_dir)
            if status == "error":
                result.error_message = f"Preflight failed (status={status})"
                result.manifest_path = _write_research_manifest(result, request)
                result.report_manifest_path = _write_research_report_manifest(result, request)
                return result
        else:
            spec = StrategySpec.from_yaml(request.strategy_path)

        # Stage 2: Evaluation
        if not request.skip_eval:
            t0 = time.perf_counter()
            if shareable:
                status, eval_result = _run_eval(store, spec, request, frame=_shared_frame())
            else:
                status, eval_result = _run_eval(store, spec, request)
            result.stage_durations_s["eval"] = round(time.perf_counter() - t0, 3)
            result.eval_status = status
            if status == "ok":
                result.eval_paths = _write_eval_artifacts(eval_result, request)
            if status == "error":
                result.error_message = "Evaluation failed"
                result.manifest_path = _write_research_manifest(result, request)
                result.report_manifest_path = _write_research_report_manifest(result, request)
                return result

        # Stage 3: Backtest
        t0 = time.perf_counter()
        if shareable:
            status, paths = _run_backtest(store, spec, request, frame=_shared_frame())
        else:
            status, paths = _run_backtest(store, spec, request)
        result.stage_durations_s["backtest"] = round(time.perf_counter() - t0, 3)
        result.backtest_status = status
        result.backtest_paths = paths

        result.manifest_path = _write_research_manifest(result, request)
        result.report_manifest_path = _write_research_report_manifest(result, request)
        return result
    finally:
        # Dispose DB engines so batch runners do not leak connections;
        # getattr guard keeps test fakes without close() working.
        close = getattr(store, "close", None)
        if callable(close):
            close()
