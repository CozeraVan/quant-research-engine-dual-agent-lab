# Task Handoff

## Current Task

Expose report manifest schema version in JSON tooling.

## Task ID

QRE-REPORT-MANIFEST-SCHEMA-JSON-001

## Current Status

Planned by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Previous task `QRE-REPORT-MANIFEST-SCHEMA-VERSION-001` was reviewed and committed locally as `72533bb feat: add report manifest schema version`.
- New brief prepared for exposing optional manifest schema version through helper and JSON CLI output.

## In Progress

Claude Code should implement:

- `QRE-REPORT-MANIFEST-SCHEMA-JSON-001`

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

- Do not make old manifests without `schema_version` invalid.
- Do not change text-mode CLI output.
- Keep JSON field addition additive and deterministic.

## Next Suggested Step

Claude Code implements the brief, updates `09/04/05/11/12`, and hands back with:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
