# Implementation Brief

## Task ID

QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Make `qre report-files <research-run>/report_manifest.json --validate-contents` and `qre report-audit <research-run>/report_manifest.json` validate the nested stage report manifests, not only their existence.

The previous task added a top-level `research_run_report_manifest` so operators can discover the whole run directory. That closes the entry-point gap, but the current validation still treats `eval/report_manifest.json` and `backtest/report_manifest.json` as ordinary JSON files with unknown roles. As a result, a top-level audit can pass even if a nested stage manifest is malformed or if its listed artifacts are broken.

This task should add recursive validation for stage report manifests referenced by a `research_run_report_manifest`, while preserving existing behavior for other report manifest kinds.

## Evidence From Codex Review

Accepted behavior from `QRE-RESEARCH-RUN-ROOT-REPORT-MANIFEST-001`:

```bash
uv run qre report-files <run>/report_manifest.json --check-exists --validate-contents
# exits 0 when root entries exist and research_run_manifest validates

uv run qre report-audit <run>/report_manifest.json --role run_manifest --require-match
# exits 0
```

Remaining gap:

- Root manifest entries with role `eval_report_manifest` or `backtest_report_manifest` are checked for existence only.
- `ReportManifest.validate_contents()` does not recursively parse those nested report manifests.
- A malformed `eval/report_manifest.json` or a valid nested stage manifest with missing listed files can escape a top-level research-run audit.

## Required Behavior

1. Recursive stage-manifest validation
   - When `self.kind == "research_run_report_manifest"`, `ReportManifest.validate_contents()` should recursively validate entries with roles:
     - `eval_report_manifest`
     - `backtest_report_manifest`
   - For each matched nested stage manifest:
     - Load it with `ReportManifest.from_path(path)`.
     - Run its `validate_contents()` with no role/symbol/window/group_by/window_size filter unless a safer scoped behavior is clearly justified.
     - Convert nested issues into top-level `ReportValidationIssue` entries.
   - If the nested manifest itself cannot be parsed by `ReportManifest.from_path()`, return a top-level issue instead of raising to the CLI.

2. Issue shape and diagnostics
   - Preserve existing `ReportValidationIssue` dataclass.
   - Use stable codes such as:
     - `invalid_nested_report_manifest`
     - `nested_report_manifest_issue`
   - Include enough context in `message` to identify the parent entry key and nested issue key/code/message.
   - `path` should point to the nested manifest or the nested problematic artifact path, whichever is more useful and consistent with existing diagnostics.

3. Filtering semantics
   - `report-audit <run>/report_manifest.json --role run_manifest` should continue to validate only the run manifest and should not recursively audit stage manifests.
   - `report-audit <run>/report_manifest.json --role eval_report_manifest` should validate the eval nested manifest and its listed artifacts.
   - Unfiltered `report-audit <run>/report_manifest.json` should validate all root entries and recursively validate eval/backtest stage manifests.
   - `report-files <run>/report_manifest.json --validate-contents` should surface the same recursive validation issues as `report-audit`.

4. Compatibility
   - Do not change existing validation behavior for `batch_backtest_report_manifest`, `shared_cash_backtest_report_manifest`, `evaluation_report_manifest`, or `strategy_smoke_report_manifest` except through shared helper refactors that preserve outputs.
   - Do not recursively validate arbitrary report manifest files outside `research_run_report_manifest` in this slice.
   - Do not change report manifest schema shape.

5. Documentation and state
   - Update README or module docs only if existing wording would become misleading.
   - Update `09_CODING_HANDOFF.md` with exact validation results and any database-backed validation gap.

## Non-Goals

- Do not add database writes.
- Do not change research-run execution, evaluation math, backtest semantics, or artifact layout.
- Do not add a new CLI flag unless necessary; recursive validation should be the default content-validation behavior for research-run root manifests.
- Do not implement real benchmark wiring, regime classification, or time-varying suspension/ST/risk-warning metadata.
- Do not expand recursive validation beyond eval/backtest stage report manifests unless needed to satisfy this brief.

## Suggested Implementation Notes

- Add a small private helper in `portfolio/report_manifest.py`, for example `_validate_nested_report_manifest(parent_entry, path) -> list[ReportValidationIssue]`.
- Call it inside `ReportManifest.validate_contents()` after the file existence check and before role-specific CSV/JSON validation, gated by `self.kind == "research_run_report_manifest"` and `entry.role in {"eval_report_manifest", "backtest_report_manifest"}`.
- Avoid infinite recursion by only recursing for the root research-run kind and not for nested manifests.
- Tests can build minimal nested evaluation/backtest manifests in temporary directories without running a database-backed research run.

## Tests Required

Add or update tests for:

1. Root research-run manifest with valid nested eval/backtest report manifests validates cleanly.
2. Root research-run manifest with malformed nested eval report manifest returns `invalid_nested_report_manifest` through `ReportManifest.validate_contents()`.
3. Root research-run manifest with valid nested eval manifest that points to a missing artifact returns a nested validation issue through the root manifest.
4. `qre report-audit <run>/report_manifest.json --json` includes recursive nested issue details.
5. `qre report-files <run>/report_manifest.json --validate-contents --json` includes recursive nested issue details.
6. `--role run_manifest` does not trigger nested stage validation.
7. `--role eval_report_manifest` does trigger validation of the eval nested manifest.
8. Existing non-research-run manifest validation tests still pass.

## Validation Commands

Run at least:

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q -k "nested_report_manifest or research_run_report_manifest or report_audit"
uv run pytest tests/test_research_run.py tests/test_cli.py -q -k "research_run or research_run_report_manifest"
uv run pytest tests/test_portfolio_report_manifest.py tests/test_portfolio_io.py -q
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
