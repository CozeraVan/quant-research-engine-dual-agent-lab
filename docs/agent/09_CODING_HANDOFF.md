# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-AUDIT-001

## Written By

PENDING_CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

PENDING_IMPLEMENTATION

## Objective

Claude Code should implement `docs/agent/08_IMPLEMENTATION_BRIEF.md`, then replace this file with the implementation handoff.

## Required Handoff Contents After Implementation

- Summary of behavior changes.
- Files changed.
- Tests added or updated.
- Validation commands and exact results.
- Known validation gaps, especially whether a real database-backed `qre research-run` was unavailable.
- Any blockers or deviations from the brief.

## Current Codex Finding

The top-level research-run audit now validates run manifests and recursively validates nested eval/backtest report manifests, but it still checks `preflight/preflight_report.json` only for existence. This slice should add narrow JSON content validation for the research-run `preflight_report` role.
