# Agent Board

## Current Task ID

QRE-SHARED-CASH-METADATA-OUTPUTS-001

## Current Recipient

USER

## Message Type

CODEX_TO_USER

## Sender

CODEX

## Short Message

Review complete. Shared-cash metadata output passthrough is accepted locally.

## Implementation Summary

Claude Code implemented the brief and fixed Codex's required collision issue:

1. Added `metadata_columns: list[str] | None = None` to `SharedCashBacktestRequest`.
2. Added `_build_metadata_lookup()` for request-driven, symbol-keyed static metadata passthrough.
3. Threaded metadata through shared-cash order, trade, and failed-order row builders.
4. Protected canonical row fields with per-key guards, so metadata cannot overwrite fields such as `trade_date`, `exit_reason`, or `failure_reason`.
5. Added `backtest-shared --metadata-columns ...`.
6. Recorded requested `metadata_columns` in `run_manifest.json`.
7. Added engine, CLI, and collision regression coverage.

## Validation

- Collision reproduction: order dates preserved after requesting `metadata_columns=["trade_date"]`
- `uv run pytest tests/test_portfolio_shared.py tests/test_cli.py tests/test_portfolio_io.py -q` -> `142 passed in 2.18s`
- `uv run pytest -q` -> `293 passed in 2.80s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

## Constraints Check

- No shared-cash group-by reports added.
- No shared-cash simulation math, order selection, cash accounting, risk exits, rebalancing, or market validation changed.
- No upstream schema or table name guesses.
- No time-varying status semantics.
- Metadata propagation is request-driven and additive.
- Metadata cannot overwrite canonical output row fields.
- Not pushed.

## Changed Files

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_shared.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/10_REVIEW_REPORT.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Next Step

Codex should select the next unblocked task after finalization.
