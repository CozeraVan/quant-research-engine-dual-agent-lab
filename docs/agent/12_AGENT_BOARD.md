# Agent Board

## Current Task ID

QRE-RUN-ID-MANIFEST-LINKAGE-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

Implement optional `--run-id` linkage for preflight, eval-config, and portfolio durable outputs.

## Implementation Brief

Read `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

Core requirements:

1. Add optional `--run-id` to `preflight`, `eval-config`, `backtest-single`, `backtest-batch`, and `backtest-shared`. ✅ target
2. Persist top-level `run_id` in preflight `--output-json`. ✅ target
3. Persist top-level `run_id` in evaluation `run_manifest.json`. ✅ target
4. Persist top-level `run_id` in portfolio `portfolio_backtest_run_manifest`. ✅ target
5. Keep `run_id` optional and metadata-only. ✅ constraint
6. Preserve existing command behavior when omitted. ✅ constraint
7. Do not add an orchestrator command, database writes, or benchmark/regime wiring. ✅ constraint

## Required Validation

- `uv run pytest tests/test_cli.py tests/test_portfolio_io.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Expected Changed Files

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/io.py`
- `tests/test_cli.py`
- `tests/test_portfolio_io.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Next Step

Claude Code should implement the brief and write `09_CODING_HANDOFF.md` for Codex review.
