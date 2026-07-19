# Task Handoff

## Task ID

QRE-VECTORIZED-ENGINE-001 (M9.1b)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Current Owner

KIMI_CODE

## Problem Summary

The batch-path single-symbol engine simulates via per-symbol full-frame filtering plus a Python `iterrows` loop over every bar — ~98% of backtest runtime (measured: backtest stage 1,718.9s of 1,742.5s total for tf01a quick mode). Batch-path semantics (single position, all-in entries, no intra-hold decisions) allow an exactly equivalent trade-level implementation. The user additionally requested simple/compound position-sizing models and reaffirmed R-QRE-009: small-sample validation before any full-scale run.

## Implementation Summary

Planning only so far (direction user-approved 2026-07-19, recorded in `06_DECISION_LOG.md`):

1. New `portfolio/single_symbol_vectorized.py`: one-pass groupby pre-split, per-subframe signal evaluation (no cross-symbol leakage), event-level simulation on numpy arrays (loop over candidate event bars only), identical execution rules (T+1, slippage, lot rounding, order validation, costs, failed orders, sell retry), vectorized equity-curve reconstruction, `position_sizing` (`full_compound` default = current behavior, `fixed_cash`).
2. Wiring: `engine_impl` flag (`simulator` default during rollout) through `BatchBacktestRequest` → research_run → runner `--engine-impl`; default flips to `vectorized` only after recorded equality evidence.
3. Verification ladder per R-QRE-009: synthetic equality suite (orders/trades/equity/failed/summary exact match, incl. rejection/retry/edge cases) → 3-10 strategies × ~50 symbols × 1y real-DB equality + timing → catalog-scale spot-check.
4. Benchmark target: backtest stage ≤ 30s (from 1,718.9s) with identical outputs.

Previous task `QRE-BATCH-PERF-SLIM-001` (M9.1) finalized in commit `24699ce`. Run outputs were externalized 2026-07-19 (`QRE-OUTPUTS-EXTERNAL-001`): `outputs` is now a symlink to `/home/van/qre-outputs/`; the batch runner honors `QRE_OUTPUT_DIR`; all documented output paths keep working through the symlink.

## Hard Constraints

- Metric-identical results vs the bar simulator (equality is the acceptance gate, not approximation).
- Shared-cash engine untouched; no new dependencies; no behavior change in default outputs until the evidence-backed default flip.
- R-QRE-009: no catalog-scale run before the small-sample verification passes.

## Validation Evidence

```bash
# Planning slice — docs only, no code changed yet
scripts/check-progress-docs.sh → to be run before commit
```
