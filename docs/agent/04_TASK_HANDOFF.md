# Task Handoff

## Current Task

Add CLI regression coverage for valid explicit `null` optional file-entry metadata.

## Task ID

QRE-REPORT-MANIFEST-CLI-OPTIONAL-NULL-METADATA-REGRESSION-001

## Current Status

Review passed. Ready for local checkpoint.

## Current Owner

CODEX

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-CLI-TOPLEVEL-TYPE-REGRESSION-001`.
- Local checkpoint created: `75b42bc Lock manifest type failures at the CLI boundary`.
- Next task selected: CLI regression coverage for invalid JSON and non-object manifest roots.
- Claude Code added 4 CLI regression tests: invalid JSON and non-object root across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `be62461 Lock malformed manifest roots at the CLI boundary`.
- Next task selected: CLI regression coverage for malformed manifest file entries.
- Claude Code added 4 CLI regression tests: non-object file entry and non-string required file-entry field across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `ac234d8 Lock manifest file-entry shape failures at the CLI boundary`.
- Next task selected: CLI regression coverage for schema-version type errors.
- Claude Code added 4 CLI regression tests: string and boolean `schema_version` across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `bdce0fa Lock schema-version type failures at the CLI boundary`.
- Next task selected: CLI regression coverage for optional file-entry metadata type errors.
- Claude Code added 4 CLI regression tests: non-string optional `symbol` and `window` across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `a4693ab Lock optional manifest entry type failures at the CLI boundary`.
- Next task selected: CLI regression coverage for optional `group_by` file-entry metadata type errors.
- Claude Code added 2 CLI regression tests: non-string optional `group_by` across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `0083c82 Lock optional group-by manifest type failures at the CLI boundary`.
- Next task selected: CLI regression coverage for valid explicit `null` optional file-entry metadata.
- Claude Code added 2 CLI regression tests: explicit `null` optional metadata via `report-files --json` and `report-audit --json`.
- Codex review passed with no Required Fixes.

## In Progress

Codex should create the local checkpoint for `QRE-REPORT-MANIFEST-CLI-OPTIONAL-NULL-METADATA-REGRESSION-001`, then prepare the next brief.

## Expected Files

- `tests/test_cli.py`
- `src/**` only if a tiny bugfix is strictly necessary

## Validation Baseline

- Last accepted focused validation: `uv run pytest tests/test_cli.py -q` -> `85 passed in 1.07s`
- Last accepted full validation: `uv run pytest -q` -> `229 passed in 2.14s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

## Known Risks

- Keep the implementation scoped to CLI regression coverage only.
- Preserve current CLI exit codes and stderr behavior.
- Avoid changing JSON serialization behavior for null optional metadata.

## Next Suggested Step

Codex should commit locally, then prepare the next manifest CLI explicit `null` schema-version regression brief.
