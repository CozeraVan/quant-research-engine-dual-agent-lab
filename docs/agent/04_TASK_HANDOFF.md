# Task Handoff

## Current Task

QRE-RESEARCH-RUN-AUDIT-ROLE-SELECTOR-PARITY-001: Lock CLI role selector parity for top-level `research_run_report_manifest` audits across `report-files`, `report-audit`, JSON/text output, and `--require-match`.

## Task ID

QRE-RESEARCH-RUN-AUDIT-ROLE-SELECTOR-PARITY-001

## Current Status

DONE. Implemented by Claude Code (10 CLI tests, no runtime changes). Reviewed PASS by Codex. Ready for git finalization.

## Current Owner

CODEX (git finalization)

## Problem Summary

Research-run root report-manifest content validation now covers `run_manifest`, `preflight_report`, `eval_report_manifest`, and `backtest_report_manifest`. The remaining hardening gap was CLI selector parity: `report-files` and `report-audit` should behave consistently for these roles across JSON/text output, `--require-match`, and no-match cases.

## Implementation Summary

All 10 required CLI regression tests pass against the existing implementation without any runtime changes:
- `backtest_report_manifest` selectors surface nested issues via both `report-audit` and `report-files`
- Sibling role isolation confirmed: `eval_report_manifest` ignores malformed backtest, `preflight_report` ignores malformed nested stages, `run_manifest` ignores both
- `--require-match` parity: matching roles exit 0, no-match roles exit 2 with JSON `matched_files=0` or text diagnostic

## Review Summary

Codex review PASS. `10_REVIEW_REPORT.md` confirms all 10 brief requirements covered, all locked requirements respected, no required fixes.

## Codex Finding

```bash
uv run qre report-audit <run>/report_manifest.json --role <role> --require-match --json
# selector behavior is now locked for run_manifest, preflight_report, eval_report_manifest, and backtest_report_manifest
```
