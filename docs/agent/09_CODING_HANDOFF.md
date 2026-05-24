# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-ROOT-REPORT-MANIFEST-001

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

## Current Codex Probe

```bash
uv run qre report-files <tmp>/research_run_manifest.json
# manifest kind must be one of: batch_backtest_report_manifest, evaluation_report_manifest, shared_cash_backtest_report_manifest, strategy_smoke_report_manifest
# exit=2
```
