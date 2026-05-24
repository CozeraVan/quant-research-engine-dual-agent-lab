# Implementation Brief

## Task ID

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-SHAPE-AUDIT-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Harden top-level research-run preflight report content validation by checking the shape of `checks[]` entries and accepted status values.

The current `research_run_report_manifest` audit validates that `preflight_report` is JSON, the root is an object, `status` is a non-empty string, and optional `checks` / `missing_factor_requests` fields are lists. This still allows structurally useless preflight reports such as:

```json
{"status": "maybe", "checks": [123]}
```

The real `PreflightReport.to_dict()` emits `checks` as a list of objects with `name`, `status`, and `message` string fields. This task should add narrow shape validation for that already-emitted structure without requiring every historical preflight field.

## Required Behavior

1. Status validation
   - `status` remains required.
   - `status` must be a string and one of: `ok`, `warning`, `error`.
   - Missing status should continue to return `missing_preflight_report_field`.
   - Non-string or unsupported status should return `invalid_preflight_report_field`.

2. `checks` item validation
   - If `checks` is present, it must still be a list.
   - Each `checks[]` item must be an object.
   - Each check object must contain:
     - `name`: non-empty string
     - `status`: string in `ok`, `warning`, `error`
     - `message`: string
   - Invalid check items should return structured `ReportValidationIssue` entries with code `invalid_preflight_report_check`.
   - Missing required check fields should return `missing_preflight_report_check_field`.
   - Messages should include the field name and list index where useful.

3. `missing_factor_requests` remains list-only
   - Keep current behavior: if present, it must be a list.
   - Do not validate each missing-factor request item in this slice.

4. Scope guards
   - Validation still applies only when `self.kind == "research_run_report_manifest"` and `entry.role == "preflight_report"`.
   - Non-research-run manifest kinds must remain unaffected.
   - Role filtering semantics must remain unchanged.

## Non-Goals

- Do not require every field from `PreflightReport.to_dict()`.
- Do not validate `factor_coverages`, universe fields, benchmark fields, or fallback fake-report fields.
- Do not validate `missing_factor_requests[]` item schema in this slice.
- Do not change preflight execution, serialization, or research-run orchestration.
- Do not add DB-backed tests.

## Suggested Implementation Notes

- Add helper functions near `_validate_preflight_report()` if that keeps the code readable.
- Prefer stable, specific issue codes for check item errors:
  - `invalid_preflight_report_check`
  - `missing_preflight_report_check_field`
- Existing `invalid_preflight_report_field` should remain for root-level field type/status errors.
- Keep existing minimal valid payloads passing when appropriate:
  - `{"status": "ok"}`
  - `{"status": "warning", "checks": []}`

## Tests Required

Add or update tests for:

1. `{"status": "ok"}` still passes.
2. `{"status": "warning", "checks": []}` passes.
3. Unsupported root status such as `"maybe"` returns `invalid_preflight_report_field`.
4. `checks` item that is not an object returns `invalid_preflight_report_check`.
5. Check item missing `name` returns `missing_preflight_report_check_field`.
6. Check item with empty/non-string `name` returns `invalid_preflight_report_check`.
7. Check item missing `status` returns `missing_preflight_report_check_field`.
8. Check item with unsupported `status` returns `invalid_preflight_report_check`.
9. Check item missing `message` returns `missing_preflight_report_check_field`.
10. Check item with non-string `message` returns `invalid_preflight_report_check`.
11. CLI `report-audit --json --role preflight_report` surfaces a check-item issue.
12. Non-research-run manifest kinds with role `preflight_report` still do not trigger this validation.

## Validation Commands

Run at least:

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q -k "preflight_report or research_run_report_manifest or report_audit"
uv run pytest tests/test_research_run.py tests/test_cli.py -q -k "research_run or research_run_report_manifest"
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

Document that no DB-backed `qre research-run` smoke was run unless a suitable DB URL is already configured.
