# Task Handoff

## Current Task

Add CLI malformed-manifest regression coverage.

## Task ID

QRE-REPORT-CLI-INVALID-MANIFEST-001

## Current Status

Planned by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Previous task `QRE-REPORT-MANIFEST-ENTRY-VALIDATION-001` was reviewed and committed locally as `feab301 feat: validate report manifest file entries`.
- New brief prepared for CLI malformed-manifest regression tests.

## In Progress

Claude Code should implement:

- `QRE-REPORT-CLI-INVALID-MANIFEST-001`

Implementation source of truth:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`

## Modified Files For Review

None yet. Expected files are listed in `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

## Validation

Required validation for the next implementation:

- `uv run pytest tests/test_cli.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Known Risks

- Do not change valid-manifest CLI behavior.
- Keep this task narrow; prefer tests-only unless a tiny CLI error-path fix is necessary.

## Next Suggested Step

Claude Code implements the brief, updates `09/04/05/11/12`, and hands back with:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
