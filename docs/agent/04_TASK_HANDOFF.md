# Task Handoff

## Current Task

Validate report manifest schema version.

## Task ID

QRE-REPORT-MANIFEST-SCHEMA-VALIDATION-001

## Current Status

Planned by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Previous task `QRE-REPORT-MANIFEST-SCHEMA-DOCS-001` was reviewed and committed locally as `19d9ae4 docs: document report manifest schema version`.
- New brief prepared for explicit manifest schema-version validation.

## In Progress

Claude Code should implement:

- `QRE-REPORT-MANIFEST-SCHEMA-VALIDATION-001`

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

- Do not reject old manifests without `schema_version`.
- Do not change valid-manifest output behavior.
- Keep this focused on manifest loading and validation.

## Next Suggested Step

Claude Code implements the brief, updates `09/04/05/11/12`, and hands back with:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
