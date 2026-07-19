# Coding Handoff

## Task ID

QRE-VECTORIZED-ENGINE-001 (M9.1b)

## Written By

KIMI_CODE (single agent)

## Status

IN_PROGRESS (implementation complete; R-QRE-009 verification ladder running)

## Current Owner

KIMI_CODE

## Implementation Summary

1. **Shared helpers extracted** (`portfolio/single_symbol.py`): `empty_single_symbol_result()` and `build_single_symbol_summary()` are now module-level and shared by both engines (simulator methods delegate) — the summary/empty contract is identical by construction.
2. **New vectorized engine** (`portfolio/single_symbol_vectorized.py`, ~300 lines):
   - Same `SingleSymbolBacktestRequest`/`Result` contract; `run()` mirrors the simulator interface, `run_working()` takes a pre-filtered subframe (batch fast path).
   - Event-level loop: static candidates = bars with entry/exit signals; dynamic candidates (execution, holding-expiry, rejection-retry bars) merged via a heap. All other bars are provably no-ops and skipped.
   - State machine is a 1:1 translation of the simulator, including the subtle semantics: dead pending-buy when `buy_quantity == 0` or `notional + cost > cash` (symbol never trades again), sell-rejection retry with original reason preserved, exit-signal rescheduling to an earlier bar, holding-expiry precedence over exit-signal scheduling.
   - Vectorized equity reconstruction from fill segments (piecewise-constant cash/quantity × close), producing the same daily rows and dtypes as the simulator.
   - `position_sizing`: `full_compound` (default, current all-in behavior) and `fixed_cash` (fixed notional = initial_cash per entry; affordability check unchanged).
3. **Batch wiring** (`portfolio/batch.py`): `BatchBacktestRequest.engine_impl` (`simulator` default during rollout) + `position_sizing`; vectorized path pre-splits the frame with ONE `groupby("ts_code")` (eliminates ~5,292 full-frame scans per strategy) and reuses `_summary_row` on group subframes (same metadata first row). Validation: `fixed_cash` requires `vectorized`; unknown impl/sizing rejected.
4. **Threading**: `ResearchRunRequest.engine_impl`/`position_sizing` → `BatchBacktestRequest`; `BatchRunConfig` + runner script flags `--engine-impl` / `--position-sizing`, echoed into `batch_summary.json` config.
5. **Equality suite** (`tests/test_single_symbol_vectorized.py`, 61 tests): deterministic edges (holding expiry, exit signal, limit-up buy rejection, limit-down sell rejection + retry, suspension, signal-every-day stress, absent symbol, last-bar signal, flat zero-trade, dead-pending zero-quantity, dead-pending costs-exceed-cash, no optional columns, pre_close limit fallback, NaN flags, ST rules), 40 seeded randomized frames (1-200 bars, random flags/NaNs/columns presence, 4 entry expressions, optional exit, cash from 3.5k to 5M), batch-level equality (summary + metrics + per-symbol), sizing/validation errors.

## Files Changed

- `src/quant_research_engine/portfolio/single_symbol.py` (shared helpers extracted, simulator delegates)
- `src/quant_research_engine/portfolio/single_symbol_vectorized.py` (new)
- `src/quant_research_engine/portfolio/batch.py` (`engine_impl`/`position_sizing` + vectorized path)
- `src/quant_research_engine/orchestration/research_run.py` (request fields + threading)
- `src/quant_research_engine/orchestration/batch_runner.py` (config fields + threading)
- `scripts/batch_backtest_runner.py` (`--engine-impl` / `--position-sizing`)
- `tests/test_single_symbol_vectorized.py` (new, 61 tests)

## Validation Output

```bash
uv run pytest tests/test_single_symbol_vectorized.py -q → 61 passed
uv run pytest -q → 1028 passed, 2 warnings (967 baseline + 61 new)
```

## R-QRE-009 Verification Ladder (results to be recorded)

- STEP 1: 3 representative strategies × 50 real symbols × 1y — both engines, `summary.csv` + `summary_metrics.json` diff. **PASS (all identical).**
- STEP 2: all 106 catalog strategies × 50 symbols — both engines, per-strategy `summary.csv` diff. **PASS (106/106 identical, 0 failures).**
- STEP 3: tf01a full-market quick-mode vectorized benchmark — **summary.csv identical to baseline**; backtest stage 854.2s (see analytics finding below).

## Analytics Bottleneck Finding (2026-07-19, cProfile)

The ≤30s target was missed at 854.2s, and profiling showed the engine was NOT the cause:

- Baseline decomposition (1,718.9s): simulator engine ~870s + window/rolling output analytics ~850s.
- Vectorized benchmark decomposition (854.2s): vectorized engine **~9s** (0.52s per 300 symbols, ~190× the simulator) + the SAME analytics ~845s. Compact mode removed file IO but kept the analytics computation.
- Root cause: `summarize_batch_rolling_summary` / `summarize_batch_window_summary` called `summarize_equity_curve` per symbol per 20-day window (~1.19M heavy pandas calls per strategy), but only `total_return`/`max_drawdown` are used.
- Fix: vectorized collectors `_collect_window_return_rows` / `_collect_rolling_return_rows` in `analytics.py` (numpy sliding-window + per-symbol first/last groupby). `risk.py` untouched and serves as the test oracle.
- Equality: `tests/test_analytics_vectorized.py` (6 tests) compares old-path vs new-path outputs exactly, including NaN rows, short curves, missing columns, zero-start (note: fully-zero equity crashes the OLD oracle — latent pre-existing issue, unreachable from engine outputs).
- Verification: `tests/test_analytics_vectorized.py` 6 passed; full suite **1034 passed**.
- Benchmark re-run (engine + analytics both vectorized): results to be recorded below.

## Benchmark Final

- tf01a full-market quick mode, vectorized engine + vectorized analytics + shared research frame: **backtest stage 40.2s** (baseline 1,718.9s → **42.8× speedup**); eval 17.3s.
- All artifacts byte-identical to baseline: `summary.csv`, `summary_metrics.json`, `window_summary_M/Q/Y.csv`, `rolling_summary_20.csv`.
- The ≤30s brief target is recorded as narrowly MISSED (40.2s). Remaining decomposition at 300-symbol scale: engine 0.56s + write/analytics 1.62s (window M/Q/Y ~0.44s each + rolling 0.30s); the next levers are cross-symbol-concatenated analytics and groupby-aware signal evaluation — listed as follow-up micro-slices, not started (diminishing returns vs equality-verification cost).
- Shared research frame (2026-07-19): `run_research_run` builds the market+factor frame once and shares it between eval and backtest when no benchmark columns are requested (`_build_research_frame`, monkeypatch seam added to 3 existing tests + 1 CLI test); saved ~5.5s of 45.7s.
- Default flip: runner `--engine-impl` now defaults to `vectorized` (evidence: 61 synthetic equality tests, 40 randomized frames, 106/106 catalog × 50 symbols byte-identical, baseline artifact identity). `simulator` remains as fallback; library-level defaults (`BatchBacktestRequest`, `ResearchRunRequest`) stay `simulator` for API conservatism.
- Estimated catalog impact: quick batch (106 strategies) ≈ 25-30 min with `--jobs 4` (vs 11.1h); full-mode (2015-2025) becomes feasible (~3h overnight estimate).
