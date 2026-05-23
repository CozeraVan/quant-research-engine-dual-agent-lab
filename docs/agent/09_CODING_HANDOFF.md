# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-ORCHESTRATION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Objective

Add `qre research-run` command that chains preflight → eval-config → backtest as a single orchestrated research run with a common `--run-id` and a research-run manifest.

## Implementation Summary

- `src/quant_research_engine/orchestration/__init__.py` — package init
- `src/quant_research_engine/orchestration/research_run.py` — orchestrator module (~200 lines):
  - `ResearchRunRequest` dataclass — all configuration for a research run
  - `ResearchRunResult` dataclass — run outcome with per-stage status, paths, manifest path
  - `run_research_run()` — main orchestrator: DB connect → preflight → eval → backtest → manifest
  - `_write_research_manifest()` — writes `research_run_manifest.json` with run_id, stages, artifacts
  - `_run_preflight()`, `_run_eval()`, `_run_backtest()` — per-stage execution helpers
  - auto-generates `run_id` when not provided
  - stops on preflight/eval error, writes partial manifest
- `src/quant_research_engine/apps/cli.py`:
  - `qre research-run` parser with strategy, --start, --end, --output-dir (required), plus --db-url, --codes, --market-profile, --skip-preflight, --skip-eval, --backtest-mode, --initial-cash, --min-factor-coverage, --group-by, --random-baseline-seed, --round-trip-cost-rate, --metadata-columns, --window-size, --run-id
  - handler prints run_id, per-stage status, manifest path, backtest artifact paths; exits 2 on error
- `tests/test_research_run.py` — 7 unit tests (ResearchRunRequest construction, ResearchRunResult construction, manifest writing with ok/error/skipped stages)
- `tests/test_cli.py` — 3 CLI tests (--help, missing required args, no-DB error)
- `docs/agent/03_ROADMAP.md` — M8.42 added, stale M7.x/M8.1/M8.3/M8.10 synced to DONE
- `docs/agent/01_CURRENT_STATUS.md` — synced with current state, known gaps updated

## Validation

```bash
uv run pytest tests/test_research_run.py -q
# 7 passed in 0.46s

uv run pytest tests/test_cli.py -q --tb=short -k "research_run"
# 3 passed in 0.80s

uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_research_run.py -q
# 476 passed, 2 warnings in 4.98s

scripts/check-progress-docs.sh
# passed

git diff --check
# passed
```
