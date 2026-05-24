# Agent Board

## Current Task ID

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-SHAPE-AUDIT-001

## Current Recipient

CLAUDE_CODE

## Message Type

IMPLEMENTATION_BRIEF_READY

## Sender

CODEX

## Short Message

Codex prepared the next implementation brief. Claude Code should harden top-level research-run `preflight_report` validation for accepted status values and `checks[]` item shape.

## Required Outcome

| Area | Required |
|---|---|
| Root status | `status` must be `ok`, `warning`, or `error` |
| Checks list | `checks`, when present, remains list-only |
| Check items | each check item must be an object with `name`, `status`, `message` |
| Error codes | stable issue codes for invalid/missing check fields |
| Scope guard | only `research_run_report_manifest` + `preflight_report` triggers this validation |
| Tests | unit + CLI regressions for shape errors and compatibility |

## Review Status

PENDING_IMPLEMENTATION

## Evidence

- Previous finalized baseline: `9e00f0a` research-run audit usage documentation; full suite `836 passed, 2 warnings`.
- Codex audit gap: current preflight report validation accepts unsupported status values and malformed `checks[]` items.

## Next Step

Claude Code implements `08_IMPLEMENTATION_BRIEF.md`, then updates `09_CODING_HANDOFF.md` for Codex review.
