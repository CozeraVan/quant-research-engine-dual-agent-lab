# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Summary of Behavior Changes

`ReportManifest.validate_contents()` now recursively validates nested `eval_report_manifest` and `backtest_report_manifest` entries when `self.kind == "research_run_report_manifest"`. Previously these entries were checked for existence only; now their contents are fully validated through the same `ReportManifest.from_path()` + `validate_contents()` pipeline.

### What Changed

1. **`report_manifest.py`: Recursive validation gate** — Inside `validate_contents()`, after the file-existence check, entries with role `eval_report_manifest` or `backtest_report_manifest` in a `research_run_report_manifest` are routed to `_validate_nested_report_manifest()` instead of falling through to the unknown-role default (which was a no-op).

2. **`report_manifest.py`: New `_validate_nested_report_manifest()` helper** — Loads the nested manifest via `ReportManifest.from_path()`, runs its `validate_contents()`, and wraps nested issues as top-level `ReportValidationIssue` entries with code `nested_report_manifest_issue`. If the nested manifest cannot be parsed, returns `invalid_nested_report_manifest`.

3. **Filtering semantics**:
   - `--role run_manifest` skips nested stage validation (run_manifest validation only)
   - `--role eval_report_manifest` triggers full recursive validation of the eval nested manifest
   - Unfiltered audit triggers recursive validation for both eval and backtest stage manifests
   - `--role backtest_report_manifest` works the same as eval — triggers nested validation

4. **Compatibility** — Non-research-run report manifest kinds (`batch_backtest_report_manifest`, `shared_cash_backtest_report_manifest`, `evaluation_report_manifest`, `strategy_smoke_report_manifest`) never trigger recursive validation, even if they happen to contain entries named `eval_report_manifest`.

## Files Changed

- `src/quant_research_engine/portfolio/report_manifest.py` — Added recursive validation gate in `validate_contents()` and `_validate_nested_report_manifest()` helper
- `tests/test_portfolio_report_manifest.py` — Fixed 1 existing test (valid nested manifests instead of `{}`), added 7 new tests
- `tests/test_cli.py` — Added 4 new CLI regression tests

## Tests Added or Updated

### Unit tests (`test_portfolio_report_manifest.py`)

1. `test_research_run_report_manifest_recursive_validates_nested_eval_manifest` — valid nested eval manifest validates cleanly
2. `test_research_run_report_manifest_recursive_validates_nested_backtest_manifest` — valid nested backtest manifest validates cleanly
3. `test_research_run_report_manifest_reports_invalid_nested_manifest` — malformed nested manifest returns `invalid_nested_report_manifest`
4. `test_research_run_report_manifest_reports_nested_missing_artifact` — valid nested manifest with missing file returns `nested_report_manifest_issue`
5. `test_role_run_manifest_does_not_trigger_nested_validation` — `--role run_manifest` skips nested validation
6. `test_role_eval_report_manifest_triggers_nested_validation` — `--role eval_report_manifest` triggers nested validation
7. `test_non_research_run_manifest_no_recursive_validation` — non-research-run manifest never recurses

Fixed: `test_research_run_report_manifest_with_all_stage_entries` — updated nested manifests from `{}` to valid `{"kind": ..., "files": []}` payloads.

### CLI tests (`test_cli.py`)

1. `test_cli_report_audit_json_includes_nested_issue_details` — `report-audit --json` surfaces `invalid_nested_report_manifest` code
2. `test_cli_report_files_json_validate_contents_includes_nested_issue_details` — `report-files --validate-contents --json` reports nested issues on stderr
3. `test_cli_report_audit_role_run_manifest_skips_nested_validation` — `--role run_manifest` exits 0 despite malformed nested manifest
4. `test_cli_report_audit_role_eval_report_manifest_triggers_nested_validation` — `--role eval_report_manifest` exits 2 on malformed nested manifest

## Validation Results

```bash
# Full suite
uv run pytest -q
# 814 passed, 2 warnings in 13.82s (803 → 814: +11 tests)

# Targeted: nested + research_run manifest tests
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q -k "nested_report_manifest or research_run_report_manifest or report_audit"
# 63 passed, 315 deselected in 1.30s

# Targeted: research_run + CLI
uv run pytest tests/test_research_run.py tests/test_cli.py -q -k "research_run or research_run_report_manifest"
# 31 passed, 281 deselected in 0.43s

# Targeted: portfolio report manifest + io
uv run pytest tests/test_portfolio_report_manifest.py tests/test_portfolio_io.py -q
# 114 passed in 5.68s

# Diff check
git diff --check
# clean

# Progress docs check
scripts/check-progress-docs.sh
# passed
```

## Known Validation Gaps

- No database-backed `qre research-run` end-to-end test was run (no DB configured). The recursive validation targets only the report manifest layer, which is fully covered by the tmp_path-based tests.
- `--role backtest_report_manifest` filtering is not explicitly tested at the CLI level, but the unit test covers the same code path.

## Deviations from Brief

None. All 8 required test categories from the brief are covered.

## Next Agent State

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
