# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-AUDIT-ROLE-SELECTOR-PARITY-001

## Written By

CODEX

## Intended Reviewer

CODEX

## Status

PENDING_IMPLEMENTATION

## Summary

Claude Code should implement `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

The active task is to lock CLI role selector parity for top-level `research_run_report_manifest` audits across `report-files` and `report-audit`, especially for `--role`, `--require-match`, JSON output, text output, and no-match behavior.

## Implementation Scope

- Add research-run-specific CLI regression tests for selector parity.
- Make narrow CLI/filtering fixes only if those tests expose a bug.
- Do not change execution semantics, DB access, or report manifest schema.

## Required Validation

Run and record:

```bash
uv run pytest tests/test_cli.py -q -k "research_run_report_manifest or report_audit or report_files or require_match"
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q -k "research_run_report_manifest or preflight_report or nested_report_manifest or require_match"
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
