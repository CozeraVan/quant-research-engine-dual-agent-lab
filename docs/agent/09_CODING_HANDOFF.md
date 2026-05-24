# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-STAGE-ARTIFACT-PARITY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

FIXED

## Objective

Address the 3 Required Fixes and 2 Recommended Fixes from `10_REVIEW_REPORT.md`.

## Fix 1: Real `_run_eval()` with correct `EvaluationRequest` signature

- Changed `_run_eval()` from invalid `EvaluationRequest(frame=..., expression=..., start=..., end=...)` + `EvaluationEngine().run()` to the correct `EvaluationRequest(signal_expression=..., forward_horizons=..., factor_columns=..., quantiles=..., round_trip_cost_rate=..., group_by=..., random_baseline_seed=...)` + `EvaluationEngine().evaluate(frame, eval_req)`. Matches the `eval-config` handler pattern exactly.
- Added `TestRunEvalReal.test_run_eval_with_correct_evaluation_request_shape` that creates a real FakeStore with 5 days of market data and calls `_run_eval()` directly (no monkeypatch). Asserts `forward_return_1` column appears in the events, confirming the real evaluation engine ran.

## Fix 2: Preserve real `PreflightReport.to_dict()` fields

- `_write_preflight_artifact()` now checks `hasattr(report, "to_dict")` first and writes the full `to_dict()` payload. Falls back to manual attribute extraction for test fakes without `to_dict()`.
- Added `TestWritePreflightArtifact.test_writes_preflight_json_with_to_dict` using a real `PreflightReport` instance with `FactorCoverage` data. Asserts `market_rows`, `latest_market_date`, `requested_symbols`, `loaded_symbols`, `missing_symbols`, `factor_coverages`, `joined_rows`, `join_coverage_ratio`, `metadata_rows`, `universe_total_symbols`, `benchmark_rows`, `benchmark_non_null_rows`, and `checks` all survive in the JSON.
- Updated the fake fallback test to use a plain class (MagicMock auto-creates `to_dict` on attribute access, which would bypass the fallback).

## Fix 3: Track `evaluation/io.py`

- `src/quant_research_engine/evaluation/io.py` is confirmed present and importable. The file is currently untracked (`git status` shows `??`). Per R-GIT-001, Claude Code does not stage or commit files — **Codex must `git add` this file during finalization.**

## Recommended Fix 1: Pass `market_profile` to `write_evaluation_output()`

- `_write_eval_artifacts()` now passes `market_profile=str(request.market_profile_path) if request.market_profile_path else None` to `write_evaluation_output()`, matching `eval-config` provenance behavior.

## Recommended Fix 2: Stage-qualified top-level artifact keys

- Top-level `research_run_manifest["artifacts"]` now uses stage-qualified keys: `preflight:<key>`, `eval:<key>`, `backtest:<key>`. This avoids ambiguous duplicates when eval and backtest both emit `report_manifest` or `run_manifest`.
- Updated all 6 manifest tests to assert stage-qualified keys.

## Validation

```bash
# Full suite
uv run pytest -q
# 791 passed, 2 warnings (789 → 791: +2 tests for real-run-eval and preflight-to-dict)

# Targeted
uv run pytest tests/test_research_run.py tests/test_cli.py -q -k "research_run or eval_config"
# 38 passed, 2 warnings

# Portfolio regression
uv run pytest tests/test_portfolio_report_manifest.py tests/test_portfolio_io.py -q
# 102 passed

# Research-run specific
uv run pytest tests/test_research_run.py -q
# 19 passed (17 → 19: +2 regression tests for Required Fixes 1 and 2)

# CLI research-run
uv run pytest tests/test_cli.py -q -k "research_run"
# 5 passed

# Eval-config regression
uv run pytest tests/test_cli.py -q -k "eval_config"
# 14 passed

# Progress docs
scripts/check-progress-docs.sh
# passed

# Diff
git diff --check
# clean
```

## Files Changed

- `src/quant_research_engine/orchestration/research_run.py` — Fixed `_run_eval()` (correct `EvaluationRequest` + `.evaluate()`), fixed `_write_preflight_artifact()` (use `to_dict()` when available), added `market_profile` pass-through, stage-qualified top-level artifacts
- `tests/test_research_run.py` — 19 tests: added `test_writes_preflight_json_with_to_dict` (real `PreflightReport`), `test_writes_preflight_json_with_fake_fallback` (plain class), `test_run_eval_with_correct_evaluation_request_shape` (real `_run_eval()` with fake store)
- `src/quant_research_engine/evaluation/io.py` — **UNTRACKED, must be git-add'ed by Codex during finalization**

## Known Validation Gaps

- No database available for end-to-end `qre research-run`. The monkeypatched tests cover all code paths; the new `test_run_eval_with_correct_evaluation_request_shape` exercises the real `_run_eval()` through the assembler → engine pipeline with a fake store. If a database is available, also run the real narrow `qre research-run` and report discovery/audit checks from `08_IMPLEMENTATION_BRIEF.md`.
