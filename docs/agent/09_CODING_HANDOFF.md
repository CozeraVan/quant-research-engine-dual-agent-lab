# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001

## Written By

CODEX

## Intended Reviewer

CODEX

## Status

PENDING_IMPLEMENTATION

## Summary

Claude Code should implement `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

The active task is documentation-only unless a directly conflicting doc test or link issue is found. Sync README/module docs with the finalized research-run report-manifest audit contract.

## Implementation Scope

- Update README research-run audit examples.
- Update `docs/modules/portfolio_workflow.md` with the role-level audit contract.
- Add a short pointer in `docs/modules/portfolio_layer.md` if relevant.
- Update active agent docs during handoff.
- Do not edit archived legacy docs.

## Required Validation

Run and record:

```bash
scripts/check-progress-docs.sh
git diff --check
rg -n "research-run|research_run_report_manifest|preflight_report|eval_report_manifest|backtest_report_manifest" README.md docs/modules/portfolio_workflow.md docs/modules/portfolio_layer.md
```

If no code changed, document that full pytest was skipped because this is docs-only. If any code changes, run `uv run pytest -q`.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
