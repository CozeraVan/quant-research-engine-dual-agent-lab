# Coding Handoff

## Task ID

QRE-EVAL-CONFIG-OUTPUT-ARTIFACTS-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Accepted locally and committed.

## Implementation Summary

- Added `evaluation_report_manifest` to `_SUPPORTED_MANIFEST_KINDS` in `report_manifest.py`.
- Added evaluation artifact role column requirements to `_REQUIRED_COLUMNS_BY_ROLE`: `events` (`ts_code`, `trade_date`), `evaluation_summary` (`horizon`, `event_count`), `ic_summary` (`factor`, `horizon`, `observation_dates`), `quantile_summary` (`factor`, `horizon`, `quantile`, `row_count`), `evaluation_group_summary` (`group_by`, `group_value`, `horizon`, `event_count`).
- Added `--output-dir` CLI argument to `eval-config` subcommand.
- Implemented `_write_evaluation_output()` and `_eval_manifest_role()` in `cli.py`.
- When `--output-dir` is provided: writes `events.csv` (always), `summary.csv`/`ic_summary.csv`/`quantile_summary.csv`/`group_summary.csv` (when non-empty), `run_manifest.json` (safe run metadata, no sensitive connection values), and `report_manifest.json` (kind `evaluation_report_manifest`).
- Run manifest records: schema_version, kind, command, strategy_path, start/end dates, codes, round_trip_cost_rate, market_profile when provided, group_by, and emitted artifact keys.

## Files Changed

- `src/quant_research_engine/portfolio/report_manifest.py` — `_SUPPORTED_MANIFEST_KINDS` and `_REQUIRED_COLUMNS_BY_ROLE`
- `src/quant_research_engine/apps/cli.py` — `--output-dir` argument; `_write_evaluation_output()` and `_eval_manifest_role()` helpers; `EvaluationResult` import
- `tests/test_cli.py` — 2 new tests (output-dir writes artifacts; output-dir with group_by and cost rate)
- `tests/test_portfolio_report_manifest.py` — 8 new tests (loads evaluation kind; validates events/summary/ic/quantile/group columns; validates full artifacts; missing file)

## Validation Results

```bash
uv run pytest tests/test_cli.py -q                          # 95 passed in 1.57s
uv run pytest tests/test_portfolio_report_manifest.py -q    # 34 passed
uv run pytest -q                                            # 265 passed in 2.83s
scripts/check-progress-docs.sh                              # passed
git diff --check                                            # passed
scripts/git-finalize-check.sh                               # passed
```

## Constraints

- Preserve evaluation calculations. ✅ no changes to engine.
- Preserve existing `eval-config` stdout behavior. ✅ stdout unchanged; output-dir additive.
- Keep data access read-only. ✅ no writes to upstream databases.
- Do not record sensitive connection values. ✅ run_manifest omits db-url.
- Preserve `market_profile` provenance when used to derive the effective cost rate. ✅
- Do not push. ✅ not pushed.

## Git State

- Branch: `master`
- Commit: `f592d4a Persist eval-config output artifacts with provenance`
- Working tree clean after local finalize.
