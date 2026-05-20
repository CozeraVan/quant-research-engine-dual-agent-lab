# Agent Board

## Current Task ID

QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001

## Current Recipient

USER

## Message Type

CODEX_TO_USER

## Sender

CODEX

## Short Message

Review complete. Shared-cash metadata group summaries are accepted locally.

## Implementation Summary

Claude Code implemented the brief and fixed Codex's required empty-output issue:

1. Added row-based shared-cash group summary helpers for orders, trades, and failed orders.
2. Added `backtest-shared --group-by ...`.
3. Wrote grouped CSV artifacts under `--output-dir`.
4. Added report manifest roles and `group_by` metadata for grouped artifacts.
5. Preserved default shared-cash output behavior when `group_by` is omitted.
6. Fixed empty no-column shared row artifacts so grouped output writes stable empty CSV headers instead of crashing.

## Validation

- Empty no-column failed orders write `failed_orders_by_<column>.csv` with stable headers.
- `uv run pytest tests/test_portfolio_analytics.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q` -> `179 passed in 2.31s`
- `uv run pytest -q` -> `315 passed in 3.00s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

## Constraints Check

- No shared-cash group return attribution or holdings exposure added.
- No shared-cash simulation math, order selection, cash accounting, risk exits, rebalancing, or market validation changed.
- No upstream schema or table name guesses.
- Report manifests remain compatible with `report-files` and `report-audit`.
- Not pushed.

## Next Step

Codex should select the next unblocked task after finalization.
