# Task Handoff

## Current Task

Add evaluation factor decay summaries from existing IC and Rank IC outputs.

## Task ID

QRE-EVAL-FACTOR-DECAY-SUMMARY-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex finalized `QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001`.
- Codex selected the next unblocked evaluation task: factor decay summaries over existing forward horizons.
- Codex prepared `08_IMPLEMENTATION_BRIEF.md`.

## In Progress

- Claude Code should implement the brief and write `09_CODING_HANDOFF.md`.

## Expected Files

- `src/quant_research_engine/evaluation/models.py`
- `src/quant_research_engine/evaluation/engine.py`
- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_evaluation_forward_returns.py`
- `tests/test_cli.py`
- `tests/test_portfolio_report_manifest.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Last finalized implementation baseline:

- `uv run pytest tests/test_portfolio_analytics.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q` -> `179 passed in 2.31s`
- `uv run pytest -q` -> `315 passed in 3.00s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

Required validation for this task:

- `uv run pytest tests/test_evaluation_forward_returns.py tests/test_cli.py tests/test_portfolio_report_manifest.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Known Risks

- Factor decay should be computed from existing IC/Rank IC outputs; do not invent new factor math.
- No benchmark tables, regime tables, or external data-source assumptions.
- Preserve existing evaluation outputs when no factor columns are supplied.
- Keep output artifacts and manifest validation compatible with `report-files` and `report-audit`.

## Next Suggested Step

Claude Code should read `11_AGENT_STATE.md`, `12_AGENT_BOARD.md`, and `08_IMPLEMENTATION_BRIEF.md`, then implement `QRE-EVAL-FACTOR-DECAY-SUMMARY-001`.
