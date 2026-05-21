# Task Handoff

## Current Task

Harden batch grouped-artifact `group_by` header consistency.

## Task ID

QRE-REPORT-BATCH-GROUP-BY-HEADER-CONSISTENCY-001

## Current Status

Accepted locally by Codex review. Ready for local git finalization.

## Current Owner

CODEX

## Completed

- Claude Code added `_BATCH_GROUPED_ROLES` set and `_validate_csv_batch_group_by_header()` function.
- For batch grouped roles (`group_summary`, `group_ranked_symbols`, `window_summary`, `window_ranked_symbols`, `rolling_summary`, `rolling_ranked_symbols`) with manifest `group_by` metadata, the CSV header must contain the column named by the manifest `group_by` value.
- Mismatches produce a `group_by_header_mismatch` validation issue with the manifest value and observed header columns.
- Entries without manifest `group_by` metadata are not checked.
- Evaluation/shared grouped consistency checks from `a3768fb` remain unchanged.
- 8 new tests added (6 manifest + 2 CLI). All 183 tests pass.
- `scripts/check-progress-docs.sh` and `git diff --check` pass.
- Codex reran the batch grouped-file reproduction and confirmed that manifest `group_by='board'` with CSV header `symbol_count,sector` now returns `group_by_header_mismatch`.
- Codex review now marks `10_REVIEW_REPORT.md` as PASS.

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

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 183 passed in 1.94s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Known Risks

- Preserved existing batch `report-files` / `report-audit` filtering semantics.
- No manifest schema-version bump.
- Evaluation/shared grouped consistency checks from `a3768fb` unchanged.
- Batch `group_by` header check only applies to entries with manifest `group_by` metadata.

## Next Suggested Step

Codex should run finalization checks and create the local completion commit for `QRE-REPORT-BATCH-GROUP-BY-HEADER-CONSISTENCY-001`.
