# Implementation Brief

## Task ID

QRE-BATCH-FULL-VALIDATION-001 (M9.4, CR-0002)

## Created By

KIMI_CODE (single agent; user direction "请你继续推进下一步任务" 2026-07-19; standing instruction satisfied — core engine work is complete, so full-history validation starts with SMALL SAMPLES only)

## Intended Implementer

KIMI_CODE

## Goal

Prepare full-history (2015-2025) strategy validation: (1) hand the 5 blocked strategies' missing factors to upstream with a consolidated `missing_factor_requests.json`; (2) measure full-history feasibility with a small-sample run (representative strategies × ~50 symbols × 2015-2025) using the vectorized engine, producing both timing evidence for the full-scale decision and the first multi-regime results. **No full-scale execution** — full-market full-history remains a separate user decision.

## Background Evidence

- Core engine work is complete (M9.1b vectorized engine 42.8×, M10.1 fit analysis, M10.2a params, M10.2b stops, M10.3 refresh) — the user's precondition for full-history ("基本内核引擎任务大体完成") is met, with small samples mandated first ("再跑小样本全期回测").
- 5 blocked strategies and their missing columns are known since May: `bo02`/`tf04` (atr_10), `mr02b` (sma_50), `tf05a` (sma_9/26/52), `tf07e` (sma_7/20/65).
- Vectorized quick-mode (1y) backtest stage: ~40s/strategy full-market; scaling is near-linear in total bars, so small-sample 10y runs are minutes.

## Scope

1. **Missing-factor handoff**: run `qre preflight` on the 5 blocked strategy YAMLs (read-only), consolidate into `outputs/handoff/missing_factor_requests.json` via the existing `extract_missing_factors`/`emit_missing_factor_requests` mechanism, with a short README section noting the upstream owner (`indicators_tushare` computes into `factors.*`; QRE does not compute indicators, R-QRE-002).
2. **Small-sample full-history run**: 5 representative strategies (mr04a_ibs_reversal, cs01a_pure_small_cap, bo06a_atr_anomaly_momentum, tf01a_ma_cross_20_120, cb01b_macd_cross_volume) × 50 symbols (same fixed set as earlier verification) × 2015-01-01→2025-12-31, `--engine-impl vectorized --compact --jobs 4 --skip-preflight --skip-eval`. Record per-strategy wall times and stage durations.
3. **Feasibility report**: extrapolate full-scale cost (106 strategies × full market × 10y) from the measured numbers; write `outputs/full_history_pilot/feasibility.md` with timing evidence + per-strategy summary metrics (screening evidence, R-QRE-008 caveat).
4. **Docs**: record results in `09_CODING_HANDOFF.md`; update CR-0002 M9.4 status.

## Non-Goals

- No full-market full-history batch (user decision after seeing feasibility numbers).
- No indicator computation inside QRE; no upstream (`indicators_tushare`/`quant_ts`) modifications.
- No new dependencies.

## Expected Tests

```bash
uv run pytest -q   # no new runtime code expected; suite stays green
```

## Validation Commands

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
# pilot run: 5 strategies × 50 codes × 2015-2025 (this slice's only execution)
```

## Acceptance Criteria

- `outputs/handoff/missing_factor_requests.json` consolidates all 5 blocked strategies' missing columns and is consistent with `qre preflight` output.
- Pilot completes; per-strategy timings recorded; feasibility report includes a full-scale cost estimate with clear assumptions and the R-QRE-008 caveat.
- No full-scale run performed; pytest suite green.
