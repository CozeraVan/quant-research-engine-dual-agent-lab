# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001

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

The top-level `research_run_report_manifest` now makes a research-run bundle discoverable, but validation currently checks nested `eval/report_manifest.json` and `backtest/report_manifest.json` for existence only. The next slice should recursively validate those stage report manifests when validating or auditing the root research-run manifest.
