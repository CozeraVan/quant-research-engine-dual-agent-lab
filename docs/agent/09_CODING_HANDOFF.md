# Coding Handoff

## Task ID

QRE-PORTFOLIO-BACKTEST-RUN-MANIFEST-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Reviewed and accepted locally.

## Initial Implementation

- Added `_write_run_manifest()` function to `io.py` — writes `run_manifest.json` with `schema_version`, `kind` (`portfolio_backtest_run_manifest`), `command`, `strategy_path`, `request`, and sorted `artifacts`.
- Added optional `run_request` parameter to `write_single_symbol_result()`, `write_shared_cash_result()`, and `write_batch_result()`.
- Updated `validate_contents()` in `report_manifest.py` to validate `run_manifest` role as a JSON object, alongside `summary`.
- Wired CLI backtest handlers to build safe `run_request` dicts and pass them to the output writers.
- Added `run_manifest` to `_shared_report_paths` and `_batch_report_paths` labels for Markdown summary output.

## Required Fixes Applied (Codex Review Round 1)

- Added `market_profile` to all 3 backtest handler `run_request` dicts (single, batch, shared).
- Added `group_by` and `group_rank_top_n` to batch handler `run_request`.
- Added `benchmark_table`, `benchmark_code`, and `benchmark_value_column` to shared handler `run_request`.
- Updated 3 existing tests to assert the new fields are present in `run_manifest.json`.

## Required Fixes Applied (Codex Review Round 2)

- Added explicit `run_manifest` role case to `_batch_manifest_role()` (was returning `"artifact"`).
- Added explicit `run_manifest` role case to `_shared_manifest_role()` (was relying on fallthrough `return key`).
- Updated 2 existing tests in `test_portfolio_io.py` to assert `role == "run_manifest"` in emitted report manifest entries.
- Added 2 end-to-end tests proving `ReportManifest.validate_contents(role="run_manifest")` passes on emitted report manifests from both batch and shared writers.

## Files Changed

- `src/quant_research_engine/portfolio/io.py` — `_write_run_manifest()` added; `run_request` parameter on 3 writer functions
- `src/quant_research_engine/portfolio/report_manifest.py` — `validate_contents()` validates `run_manifest` role as JSON object
- `src/quant_research_engine/apps/cli.py` — 3 backtest handlers build and pass `run_request` with market_profile, grouping, and benchmark fields
- `tests/test_portfolio_io.py` — 4 new tests + 3 updated with new field assertions
- `tests/test_portfolio_report_manifest.py` — 2 new tests

## Validation Results

```bash
uv run pytest tests/test_portfolio_io.py -q              # 14 passed
uv run pytest tests/test_portfolio_report_manifest.py -q # 26 passed
uv run pytest tests/test_cli.py -q                       # 91 passed
uv run pytest -q                                         # 246 passed in 2.37s
scripts/check-progress-docs.sh      # passed
git diff --check                    # passed
```

## Constraints

- Sensitive connection values are not stored in the manifest. ✅ compliant
- Existing behavior preserved. ✅ additive only
- No forbidden files modified. ✅ compliant
- Report discovery and audit behavior preserved. ✅ `run_manifest` validates as JSON object through emitted report manifests
- `market_profile` stored as file path string or `"built-in"`; benchmark fields only present when user provides them. ✅
- `run_manifest` role mapping is now explicit in both `_batch_manifest_role()` and `_shared_manifest_role()`. ✅
- Do not push. ✅ not pushed

## Git State

- Branch: `master`
- Accepted by Codex review.
- Local checkpoint pending.
