# Task Handoff

## Current Task

Add CLI regression coverage for missing top-level manifest fields.

## Task ID

QRE-REPORT-MANIFEST-CLI-TOPLEVEL-FIELDS-REGRESSION-001

## Current Status

Review passed. Ready for local checkpoint.

## Current Owner

CODEX

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-FILES-PRESENCE-VALIDATION-001`.
- Local checkpoint created: `53f9aba Keep missing manifest files distinct from empty manifests`.
- Next low-risk follow-up task selected from the ongoing report-manifest robustness track.
- Next task selected: CLI regression coverage for missing top-level manifest fields.
- Claude Code added 4 CLI regression tests: `report-files`/`report-audit` with missing `kind` and missing `files`.
- Codex review passed with no Required Fixes.

## In Progress

Codex should create the local checkpoint commit for `QRE-REPORT-MANIFEST-CLI-TOPLEVEL-FIELDS-REGRESSION-001`.

## Expected Files

- `tests/test_cli.py`
- `src/**` only if a tiny bugfix is strictly necessary

## Validation Baseline

- Last accepted focused validation: `uv run pytest tests/test_cli.py -q` -> `61 passed in 1.07s`
- Last accepted full validation: `uv run pytest -q` -> `205 passed in 1.98s`
- `scripts/check-progress-docs.sh` -> passed
- `scripts/git-finalize-check.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Keep the implementation scoped to CLI regression coverage only.
- Preserve current CLI exit codes and stderr behavior for invalid manifests.
- Avoid reopening loader logic unless a tiny command-boundary fix is strictly necessary.

## Next Suggested Step

Codex should commit the accepted implementation locally, then prepare the next manifest CLI type-error regression brief for Claude Code.
