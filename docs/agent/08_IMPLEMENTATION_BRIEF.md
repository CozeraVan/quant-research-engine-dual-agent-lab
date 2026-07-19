# Implementation Brief

## Task ID

QRE-BATCH-PERF-SLIM-001

## Created By

KIMI_CODE (single agent; first slice of CR-0002, pending user approval)

## Intended Implementer

KIMI_CODE

## Goal

Make deeper-window catalog batch backtests practical: cut wall-clock time and output-file volume of `scripts/batch_backtest_runner.py`, then run the quick-mode (1-year) batch for the 106 ready catalog strategies. This is the enabling slice of Milestone 9 (Strategy Research Validation, `docs/agent/change_requests/CR-0002-strategy-research-validation.md`).

## Background Evidence

- Smoke batch (2-month window, 106 strategies, serial single-process) took ~11.5h → ~6.5 min/strategy and produced ~3M output files (~5 files × ~5,292 symbols × 106 strategies).
- Naive extrapolation: quick mode (1 year, 6× data) ≈ 35h+ serial; full mode (2015-2025) is impractical without this slice.
- Current runner (`scripts/batch_backtest_runner.py`, 404 lines) is serial, lives outside `src/` (not unit-testable via pytest), and every strategy reloads the same market bars from Postgres and rewrites per-symbol output trees.

## Scope

1. **Profiling baseline**: add per-stage timing (preflight / eval / backtest / output-write) to the runner; measure 2-3 representative strategies in quick mode; record the split in `09_CODING_HANDOFF.md`. All later claims about bottlenecks must cite these numbers.
2. **Move runner core into src**: new `src/quant_research_engine/orchestration/batch_runner.py` holding `BatchRunResult`/`BatchSummary`/discovery/resume/single-strategy logic; `scripts/batch_backtest_runner.py` becomes a thin argparse wrapper. Enables real unit tests (pytest `pythonpath=["src"]`).
3. **Parallel execution**: `--jobs N` via `concurrent.futures.ProcessPoolExecutor`; each worker process runs `run_research_run` independently (own SQLAlchemy engines); deterministic per-strategy output dirs unchanged; progress lines printed as futures complete; `--resume` semantics preserved.
4. **Compact output mode**: `--compact` flag threaded runner → `ResearchRunRequest` → batch backtest IO: per-symbol metrics aggregated into one strategy-level `symbol_metrics.csv` (CSV, no new dependencies); keep `summary.json`, `batch_summary.json`, and `report_manifest.json`; skip per-symbol output subdirectories in compact mode. Register the new artifact role so `qre report-files` / `qre report-audit` keep working. Verify metric equality between compact and standard modes on a small window.
5. **Data-load reuse (conditional)**: only if profiling shows DB load is a top cost — preload shared market bars once per worker and reuse across strategies (e.g. store-level cache keyed by table/window). Factor loads stay per-strategy.
6. **Quick-mode batch run**: execute the 106 ready strategies, quick mode (2024-01-01 → 2024-12-31), with `--jobs N --compact --skip-preflight --resume`; record batch id, wall time, per-strategy mean duration, and output size in `09_CODING_HANDOFF.md`.
7. **Tests**: unit tests for discovery, resume, jobs scheduling, compact aggregation, manifest role registration; full suite stays green.
8. **Docs**: README batch section + `docs/agent/` updates per R-AGENT-002.

## Non-Goals

- No engine trading-rule, cost-model, or signal-semantics changes.
- No statistical validation layer (walk-forward, multiple-testing) — that is M9.2.
- No new indicator computation inside QRE (R-QRE-002); the 5 blocked strategies stay blocked until upstream delivers factors.
- No parquet/new dependencies; CSV only.
- No GUI work.

## Expected Tests

```bash
uv run pytest -q                                          # full suite green (947 + new)
uv run pytest tests/test_batch_runner.py -q               # new unit tests
uv run python scripts/batch_backtest_runner.py --dry-run  # discovery sanity
# compact-vs-standard metric equality on 3 symbols / 2-month window
```

## Validation Commands

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
uv run python scripts/batch_backtest_runner.py --mode quick --compact --jobs 4 --skip-preflight --resume
```

## Acceptance Criteria

- Quick-mode batch of the 106 ready strategies completes; batch id, wall time, and per-strategy mean duration recorded.
- Output files per strategy ≤ ~20 (vs ~26k in smoke mode); aggregate batch output size drops by >80%.
- Wall time for the quick batch ≤ 6h (vs ~35h serial extrapolation).
- `qre report-files` / `qre report-audit` discover and validate compact-mode artifacts.
- Full pytest suite green; no behavior change in standard (non-compact) mode.
