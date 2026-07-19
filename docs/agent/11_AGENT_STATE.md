# Agent State

This file is the source of truth for single-agent workflow recovery.

## Current Phase

AWAITING_GIT_APPROVAL

## Current Owner

KIMI_CODE (sole development agent; user is final approver)

## Current Task

QRE-PARAM-OVERRIDE-001 / M10.2a (implementation DONE, self-review PASS — awaiting user-approved git finalization)

## Standing Instructions (user)

- 2026-07-19: No full-scale backtest runs until the core engine work is mostly complete; after that, full-history (M9.4) runs start with small samples (R-QRE-009). Current slices (M10.1 analysis of existing artifacts) comply — zero backtest execution.

Parent change request: `docs/agent/change_requests/CR-0002-strategy-research-validation.md` (Milestone 9: Strategy Research Validation).

## Last Completed Step

**QRE-PARAM-OVERRIDE-001 / M10.2a (DONE 2026-07-19, awaiting commit):**

1. `portfolio/universe.py`: metadata loader (stock_suspend/stock_st as-of, daily-derived list_date) + `apply_universe_filter` with complete drop accounting and honest `unavailable_rules`; `validate_profile_overrides`.
2. research_run: `profile_overrides` (dataclasses.replace + validation) and `universe_filter` (opt-in) wired for batch/shared modes; `universe_report.json` backtest artifact; manifest records overrides + flag.
3. Runner flags: `--universe-filter`, `--commission-rate/--min-commission/--stamp-tax/--transfer-fee/--slippage-buy/--slippage-sell`.
4. Small-sample verified: overrides measurably change results; unavailable rules honestly reported on real data; default runs unchanged.
5. 1059 tests green (14 new). Stops split to M10.2b (engine exit logic, dual-engine equality).

**QRE-STRATEGY-FIT-ANALYSIS-001 / M10.1 (DONE, finalized 2026-07-19, commit `d514c4c`):**

1. `analysis/strategy_fit.py`: exact binomial significance tiers (90/99/99.9%), magnitude gate (net + excess vs buy-hold), free-rider accounting, strategy meta-test vs false-positive expectation, hypergeometric enrichment, BH-FDR, deterministic outputs + manifest.
2. `scripts/strategy_fit_report.py` + `strategy_fit_report_manifest` kind registered (report-audit passes); runner `--metadata-columns` passthrough.
3. Metadata reality: `reference.stock_basic` EMPTY upstream — metadata composed from `daily_basic` snapshot + `derive_board`; `industry_group` = unknown (gap documented).
4. Real batch (2024, 106 strategies): **all below 90% meta tier** (significant-stock counts below false-positive expectation — hand-verified true result); 25 stocks at 99% tier recorded as leads in `strategy_fit_stocks.csv`.
5. 1045 tests green (11 new); R-QRE-008 screening-evidence caveat in report.

**QRE-VECTORIZED-ENGINE-001 / M9.1b (DONE, finalized 2026-07-19, commit `c86441b`):**

1. Vectorized trade-level single-symbol engine: event-level loop on candidate bars, one-pass groupby pre-split, vectorized equity reconstruction; `position_sizing` (`full_compound`/`fixed_cash`).
2. Vectorized window/rolling analytics collectors (`risk.py` untouched, used as equality oracle); shared research frame between eval and backtest stages.
3. Equality evidence: 61 synthetic + 40 randomized tests, 106/106 catalog × 50 symbols byte-identical, full-market artifacts identical to simulator baseline.
4. Benchmark: backtest stage 1,718.9s → 40.2s (**42.8×**); quick batch estimate 11.1h → ~25-30 min. Runner `--engine-impl` defaults to `vectorized` (simulator kept as fallback); 1034 tests green.

**QRE-BATCH-PERF-SLIM-001 / M9.1 (DONE, finalized 2026-07-19, commit `24699ce`):**

1. Batch runner core moved into `orchestration/batch_runner.py`; `--jobs N` process-pool parallelism; `--compact` output mode (9 files vs ~26k per strategy, metrics byte-identical).
2. Per-stage timing in research-run manifests; `PostgresDataStore.close()` engine disposal; resume scan fixed (both directory levels).
3. Profiling baseline: tf01a quick mode serial = 1742.5s (backtest stage 98.6%); data-load reuse ruled out by evidence.
4. Quick batch `f365c8a07b33` (2026-07-19 06:32 +08): **106 OK / 5 error** (known missing-factor strategies), wall time **11.1h** with 4 jobs (vs ~51h serial), per-strategy mean 1459s (-16%), **2,013 files / 2.8GB** (~99.9% fewer files, ~89% fewer bytes); `qre report-audit` on compact manifests → ok.
5. Milestone 10 planned (CR-0003): M10.1 strategy-fit clustering, M10.2 parameter overrides, M10.3 continuous refresh, M10.4 optional ML clustering; M9.2/M9.3 merged into M10.1.
6. R-QRE-009 locked (user standing instruction): small-sample validation before any full-scale run.

## Git State

- Current branch: `master`
- Last commit: `d514c4c` Add strategy-fit analysis with significance tiers (M10.1) (15 files)
- Working tree: clean except untracked `.claude/scheduled_tasks.lock` (lock file, intentionally untracked).
- **Run outputs now live outside the repo**: `outputs` → symlink to `/home/van/qre-outputs/` (all 19GB preserved there); `QRE_OUTPUT_DIR` env var overrides the batch runner output root.
- Remote: none configured.

## Latest Validation Evidence

```
uv run pytest -q → 1034 passed, 4 warnings (2026-07-19, M9.1b final)
scripts/check-progress-docs.sh → passed
git diff --check → clean
equality ladder: 61 synthetic + 40 randomized + 106/106 catalog × 50 + full-market artifacts identical
benchmark: backtest stage 1718.9s → 40.2s (42.8×)
```

## Pending Decisions (user)

1. ~~CR-0002 / 08 brief~~ — APPROVED 2026-07-18. ~~M9.1 commit~~ — `24699ce`. ~~M9.1b commit~~ — `c86441b`.
2. **Go-ahead for M10.1 implementation** (brief written 2026-07-19).
3. Whether to commission upstream factor computation (`atr_10`, `sma_7/9/20/26/50/52/65`) in `indicators_tushare` / `quant_ts` to unblock the 5 remaining catalog strategies (needed for M9.4).
4. ~~Engine-loop optimization~~ — DONE as M9.1b (`c86441b`). Follow-up micro-slices available: cross-symbol-concatenated analytics, groupby-aware signal evaluation (speed target 40.2s → ≤30s).
5. ~~F1/F2/F3 granularity~~ — ALIGNED 2026-07-19 (CR-0003): M9.1b → M10.1 → M10.2 → M10.3; M10.4 ML clustering needs separate dependency approval.

## Quick Batch In Flight

- `outputs/backtests/quick_batch_106/f365c8a07b33/`, launched 2026-07-18 ~18:40, `--jobs 4 --compact --skip-preflight --resume`.
- Per-strategy ≈ 27-30 min (CPU-bound engine loop); expected total ≈ 13h. User decided to let it finish at `--jobs 4`.
- On completion: record batch results in `09`, verify compact output size reduction, then propose commit.

## Quick Batch Final (2026-07-19 06:32 +08)

- 106 OK / 5 error (only the known missing-factor strategies); wall time 11.1h; per-strategy mean 1459s (-16% vs baseline); 2,013 files / 2.8GB (≈99.9% fewer files, ≈89% fewer bytes vs standard mode); report-audit on compact manifests → status=ok, 0 issues.
- Remaining before commit: user approval.

## Phase Vocabulary (single-agent, since 2026-07-18)

- `PLANNING`: writing/updating `08_IMPLEMENTATION_BRIEF.md`
- `IMPLEMENTING`: executing the brief; records go to `09_CODING_HANDOFF.md`
- `SELF_REVIEW`: writing `10_REVIEW_REPORT.md`; Required Fixes send the task back to `IMPLEMENTING`
- `AWAITING_GIT_APPROVAL`: review passed, commit message proposed, waiting for user approval
- `DONE`: finalized (or docs-only task completed without commit need)
- `USER_DIRECTED`: no active workflow task; user decides the next move

## Standing Approvals

None. Every git commit requires explicit user approval in the current session.

## Completion Status

Engine feature-complete (947 tests green); single-agent workflow active; batch pipeline committed. Next phase (Strategy Research Validation) planned and awaiting user go-ahead: CR-0002 + first-slice brief `QRE-BATCH-PERF-SLIM-001` are drafted in `docs/agent/`.
