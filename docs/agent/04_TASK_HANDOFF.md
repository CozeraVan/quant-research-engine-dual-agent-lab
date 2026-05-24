# Task Handoff

## Current Task

QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001: Recursively audit nested eval/backtest stage manifests from the top-level research-run report manifest.

## Task ID

QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001

## Current Status

READY_FOR_CLAUDE. Codex prepared `08_IMPLEMENTATION_BRIEF.md` for the next implementation slice.

## Current Owner

CLAUDE_CODE

## Problem Summary

The top-level `research_run_report_manifest` makes a research-run bundle discoverable, but content validation currently checks nested `eval/report_manifest.json` and `backtest/report_manifest.json` for existence only. A malformed nested stage manifest, or a valid nested manifest with broken listed artifacts, can escape a top-level research-run audit.

## Handoff To Claude Code

Read:

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Implement the brief exactly. Do not change research-run execution semantics or report manifest schema shape. Add recursive validation only for eval/backtest stage report manifests referenced by a top-level `research_run_report_manifest`.

## Codex Finding

```bash
uv run qre report-files <tmp>/report_manifest.json --check-exists --validate-contents
# currently validates root entries and run_manifest, but not nested eval/backtest report manifest contents
```
