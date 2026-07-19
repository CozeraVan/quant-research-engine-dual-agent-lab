# Coding Handoff

## Task ID

QRE-UPSTREAM-FACTOR-DELIVERY-001

## Written By

KIMI_CODE (single agent)

## Status

DONE (upstream delivery complete; 5/5 strategies unblocked)

## Implementation Summary

1. **Investigation**: canonical project `/home/van/quant-workspace/indicators_tushare` (git main; `/home/van/indicators_tushare` is a stray .venv). systemd timers confirmed: `quant-ts-daily` 16:30 (data sync) → `indicators-tushare-daily` 16:40 (factor update), both enabled — yaml-config factors auto-join the daily schedule with zero scheduler changes.
2. **Edits (indicators repo, no git action)**: `config/factors.yaml` sma periods += 7/9/26/50/52 + `atrraw` entry; `factors/volatility_factors.py` new `ATRRawFactor` class (raw `atr_{n}` naming; identical formula to existing `atrr_10` — pandas_ta RMA/Wilder, discovered and documented).
3. **Project flow**: validate (success/0 failures) → plan (7 target columns confirmed; superset = other pending config columns in overlap/volatility also covered per project config-parity behavior) → small-sample backfill (000001.SZ) → **value parity verified** vs hand-computed SMA/Wilder-ATR (storage-rounding diffs only, 100% non-null) → full-history backfill: **processed 5,544 stocks, failed_count 0**.
4. **Final coverage**: sma_7 13.28M rows/5,541 stocks, sma_9 13.27M/5,539, sma_26 13.17M/5,531, sma_50 13.04M/5,416, sma_52 13.03M/5,415, atr_10 13.26M/5,539.
5. **QRE side**: `factor_request_queue.py recheck` → **7 newly fulfilled, 0 pending**. Small-sample re-run of the 5 shelved strategies: 4 OK + tf07e failed with a NEW root cause — signal expression precedence bug `(sma_7 / sma_65 - 1).abs() > 0.03 & (close > sma_20)` (Python parses `> (0.03 & ...)`). Fixed with parens in BOTH the YAML and `scripts/generate_strategy_yamls.py`; tf07e now OK. **All 5/5 strategies unblocked.**
6. Daily updates: from the next 16:40 trigger, `run_daily.py` covers the new columns automatically (yaml-driven).

## Validation Output

```bash
indicators validate → success, failure_count 0
small-sample parity: sma_7/9/26/50/52 + atr_10 within storage rounding, 100% non-null
full backfill: processed 5544, failed_count 0
queue recheck: 7 newly fulfilled, 0 pending
unblock batch (5 strategies × 3 codes × smoke): 5/5 OK after tf07e expression fix
uv run pytest -q → 1137 passed
```

## Notes

- The full backfill also covered other pending config columns in the overlap/volatility categories (project config-parity behavior) — disclosed and accepted.
- tf07e's precedence bug only surfaced now because the strategy was shelved before ever reaching expression evaluation; the paren fix is in the YAML and the generator (regeneration-safe).
- indicators repo working tree left untouched (their pre-existing uncommitted changes not mine to resolve).

# Coding Handoff (archive: QRE-STRATEGY-FIT-STABILITY-001)

## Task ID

QRE-STRATEGY-FIT-STABILITY-001 (M10.1 v1.1)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + pilot; awaiting self-review and user-approved commit)

## Implementation Summary

1. **Artifact** `symbol_month_returns.csv`: per-(symbol, calendar month) `total_return` (last/first equity − 1, NaN when first ≤ 0) via the concat window collector, written by `write_batch_result` in BOTH modes — scope adjusted from "compact only" to both modes to preserve the M9.1 contract that compact outputs are a strict subset of standard outputs (the committed parity test caught it). Manifest role `symbol_month_returns` with required columns `{window, symbol, total_return}`; passes `qre report-audit`.
2. **Stability metric** (`analysis/strategy_fit.py`): `load_batch` picks up the artifact when present; per strategy at pool_tier — `stability_months_covered` (months with ≥1 pool stock reporting), `stability_ratio` (fraction of covered months where pool mean monthly return > universe mean), `stability_pool_month_mean_min`. Blank when the artifact is absent (older batches). Surfaced in `strategy_fit_summary.csv` and the markdown ranking table (`ratio/months` format). Informational only, no hard gate.
3. **Tests** (3 new): artifact content vs hand-computed oracle + manifest entry + ReportManifest validation; stability computation (pool wins one of two months → ratio 0.5, covered=2, min locked); blanks without artifact. Existing compact-parity test updated via the both-modes decision.
4. **Pilot**: 2 strategies × 3 codes × smoke — artifact written per strategy, audit clean, fit report shows stability columns.

## Validation Output

```bash
uv run pytest -q → 1137 passed, 4 warnings (1134 baseline + 3 new)
pilot: artifact OK; qre report-audit → 0 issues; fit summary stability columns present
```

## Note for Existing Batches

Older batches (incl. quick_batch_106) lack `symbol_month_returns.csv`; the fit report shows blank stability for them. Future batches and refresh runs include it automatically. If stability on the 2024 catalog is wanted before the next scheduled run, a `--resume`-compatible re-run is needed (user decision).

# Coding Handoff (archive: QRE-ANALYTICS-CONCAT-001)

## Task ID

QRE-ANALYTICS-CONCAT-001 (M9.1b ≤30s target completion)

## Written By

KIMI_CODE (single agent)

## Status

DONE — **≤30s acceptance target MET** (backtest stage 25.9s)

## Implementation Summary

1. **Concat window collector** (`_collect_window_return_rows`): one concatenated frame across symbols (per-symbol stable sort preserved for contract equality), one datetime conversion, ONE `groupby([window, symbol], sort=False)` aggregation for first/last — replacing ~5,292 per-symbol pandas groupby objects. Row order contract (dict order, windows ascending) preserved via sort=False first-occurrence semantics.
2. **Concat rolling collector** (`_collect_rolling_return_rows`): output assembled from concatenated numpy arrays into ONE final DataFrame — eliminating per-symbol DataFrame construction + the expensive 5,292-frame `pd.concat`.
3. **Equality gate**: `tests/test_analytics_vectorized.py` (risk.py oracle) passes unchanged; real-DB benchmark diff vs baseline is byte-identical for all six artifacts.
4. **Final benchmark (BENCH4)**: backtest stage **25.852s** (vs 40.172s before this slice, vs 1,718.9s original simulator baseline → **66.5×**); eval 18.4s. New decomposition: frame load ~17s (now dominant), engine ~6s, analytics ~2-3s. The M9.1b ≤30s acceptance line is now MET.

## Validation Output

```bash
uv run pytest tests/test_analytics_vectorized.py -q → 6 passed (oracle unchanged)
uv run pytest -q → 1134 passed
BENCH4 stage_durations_s: {'backtest': 25.852, 'eval': 18.419}
artifacts vs baseline: summary.csv/metrics/window M/Q/Y/rolling_20 ALL IDENTICAL
```

# Coding Handoff (archive: QRE-TRAILING-STOP-BATCH-001)

## Task ID

QRE-TRAILING-STOP-BATCH-001 (M10.2b follow-up)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + verification; awaiting self-review and user-approved commit)

## Current Owner

KIMI_CODE

## Implementation Summary

1. **Semantics (locked, batch-path model)**: anchor starts at actual fill `entry_price`, updates every bar while holding with the bar's `high` (fallback to `mark_price_column` when `high` unavailable); trigger when `close <= anchor × (1 - trailing_stop_pct)` → sell next bar open, reason `trailing_stop`. Precedence: pending retry > holding expiry > stop_loss > take_profit > trailing_stop > exit_signal. Deliberate difference from the shared engine (intraday low/high touch + same-day fill) — documented.
2. **Simulator** (`single_symbol.py`): `trailing_stop_pct` field; `trailing_anchor` state (set on fill, updated per bar, reset on exit); trigger branch at locked precedence.
3. **Vectorized engine**: identical anchor/branch; dense candidate set when ANY stop type enabled (fixed or trailing); `high` column array with close fallback.
4. **Wiring**: `BatchBacktestRequest.trailing_stop_pct` + validation (>0); both batch paths thread it; `ResearchRunRequest.trailing_stop_pct` override (None = spec value when `apply_stops`); runner `--trailing-stop-pct`; batch_summary config echo. Shared-mode passthrough was already wired in M10.2b and now uses the hoisted value.
5. **Tests** (5 new deterministic + randomized suite extended with trailing params): trigger with hand-computed anchor/exit, anchor reset between trades, high-column fallback, precedence vs exit_signal (reconstructed after the first data design let exit_signal preempt — documented), batch validation.

## Files Changed

- `src/quant_research_engine/portfolio/single_symbol.py`, `single_symbol_vectorized.py` (anchor + branch)
- `src/quant_research_engine/portfolio/batch.py` (field + validation + threading)
- `src/quant_research_engine/orchestration/research_run.py`, `batch_runner.py`, `scripts/batch_backtest_runner.py` (override + flag)
- `tests/test_single_symbol_vectorized.py` (+5 deterministic, randomized suite now includes trailing)

## Validation Output

```bash
uv run pytest -q → 1134 passed, 4 warnings (1129 baseline + 5 new)

# R-QRE-009 real-DB small-sample:
#   mr04a × 3 codes × smoke, --apply-stops --trailing-stop-pct 0.05:
#     simulator vs vectorized → summary.csv IDENTICAL
#   A/B (1% trailing vs off): summaries differ — trailing measurably honored
#   real trailing_stop exit observed (000001.SZ)
```
