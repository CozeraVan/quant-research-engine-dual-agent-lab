# Coding Handoff

## Task ID

QRE-BATCH-PERF-SLIM-001

## Written By

KIMI_CODE (single agent)

## Status

IN_PROGRESS (implementation complete; quick-mode batch run pending)

## Current Owner

KIMI_CODE

## Implementation Summary

1. **Per-stage timing**: `ResearchRunResult.stage_durations_s` added; `run_research_run()` times preflight/eval/backtest stages; durations persisted into `research_run_manifest.json` (`stage_durations_s` key).
2. **DB engine disposal**: `PostgresDataStore.close()` added (disposes all four engines, dedup by identity); `run_research_run()` wraps stages in try/finally and closes the store (getattr guard keeps test fakes without `close()` working). Prevents connection leaks when many strategies run in one process.
3. **Runner core moved into src**: new `src/quant_research_engine/orchestration/batch_runner.py` holds `BatchRunResult`/`BatchSummary`/`BatchRunConfig`, `discover_strategies`, `strategy_meta`, `completed_strategies`, `run_single_strategy`, `execute_batch`, `summarize_results`, `write_batch_summary`. `scripts/batch_backtest_runner.py` is now a thin argparse wrapper (same flags plus new ones).
4. **Parallel execution**: `--jobs N` via `concurrent.futures.ProcessPoolExecutor`; each worker runs the full research-run pipeline in its own process (own engines); worker-crash path degrades to an `error` result; serial mode unchanged (default `--jobs 1`).
5. **Compact output mode**: `--compact` threads runner → `ResearchRunRequest.compact` → `write_batch_result(compact=True)`, which skips per-symbol output trees and the full-market workbook/HTML/charts. Strategy-level artifacts kept: `summary.csv`, `summary_metrics.json`, `summary.md`, `report_manifest.json`, `run_manifest.json`, `window_summary_M/Q/Y.csv`, `rolling_summary_20.csv` (9 files vs ~26k for full market).
6. **Resume semantics fixed**: `completed_strategies()` now scans both a batch directory and a parent-of-batches directory (the old one-level scan never matched when `--output-dir` was a parent, so `--resume` silently never skipped). A strategy counts complete only when its manifest records `stages.backtest == "ok"`.
7. **batch_summary.json enrichment**: config now records `jobs`/`compact`; per-strategy entries include `stage_durations_s` when available.
8. **Docs**: README section 7b (catalog batch runner with `--jobs`/`--compact`), QUICKSTART section 7, Makefile `backtest-quick`/`backtest-full` targets now use `--jobs $(JOBS) --compact --resume` with `JOBS ?= 4`.

## Files Changed

- `src/quant_research_engine/orchestration/research_run.py` (timing, compact threading, store close)
- `src/quant_research_engine/orchestration/batch_runner.py` (new)
- `src/quant_research_engine/data/postgres.py` (`close()`)
- `src/quant_research_engine/portfolio/io.py` (`write_batch_result(compact=...)`)
- `scripts/batch_backtest_runner.py` (thin wrapper, `--jobs`/`--compact`)
- `tests/test_batch_runner.py` (new, 20 tests)
- `README.md`, `QUICKSTART.md`, `Makefile`

## Validation Output

```bash
uv run pytest tests/test_batch_runner.py -q → 20 passed
uv run pytest -q → 967 passed, 2 warnings (947 baseline + 20 new)

# Real-DB compact-vs-standard parity (3 symbols, smoke window, tf01a):
#   summary.csv byte-identical; summary_metrics.json identical
#   compact backtest dir = 9 strategy-level files, no symbol dirs, no xlsx/html

# Profiling baseline (1 strategy, quick mode, serial, standard outputs): RUNNING, see below
```

## Profiling Baseline

- Strategy: `tf01a_ma_cross_20_120`, quick mode (2024-01-01 → 2024-12-31), full market (~5,292 symbols), serial, standard outputs, skip-preflight.
- Total: **1742.5s** (~29 min). Stage split (from `research_run_manifest.json`):
  - eval: **21.3s** (1.2%) — includes market+factor frame build
  - backtest: **1718.9s** (98.6%) — includes frame rebuild, per-symbol engine loop, and writing **26,312 files / 239MB**
- Output dir: `outputs/backtests/profile_baseline/a2db386713da/`
- **Decision (brief step 5)**: data-load reuse NOT implemented — DB load is ~1-2% of runtime, not a top cost. The dominant cost is the backtest stage (per-symbol loop + per-symbol file writing + workbook generation), addressed by `--compact` (kills file writing/workbook) and `--jobs` (parallelizes the loop across strategies).

## Quick Batch Run (106 strategies)

- Command: `--mode quick --jobs 4 --compact --skip-preflight --resume --output-dir outputs/backtests/quick_batch_106`
- Batch dir: `outputs/backtests/quick_batch_106/f365c8a07b33/` (launched 2026-07-18 ~18:40)
- **Measured per-strategy duration ≈ 27-30 min, same as baseline.** Compact mode did NOT reduce wall time: the backtest stage is ~98% CPU-bound per-symbol engine loop; file writing was never the bottleneck (compact's value is output size: 239MB → ~1MB per strategy, 26,312 → 9 files).
- Baseline comparison point: serial extrapolation ≈ 106 × 1742s ≈ 51h. Expected with 4 workers: **~13h** (measured throughput, not the brief's ≤6h estimate — that estimate wrongly assumed output writing dominated; corrected here with manifest timings as evidence).
- System state during run: 4 workers × ~91% CPU, load 4.0/8 cores, ~1.3GB RSS per worker — healthy, no oversubscription.
- **User decision (2026-07-18)**: let the `--jobs 4` batch run to completion rather than restarting at `--jobs 8` or stopping for engine-loop optimization. The ≤6h acceptance line is recorded as MISSED; the real speed lever is engine-loop optimization (per-symbol frame filtering + per-bar Python loop), a candidate follow-up slice.
- Status: **COMPLETE (2026-07-19 06:32 +08, batch `f365c8a07b33`)**.

## Quick Batch Final Results

- Outcome: **106 OK / 5 error** — errors are exactly the 5 known missing-factor strategies (`bo02`, `mr02b`, `tf04`, `tf05a`, `tf07e`); zero backtest/preflight failures.
- Wall time: **11.1h** with `--jobs 4` (serial extrapolation ≈ 51h → 4.6× throughput). The brief's ≤6h line is recorded as MISSED (wrong initial assumption, see above).
- Per-strategy duration: min 1233s / median 1435s / mean 1459s / max 1828s — **~16% faster than the 1742s baseline** (compact skips per-symbol file writing and workbook generation).
- Output: **2,013 files / 2.8GB** for 106 strategies (backtest aggregates + eval artifacts), vs standard-mode extrapolation ≈ 2.79M files / ~25GB → **~99.9% fewer files, ~89% fewer bytes** (acceptance line >80%: MET).
- Auditability: `qre report-files` / `qre report-audit` on compact strategy manifests → `missing_files=0, validation_issues=0, status=ok`.
- Note: eval artifacts (`eval/events.csv` etc.) now dominate output volume in compact mode; further slimming would target those, not the backtest stage.
