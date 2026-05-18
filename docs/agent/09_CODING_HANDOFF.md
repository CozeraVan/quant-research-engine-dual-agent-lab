# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-SCHEMA-JSON-001

## Written By

CODEX

## Intended Reviewer

CODEX

## Implemented

Not started.

## Modified Files

None yet.

## Not Implemented

- Expose optional `ReportManifest.schema_version`.
- Include `schema_version` in `report-files --json`.
- Include `schema_version` in `report-audit --json`.
- Add focused tests for versioned and old manifests.

## Deviations from Brief

None yet.

## Validation Commands Run

Not run. Implementation has not started.

## Validation Results

Not applicable.

## Known Risks

- Keep old manifests without `schema_version` readable.
- Do not change text-mode CLI output.
- Do not change existing filtering, validation, path resolution, or exit-code behavior.

## Questions for Reviewer

None yet.

## Git Status at Handoff

Implementation has not started. Claude Code should record `git status --short` here after implementation.

## Next Suggested Step

Claude Code should implement strictly from:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`

## Next Agent State After Implementation

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
