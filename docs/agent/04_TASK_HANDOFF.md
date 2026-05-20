# Task Handoff

## Current Task

Strengthen `run_manifest` content validation for report audit.

## Task ID

QRE-RUN-MANIFEST-CONTENT-VALIDATION-001

## Current Status

Accepted locally by Codex review. Ready for local git finalization.

## Current Owner

CODEX

## Completed

- Claude Code added `_validate_run_manifest()` in `ReportManifest` with field-level validation for `schema_version`, `kind`, `run_id`, `command`, `strategy_path`, and `artifacts`.
- `run_id` accepts string or null; `kind` restricted to `portfolio_backtest_run_manifest` and `evaluation_run_manifest`.
- Missing fields produce `missing_run_manifest_field` issues; type errors produce `invalid_run_manifest_field` issues.
- Present-but-null values for `schema_version`, `kind`, `command`, `strategy_path`, and `artifacts` now produce `invalid_run_manifest_field` issues. `run_id: null` remains valid.
- Summary JSON validation is unchanged.
- CLI `report-audit --role run_manifest --json` reports malformed run manifests through existing structured issue output.
- Codex reproduction case (4 null non-nullable fields) now returns 4 issues (was 0).
- Codex updated `10_REVIEW_REPORT.md` with outcome PASS.
- Codex validation passed:
  - `uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q` -> `158 passed, 2 warnings in 1.78s`
  - `uv run pytest -q` -> `346 passed, 2 warnings in 3.30s`
  - `scripts/check-progress-docs.sh` -> passed
  - `git diff --check` -> passed

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Accepted fix validation:

- `uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q` -> `158 passed, 2 warnings in 1.78s`
- `uv run pytest -q` -> `346 passed, 2 warnings in 3.30s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

Codex reproduction re-run:

- A run manifest with `schema_version: null`, `command: null`, `strategy_path: null`, and `artifacts: null` now returns 4 `invalid_run_manifest_field` issues.

## Known Risks

- Keep `run_id` optional and allow explicit null. ✅
- Do not alter report manifest file-entry schema. ✅
- Preserve existing report-files/report-audit semantics except for the new malformed-run-manifest content issues. ✅
- Do not validate nested strategy semantics or add orchestration behavior. ✅

## Next Suggested Step

Codex should finalize the accepted implementation with a local commit, then prepare the next Claude Code implementation brief.
