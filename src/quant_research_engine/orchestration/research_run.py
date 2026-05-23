from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from quant_research_engine.data.assembler import ResearchFrameAssembler
from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.settings import DatabaseSettings
from quant_research_engine.evaluation.engine import EvaluationEngine
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


@dataclass
class ResearchRunResult:
    run_id: str
    output_dir: Path
    preflight_status: str  # "ok", "error", "skipped"
    eval_status: str  # "ok", "error", "skipped"
    backtest_status: str  # "ok", "error"
    backtest_paths: dict[str, Path] = field(default_factory=dict)
    manifest_path: Path | None = None
    error_message: str | None = None


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
    )
    report = PreflightRunner(store).run(preflight_req)
    status = report.status
    return status, report


def _run_eval(
    store: PostgresDataStore,
    spec: StrategySpec,
    request: ResearchRunRequest,
) -> tuple[str, object | None]:
    """Run evaluation. Returns (status, eval_result_or_None)."""
    assembler = ResearchFrameAssembler(store)
    frame = assembler.build(
        ts_codes=request.codes,
        start=request.start,
        end=request.end,
        market_fields=spec.market_fields,
        factor_fields=spec.factor_fields,
    )
    eval_req = EvaluationRequest(
        frame=frame,
        expression=spec.signal_expression,
        start=request.start,
        end=request.end,
        group_by=request.group_by,
        round_trip_cost_rate=request.round_trip_cost_rate,
        random_baseline_seed=request.random_baseline_seed,
    )
    result = EvaluationEngine().run(eval_req)
    return "ok", result


def _run_backtest(
    store: PostgresDataStore,
    spec: StrategySpec,
    request: ResearchRunRequest,
) -> tuple[str, dict[str, Path]]:
    """Run backtest. Returns (status, paths_dict)."""
    assembler = ResearchFrameAssembler(store)
    frame = assembler.build(
        ts_codes=request.codes,
        start=request.start,
        end=request.end,
        market_fields=spec.market_fields,
        factor_fields=spec.factor_fields,
    )
    market_profile = (
        __import__("quant_research_engine.config.loader", fromlist=["load_market_profile"]).load_market_profile(
            request.market_profile_path
        )
        if request.market_profile_path
        else AShareMarketProfile()
    )

    if request.backtest_mode == "batch":
        batch_req = BatchBacktestRequest(
            initial_cash=request.initial_cash,
            entry_signal=spec.signal_expression,
            exit_signal=spec.exit_signal_expression,
            holding_days=spec.holding_days,
            metadata_columns=request.metadata_columns,
            window_size=request.window_size,
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
        paths = write_batch_result(result, request.output_dir, run_request=run_request_payload, run_id=request.run_id)
        return "ok", paths

    # shared-cash mode
    from quant_research_engine.portfolio.io import write_shared_cash_result
    from quant_research_engine.portfolio.shared import SharedCashBacktestEngine, SharedCashBacktestRequest

    shared_req = SharedCashBacktestRequest(
        initial_cash=request.initial_cash,
        entry_signal=spec.signal_expression,
        exit_signal=spec.exit_signal_expression,
        holding_days=spec.holding_days,
        metadata_columns=request.metadata_columns,
        window_size=request.window_size,
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
    paths = write_shared_cash_result(shared_result, request.output_dir, run_request=run_request_payload, run_id=request.run_id)
    return "ok", paths


def _write_research_manifest(result: ResearchRunResult) -> Path:
    """Write research_run_manifest.json and return its path."""
    manifest_path = result.output_dir / "research_run_manifest.json"
    payload: dict[str, object] = {
        "run_id": result.run_id,
        "output_dir": str(result.output_dir),
        "stages": {
            "preflight": result.preflight_status,
            "eval": result.eval_status,
            "backtest": result.backtest_status,
        },
        "backtest_artifacts": {
            key: str(path.relative_to(result.output_dir))
            for key, path in result.backtest_paths.items()
        },
    }
    if result.error_message:
        payload["error"] = result.error_message
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


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

    # Stage 1: Preflight
    if not request.skip_preflight:
        spec = StrategySpec.from_yaml(request.strategy_path)
        status, report = _run_preflight(store, spec, request)
        result.preflight_status = status
        if status == "error":
            result.error_message = f"Preflight failed (status={status})"
            result.manifest_path = _write_research_manifest(result)
            return result
    else:
        spec = StrategySpec.from_yaml(request.strategy_path)

    # Stage 2: Evaluation
    if not request.skip_eval:
        status, eval_result = _run_eval(store, spec, request)
        result.eval_status = status
        if status == "error":
            result.error_message = "Evaluation failed"
            result.manifest_path = _write_research_manifest(result)
            return result

    # Stage 3: Backtest
    status, paths = _run_backtest(store, spec, request)
    result.backtest_status = status
    result.backtest_paths = paths

    result.manifest_path = _write_research_manifest(result)
    return result
