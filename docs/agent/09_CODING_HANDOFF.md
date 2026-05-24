# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Summary of Behavior Changes

This is a documentation-only task. No runtime code, tests, or schemas were changed.

### What Was Documented

1. **README section 10 (研究流程编排)** — Expanded with role-specific audit examples for `run_manifest`, `preflight_report`, `eval_report_manifest`, and `backtest_report_manifest`. Added a "按角色审计" subsection explaining selector isolation and `--require-match` parity. Added a "严格匹配与批量发现" subsection with JSON/text `--require-match` examples.

2. **`docs/modules/portfolio_workflow.md`** — Added a "Implemented research-run report-manifest audit contract" subsection describing the four role entries, their validation triggers, selector isolation rules, `--require-match` semantics, and the research-run-specific guard (non-research-run kinds do not trigger nested/preflight validation).

3. **`docs/modules/portfolio_layer.md`** — Added a "Report-Manifest Audit" section with a short pointer to the workflow doc and README for research-run audit commands.

## Files Changed

- `README.md` — Expanded research-run audit section (section 10)
- `docs/modules/portfolio_workflow.md` — Added research-run audit contract subsection
- `docs/modules/portfolio_layer.md` — Added report-manifest audit pointer section

## Validation Results

```bash
# Full suite
uv run pytest -q
# 836 passed, 2 warnings in 12.42s (unchanged — docs only, ran for safety)

# Progress docs check
scripts/check-progress-docs.sh
# passed

# Diff check
git diff --check
# clean

# Content coverage
rg -n "research-run|research_run_report_manifest|preflight_report|eval_report_manifest|backtest_report_manifest" README.md docs/modules/portfolio_workflow.md docs/modules/portfolio_layer.md
# README: 18 matches (was 6)
# portfolio_workflow.md: 14 matches (was 0)
# portfolio_layer.md: 1 match (was 0)
```

## Deviations from Brief

None. All required documentation areas covered. No runtime/schema changes. No legacy-doc edits.

## Next Agent State

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
