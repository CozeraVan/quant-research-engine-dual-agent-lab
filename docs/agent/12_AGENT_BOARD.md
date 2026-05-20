# Agent Board

## Current Task ID

QRE-PORTFOLIO-BATCH-METADATA-GROUPBY-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

Implement the next portfolio reporting task: make `backtest-batch --group-by` work with optional metadata columns preserved by the data layer.

## Implementation Summary

Focus the implementation on the existing batch summary and grouped report path:

1. Preserve the default fixed metadata columns currently copied into batch summaries.
2. Add a request-driven way to include additional metadata columns in `BatchBacktestResult.summary`.
3. Have CLI `backtest-batch --group-by <column>` request those columns from the engine.
4. Reuse existing `summarize_batch_by()` and `write_batch_result(..., group_by=...)` behavior.
5. Add focused tests for engine summary metadata and CLI grouping with a passthrough metadata column.

## Validation

- No implementation validation yet. Claude Code should report focused test output in the coding handoff.

## Constraints Check

- Preserve existing batch summary behavior. ✅ required.
- Keep data access read-only. ✅ required.
- Avoid benchmark/time-varying-status table guesses. ✅ required.
- Do not change portfolio math. ✅ required.
- Do not push. ✅

## Changed Files

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
