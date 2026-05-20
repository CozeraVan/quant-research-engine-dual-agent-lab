# Coding Handoff

## Task ID

QRE-EVAL-GROUP-BY-MANIFEST-PARITY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Implementation Summary

Added per-column evaluation grouped artifacts and manifest metadata so evaluation grouped outputs can be discovered and audited with `--group-by`, matching batch/shared-cash parity.

Key changes:

- `_eval_manifest_role`: extended to handle `group_summary_by_*` keys, returning `evaluation_group_summary`.
- `_eval_manifest_group_by`: new helper that extracts the group column name from per-column artifact keys.
- `_eval_manifest_entry`: new helper that builds manifest file entries with `group_by` metadata when present.
- `_write_evaluation_output`: now emits one `group_summary_by_<col>.csv` per unique `group_by` value in the combined group summary, alongside the existing combined `group_summary.csv`. Each per-column file contains only rows for that `group_by` value.
- Manifest entries for per-column files carry role `evaluation_group_summary` and metadata `group_by=<col>`, enabling `report-files` / `report-audit --group-by` filtering.

## Files Changed

- `src/quant_research_engine/apps/cli.py` — added `_eval_manifest_group_by`, `_eval_manifest_entry` helpers; extended `_eval_manifest_role`; updated `_write_evaluation_output` to emit per-column grouped CSVs and use `_eval_manifest_entry` for manifest construction.
- `tests/test_cli.py` — updated `test_cli_eval_config_output_dir_with_group_by_and_market_profile` to verify per-column files and manifest metadata; added `test_cli_eval_config_output_dir_multi_group_by_writes_per_column_files`, `test_cli_report_files_eval_group_by_filter`, `test_cli_report_audit_eval_group_by_filter`, `test_cli_report_audit_eval_group_by_missing_file`.
- `tests/test_portfolio_report_manifest.py` — added `test_report_manifest_validates_evaluation_group_by_per_column` and `test_report_manifest_validates_evaluation_per_column_missing_columns`.

## Validation Results

```bash
uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q  # 164 passed
scripts/check-progress-docs.sh                                               # passed
git diff --check                                                             # passed
```

## Constraints

- Preserved existing combined `group_summary.csv`. ✅
- No manifest schema-version change. ✅
- No batch/shared filtering behavior weakened. ✅
- No `docs/legacy/**` changes. ✅
- No new external data dependencies. ✅

## Git State

- Branch: `master`
- All changes uncommitted.
- Ready for Codex review.

## Next Suggested Step

Codex should review and produce `10_REVIEW_REPORT.md`.
