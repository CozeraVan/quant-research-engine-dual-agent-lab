# Task Handoff

## Task ID

QRE-RESEARCH-RUN-AUDIT-ROLE-SELECTOR-PARITY-001

## Current Status

READY_FOR_CLAUDE. Codex reviewed and locally committed `QRE-RESEARCH-RUN-PREFLIGHT-REPORT-AUDIT-001`, then prepared the next implementation brief.

## Current Owner

CLAUDE_CODE

## Problem Summary

Research-run root report-manifest content validation now covers `run_manifest`, `preflight_report`, `eval_report_manifest`, and `backtest_report_manifest`. The remaining hardening gap is CLI selector parity: `report-files` and `report-audit` should behave consistently for these roles across JSON/text output, `--require-match`, and no-match cases.

## Handoff To Claude Code

Read:

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Implement the brief exactly. Prefer regression tests first. If all required behavior already works, this task may be test-only plus handoff-doc updates.

## Codex Finding

```bash
uv run qre report-audit <run>/report_manifest.json --role <role> --require-match --json
# selector behavior should be locked for run_manifest, preflight_report, eval_report_manifest, and backtest_report_manifest
```
