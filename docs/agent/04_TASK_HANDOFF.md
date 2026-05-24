# Task Handoff

## Task ID

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-SHAPE-AUDIT-001

## Current Status

READY_FOR_CLAUDE. Codex reviewed and locally committed `QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001`, then prepared the next implementation brief.

## Current Owner

CLAUDE_CODE

## Problem Summary

Top-level research-run preflight report auditing now validates that `preflight_report` is JSON, object-rooted, has a non-empty `status`, and has list-shaped optional fields. It still accepts unsupported status values and malformed `checks[]` items, even though real `PreflightReport.to_dict()` emits checks as `{name, status, message}` objects.

## Handoff To Claude Code

Read:

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Implement the brief exactly. Keep the task focused on preflight report audit shape validation. Do not change preflight execution, serialization, or DB access.

## Codex Finding

```json
{"status": "maybe", "checks": [123]}
```

The payload above currently satisfies the root-level preflight audit shape but is not a structurally useful preflight report.
