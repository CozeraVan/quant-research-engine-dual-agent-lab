# Task Handoff

## Current Task

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-AUDIT-001: Validate research-run preflight report JSON content during top-level report audits.

## Task ID

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-AUDIT-001

## Current Status

READY_FOR_CLAUDE. Codex reviewed `QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001` post-commit, accepted it, and prepared the next implementation brief.

## Current Owner

CLAUDE_CODE

## Problem Summary

The top-level `research_run_report_manifest` now validates run manifests and recursively validates nested eval/backtest stage report manifests. The remaining root audit gap is `preflight/preflight_report.json`: it is still checked only for existence, so malformed or structurally useless preflight JSON can pass top-level audit.

## Handoff To Claude Code

Read:

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Implement the brief exactly. Do not change preflight execution semantics or report manifest schema shape. Add narrow JSON content validation only for `preflight_report` entries referenced by a top-level `research_run_report_manifest`.

## Codex Finding

```bash
uv run qre report-files <tmp>/report_manifest.json --check-exists --validate-contents
# currently validates root entries, run_manifest, and nested eval/backtest manifests, but not preflight report content
```
