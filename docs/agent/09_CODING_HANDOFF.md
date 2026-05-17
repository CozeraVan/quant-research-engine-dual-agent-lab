# Coding Handoff

## Task ID

QRE-REPORT-AUDIT-FAILED-ORDERS-SCHEMA-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Implemented

Not started.

## Modified Files

- None yet.

## Not Implemented

- Stable `failed_orders.csv` headers for empty outputs.
- Failed-order CSV content validation in report audit.
- Related IO and CLI tests.

## Deviations from Brief

None yet.

## Validation Commands Run

Not run. Implementation has not started.

## Validation Results

Not applicable.

## Known Risks

- The brief intentionally keeps required failed-order columns minimal to avoid unnecessary report compatibility breakage.
- Single-symbol and shared-cash failed-order outputs have slightly different optional fields.

## Questions for Reviewer

- None yet.

## Git Status at Handoff

Implementation has not started. Claude Code should record `git status --short` here after implementation.

## Next Suggested Step

Claude Code should implement strictly from:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`

## Next Agent State After Implementation

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
