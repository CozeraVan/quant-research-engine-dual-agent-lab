# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-MANIFEST-INTEGRATION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Objective

Integrate `research_run_manifest.json` into the report manifest system so it is discoverable through `qre report-files` and `qre report-audit`, matching the existing `portfolio_backtest_run_manifest` and `evaluation_run_manifest` pattern.

## Implementation Summary

- `src/quant_research_engine/orchestration/research_run.py` — `_write_research_manifest()` updated:
  - Now accepts `request: ResearchRunRequest` parameter
  - Emits standard run_manifest fields: `schema_version: 1`, `kind: "research_run_manifest"`, `command: "research-run"`, `strategy_path` (from request), `artifacts` (sorted list of backtest artifact keys)
  - Uses `sort_keys=True` for deterministic JSON output
  - All three call sites in `run_research_run()` updated to pass `request`
- `src/quant_research_engine/portfolio/report_manifest.py`:
  - `_RUN_MANIFEST_KINDS` now includes `"research_run_manifest"`
  - `_validate_run_manifest()` accepts the new kind; content validation passes
- `tests/test_research_run.py` — 3 manifest tests updated:
  - Added `_make_request()` helper for test request construction
  - Tests verify `schema_version`, `kind`, `command`, `strategy_path`, `artifacts` in emitted manifest
- `tests/test_portfolio_report_manifest.py` — 1 new test:
  - `test_validate_contents_accepts_valid_research_run_manifest` — validates a correctly-formed research_run_manifest.json with role `run_manifest` passes `validate_contents()`
- `docs/agent/03_ROADMAP.md` — M8.43 added
- `docs/agent/01_CURRENT_STATUS.md` — test count updated, manifest integration added to completed
- `docs/agent/06_DECISION_LOG.md` — decision entry added
- `docs/agent/10_REVIEW_REPORT.md` — PASS (no required fixes)
- `docs/agent/04_TASK_HANDOFF.md`, `05_PROGRESS.md`, `11_AGENT_STATE.md`, `12_AGENT_BOARD.md` — synced

## Validation

```bash
uv run pytest tests/test_research_run.py -q
# 7 passed in 0.46s

uv run pytest tests/test_portfolio_report_manifest.py -q
# passed

uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_research_run.py -q
# 477 passed, 2 warnings in 5.07s

scripts/check-progress-docs.sh
# passed

git diff --check
# passed
```
