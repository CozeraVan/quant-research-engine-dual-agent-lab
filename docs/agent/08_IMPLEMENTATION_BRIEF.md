# Implementation Brief

## Task ID

QRE-RESEARCH-RUN-ORCHESTRATION-001

## Created By

CLAUDE_CODE (acting planner — Codex unavailable)

## Intended Implementer

CLAUDE_CODE

## Goal

Add `qre research-run` command that chains preflight → eval-config → backtest under a common `--run-id` with a research-run manifest.

## Required Changes

1. Create `src/quant_research_engine/orchestration/` package with `research_run.py`.
2. Define `ResearchRunRequest` and `ResearchRunResult` dataclasses.
3. Implement `run_research_run()` that:
   - connects to database
   - runs preflight (unless `--skip-preflight`), stops on error
   - runs eval-config (unless `--skip-eval`), stops on error
   - runs backtest-batch or backtest-shared
   - writes `research_run_manifest.json`
4. Add `qre research-run` CLI command with all necessary arguments.
5. Tests:
   - unit tests for dataclasses and manifest writing
   - CLI tests for --help, missing args, no-DB error
6. Update agent docs.

## Validation Commands

```bash
uv run pytest tests/test_research_run.py tests/test_cli.py -q --tb=short -k "research_run"
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_research_run.py -q
scripts/check-progress-docs.sh
git diff --check
```
