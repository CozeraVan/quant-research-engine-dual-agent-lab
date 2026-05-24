# Task Handoff

## Current Task

QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001: Sync README and module docs with the finalized research-run report-manifest audit contract.

## Task ID

QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001

## Current Status

IMPLEMENTED. Claude Code updated README section 10 with role-specific audit examples, added a research-run audit subsection to `portfolio_workflow.md`, and added a report-manifest audit pointer to `portfolio_layer.md`. Full suite unchanged at 836 passed.

## Current Owner

CODEX

## Problem Summary

The runtime and test contract for top-level `research_run_report_manifest` audits was complete, but README/module docs still presented only a minimal audit example. Users needed role-level examples and a concise explanation of selector isolation.

## Implementation Summary

- **README section 10**: Expanded from 1 basic audit example to role-specific examples for `run_manifest`, `preflight_report`, `eval_report_manifest`, `backtest_report_manifest`, plus `--require-match` and `--json` parity examples.
- **`docs/modules/portfolio_workflow.md`**: Added research-run report-manifest audit contract subsection covering the four role entries, validation triggers, selector isolation rules, and research-run-specific guard.
- **`docs/modules/portfolio_layer.md`**: Added short "Report-Manifest Audit" section with pointers to workflow doc and README.

## Handoff To Codex

Read `docs/agent/09_CODING_HANDOFF.md` for the full implementation handoff. Review the diff, run validation, and write `10_REVIEW_REPORT.md`.

## Codex Finding

```bash
rg -n "preflight_report|eval_report_manifest|backtest_report_manifest" README.md docs/modules/portfolio_workflow.md docs/modules/portfolio_layer.md
# all four research-run audit roles now documented with usage examples and selector isolation wording
```
