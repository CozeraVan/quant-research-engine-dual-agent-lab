"""Batch backtest runner core for strategy catalog YAMLs.

This module holds the unit-testable runner logic; the CLI entry point
``scripts/batch_backtest_runner.py`` is a thin argparse wrapper around it.

Layout produced per batch run::

    <output_dir>/<batch_id>/
      batch_summary.json
      <strategy_id>/
        research_run_manifest.json
        report_manifest.json
        preflight/preflight_report.json   (unless --skip-preflight)
        eval/...                          (unless --skip-eval)
        backtest/...                      (compact or standard artifacts)

Resume semantics: ``completed_strategies`` scans both
``<output_dir>/<strategy>/research_run_manifest.json`` (output_dir is a batch
directory) and ``<output_dir>/*/<strategy>/research_run_manifest.json``
(output_dir is a parent of batch directories). A strategy counts as completed
only when its manifest records ``stages.backtest == "ok"``.
"""

from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

MODE_CONFIGS = {
    "smoke": {"start": "2024-01-01", "end": "2024-03-01", "label": "Smoke (2 months)"},
    "quick": {"start": "2024-01-01", "end": "2024-12-31", "label": "Quick (1 year)"},
    "full": {"start": "2015-01-01", "end": "2025-12-31", "label": "Full (2015-2025)"},
}

STATUS_ICONS = {
    "ok": "+",
    "preflight_failed": "P",
    "eval_failed": "E",
    "backtest_failed": "B",
    "error": "X",
    "skipped": "S",
}


@dataclass
class BatchRunResult:
    strategy_id: str
    category: str
    research_run_id: str
    status: str  # ok | preflight_failed | eval_failed | backtest_failed | error | skipped
    preflight_status: str = ""
    eval_status: str = ""
    backtest_status: str = ""
    output_dir: str = ""
    error_message: str = ""
    duration_s: float = 0.0
    stage_durations_s: dict[str, float] = field(default_factory=dict)


@dataclass
class BatchSummary:
    batch_id: str
    generated_at: str
    mode: str
    date_range: dict[str, str]
    config: dict[str, Any]
    results: list[BatchRunResult] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class BatchRunConfig:
    """Everything needed to run one strategy through the research-run pipeline."""

    output_base: Path
    start: date
    end: date
    skip_preflight: bool = False
    skip_eval: bool = False
    backtest_mode: str = "batch"
    initial_cash: float = 1_000_000
    min_factor_coverage: float = 0.5
    codes: list[str] | None = None
    compact: bool = False
    catalog_dir: Path | None = None
    engine_impl: str = "simulator"
    position_sizing: str = "full_compound"


def discover_strategies(
    catalog_dir: Path,
    category: str | None = None,
    strategy_ids: list[str] | None = None,
) -> list[Path]:
    """Find strategy YAML files under the catalog, optionally filtered."""
    if strategy_ids:
        paths = []
        for sid in strategy_ids:
            matches = list(catalog_dir.rglob(f"{sid}.yaml"))
            paths.extend(matches)
        return sorted(set(paths))

    if category:
        target = catalog_dir / category
        if not target.is_dir():
            raise ValueError(f"Category not found: {category}")
        return sorted(target.glob("*.yaml"))

    return sorted(catalog_dir.rglob("*.yaml"))


def strategy_meta(yaml_path: Path, catalog_dir: Path | None) -> tuple[str, str]:
    """Return (strategy_id, category) for a catalog YAML path."""
    strategy_id = yaml_path.stem
    if catalog_dir is None:
        return strategy_id, "root"
    try:
        rel = yaml_path.relative_to(catalog_dir)
    except ValueError:
        return strategy_id, "root"
    category = rel.parts[0] if len(rel.parts) > 1 else "root"
    return strategy_id, category


def _completed_from_dir(run_dir: Path, completed: set[str]) -> None:
    manifest = run_dir / "research_run_manifest.json"
    if not manifest.exists():
        return
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        stages = data.get("stages", {})
        if stages.get("backtest") == "ok":
            strategy_path = data.get("strategy_path", "")
            completed.add(Path(strategy_path).stem)
    except (json.JSONDecodeError, KeyError, AttributeError):
        return


def completed_strategies(output_dir: Path) -> set[str]:
    """Strategy IDs with a completed backtest under output_dir.

    Accepts either a batch directory (``<output_dir>/<strategy>/``) or a
    parent of batch directories (``<output_dir>/<batch_id>/<strategy>/``).
    """
    completed: set[str] = set()
    if not output_dir.is_dir():
        return completed
    for entry in sorted(output_dir.iterdir()):
        if not entry.is_dir():
            continue
        _completed_from_dir(entry, completed)
        if (entry / "research_run_manifest.json").exists():
            continue
        # entry may be a batch directory holding per-strategy subdirectories
        for run_dir in sorted(entry.iterdir()):
            if run_dir.is_dir():
                _completed_from_dir(run_dir, completed)
    return completed


def run_single_strategy(yaml_path: Path, config: BatchRunConfig) -> BatchRunResult:
    """Run one strategy through the research-run pipeline."""
    from quant_research_engine.orchestration.research_run import (
        ResearchRunRequest,
        run_research_run,
    )

    strategy_id, category = strategy_meta(yaml_path, config.catalog_dir)
    t0 = time.perf_counter()
    output_dir = config.output_base / strategy_id

    result = BatchRunResult(
        strategy_id=strategy_id,
        category=category,
        research_run_id="",
        status="error",
        output_dir=str(output_dir),
    )

    try:
        req = ResearchRunRequest(
            strategy_path=yaml_path,
            start=config.start,
            end=config.end,
            output_dir=output_dir,
            backtest_mode=config.backtest_mode if config.backtest_mode in ("batch", "shared") else "batch",
            skip_preflight=config.skip_preflight,
            skip_eval=config.skip_eval,
            initial_cash=config.initial_cash,
            min_factor_coverage=config.min_factor_coverage,
            codes=config.codes,
            compact=config.compact,
            engine_impl=config.engine_impl,
            position_sizing=config.position_sizing,
        )

        run_result = run_research_run(req)
        result.research_run_id = run_result.run_id
        result.preflight_status = run_result.preflight_status
        result.eval_status = run_result.eval_status
        result.backtest_status = run_result.backtest_status
        result.stage_durations_s = dict(run_result.stage_durations_s)

        if run_result.preflight_status == "error":
            result.status = "preflight_failed"
        elif run_result.eval_status == "error":
            result.status = "eval_failed"
        elif run_result.backtest_status == "error":
            result.status = "backtest_failed"
        else:
            result.status = "ok"

        if run_result.error_message:
            result.error_message = run_result.error_message

    except Exception as exc:
        result.status = "error"
        result.error_message = str(exc)

    result.duration_s = time.perf_counter() - t0
    return result


def print_progress(i: int, total: int, result: BatchRunResult) -> None:
    """Print a one-line progress update."""
    icon = STATUS_ICONS.get(result.status, "?")
    dur = f"{result.duration_s:.0f}s"
    print(f"  [{i}/{total}] {icon} {result.strategy_id:45s} {result.status:20s} {dur}")


def execute_batch(
    yaml_paths: list[Path],
    config: BatchRunConfig,
    *,
    jobs: int = 1,
    on_progress: Callable[[int, int, BatchRunResult], None] | None = print_progress,
) -> list[BatchRunResult]:
    """Run all strategies, serially or in a process pool.

    With ``jobs > 1`` each worker process runs the full research-run pipeline
    independently (own DB engines), so workers never share connections.
    Results are returned in completion order for parallel mode.
    """
    total = len(yaml_paths)
    results: list[BatchRunResult] = []

    if jobs <= 1:
        for i, yaml_path in enumerate(yaml_paths):
            result = run_single_strategy(yaml_path, config)
            results.append(result)
            if on_progress is not None:
                on_progress(i + 1, total, result)
        return results

    with ProcessPoolExecutor(max_workers=jobs) as pool:
        future_to_path = {
            pool.submit(run_single_strategy, yaml_path, config): yaml_path
            for yaml_path in yaml_paths
        }
        for i, future in enumerate(as_completed(future_to_path)):
            yaml_path = future_to_path[future]
            try:
                result = future.result()
            except Exception as exc:  # worker process died before returning
                strategy_id, category = strategy_meta(yaml_path, config.catalog_dir)
                result = BatchRunResult(
                    strategy_id=strategy_id,
                    category=category,
                    research_run_id="",
                    status="error",
                    output_dir=str(config.output_base / strategy_id),
                    error_message=f"worker failed: {exc}",
                )
            results.append(result)
            if on_progress is not None:
                on_progress(i + 1, total, result)
    return results


def summarize_results(results: list[BatchRunResult]) -> dict[str, int]:
    """Status counts for batch_summary.json."""
    return {
        "total": len(results),
        "ok": sum(1 for r in results if r.status == "ok"),
        "preflight_failed": sum(1 for r in results if r.status == "preflight_failed"),
        "eval_failed": sum(1 for r in results if r.status == "eval_failed"),
        "backtest_failed": sum(1 for r in results if r.status == "backtest_failed"),
        "error": sum(1 for r in results if r.status == "error"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
    }


def result_to_payload(result: BatchRunResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "strategy_id": result.strategy_id,
        "category": result.category,
        "research_run_id": result.research_run_id,
        "status": result.status,
        "preflight_status": result.preflight_status,
        "eval_status": result.eval_status,
        "backtest_status": result.backtest_status,
        "output_dir": result.output_dir,
        **({"error_message": result.error_message} if result.error_message else {}),
        "duration_s": round(result.duration_s, 1),
    }
    if result.stage_durations_s:
        payload["stage_durations_s"] = result.stage_durations_s
    return payload


def write_batch_summary(summary: BatchSummary, output_base: Path) -> Path:
    """Write the master batch_summary.json."""
    output_base.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "batch_id": summary.batch_id,
        "generated_at": summary.generated_at,
        "mode": summary.mode,
        "date_range": summary.date_range,
        "config": summary.config,
        "summary": summary.summary,
        "results": [result_to_payload(r) for r in summary.results],
    }

    path = output_base / "batch_summary.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def new_batch_id() -> str:
    return uuid.uuid4().hex[:12]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
