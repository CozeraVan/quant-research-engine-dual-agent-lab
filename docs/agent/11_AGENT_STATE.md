# Agent State

This file is the source of truth for single-agent workflow recovery.

## Current Phase

AWAITING_GIT_APPROVAL

## Current Owner

KIMI_CODE (sole development agent; user is final approver)

## Current Task

QRE-UPSTREAM-FACTOR-DELIVERY-001 (DONE — backfill complete, queue 7/7 fulfilled, 5/5 strategies unblocked; awaiting user-approved git finalization)

Progress:
1. Verified canonical project `/home/van/quant-workspace/indicators_tushare` and systemd timers (quant-ts 16:30, indicators 16:40, both enabled; yaml-config factors auto-join daily updates).
2. Edits made (indicators repo, no git action): `config/factors.yaml` sma periods += 7/9/26/50/52 + `atrraw` entry; `factors/volatility_factors.py` new `ATRRawFactor` class (raw `atr_{n}` naming; same values as existing `atrr_10`).
3. Project flow: validate (success, 0 failures) → plan (all 7 target columns present; superset: other pending config columns in overlap/volatility categories also covered) → small-sample backfill of 000001.SZ → value parity vs hand-computed SMA/Wilder-ATR within storage rounding, 100% non-null.
4. Full-history backfill (`backfill --categories overlap volatility --execute --max-workers 4`) RUNNING in background.

Next when backfill completes: `factor_request_queue.py recheck` → fulfilled; small-sample re-run of the 5 shelved strategies (R-QRE-009); then user decides on full re-run.

## Standing Instructions (user)

- 2026-07-19: No full-scale backtest runs until the core engine work is mostly complete; after that, full-history (M9.4) runs start with small samples (R-QRE-009). Current slices (M10.1 analysis of existing artifacts) comply — zero backtest execution.

Parent change request: `docs/agent/change_requests/CR-0002-strategy-research-validation.md` (Milestone 9: Strategy Research Validation).

## Last Completed Step

**QRE-ANALYTICS-CONCAT-001 (DONE, finalized 2026-07-19, commit `b72b9af`):** backtest stage 25.852s — M9.1b ≤30s target MET (66.5×).

**QRE-TRAILING-STOP-BATCH-001 (DONE, finalized 2026-07-19, commit `77b8897`):** stop family complete in batch path.

**QRE-MISSING-FACTOR-QUEUE-001 (DONE, finalized 2026-07-19, commit `5c60b8b`):** queue store + shelve semantics + auto-queue + CLI + `docs/handoff.md`; 7 pending requests tracked.

**QRE-PREFLIGHT-MISSING-FACTOR-ROBUSTNESS-001 (DONE, finalized 2026-07-19, commit `6628631`).**

**QRE-BATCH-FULL-VALIDATION-001 / M9.4 pilot (DONE, finalized 2026-07-19, commit `f90567c`):** handoff emitted (7 requests); small-sample full-history pilot OK; ~3h full-scale estimate. Full-scale trigger + upstream factors remain user decisions.

**QRE-CONTINUOUS-REFRESH-001 / M10.3 (DONE, finalized 2026-07-19, commit `1345471`):**

1. `orchestration/refresh.py`: watermark query, RefreshState, rolling window, per-strategy delta computation, delta report writer with manifest.
2. `scripts/refresh_batch.py`: check-only/force/window/codes flags; idempotent vectorized re-run; state + delta persisted.
3. `deploy/qre-refresh.{service,timer}` documented (daily 18:30), NOT installed; README 7b-2 with install commands.
4. Small-sample e2e on real data: first run 106 ok/111; check-only side-effect free; same-watermark no-op; delta manifest audit ok.
5. 1118 tests green (9 new). No full-scale execution (standing instruction honored).

**QRE-STOPS-BATCH-ENGINE-001 / M10.2b (DONE, finalized 2026-07-19, commit `24c284d`):**

1. stop_loss_pct/take_profit_pct honored in both engines: close-based evaluation vs fill price, next-open execution, precedence pending retry > expiry > stop_loss > take_profit > exit_signal; dense candidates in vectorized engine when enabled.
2. Opt-in wiring: `apply_stops` + request overrides (None = spec values); shared mode passthrough incl. trailing_stop_pct; runner `--apply-stops/--stop-loss-pct/--take-profit-pct`.
3. Verification: 50 new tests (40 randomized-with-stops equality seeds); real-DB dual-engine identity (tf01a, mr04a); A/B effect + real stop_loss exit observed; default runs unchanged.
4. 1109 tests green. Trailing stop remains follow-up (shared engine already has it).

**QRE-PARAM-OVERRIDE-001 / M10.2a (DONE, finalized 2026-07-19, commit `a16d6c5`):**

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
- Last commit: `b72b9af` Vectorize analytics cross-symbol; backtest stage 25.9s (target met) (6 files)
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

1. ~~CR-0002/0003 slices~~ — ALL DONE through M10.3 (commits `24699ce`/`c86441b`/`d514c4c`/`a16d6c5`/`24c284d`/`1345471`).
2. **Trigger full-scale full-history batch?** (~3h estimate, `outputs/full_history_pilot/feasibility.md`) — ready when you are.
3. ~~Upstream factor computation~~ — DONE (QRE-UPSTREAM-FACTOR-DELIVERY-001): backfill 5,544 stocks/0 failed; queue 7/7 fulfilled; 5/5 strategies unblocked; daily timer covers new columns from tomorrow. Full 111-strategy re-run (incl. formerly-shelved 5) is now a user decision alongside the full-history trigger.
4. M10.4 ML clustering — needs separate dependency approval (5070 Ti noted).
5. Follow-up micro-slices (optional): groupby-aware signal evaluation; runner-level cross-strategy frame caching (frame load ~17s is now the dominant cost). ~~Preflight UndefinedColumn robustness~~ — DONE. ~~Trailing stop~~ — DONE. ~~Cross-symbol analytics (≤30s)~~ — DONE, target MET at 25.852s.

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
