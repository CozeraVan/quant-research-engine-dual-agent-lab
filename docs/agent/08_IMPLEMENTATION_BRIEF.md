# Implementation Brief

## Task ID

QRE-STRATEGY-FIT-STABILITY-001 (M10.1 v1.1, deferred follow-up recorded in CR-0003)

## Created By

KIMI_CODE (single agent; user direction "请你继续推进下一步任务" 2026-07-19)

## Intended Implementer

KIMI_CODE

## Goal

Deliver the deferred v1.1: persist per-symbol monthly returns as a compact-mode artifact, and add a time-stability metric to the strategy-fit report — so a strategy's pool edge can be judged not only by significance and magnitude but by whether it repeats across months.

## Background Evidence

- M10.1 v1 explicitly deferred time stability: per-symbol monthly returns are not persisted in compact artifacts (recorded in CR-0003 and the M10.1 review).
- The concat window collector (`_collect_window_return_rows`) already produces exactly the needed intermediate: `(window, symbol, total_return)` rows from equity curves — the artifact is a materialization of that row set.
- Compact batches keep equity curves in memory at write time, so the artifact costs one vectorized pass, no re-run.

## Semantics (locked)

- Artifact `symbol_month_returns.csv` (compact mode): one row per (symbol, calendar month) with `total_return` = last/first equity − 1 within the month (identical computation to the window-summary collector; NaN when first equity ≤ 0). Manifest role `symbol_month_returns` with required columns `{window, symbol, total_return}`.
- Stability metric (strategy_fit, per strategy): for the significant pool at pool_tier, per month compare pool mean monthly return vs universe mean monthly return; `stability_ratio` = fraction of covered months where pool > universe (months with ≥1 pool stock having a return that month). Report `stability_months_covered`, `stability_ratio`, `stability_pool_month_mean_min`. Informational (no hard gate in v1.1); strategies without the artifact report blank stability fields.

## Scope

1. `write_batch_result` (compact path): write `symbol_month_returns.csv` from result equity curves via the concat collector (window="M"); register in the batch report manifest (paths + role); required-columns contract in `report_manifest.py`.
2. `analysis/strategy_fit.py`: load the artifact per strategy when present; compute stability fields; add them to `strategy_fit_summary.csv` and the markdown report.
3. Tests: artifact content vs hand-computed oracle, manifest registration/validation, stability computation with synthetic monthly data, absent-artifact blanks, full-suite green.
4. Small-sample pilot (R-QRE-009): 2 strategies × 3 codes × smoke with compact → artifact present and manifest-audited; fit report shows stability columns.

## Non-Goals

- No re-run of existing batches (artifact applies to future batches/refreshes; existing quick_batch_106 lacks it until re-run).
- No buy-hold monthly excess in v1.1 (stability uses within-strategy pool-vs-universe monthly returns — documented semantics).
- No hard stability gate; informational only.

## Expected Tests

```bash
uv run pytest -q
```

## Acceptance Criteria

- Compact batches write `symbol_month_returns.csv`, manifest-registered and passing `qre report-audit`.
- Fit report exposes stability columns for strategies with the artifact; blank otherwise.
- Full pytest suite green; pilot verified on real data.
