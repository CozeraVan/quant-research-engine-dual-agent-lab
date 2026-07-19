# Coding Handoff

## Task ID

QRE-PREFLIGHT-MISSING-FACTOR-ROBUSTNESS-001

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + real-DB verification; awaiting self-review and user-approved commit)

## Implementation Summary

1. **Fix** (`preflight.py`): `PreflightRunner.run()` now loads only schema-valid factor fields via `load_factor_history` (table exists AND column exists, per `_factor_schema_checks`). Previously it passed ALL requested factors and crashed with raw `UndefinedColumn` before the report — and the M8.3 missing-factor handoff — could complete.
2. **Contract restored**: strategies with missing factor columns now complete with `status=error`, `factor_schema:*` error checks, and a working `extract_missing_factors` → `missing_factor_requests.json` path.
3. **Tests** (3 new in `test_preflight.py`): missing-column completes + request extracted + only loadable fields loaded; missing-table completes with zero loads; available-factor path unchanged.
4. **Real-DB verification**: `qre preflight` on bo02/mr02b/tf07e now emits `missing_factor_requests.json` with `status=error` (previously crashed). The M9.4 consolidated handoff (`outputs/handoff/missing_factor_requests.json`) is now reproducible through the standard CLI path.

## Validation Output

```bash
uv run pytest tests/test_preflight.py -q → 10 passed
uv run pytest -q → 1121 passed, 4 warnings (1118 baseline + 3 new)
qre preflight bo02_keltner_breakout ... → status=error, missing_factor_requests.json emitted
qre preflight mr02b_stochastic_cross ... → status=error, missing_factor_requests.json emitted
qre preflight tf07e_ravi_trend_strength ... → status=error, missing_factor_requests.json emitted
```

# Coding Handoff (archive: M9.4 pilot)

## Task ID

QRE-BATCH-FULL-VALIDATION-001 (M9.4, CR-0002) — pilot slice

## Written By

KIMI_CODE (single agent)

## Status

DONE (handoff + small-sample pilot; full-scale execution is a separate user decision)

## Implementation Summary

1. **Missing-factor handoff**: consolidated `outputs/handoff/missing_factor_requests.json` — 7 requests covering all 5 blocked strategies (atr_10 ×2 [bo02, tf04], sma_50 [mr02b], sma_9/26/52 [tf05a], sma_7 [tf07e]), built from spec factor_fields vs read-only DB schema check (preflight crashes on UndefinedColumn for these — noted as a robustness follow-up). sma_20/sma_65 verified present in DB.
2. **Small-sample full-history pilot** (standing instruction honored): 5 representative strategies × 50 fixed symbols × 2015-2025, vectorized + compact + jobs 4 — all OK, 4.3-9.0s per strategy.
3. **Feasibility report** `outputs/full_history_pilot/feasibility.md`: full-market full-history estimate ≈ 360-400s/strategy → ~3h for 106 strategies with 4 workers (vs weeks pre-vectorization). First multi-regime results recorded (tf01a 10y mean +12.3% vs weak 2024 profile — regime effect documented).
4. No new runtime code; pytest suite unchanged (1118 green).

## Validation Output

```bash
pilot batch 806632904159: 5/5 OK, stage durations 4.3-9.0s recorded in manifests
uv run pytest -q → 1118 passed
```

# Coding Handoff (archive: M10.3)

## Task ID

QRE-CONTINUOUS-REFRESH-001 (M10.3, CR-0003 F2)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + small-sample e2e; awaiting self-review and user-approved commit)

## Current Owner

KIMI_CODE

## Implementation Summary

1. **`orchestration/refresh.py`**: `data_watermark()` (read-only MAX(trade_date)), `RefreshState` JSON roundtrip (`outputs/refresh/state.json`), `needs_refresh()`, `compute_window()` (rolling calendar years, Feb-29 safe), `compute_delta()` (per-strategy transitions: new/removed/status-change/unchanged + metric deltas from batch_summary + summary_metrics), `write_delta_report()` (JSON + MD + `strategy_refresh_delta_manifest`).
2. **`scripts/refresh_batch.py`**: `--check-only` / `--force` / `--window-years` (default 2) / `--jobs` / `--codes` / `--with-eval` / `--apply-stops` / `--universe-filter` / category+strategy limits. Idempotent re-run via the vectorized batch-runner core; state saved after each run; delta dirs named `<timestamp>_<batch_id>` (collision-free for rapid successive runs).
3. **Scheduler**: `deploy/qre-refresh.service` + `deploy/qre-refresh.timer` (systemd user units, daily 18:30) with README install instructions — documented, NOT installed by the agent.
4. **Manifest**: `strategy_refresh_delta_manifest` registered; `qre report-audit` passes on real delta output.
5. **Tests** `tests/test_refresh.py` (9): state roundtrip, needs_refresh edges, window computation (incl. Feb-29), delta transitions (new/removed/status-change/metric deltas), first-run delta, manifest validation via ReportManifest, script-level e2e (first run executes → same watermark no-ops → bumped watermark refreshes; check-only writes nothing; force overrides).

## Files Changed

- `src/quant_research_engine/orchestration/refresh.py` (new)
- `src/quant_research_engine/portfolio/report_manifest.py` (kind + roles)
- `scripts/refresh_batch.py` (new)
- `deploy/qre-refresh.service`, `deploy/qre-refresh.timer` (new)
- `tests/test_refresh.py` (new, 9 tests)
- `README.md` (7b-2 section + systemd instructions)

## Validation Output

```bash
uv run pytest -q → 1118 passed, 4 warnings (1109 baseline + 9 new)

# Small-sample e2e (R-QRE-009, 106 strategies × 3 symbols):
#   first run: 106 ok / 111 total (5 expected missing-factor), batch + delta + state written
#   --check-only: watermark 2026-07-17 == state → refresh needed: False
#   second run: "No new data since last refresh — nothing to do." (no-op ✓)
#   qre report-audit on delta manifest → missing_files=0, validation_issues=0, status=ok
```

## Compliance Notes

- No full-scale execution during this slice (user standing instruction): verification used `--codes` with 3 symbols only.
- Idempotent re-run by design (no incremental engine state); read-only DB access (R-QRE-005); no new dependencies; systemd units documented but not installed.
