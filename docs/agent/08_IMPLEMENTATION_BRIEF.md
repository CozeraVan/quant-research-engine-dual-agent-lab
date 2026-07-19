# Implementation Brief

## Task ID

QRE-VECTORIZED-ENGINE-001 (M9.1b)

## Created By

KIMI_CODE (single agent; direction user-approved 2026-07-19, granularity aligned in decision log entry of same date)

## Intended Implementer

KIMI_CODE

## Goal

Replace the per-bar `iterrows` simulation in the batch backtest path with a vectorized trade-level implementation that produces **metric-identical results** to the existing bar simulator, cutting the backtest stage from ~1,400s to ≤30s per strategy (quick-mode full-market). This is the speed foundation for full-history runs (M9.4) and continuous refresh (M10.3).

## Background Evidence

- Profiling (batch `f365c8a07b33`, recorded in prior `09_CODING_HANDOFF.md`): backtest stage = 98.6% of runtime; eval stage 21s vs backtest 1,719s per strategy.
- The cost is implementation-shaped, not semantics-shaped: per-symbol full-frame filtering (`single_symbol.py:38`, ~5,292 scans of a ~1.3M-row frame per strategy) plus a Python `iterrows` loop with per-bar dict allocations (`single_symbol.py:63`).
- Batch-path semantics permit exact trade-level computation: single position at a time, all-in entries, no intra-hold decisions; only signal days, execution days, exit days, and rejection-retry days can change state.

## Scope

1. **New module** `src/quant_research_engine/portfolio/single_symbol_vectorized.py` implementing the same `SingleSymbolBacktestRequest`/`Result` contract:
   - Frame pre-split by `ts_code` in one pass (no repeated full-frame scans) — shared across symbols at the batch-engine level.
   - Signal evaluation per symbol subframe (identical semantics to today; `shift`/`rolling` must never leak across symbols — no full-frame signal evaluation).
   - Event-level simulation on numpy arrays: candidate event bars are signal days, pending-execution days, holding-expiry days, exit-signal days, and rejection-retry days; all other bars are provably no-ops. Per-bar work uses array indexing, not `iterrows`/dict building.
   - Identical execution rules: T+1 next-open execution, slippage, lot rounding, suspension/limit-up/limit-down validation via `market_profile.validate_order`, cost via `calculate_cost`, failed-order records, sell-rejection retry next bar.
   - Vectorized equity-curve reconstruction between events (piecewise-constant quantity × close + cash), yielding the same daily equity curve as the simulator.
   - `position_sizing` option: `full_compound` (default, current all-in behavior) and `fixed_cash` (fixed notional per trade) — per user request for simple/compound sizing models.
2. **Wiring**: `BatchBacktestRequest.engine_impl: Literal["simulator", "vectorized"]` (default `"simulator"` during rollout) threaded through `batch.py` → per-symbol engine selection; `ResearchRunRequest` and batch runner gain the same flag (`--engine-impl`). Default flips to `"vectorized"` only after the equality evidence in step 4 is recorded.
3. **Unit equality tests**: side-by-side comparison of both engines on synthetic frames — orders/trades/equity_curve/failed_orders/summary must match exactly. Cases: plain entry+holding expiry; exit-signal path; limit-up buy rejection; limit-down sell rejection with retry; suspended symbol; signal-every-day stress; empty frame; last-bar signal (no t+1); fixed_cash sizing; zero-trade symbols.
4. **Small-sample real-DB verification (R-QRE-009)**: 3-10 representative catalog strategies × ~50 symbols × 1-year window — per-symbol metric equality plus wall-time measurement, recorded in `09_CODING_HANDOFF.md`. Only after this passes: catalog-scale equality spot-check (subset of symbols across all 106 strategies).
5. **Benchmark**: same tf01a quick-mode measurement as the baseline (1,742.5s total / 1,718.9s backtest stage); target backtest stage ≤ 30s.
6. **Docs**: README/QUICKSTART note on `--engine-impl` and `position_sizing`; module docstrings; `docs/agent/` updates.

## Non-Goals

- Shared-cash engine untouched (portfolio-level capital interleaving genuinely needs time-ordered simulation).
- No result/behavior changes in the existing simulator or in default outputs (R-CORE-001); default flips only on recorded equality evidence.
- No new dependencies (numpy comes with pandas).
- No intraday data, no short selling, no ML.

## Expected Tests

```bash
uv run pytest tests/test_single_symbol_vectorized.py -q   # new equality suite
uv run pytest -q                                           # full suite green (967+)
uv run pytest tests/test_batch_runner.py tests/test_research_run.py -q
```

## Validation Commands

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
# R-QRE-009 sequence: synthetic equality → 50-symbol real-DB equality + timing → catalog-scale spot-check
```

## Acceptance Criteria

- Vectorized engine passes all equality tests (synthetic + real-DB sample), including rejection/retry and sizing modes.
- tf01a quick-mode backtest stage ≤ 30s (from 1,718.9s) with identical outputs.
- `--engine-impl simulator` preserves current behavior bit-for-bit; default flip documented with evidence.
- Full pytest suite green; no API breakage in `SingleSymbolBacktestRequest`/`Result` consumers.
