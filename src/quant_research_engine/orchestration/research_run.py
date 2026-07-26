from __future__ import annotations

import json
import time

import pandas as pd
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
    include_full_market: bool = False
    engine_impl: str = "simulator"
    position_sizing: str = "full_compound"
    profile_overrides: dict[str, float] | None = None
    universe_filter: bool = False
    apply_stops: bool = False
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    symbol_chunk_size: int | None = None


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


def _strategy_identity(strategy_path: Path) -> tuple[str, str | None]:
    """Return (strategy_id, strategy_family) for a strategy YAML path.

    strategy_id is the YAML file stem; strategy_family is the catalog
    subdirectory when the path looks like strategies/catalog/<family>/x.yaml.
    """
    path = Path(strategy_path)
    family = None
    parts = path.parts
    if "catalog" in parts:
        index = parts.index("catalog")
        if len(parts) > index + 2:
            family = parts[index + 1]
    return path.stem, family


def _merge_metadata_into_frame(
    store: PostgresDataStore,
    frame,
    request: ResearchRunRequest,
):
    """Fill summary metadata columns (board/industry_group/cap & liquidity
    buckets) when ``request.metadata_columns`` asks for them. Display-only:
    the engines ignore extra frame columns."""
    if not request.metadata_columns:
        return frame
    from quant_research_engine.data.metadata_compose import (
        compose_symbol_metadata,
        merge_symbol_metadata,
    )

    ts_codes = sorted(frame["ts_code"].dropna().astype(str).unique().tolist())
    if not ts_codes:
        return frame
    metadata = compose_symbol_metadata(store, ts_codes, as_of=request.metadata_as_of or request.start)
    return merge_symbol_metadata(frame, metadata)


def _run_request_payload(
    spec: StrategySpec,
    request: ResearchRunRequest,
    *,
    command: str,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the run_request payload persisted next to backtest artifacts.

    Carries strategy identity (id/name/family), run window and the fields the
    report layer renders in the strategy-intro block. Display metadata only —
    no engine semantics here.
    """
    strategy_id, strategy_family = _strategy_identity(request.strategy_path)
    body: dict[str, object] = {
        "strategy_id": strategy_id,
        "strategy_name": spec.name,
        "strategy_family": strategy_family,
        "initial_cash": request.initial_cash,
        "entry_signal": spec.signal_expression,
        "exit_signal": spec.exit_signal_expression,
        "holding_days": spec.holding_days,
        "stop_loss_pct": spec.stop_loss_pct,
        "take_profit_pct": spec.take_profit_pct,
        "trailing_stop_pct": spec.trailing_stop_pct,
        "exclude_st": spec.exclude_st,
        "exclude_suspended": spec.exclude_suspended,
        "min_listing_days": spec.min_listing_days,
        "min_amount": spec.min_amount,
        "start": str(request.start),
        "end": str(request.end),
        "date_start": str(request.start),
        "date_end": str(request.end),
    }
    if extra:
        body.update(extra)
    return {
        "command": command,
        "strategy_path": str(request.strategy_path),
        "request": body,
    }


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


def _run_batch_chunked(
    store: PostgresDataStore,
    spec: StrategySpec,
    request: ResearchRunRequest,
    market_profile,
    run_id: str | None = None,
) -> tuple[str, dict[str, Path]]:
    """Memory-safe symbol-chunked batch backtest (OOM guard for long windows).

    Symbols are processed in chunks of ``request.symbol_chunk_size``; each chunk
    loads only its own frame slice. Batch engines are per-symbol independent,
    so results are identical to an unchunked run (verified by tests).
    """
    import gc

    from quant_research_engine.portfolio.analytics import summarize_batch_summary
    from quant_research_engine.portfolio.batch import (
        BatchBacktestEngine,
        BatchBacktestRequest,
        BatchBacktestResult,
    )

    symbols = request.codes or store.list_symbols_with_bars(request.start, request.end)
    if request.symbol_chunk_size <= 0:
        raise ValueError("symbol_chunk_size must be positive")
    chunk_size = request.symbol_chunk_size
    n_chunks = (len(symbols) + chunk_size - 1) // chunk_size

    # Effective stop levels (same rule as the unchunked path).
    if request.apply_stops:
        stop_loss = request.stop_loss_pct if request.stop_loss_pct is not None else spec.stop_loss_pct
        take_profit = request.take_profit_pct if request.take_profit_pct is not None else spec.take_profit_pct
        trailing_stop = request.trailing_stop_pct if request.trailing_stop_pct is not None else spec.trailing_stop_pct
    else:
        stop_loss = take_profit = trailing_stop = None

    universe_spec = None
    universe_metadata = None
    universe_totals: dict[str, int] = {}
    universe_unavailable: set[str] = set()
    universe_in_rows = universe_out_rows = 0
    if request.universe_filter:
        from quant_research_engine.portfolio.universe import (
            UniverseFilterSpec,
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
            universe_metadata = load_universe_metadata(store, symbols, as_of=request.start)

    engine = BatchBacktestEngine(market_profile)
    assembler = ResearchFrameAssembler(store)
    all_results: dict = {}
    summary_rows: list[dict] = []

    for index in range(0, len(symbols), chunk_size):
        chunk = symbols[index : index + chunk_size]
        frame_chunk = assembler.build(
            ts_codes=chunk,
            start=request.start,
            end=request.end,
            market_fields=spec.market_fields,
            factor_fields=spec.factor_fields,
            metadata_as_of=request.metadata_as_of,
        )
        if universe_metadata is not None:
            from quant_research_engine.portfolio.universe import apply_universe_filter

            frame_chunk, chunk_report = apply_universe_filter(
                frame_chunk, universe_spec, start=request.start, metadata=universe_metadata
            )
            universe_in_rows += chunk_report.input_rows
            universe_out_rows += chunk_report.output_rows
            for rule, count in chunk_report.dropped_by_rule.items():
                universe_totals[rule] = universe_totals.get(rule, 0) + count
            universe_unavailable.update(chunk_report.unavailable_rules)
        frame_chunk = _merge_metadata_into_frame(store, frame_chunk, request)
        chunk_result = engine.run(
            frame_chunk,
            BatchBacktestRequest(
                symbols=chunk,
                initial_cash_per_symbol=request.initial_cash,
                entry_signal=spec.signal_expression,
                exit_signal=spec.exit_signal_expression,
                holding_days=spec.holding_days,
                summary_metadata_columns=request.metadata_columns,
                engine_impl=request.engine_impl,
                position_sizing=request.position_sizing,
                stop_loss_pct=stop_loss,
                take_profit_pct=take_profit,
                trailing_stop_pct=trailing_stop,
            ),
        )
        all_results.update(chunk_result.results)
        summary_rows.extend(chunk_result.summary.to_dict("records"))
        del frame_chunk, chunk_result
        gc.collect()
        print(f"    [chunk {index // chunk_size + 1}/{n_chunks}] done ({len(all_results)} symbols accumulated)")

    summary = pd.DataFrame(summary_rows)
    result = BatchBacktestResult(
        symbols=symbols,
        results=all_results,
        summary=summary,
        summary_metrics=summarize_batch_summary(summary),
    )
    if request.benchmark_table and request.benchmark_code:
        from quant_research_engine.portfolio.benchmark import (
            summarize_benchmark_relative_performance,
        )
        from quant_research_engine.portfolio.full_market_report import (
            build_full_market_equity_curve,
        )

        benchmark_frame = store.load_benchmark_bars(
            table_name=request.benchmark_table,
            ts_codes=[request.benchmark_code],
            start=request.start,
            end=request.end,
            fields=[request.benchmark_value_column],
        )
        benchmark_summary = summarize_benchmark_relative_performance(
            build_full_market_equity_curve(result.results, engine_mode="batch"),
            benchmark_frame,
            benchmark_value_column=request.benchmark_value_column,
        )
        result.summary_metrics["benchmark_code"] = request.benchmark_code
        for key, value in benchmark_summary.items():
            result.summary_metrics[f"benchmark_{key}"] = value

    backtest_dir = request.output_dir / "backtest"
    backtest_dir.mkdir(parents=True, exist_ok=True)
    run_request_payload = _run_request_payload(
        spec, request, command="backtest-batch", extra={"symbol_chunk_size": chunk_size},
    )
    paths = write_batch_result(
        result,
        backtest_dir,
        run_request=run_request_payload,
        run_id=run_id or request.run_id,
        compact=request.compact,
        include_full_market=request.include_full_market,
    )
    if universe_metadata is not None:
        universe_report_payload = {
            "applied": True,
            "input_rows": universe_in_rows,
            "output_rows": universe_out_rows,
            "input_symbols": len(symbols),
            "output_symbols": int(summary["symbol"].nunique()) if not summary.empty else 0,
            "dropped_by_rule": universe_totals,
            "unavailable_rules": sorted(universe_unavailable),
        }
        universe_path = backtest_dir / "universe_report.json"
        universe_path.write_text(
            json.dumps(universe_report_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        paths["universe_report"] = universe_path
    return "ok", paths


def _run_backtest(
    store: PostgresDataStore,
    spec: StrategySpec,
    request: ResearchRunRequest,
    frame=None,
    run_id: str | None = None,
) -> tuple[str, dict[str, Path]]:
    """Run backtest. Returns (status, paths_dict)."""
    effective_run_id = run_id or request.run_id
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

    # Chunked mode: never build the full frame (memory guard for long windows).
    if request.symbol_chunk_size is not None and request.backtest_mode == "batch":
        return _run_batch_chunked(store, spec, request, market_profile, run_id=run_id)

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

    frame = _merge_metadata_into_frame(store, frame, request)

    backtest_dir = request.output_dir / "backtest"
    backtest_dir.mkdir(parents=True, exist_ok=True)

    if universe_report is not None:
        universe_path = backtest_dir / "universe_report.json"
        universe_path.write_text(
            json.dumps(universe_report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    # Effective stop levels: request overrides win over spec risk fields;
    # applied only when apply_stops is explicitly enabled.
    if request.apply_stops:
        stop_loss = request.stop_loss_pct if request.stop_loss_pct is not None else spec.stop_loss_pct
        take_profit = request.take_profit_pct if request.take_profit_pct is not None else spec.take_profit_pct
        trailing_stop = request.trailing_stop_pct if request.trailing_stop_pct is not None else spec.trailing_stop_pct
    else:
        stop_loss = None
        take_profit = None
        trailing_stop = None

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
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            trailing_stop_pct=trailing_stop,
        )
        result = BatchBacktestEngine(market_profile).run(frame, batch_req)
        if request.benchmark_table and request.benchmark_code:
            from quant_research_engine.portfolio.benchmark import (
                summarize_benchmark_relative_performance,
            )
            from quant_research_engine.portfolio.full_market_report import (
                build_full_market_equity_curve,
            )

            benchmark_frame = store.load_benchmark_bars(
                table_name=request.benchmark_table,
                ts_codes=[request.benchmark_code],
                start=request.start,
                end=request.end,
                fields=[request.benchmark_value_column],
            )
            benchmark_summary = summarize_benchmark_relative_performance(
                build_full_market_equity_curve(result.results, engine_mode="batch"),
                benchmark_frame,
                benchmark_value_column=request.benchmark_value_column,
            )
            result.summary_metrics["benchmark_code"] = request.benchmark_code
            for key, value in benchmark_summary.items():
                result.summary_metrics[f"benchmark_{key}"] = value
        run_request_payload = _run_request_payload(
            spec, request, command="backtest-batch",
        )
        paths = write_batch_result(
            result,
            backtest_dir,
            run_request=run_request_payload,
            run_id=effective_run_id,
            compact=request.compact,
            include_full_market=request.include_full_market,
        )
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
        stop_loss_pct=stop_loss,
        take_profit_pct=take_profit,
        trailing_stop_pct=trailing_stop,
    )
    shared_result = SharedCashBacktestEngine(market_profile).run(frame, shared_req)
    run_request_payload = _run_request_payload(
        spec, request, command="backtest-shared",
    )
    paths = write_shared_cash_result(shared_result, backtest_dir, run_request=run_request_payload, run_id=effective_run_id)
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
            status, paths = _run_backtest(store, spec, request, frame=_shared_frame(), run_id=run_id)
        else:
            status, paths = _run_backtest(store, spec, request, run_id=run_id)
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
