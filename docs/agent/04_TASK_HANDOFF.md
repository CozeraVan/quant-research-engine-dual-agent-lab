# Task Handoff

## Current Task

Validate report manifest file entry fields.

## Task ID

QRE-REPORT-MANIFEST-ENTRY-VALIDATION-001

## Current Status

Planned by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Previous task `QRE-REPORT-MANIFEST-SCHEMA-VALIDATION-001` was reviewed and committed locally as `0fca02a feat: validate report manifest schema version`.
- New brief prepared for clear manifest file-entry required-field validation.

## In Progress

Claude Code should implement:

- `QRE-REPORT-MANIFEST-ENTRY-VALIDATION-001`

Implementation source of truth:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`

## Modified Files For Review

None yet. Expected files are listed in `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

## Validation

Required validation for the next implementation:

- `uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Known Risks

- Do not change valid manifest behavior.
- Do not make optional metadata required.
- Keep this focused on manifest file-entry validation.

## Next Suggested Step

Claude Code implements the brief, updates `09/04/05/11/12`, and hands back with:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
