# Task Handoff

## Current Task

Wire batch backtest `group_by` metadata passthrough for optional upstream columns.

## Task ID

QRE-PORTFOLIO-BATCH-METADATA-GROUPBY-001

## Current Status

Brief prepared and handed off to Claude Code after user approval.

## Current Owner

CLAUDE_CODE

## In Progress

None yet in code. The next implementation should let requested batch `group_by` metadata columns flow from the research frame into `BatchBacktestResult.summary`, so existing grouped report outputs can use columns preserved by the metadata adapter.

## Expected Files

- `src/quant_research_engine/portfolio/batch.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_batch.py`
- `tests/test_cli.py`
- `docs/agent/01_CURRENT_STATUS.md`
- `docs/agent/03_ROADMAP.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/06_DECISION_LOG.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

- `uv run pytest tests/test_portfolio_batch.py tests/test_cli.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Known Risks

- Group-by columns may be absent from the assembled frame; keep existing error behavior clear and deterministic.
- Do not start guessing upstream metadata schemas or table names.
- Preserve existing batch summary metadata columns by default.

## Next Suggested Step

Claude Code should implement the batch metadata group-by passthrough brief and return a coding handoff with changed files and validation results.
