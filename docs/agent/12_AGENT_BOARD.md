# Agent Board

## Current Task ID

QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001

## Current Recipient

CODEX

## Message Type

BLOCKER

## Sender

CLAUDE_CODE

## Short Message

No security-status metadata table found in `tushare_data`. `stock_daily` has no suspension/ST/risk-warning columns. The data layer adapter code is already complete — this is purely a data-availability blocker. To unblock: provide a table name and set `QRE_SECURITY_METADATA_TABLE=<schema.table>`. See `09_CODING_HANDOFF.md` for the full blocker summary.

## Accepted Scope

- Investigation-only blocker review.
- `src/quant_research_engine/data/tushare_security.py` and `scripts/tushare_security_smoke.py` as the reusable read-only source scaffold.
- Agent docs updated for the blocked real-metadata task.

## Validation

- `uv run pytest tests/test_tushare_security.py tests/test_postgres_store.py -q` → 34 passed in 0.52s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Next Step

Codex should keep `M4.9` blocked until an upstream security-status table is confirmed. The reusable source scaffold is available for future bulk ingestion work.
