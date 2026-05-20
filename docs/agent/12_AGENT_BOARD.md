# Agent Board

## Current Task ID

QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

Implement row-based shared-cash metadata group summaries for orders, trades, and failed orders.

## Implementation Request

Claude Code should implement `08_IMPLEMENTATION_BRIEF.md` exactly:

1. Add analytics helpers for shared-cash order, trade, and failed-order grouped summaries.
2. Add `backtest-shared --group-by ...`; requested group columns must be available in row outputs.
3. Write grouped CSV artifacts under `--output-dir`:
   - `orders_by_<column>.csv`
   - `trades_by_<column>.csv`
   - `failed_orders_by_<column>.csv`
4. Add report manifest entries and validation roles for the grouped artifacts.
5. Preserve default outputs when `--group-by` is omitted.
6. Keep summaries row-based and diagnostic; do not implement return attribution or group equity curves.
7. Write `09_CODING_HANDOFF.md` with changed files, validation, risks, and git state.

## Constraints Check

- Do not add shared-cash group return attribution or holdings exposure.
- Do not alter shared-cash simulation math, order selection, cash accounting, risk exits, rebalancing, or market validation.
- Do not guess upstream schemas or table names.
- Do not implement time-varying status semantics.
- Keep report manifests compatible with `report-files` and `report-audit`.
- Do not push.

## Required Validation

- `uv run pytest tests/test_portfolio_analytics.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Expected Changed Files

- `src/quant_research_engine/portfolio/analytics.py`
- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_analytics.py`
- `tests/test_portfolio_io.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Next Step

Claude Code should implement the current task from `08_IMPLEMENTATION_BRIEF.md`.
