# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-SHAPE-AUDIT-001

## Written By

CODEX

## Intended Reviewer

CODEX

## Status

PENDING_IMPLEMENTATION

## Summary

Claude Code should implement `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

The active task is a narrow report-manifest audit hardening slice: validate accepted `preflight_report.status` values and validate the object shape of `checks[]` entries when auditing a top-level `research_run_report_manifest`.

## Implementation Scope

- Update `src/quant_research_engine/portfolio/report_manifest.py`.
- Add unit and CLI regression tests.
- Do not change preflight execution or serialization.
- Do not add DB-backed tests.

## Required Validation

Run and record:

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q -k "preflight_report or research_run_report_manifest or report_audit"
uv run pytest tests/test_research_run.py tests/test_cli.py -q -k "research_run or research_run_report_manifest"
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
