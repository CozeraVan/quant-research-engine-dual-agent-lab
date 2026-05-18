# Task Handoff

## Current Task

Add CLI regression coverage for top-level manifest field type errors.

## Task ID

QRE-REPORT-MANIFEST-CLI-TOPLEVEL-TYPE-REGRESSION-001

## Current Status

Review passed. Ready for local checkpoint.

## Current Owner

CODEX

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-CLI-TOPLEVEL-FIELDS-REGRESSION-001`.
- Local checkpoint created: `5aa584b Lock manifest top-level field failures at the CLI boundary`.
- Next task selected: CLI regression coverage for top-level manifest field type errors.
- Claude Code added 4 CLI regression tests: non-string `kind` and non-list `files` across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.

## In Progress

Codex should create the local checkpoint commit for `QRE-REPORT-MANIFEST-CLI-TOPLEVEL-TYPE-REGRESSION-001`.

## Expected Files

- `tests/test_cli.py`
- `src/**` only if a tiny bugfix is strictly necessary

## Validation Baseline

- Last accepted focused validation: `uv run pytest tests/test_cli.py -q` -> `65 passed in 0.99s`
- Last accepted full validation: `uv run pytest -q` -> `209 passed in 1.90s`
- `scripts/check-progress-docs.sh` -> passed
- `scripts/git-finalize-check.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Keep the implementation scoped to CLI regression coverage only.
- Preserve current CLI exit codes and stderr behavior for invalid manifests.
- Avoid reopening loader logic unless a tiny command-boundary fix is strictly necessary.

## Next Suggested Step

Codex should commit the accepted implementation locally, then prepare the next manifest CLI malformed-root regression brief for Claude Code.
