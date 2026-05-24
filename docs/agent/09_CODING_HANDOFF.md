# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-AUDIT-ROLE-SELECTOR-PARITY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Summary of Behavior Changes

This is a test-only task. No runtime code was changed. All 10 required CLI regression tests pass against the existing implementation, confirming that role selector parity is already locked for top-level `research_run_report_manifest` audits across `report-files` and `report-audit`.

### What Was Verified

1. **`backtest_report_manifest` role selectors** — Both `report-audit --json` and `report-files --validate-contents --json` with `--role backtest_report_manifest` correctly surface nested manifest validation issues.
2. **Sibling role isolation** — `--role eval_report_manifest` does not validate a malformed sibling `backtest_report_manifest`; `--role preflight_report` does not validate malformed nested stage manifests; `--role run_manifest` does not validate malformed preflight or nested stage manifests.
3. **`--require-match` parity** — `--role preflight_report --require-match` exits 0 with `matched_files=1` for a valid preflight. Non-existent role selectors exit 2 with `matched_files=0` in JSON mode, and emit "no manifest entries matched filters" diagnostic in text mode across both `report-files` and `report-audit`.

## Files Changed

- `tests/test_cli.py` — Added 10 CLI regression tests before `_FakeStore` class

## Tests Added

All 10 new tests in `test_cli.py`:

1. `test_cli_report_audit_json_role_backtest_surfaces_nested_issue` — `report-audit --json --role backtest_report_manifest` surfaces `invalid_nested_report_manifest`
2. `test_cli_report_files_json_role_backtest_surfaces_nested_issue` — `report-files --validate-contents --json --role backtest_report_manifest` surfaces nested issue on stderr
3. `test_cli_report_audit_json_role_eval_does_not_validate_sibling_backtest` — `--role eval_report_manifest` exits 0 with valid eval, ignores malformed sibling backtest
4. `test_cli_report_audit_json_role_preflight_does_not_validate_nested_stage` — `--role preflight_report` exits 0 with valid preflight, ignores malformed nested eval
5. `test_cli_report_audit_json_role_run_manifest_does_not_validate_preflight_or_nested` — `--role run_manifest` exits 0 with valid run_manifest, ignores malformed preflight and nested stage
6. `test_cli_report_files_json_role_preflight_require_match_exits_0` — `report-files --json --role preflight_report --require-match` exits 0, `matched_files=1`
7. `test_cli_report_files_json_role_missing_require_match_exits_2` — `report-files --json --role missing_role --require-match` exits 2, `matched_files=0`
8. `test_cli_report_audit_json_role_missing_require_match_exits_2` — `report-audit --json --role missing_role --require-match` exits 2, `matched_files=0`
9. `test_cli_report_files_text_role_missing_require_match_exits_2` — text-mode `report-files --role missing_role --require-match` exits 2 with diagnostic
10. `test_cli_report_audit_text_role_missing_require_match_exits_2` — text-mode `report-audit --role missing_role --require-match` exits 2 with diagnostic

## Validation Results

```bash
# Full suite
uv run pytest -q
# 836 passed, 2 warnings in 12.36s (826 → 836: +10 tests)

# Targeted: research_run + report_audit + report_files + require_match
uv run pytest tests/test_cli.py -q -k "research_run_report_manifest or report_audit or report_files or require_match"
# 128 passed, 173 deselected in 1.06s

# Targeted: research_run_report_manifest + preflight + nested + require_match
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q -k "research_run_report_manifest or preflight_report or nested_report_manifest or require_match"
# 49 passed, 351 deselected in 0.49s

# Diff check
git diff --check
# clean

# Progress docs check
scripts/check-progress-docs.sh
# passed (after doc updates)
```

## Known Validation Gaps

- No database-backed `qre research-run` end-to-end test was run (no DB configured). The role selector parity is validated at the CLI/report-manifest layer through tmp_path-based tests.
- No runtime code changes were needed; all selector behavior was already correct.

## Deviations from Brief

None. All 10 required test categories are covered. No runtime changes needed — the implementation is test-only as anticipated by the brief.

## Next Agent State

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
