# Coding Handoff

## Task ID

QRE-EVAL-METADATA-GROUP-SUMMARY-REGRESSION-001

## Written By

PENDING_CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Pending implementation.

## Implementation Notes

Claude Code should implement from `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

Expected result:

- `EvaluationRequest` accepts optional grouping columns.
- `EvaluationResult` exposes `group_summary`.
- The evaluation engine builds grouped event summaries from existing research-frame columns.
- `qre eval-config --group-by ...` prints `group_summary` when requested.

## Files Changed

Pending.

## Validation Results

Pending.

## Constraints

- Preserve existing evaluation behavior when grouping is omitted.
- Use only columns already present in the research frame.
- Keep data access read-only.
- Do not compute technical indicators inside QRE.
- Do not push.

## Git State

- Branch: `master`
- Previous local checkpoint: `dea224a`
- Current task is ready for Claude Code implementation.
