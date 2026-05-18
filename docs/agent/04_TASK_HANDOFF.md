# Task Handoff

## Current Task

Add CLI regression coverage for top-level manifest field type errors.

## Task ID

QRE-REPORT-MANIFEST-CLI-TOPLEVEL-TYPE-REGRESSION-001

## Current Status

Planned by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-FILES-PRESENCE-VALIDATION-001`.
- Local checkpoint created: `53f9aba Keep missing manifest files distinct from empty manifests`.
- Next low-risk follow-up task selected from the ongoing report-manifest robustness track.
- Claude Code added 4 CLI regression tests: `report-files`/`report-audit` with missing `kind` and missing `files`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `5aa584b Lock manifest top-level field failures at the CLI boundary`.
- Next task selected: CLI regression coverage for top-level manifest field type errors.

## In Progress

Claude Code should implement `QRE-REPORT-MANIFEST-CLI-TOPLEVEL-TYPE-REGRESSION-001`.

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

Claude Code should read `docs/agent/08_IMPLEMENTATION_BRIEF.md` and `docs/agent/12_AGENT_BOARD.md`, implement the tests, run the required checks, and hand back for Codex review.
