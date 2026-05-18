# Task Handoff

## Current Task

Add CLI regression coverage for malformed manifest file entries.

## Task ID

QRE-REPORT-MANIFEST-CLI-FILE-ENTRY-SHAPE-REGRESSION-001

## Current Status

Planned by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-CLI-TOPLEVEL-TYPE-REGRESSION-001`.
- Local checkpoint created: `75b42bc Lock manifest type failures at the CLI boundary`.
- Next task selected: CLI regression coverage for invalid JSON and non-object manifest roots.
- Claude Code added 4 CLI regression tests: invalid JSON and non-object root across `report-files` and `report-audit`.
- Codex review passed with no Required Fixes.
- Local checkpoint created: `be62461 Lock malformed manifest roots at the CLI boundary`.
- Next task selected: CLI regression coverage for malformed manifest file entries.

## In Progress

Claude Code should implement `QRE-REPORT-MANIFEST-CLI-FILE-ENTRY-SHAPE-REGRESSION-001`.

## Expected Files

- `tests/test_cli.py`
- `src/**` only if a tiny bugfix is strictly necessary

## Validation Baseline

- Last accepted focused validation: `uv run pytest tests/test_cli.py -q` -> `69 passed in 0.97s`
- Last accepted full validation: `uv run pytest -q` -> `213 passed in 2.06s`
- `scripts/check-progress-docs.sh` -> passed
- `scripts/git-finalize-check.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Keep the implementation scoped to CLI regression coverage only.
- Preserve current CLI exit codes and stderr behavior for invalid manifests.
- Avoid reopening loader logic unless a tiny command-boundary fix is strictly necessary.

## Next Suggested Step

Claude Code should read `docs/agent/08_IMPLEMENTATION_BRIEF.md` and `docs/agent/12_AGENT_BOARD.md`, implement the tests, run the required checks, and hand back for Codex review.
