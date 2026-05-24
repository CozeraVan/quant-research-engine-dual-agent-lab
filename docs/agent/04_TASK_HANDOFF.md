# Task Handoff

## Current Task

QRE-RESEARCH-RUN-ROOT-REPORT-MANIFEST-001: Add a top-level report manifest entry point for completed `qre research-run` bundles.

## Task ID

QRE-RESEARCH-RUN-ROOT-REPORT-MANIFEST-001

## Current Status

READY_FOR_CLAUDE. Codex prepared `08_IMPLEMENTATION_BRIEF.md` for the next implementation slice.

## Current Owner

CLAUDE_CODE

## Problem Summary

`qre research-run` now writes stage artifacts, but the whole run directory still lacks a top-level `report_manifest.json` that existing `qre report-files` / `qre report-audit` can consume. A direct probe against `research_run_manifest.json` exits `2` because it is a run manifest, not a report manifest. README examples also still show the stale root-level `preflight_report.json` path instead of `preflight/preflight_report.json`.

## Handoff To Claude Code

Read:

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Implement the brief exactly. Do not change research semantics or make `research_run_manifest.json` masquerade as a report manifest. Add a top-level research-run report manifest and tests proving the existing report discovery/audit commands work on it.

## Codex Probe Evidence

```bash
uv run qre report-files <tmp>/research_run_manifest.json
# manifest kind must be one of: batch_backtest_report_manifest, evaluation_report_manifest, shared_cash_backtest_report_manifest, strategy_smoke_report_manifest
# exit=2
```
