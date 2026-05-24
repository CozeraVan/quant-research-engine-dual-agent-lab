# Implementation Brief

## Task ID

QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Sync user-facing and module documentation with the finalized research-run report-manifest audit contract.

Recent slices completed the runtime/test contract for top-level `research_run_report_manifest` audits:

- `run_manifest` content validation for `research_run_manifest.json`
- recursive nested validation for `eval_report_manifest` and `backtest_report_manifest`
- `preflight_report` JSON content validation
- role selector parity across `report-files`, `report-audit`, JSON/text output, and `--require-match`

The remaining gap is documentation: README examples still show only a basic top-level audit and a `run_manifest` role example. Users need the final role-level audit commands and clear expectations about what each role validates.

## Required Behavior

This is a documentation-only task unless Claude Code finds a directly conflicting doc test or link issue.

1. README research-run section
   - Update the `qre research-run` section to document the top-level `report_manifest.json` as the audit entry point for the whole run.
   - Add role-specific examples for:
     - `--role run_manifest`
     - `--role preflight_report`
     - `--role eval_report_manifest`
     - `--role backtest_report_manifest`
   - Show `--require-match` where appropriate.
   - Mention that `report-files --validate-contents` and `report-audit` share the same selector semantics.
   - Mention that `--role run_manifest` does not validate preflight or nested stage manifests; role selectors isolate validation to the selected role.

2. Module docs
   - Update `docs/modules/portfolio_workflow.md` with a concise research-run report-manifest audit subsection.
   - If `docs/modules/portfolio_layer.md` has a relevant report/audit section, add a short pointer there rather than duplicating large content.
   - Do not modify archived legacy docs under `docs/legacy/`.

3. Agent docs
   - Update active agent status docs to reflect that `QRE-RESEARCH-RUN-AUDIT-ROLE-SELECTOR-PARITY-001` is DONE and this docs sync is the active task.
   - Keep blocked data-source tasks blocked; do not imply real benchmark or real ST/risk-warning metadata is complete.

4. Tone and safety
   - Do not describe small smoke or tmp-path tests as strategy performance evidence.
   - Keep examples structural/audit-focused.
   - Do not invent DB table names or credentials.

## Non-Goals

- Do not change runtime code.
- Do not add new report-manifest roles.
- Do not alter CLI exit codes or JSON schemas.
- Do not update legacy archived docs.
- Do not attempt real database-backed research-run execution.

## Suggested Implementation Notes

- Prefer short examples over long prose.
- Keep README examples copy-pasteable.
- Use the existing role names exactly: `run_manifest`, `preflight_report`, `eval_report_manifest`, `backtest_report_manifest`.
- If adding command examples, use the existing README path:
  `outputs/research/bollinger_2024/report_manifest.json`.

## Validation Commands

Run at least:

```bash
scripts/check-progress-docs.sh
git diff --check
rg -n "research-run|research_run_report_manifest|preflight_report|eval_report_manifest|backtest_report_manifest" README.md docs/modules/portfolio_workflow.md docs/modules/portfolio_layer.md
```

If only Markdown/docs changed, full `pytest` is optional. If any code or tests change, run:

```bash
uv run pytest -q
```

Document whether full pytest was skipped because the task was docs-only.
