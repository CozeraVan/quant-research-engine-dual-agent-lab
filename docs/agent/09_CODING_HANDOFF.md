# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-AUDIT-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Summary of Behavior Changes

`ReportManifest.validate_contents()` now validates the JSON content of `preflight_report` entries when `self.kind == "research_run_report_manifest"`. Previously these entries were checked for existence only; now the `preflight/preflight_report.json` payload is parsed and validated for required fields and types.

### What Changed

1. **`report_manifest.py`: Preflight validation gate** — Inside `validate_contents()`, after the nested manifest check, entries with role `preflight_report` in a `research_run_report_manifest` are routed to `_validate_preflight_report()`.

2. **`report_manifest.py`: New `_validate_preflight_report()` helper** — Parses the preflight JSON, checks:
   - Valid JSON (`invalid_preflight_report_json`)
   - Object root (`invalid_preflight_report_object`)
   - `status` must be a non-empty string (`missing_preflight_report_field` / `invalid_preflight_report_field`)
   - `checks` if present must be a list (`invalid_preflight_report_field`)
   - `missing_factor_requests` if present must be a list (`invalid_preflight_report_field`)

3. **Filtering semantics**:
   - `--role preflight_report` validates preflight content
   - `--role run_manifest` skips preflight validation
   - Unfiltered audit validates preflight along with run manifest and nested stage manifests

4. **Compatibility** — Non-research-run report manifest kinds never trigger preflight content validation.

## Files Changed

- `src/quant_research_engine/portfolio/report_manifest.py` — Added preflight validation gate and `_validate_preflight_report()` helper

## Tests Added or Updated

### Unit tests (`test_portfolio_report_manifest.py`) — 9 new tests

1. `test_research_run_report_manifest_valid_preflight_passes` — valid `{"status": "ok"}` passes
2. `test_research_run_report_manifest_preflight_invalid_json` — `invalid_preflight_report_json`
3. `test_research_run_report_manifest_preflight_non_object` — `invalid_preflight_report_object`
4. `test_research_run_report_manifest_preflight_missing_status` — `missing_preflight_report_field`
5. `test_research_run_report_manifest_preflight_non_string_status` — `invalid_preflight_report_field`
6. `test_research_run_report_manifest_preflight_non_list_checks` — `invalid_preflight_report_field`
7. `test_research_run_report_manifest_preflight_non_list_missing_factor_requests` — `invalid_preflight_report_field`
8. `test_role_preflight_report_triggers_validation` — `--role preflight_report` triggers validation
9. `test_non_research_run_manifest_preflight_no_validation` — non-research-run manifest does not trigger

### CLI tests (`test_cli.py`) — 3 new tests

1. `test_cli_report_audit_json_role_preflight_report_surfaces_issue` — `report-audit --json --role preflight_report` surfaces `invalid_preflight_report_json`
2. `test_cli_report_files_json_validate_contents_role_preflight_surfaces_issue` — `report-files --validate-contents --json --role preflight_report` surfaces issue on stderr
3. `test_cli_report_audit_role_run_manifest_skips_preflight_validation` — `--role run_manifest` exits 0 despite malformed preflight

## Validation Results

```bash
# Full suite
uv run pytest -q
# 826 passed, 2 warnings in 14.97s (814 → 826: +12 tests)

# Targeted: preflight + research-run manifest tests
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q -k "preflight_report or research_run_report_manifest or report_audit"
# 73 passed, 317 deselected in 1.53s

# Targeted: research_run + CLI
uv run pytest tests/test_research_run.py tests/test_cli.py -q -k "research_run or research_run_report_manifest"
# 31 passed, 284 deselected in 0.51s

# Targeted: portfolio report manifest + io
uv run pytest tests/test_portfolio_report_manifest.py tests/test_portfolio_io.py -q
# 123 passed in 6.20s

# Diff check
git diff --check
# clean
```

## Known Validation Gaps

- No database-backed `qre research-run` end-to-end test was run (no DB configured). The preflight validation targets only the report manifest layer, which is fully covered by the tmp_path-based tests.

## Deviations from Brief

None. All 11 required test categories from the brief are covered.

## Next Agent State

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
