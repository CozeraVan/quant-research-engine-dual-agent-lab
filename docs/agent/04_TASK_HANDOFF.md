# Task Handoff

## Current Task

Add deterministic random-baseline comparison for `qre eval-config`.

## Task ID

QRE-EVAL-RANDOM-BASELINE-COMPARISON-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Added `evaluation_report_manifest` kind to `_SUPPORTED_MANIFEST_KINDS` in `report_manifest.py`.
- Added evaluation artifact role column requirements (`events`, `evaluation_summary`, `ic_summary`, `quantile_summary`, `evaluation_group_summary`) to `_REQUIRED_COLUMNS_BY_ROLE`.
- Added `--output-dir` CLI argument to `eval-config` subcommand.
- Implemented `_write_evaluation_output()` and `_eval_manifest_role()` helpers in `cli.py`.
- When `--output-dir` is provided, writes: `events.csv` (always), `summary.csv` (non-empty), `ic_summary.csv` (non-empty), `quantile_summary.csv` (non-empty), `group_summary.csv` (non-empty), `run_manifest.json`, and `report_manifest.json`.
- `run_manifest.json` records safe run inputs (command, strategy_path, dates, codes, cost rate or market-profile path, group columns, artifacts) without sensitive connection values.
- `report_manifest.json` uses kind `evaluation_report_manifest` and can be loaded/validated by `ReportManifest`.
- Added 2 CLI regression tests and 8 manifest validation tests.
- Existing stdout behavior preserved; output-dir is additive and optional.
- Run-manifest provenance now includes `market_profile` when that path is the source of the effective cost rate.

## In Progress

- Random-baseline comparison brief approved and handed to Claude Code for implementation.

## Expected Files

- `src/quant_research_engine/evaluation/models.py` (modified)
- `src/quant_research_engine/evaluation/engine.py` (modified)
- `src/quant_research_engine/apps/cli.py` (modified)
- `tests/test_evaluation_forward_returns.py` (new or expanded tests)
- `tests/test_cli.py` (new or expanded tests)
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

- `uv run pytest tests/test_cli.py -q` -> `95 passed in 1.57s`
- `uv run pytest tests/test_portfolio_report_manifest.py -q` -> `34 passed`
- `uv run pytest -q` -> `265 passed in 2.83s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

## Known Risks

- Random-baseline comparison must stay deterministic for regression stability.
- Existing stdout behavior remains unchanged; any new comparison output must be opt-in or additive.
- The real index benchmark wiring path remains blocked until the index table/schema is confirmed.
- No evaluation math should change outside the new comparison summary.

## Next Suggested Step

Claude Code should implement `QRE-EVAL-RANDOM-BASELINE-COMPARISON-001` from `08_IMPLEMENTATION_BRIEF.md`.
