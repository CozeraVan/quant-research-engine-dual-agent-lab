from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quant_research_engine.data.assembler import ResearchFrameAssembler
from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.settings import DatabaseSettings
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
from quant_research_engine.preflight import PreflightRequest, PreflightRunner
from quant_research_engine.strategies.compiler import (
    CompiledEntry,
    compile_entry,
    compile_to_strategy_spec_dict,
    parse_high_level_entry,
)
from quant_research_engine.strategies.missing_factor import (
    emit_missing_factor_requests,
    extract_missing_factors,
)
from quant_research_engine.strategies.spec import StrategySpec


@dataclass
class StrategySmokeResult:
    strategy_id: str
    compile: str  # pass|skip|fail
    preflight: str  # pass|skip|fail
    missing_factor: str  # pass|skip|fail
    backtest_smoke: str  # pass|skip|fail
    reason: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    durations_s: dict[str, float] = field(default_factory=dict)


@dataclass
class SmokeSummary:
    run_id: str
    generated_at: str
    environment: dict[str, str | bool]
    strategies: list[StrategySmokeResult]
    overall_status: str


def _check_db_available() -> bool:
    try:
        settings = DatabaseSettings.from_env()
        if not settings.market_db_url:
            return False
        store = PostgresDataStore(settings)
        store.ping()
        return True
    except Exception:
        return False


def _try_compile(
    strategy_path: Path,
    output_dir: Path,
) -> tuple[str, str, str, dict[str, str]]:
    """Compile a single strategy entry.

    Returns (status, strategy_id, reason, artifacts).
    strategy_id comes from the compiled entry, not the filename.
    """
    try:
        raw = parse_high_level_entry(strategy_path)
        entry = compile_entry(raw)
    except Exception as exc:
        return "fail", str(strategy_path.stem), str(exc), {}

    strategy_id = entry.strategy_id

    if not entry.ok:
        errors = [i.message for i in entry.issues if i.level == "error"]
        return "fail", strategy_id, "; ".join(errors) if errors else "compile errors", {}

    strategy_dir = output_dir / strategy_id
    strategy_dir.mkdir(parents=True, exist_ok=True)
    spec_dict = compile_to_strategy_spec_dict(entry)
    compiled_path = strategy_dir / "compiled_strategy_spec.json"
    compiled_path.write_text(
        json.dumps(spec_dict, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return "pass", strategy_id, "", {"compiled_strategy_spec": str(compiled_path)}


def _try_preflight(
    strategy_path: Path,
    strategy_id: str,
    output_dir: Path,
    artifacts: dict[str, str],
    preflight_start: str | None,
    preflight_end: str | None,
) -> str:
    """Run preflight for a strategy. Returns status string."""
    try:
        raw = parse_high_level_entry(strategy_path)
        entry = compile_entry(raw)
        spec_dict = compile_to_strategy_spec_dict(entry)
        spec = StrategySpec.from_mapping(spec_dict)

        settings = DatabaseSettings.from_env()
        store = PostgresDataStore(settings)
        store.ping()

        start = date_type.fromisoformat(preflight_start) if preflight_start else date_type(2024, 1, 1)
        end = date_type.fromisoformat(preflight_end) if preflight_end else date_type(2024, 2, 1)

        preflight_req = PreflightRequest(
            ts_codes=None,
            start=start,
            end=end,
            market_fields=spec.market_fields,
            factor_fields=spec.factor_fields,
            min_factor_coverage=0.8,
            exclude_st=spec.exclude_st,
            exclude_suspended=spec.exclude_suspended,
            exclude_risk_warning=spec.exclude_risk_warning,
            min_listing_days=spec.min_listing_days,
            min_amount=spec.min_amount,
        )

        report = PreflightRunner(store).run(preflight_req)
        missing_factors = extract_missing_factors(report, spec, preflight_req)

        strategy_dir = output_dir / strategy_id
        strategy_dir.mkdir(parents=True, exist_ok=True)

        if missing_factors:
            mf_path = emit_missing_factor_requests(missing_factors, strategy_dir)
            artifacts["missing_factor_requests"] = str(mf_path)

        return "fail" if report.status == "error" else "pass"
    except Exception:
        return "fail"


def _try_backtest_smoke(
    strategy_path: Path,
    strategy_id: str,
    output_dir: Path,
    artifacts: dict[str, str],
    preflight_start: str | None,
    preflight_end: str | None,
) -> tuple[str, str]:
    """Run a minimal batch backtest smoke. Returns (status, reason).

    status: ``"pass"`` or ``"fail"``.
    reason: error message when status is ``"fail"``, empty otherwise.
    """
    try:
        raw = parse_high_level_entry(strategy_path)
        entry = compile_entry(raw)
        spec_dict = compile_to_strategy_spec_dict(entry)
        spec = StrategySpec.from_mapping(spec_dict)

        settings = DatabaseSettings.from_env()
        store = PostgresDataStore(settings)
        store.ping()

        start = date_type.fromisoformat(preflight_start) if preflight_start else date_type(2024, 1, 1)
        end = date_type.fromisoformat(preflight_end) if preflight_end else date_type(2024, 2, 1)

        frame = ResearchFrameAssembler(store).build(
            ts_codes=None,
            start=start,
            end=end,
            market_fields=spec.market_fields,
            factor_fields=spec.factor_fields,
            include_metadata=True,
        )

        if frame is None or frame.empty:
            return "fail", "backtest smoke failed: empty research frame"

        market_profile = AShareMarketProfile()
        request = BatchBacktestRequest(
            symbols=None,
            initial_cash_per_symbol=100_000.0,
            entry_signal=spec.signal_expression,
            exit_signal=spec.exit_signal_expression,
            holding_days=spec.holding_days,
        )
        result = BatchBacktestEngine(market_profile).run(frame, request)

        strategy_dir = output_dir / strategy_id
        strategy_dir.mkdir(parents=True, exist_ok=True)

        # Main summary CSV
        summary_path = strategy_dir / "backtest_smoke_summary.csv"
        result.summary.to_csv(summary_path, index=False)
        artifacts["backtest_smoke_summary"] = str(summary_path)

        # Top-N symbol returns (lightweight diagnostic)
        if not result.summary.empty and "total_return" in result.summary.columns:
            top_n = result.summary.nlargest(20, "total_return")
            returns_path = strategy_dir / "backtest_smoke_symbol_returns.csv"
            top_n.to_csv(returns_path, index=False)
            artifacts["backtest_smoke_symbol_returns"] = str(returns_path)

        # Key aggregate metrics
        metrics: dict[str, Any] = {
            "symbol_count": len(result.symbols),
            "trade_count": int(result.summary["trade_count"].sum()) if "trade_count" in result.summary.columns else 0,
        }
        for key in ("mean_return", "win_rate"):
            if key in result.summary_metrics:
                metrics[key] = result.summary_metrics[key]
        metrics_path = strategy_dir / "backtest_smoke_metrics.json"
        metrics_path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        artifacts["backtest_smoke_metrics"] = str(metrics_path)

        return "pass", ""
    except Exception as exc:
        return "fail", f"backtest smoke failed: {exc}"


def run_strategy_smoke(
    strategy_paths: list[Path],
    output_dir: Path,
    *,
    run_preflight: bool = True,
    run_backtest: bool = True,
    preflight_start: str | None = None,
    preflight_end: str | None = None,
) -> SmokeSummary:
    """Run smoke validation for a set of strategy entry files.

    Stages per strategy:
      1. compile (always — no DB needed)
      2. preflight (if DB available and run_preflight=True)
      3. missing-factor extraction (if preflight runs)
      4. backtest smoke (if DB available, run_backtest=True, and preflight passes)

    Writes ``smoke_summary.json`` to ``output_dir`` and returns a SmokeSummary.
    """
    run_id = uuid.uuid4().hex[:12]
    generated_at = datetime.now(timezone.utc).isoformat()
    db_available = _check_db_available()

    output_dir.mkdir(parents=True, exist_ok=True)

    db_skip_reason = (
        "no database configured (QRE_MARKET_DB_URL / SR_MARKET_DB_URL unset or unreachable)"
    )

    results: list[StrategySmokeResult] = []

    for strategy_path in strategy_paths:
        # Stage 1: compile
        t0 = time.perf_counter()
        compile_status, strategy_id, compile_reason, artifacts = _try_compile(strategy_path, output_dir)
        durations: dict[str, float] = {"compile": time.perf_counter() - t0}

        if compile_status == "fail":
            results.append(StrategySmokeResult(
                strategy_id=strategy_id,
                compile="fail",
                preflight="skip",
                missing_factor="skip",
                backtest_smoke="skip",
                reason=compile_reason or "compile failed",
                artifacts=artifacts,
                durations_s=durations,
            ))
            continue

        # Stage 2: preflight
        if db_available and run_preflight:
            t0 = time.perf_counter()
            preflight_status = _try_preflight(
                strategy_path, strategy_id, output_dir, artifacts,
                preflight_start, preflight_end,
            )
            durations["preflight"] = time.perf_counter() - t0
        else:
            preflight_status = "skip"

        # Stage 3: missing-factor extraction
        if preflight_status == "pass":
            missing_factor_status = "pass"
        else:
            missing_factor_status = "skip"

        # Stage 4: backtest smoke
        backtest_reason = ""
        if db_available and run_backtest and preflight_status == "pass":
            t0 = time.perf_counter()
            backtest_status, backtest_reason = _try_backtest_smoke(
                strategy_path, strategy_id, output_dir, artifacts,
                preflight_start, preflight_end,
            )
            durations["backtest_smoke"] = time.perf_counter() - t0
        else:
            backtest_status = "skip"

        # Build skip reason
        reason_parts: list[str] = []
        if preflight_status == "skip":
            if not db_available:
                reason_parts.append(f"preflight skipped: {db_skip_reason}")
            elif not run_preflight:
                reason_parts.append("preflight skipped: disabled by runner configuration")
        if missing_factor_status == "skip" and preflight_status == "skip":
            reason_parts.append("missing-factor skipped (requires preflight)")
        if backtest_status == "skip":
            if not db_available:
                reason_parts.append("backtest smoke skipped: database required")
            elif preflight_status != "pass":
                reason_parts.append("backtest smoke skipped (requires preflight pass)")
            elif not run_backtest:
                reason_parts.append("backtest smoke skipped: disabled by runner configuration")
        if backtest_status == "fail" and backtest_reason:
            reason_parts.append(backtest_reason)

        results.append(StrategySmokeResult(
            strategy_id=strategy_id,
            compile=compile_status,
            preflight=preflight_status,
            missing_factor=missing_factor_status,
            backtest_smoke=backtest_status,
            reason="; ".join(reason_parts) if reason_parts else "",
            artifacts={k: str(v) for k, v in artifacts.items()},
            durations_s=durations,
        ))

    # Environment info
    if db_available:
        env_info: dict[str, str | bool] = {"db_configured": True}
    else:
        env_info = {"db_configured": False}

    # Overall: pass only if all strategies compiled and no preflight/backtest failed
    overall = "pass" if all(
        r.compile == "pass" and r.preflight != "fail" and r.backtest_smoke != "fail"
        for r in results
    ) else "fail"

    summary = SmokeSummary(
        run_id=run_id,
        generated_at=generated_at,
        environment=env_info,
        strategies=results,
        overall_status=overall,
    )

    _write_smoke_summary(summary, output_dir)
    _write_smoke_report_manifest(summary, output_dir)
    return summary


def _write_smoke_summary(summary: SmokeSummary, output_dir: Path) -> Path:
    """Write smoke_summary.json to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "run_id": summary.run_id,
        "generated_at": summary.generated_at,
        "environment": summary.environment,
        "strategies": [
            {
                "strategy_id": s.strategy_id,
                "compile": s.compile,
                "preflight": s.preflight,
                "missing_factor": s.missing_factor,
                "backtest_smoke": s.backtest_smoke,
                **({"reason": s.reason} if s.reason else {}),
                "artifacts": s.artifacts,
                "durations_s": s.durations_s,
            }
            for s in summary.strategies
        ],
        "overall_status": summary.overall_status,
    }
    path = output_dir / "smoke_summary.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _write_smoke_report_manifest(summary: SmokeSummary, output_dir: Path) -> Path:
    """Write smoke_report_manifest.json to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    def _entry(
        key: str,
        path: str,
        filename: str,
        role: str,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        e: dict[str, Any] = {
            "key": key,
            "path": path,
            "filename": filename,
            "role": role,
        }
        if symbol is not None:
            e["symbol"] = symbol
        return e

    files: list[dict[str, Any]] = []

    # Run-level smoke summary
    files.append(_entry(
        key="smoke_summary",
        path="smoke_summary.json",
        filename="smoke_summary.json",
        role="smoke_summary",
    ))

    for s in summary.strategies:
        sid = s.strategy_id
        for artifact_key, artifact_path in sorted(s.artifacts.items()):
            filepath = Path(artifact_path)
            rel = filepath.relative_to(output_dir).as_posix() if filepath.is_relative_to(output_dir) else filepath.as_posix()
            files.append(_entry(
                key=f"{artifact_key}_{sid}",
                path=rel,
                filename=filepath.name,
                role=artifact_key,
                symbol=sid,
            ))

    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "strategy_smoke_report_manifest",
        "files": files,
    }
    manifest_path = output_dir / "smoke_report_manifest.json"
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path
