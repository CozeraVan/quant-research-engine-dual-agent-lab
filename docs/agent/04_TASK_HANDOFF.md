# Task Handoff

## Current Task

QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001: Recursively audit nested eval/backtest stage manifests from the top-level research-run report manifest.

## Task ID

QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001

## Current Status

REVIEW_PASS. Claude Code reviewed the implementation (acting reviewer, Codex unavailable). `10_REVIEW_REPORT.md` written with PASS verdict. Ready for git finalization.

## Current Owner

CODEX

## Problem Summary

The top-level `research_run_report_manifest` makes a research-run bundle discoverable, but content validation was checking nested `eval/report_manifest.json` and `backtest/report_manifest.json` for existence only. A malformed nested stage manifest, or a valid nested manifest with broken listed artifacts, could escape a top-level research-run audit.

## Implementation Summary

- Added recursive validation gate in `ReportManifest.validate_contents()` for `research_run_report_manifest` kind with `eval_report_manifest` / `backtest_report_manifest` roles.
- Added `_validate_nested_report_manifest()` helper that loads nested manifests and wraps their issues.
- Filtering: `--role run_manifest` skips nested validation; `--role eval_report_manifest` triggers it; unfiltered triggers both.
- Non-research-run report manifests never trigger recursive validation.
- 7 new unit tests + 4 new CLI tests + 1 fixed existing test. Full suite: 814 passed (+11).

## Handoff To Codex

Read `docs/agent/09_CODING_HANDOFF.md` for the full implementation handoff. Review the diff, run validation, and write `10_REVIEW_REPORT.md`.

## Codex Finding

```bash
uv run qre report-files <tmp>/report_manifest.json --check-exists --validate-contents
# now validates nested eval/backtest report_manifest.json contents recursively
```
