# Implementation Brief

## Task ID

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-AUDIT-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Make top-level research-run report audits validate the `preflight/preflight_report.json` payload instead of only checking that the file exists.

The previous slice added recursive validation for nested eval/backtest stage report manifests. The remaining root research-run audit gap is the preflight stage entry: role `preflight_report` currently has no content validation. A malformed or structurally useless preflight JSON can still pass `qre report-audit <run>/report_manifest.json` as long as the file exists.

This task should add narrow, schema-light validation for the `preflight_report` role when it appears in a `research_run_report_manifest`.

## Evidence From Codex Review

Accepted behavior from `QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001`:

- `eval_report_manifest` and `backtest_report_manifest` recurse into nested stage report manifests.
- `run_manifest` validates through existing run-manifest validation.
- `preflight_report` still has no content validation beyond existence.

## Required Behavior

1. Preflight report content validation
   - When `self.kind == "research_run_report_manifest"` and `entry.role == "preflight_report"`, `ReportManifest.validate_contents()` should validate the JSON payload.
   - Missing file behavior should remain the existing `missing_file` issue.
   - Invalid JSON should return a structured validation issue instead of raising.
   - Non-object JSON roots should return a structured validation issue.
   - A valid preflight report must contain at least:
     - `status`: string, non-empty.
   - If `checks` exists, it must be a list.
   - If `missing_factor_requests` exists, it must be a list.
   - Do not require all fields from `PreflightReport.to_dict()`; older/fake preflight payloads may be minimal.

2. Issue shape
   - Preserve `ReportValidationIssue`.
   - Use stable codes such as:
     - `invalid_preflight_report_json`
     - `invalid_preflight_report_object`
     - `missing_preflight_report_field`
     - `invalid_preflight_report_field`
   - Messages should include the bad field name and the actual type where useful.

3. Filtering semantics
   - `report-audit <run>/report_manifest.json --role preflight_report` should validate only the preflight report entry.
   - `--role run_manifest` should not validate preflight.
   - Unfiltered root research-run audit should validate run manifest, preflight report, and nested eval/backtest stage manifests.

4. Compatibility
   - Only validate `preflight_report` content for `research_run_report_manifest` roots.
   - Do not apply this validation to smoke-run per-strategy `preflight_report.json` artifacts unless they are listed under a research-run root manifest.
   - Do not change preflight execution or serialization behavior.
   - Do not change report manifest schema shape.

5. Documentation and state
   - Update README or module docs only if existing wording would become misleading.
   - Update `09_CODING_HANDOFF.md` with exact validation results and any database-backed validation gap.

## Non-Goals

- Do not add database writes.
- Do not change preflight checks, statuses, or report generation.
- Do not require every historical preflight field in audits.
- Do not validate nested stage manifests beyond the behavior already added in the prior slice.
- Do not implement real benchmark wiring, regime classification, or time-varying suspension/ST/risk-warning metadata.

## Suggested Implementation Notes

- Add a helper in `portfolio/report_manifest.py`, for example `_validate_preflight_report(entry, path) -> list[ReportValidationIssue]`.
- Gate it inside `ReportManifest.validate_contents()` with `self.kind == "research_run_report_manifest" and entry.role == "preflight_report"` after existence check and before generic JSON handling.
- Keep validation deliberately small: parse JSON object, require `status` string, optional list checks for known list fields.

## Tests Required

Add or update tests for:

1. Valid minimal preflight report `{ "status": "ok" }` passes root research-run validation.
2. Invalid preflight JSON returns `invalid_preflight_report_json`.
3. Non-object preflight JSON returns `invalid_preflight_report_object`.
4. Missing `status` returns `missing_preflight_report_field`.
5. Non-string `status` returns `invalid_preflight_report_field`.
6. Non-list `checks` returns `invalid_preflight_report_field`.
7. Non-list `missing_factor_requests` returns `invalid_preflight_report_field`.
8. `report-audit --role preflight_report --json` surfaces the structured issue.
9. `report-files --validate-contents --json --role preflight_report` surfaces the structured issue.
10. `--role run_manifest` does not validate a malformed preflight report.
11. Non-research-run manifest kinds with role `preflight_report` do not trigger this validation.

## Validation Commands

Run at least:

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q -k "preflight_report or research_run_report_manifest or report_audit"
uv run pytest tests/test_portfolio_report_manifest.py tests/test_portfolio_io.py -q
uv run pytest tests/test_research_run.py tests/test_cli.py -q -k "research_run or research_run_report_manifest"
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

If a real database URL is configured, optionally run a narrow `qre research-run` and then:

```bash
uv run qre report-files <run-dir>/report_manifest.json --check-exists --validate-contents
uv run qre report-audit <run-dir>/report_manifest.json --require-match
```

If no database is configured, document that as a validation gap in `09_CODING_HANDOFF.md`.
