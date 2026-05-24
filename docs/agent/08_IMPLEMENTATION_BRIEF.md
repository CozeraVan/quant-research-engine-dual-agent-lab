# Implementation Brief

## Task ID

QRE-RESEARCH-RUN-AUDIT-ROLE-SELECTOR-PARITY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Lock down CLI role selector parity for top-level `research_run_report_manifest` audits now that `run_manifest`, `preflight_report`, `eval_report_manifest`, and `backtest_report_manifest` all have content-validation paths.

The previous slices added root run-manifest validation, recursive nested eval/backtest stage manifest validation, and preflight report content validation. The next risk is selector drift: `report-files` and `report-audit` should behave consistently for these roles across JSON/text output, `--require-match`, and no-match cases.

## Evidence From Codex Review

Accepted baseline:

- `run_manifest` validates the research-run manifest payload.
- `preflight_report` validates preflight JSON content for `research_run_report_manifest` only.
- `eval_report_manifest` and `backtest_report_manifest` recursively validate nested stage report manifests.
- Existing tests cover some selector paths, but CLI parity is not locked for every root research-run role and no-match mode.

## Required Behavior

1. Role selector parity
   - `qre report-files <root>/report_manifest.json --role <role>` should select only files with that exact role.
   - `qre report-audit <root>/report_manifest.json --role <role>` should audit only files with that exact role.
   - The same selector semantics should hold for:
     - `run_manifest`
     - `preflight_report`
     - `eval_report_manifest`
     - `backtest_report_manifest`

2. Validation trigger parity
   - `--role preflight_report --validate-contents` should trigger preflight validation through `report-files`.
   - `--role preflight_report` should trigger preflight validation through `report-audit`.
   - `--role eval_report_manifest` and `--role backtest_report_manifest` should trigger nested report-manifest validation through both CLI surfaces when content validation is active.
   - `--role run_manifest` should not validate preflight or nested stage manifests.

3. `--require-match` parity
   - Matching role selectors with `--require-match` should exit 0 when selected files validate.
   - No-match role selectors with `--require-match` should exit 2.
   - JSON no-match output should include `matched_files: 0` and a stable no-match error/issue shape consistent with existing CLI behavior.
   - Text no-match output should include a clear no-match diagnostic and should not report unrelated validation issues.

4. No unintended validation side effects
   - A no-match selector must not validate unrelated malformed files.
   - `--role run_manifest` must not validate malformed `preflight_report` or nested stage manifests.
   - `--role preflight_report` must not validate malformed nested stage manifests.
   - `--role eval_report_manifest` must not validate malformed preflight or backtest stage manifests.
   - `--role backtest_report_manifest` must not validate malformed preflight or eval stage manifests.

## Non-Goals

- Do not change report manifest schema.
- Do not change preflight, eval, backtest, or research-run execution.
- Do not introduce broad schema validation for stage report manifests beyond current nested manifest validation.
- Do not alter database access or add DB-backed tests.
- Do not rewrite unrelated CLI filtering code unless a parity bug requires a narrow fix.

## Suggested Implementation Notes

- Start by adding tests that express the CLI contract. If all tests already pass, the implementation may be test-only plus documentation/handoff updates.
- Prefer helper fixtures/builders in `tests/test_cli.py` if repeated research-run root manifests become noisy.
- Preserve existing exit-code and output conventions; this task should lock behavior, not invent a new response contract.

## Tests Required

Add or update tests for:

1. `report-audit --json --role backtest_report_manifest` surfaces a nested manifest validation issue.
2. `report-files --validate-contents --json --role backtest_report_manifest` surfaces a nested manifest validation issue.
3. `report-audit --json --role eval_report_manifest` does not validate a malformed sibling `backtest_report_manifest`.
4. `report-audit --json --role preflight_report` does not validate malformed nested stage manifests.
5. `report-audit --json --role run_manifest` does not validate malformed preflight or nested stage manifests.
6. `report-files --json --role preflight_report --require-match` exits 0 and reports `matched_files == 1` for a valid preflight report.
7. `report-files --json --role missing_role --require-match` exits 2 and reports `matched_files == 0`.
8. `report-audit --json --role missing_role --require-match` exits 2 and reports `matched_files == 0`.
9. Text-mode `report-files --role missing_role --require-match` exits 2 with a clear no-match diagnostic.
10. Text-mode `report-audit --role missing_role --require-match` exits 2 with a clear no-match diagnostic.

If these behaviors are already fully covered under existing generic manifest tests, add research-run-specific regression tests for the gaps rather than duplicating identical generic cases.

## Validation Commands

Run at least:

```bash
uv run pytest tests/test_cli.py -q -k "research_run_report_manifest or report_audit or report_files or require_match"
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q -k "research_run_report_manifest or preflight_report or nested_report_manifest or require_match"
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

Document if no database-backed `qre research-run` smoke is run; this task should remain CLI/tmp-path focused.
