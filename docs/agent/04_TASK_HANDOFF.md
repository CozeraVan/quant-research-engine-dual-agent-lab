# Task Handoff

## Task ID

QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001

## Current Status

READY_FOR_CLAUDE. Codex accepted the finalized selector-parity task and prepared the next documentation-sync brief.

## Current Owner

CLAUDE_CODE

## Problem Summary

The runtime and test contract for top-level `research_run_report_manifest` audits is now complete, but README/module docs still present only a minimal audit example. Users need role-level examples and a concise explanation of selector isolation.

## Handoff To Claude Code

Read:

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Implement the brief exactly. This should be documentation-only unless a directly conflicting doc test or link issue appears.

## Codex Finding

```bash
rg -n "preflight_report|eval_report_manifest|backtest_report_manifest" README.md docs/modules/portfolio_workflow.md
# current user-facing docs do not fully describe the finalized research-run audit role contract
```
