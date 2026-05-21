# Coding Handoff

## Task ID

QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Blocked. No implementation possible — the required upstream source table does not exist.

## Implementation Summary

No implementation possible for the real metadata task:

- The local `tushare_data` database does not contain a security-status metadata table.
- `stock_daily` has no suspension, ST, or risk-warning columns.
- No `QRE_SECURITY_METADATA_TABLE` env var is configured.

The reusable source scaffold now exists for future shape probing:

- `src/quant_research_engine/data/tushare_security.py`
- `scripts/tushare_security_smoke.py`
- `tests/test_tushare_security.py`

## Files Changed

- `src/quant_research_engine/data/tushare_security.py` — Added `SNAPSHOT_FIXED_COLUMNS`, `SecuritySnapshot`, `derive_board()`, `normalize_snapshot_frame()`, `_probe_bool_endpoint()`.
- `tests/test_tushare_security.py` — Added 14 new tests (17 total): `derive_board` (4), `SecuritySnapshot` (2), `normalize_snapshot_frame` (8). Added `FakeTushareProEmptySuspend` and `FakeTushareProAllAvailable` test doubles.
- `scripts/tushare_security_smoke.py` — Thin read-only CLI wrapper over the shared source adapter.
- `docs/agent/04_TASK_HANDOFF.md` — Updated for blocker status.
- `docs/agent/05_PROGRESS.md` — Updated progress table, phase, and verification state.
- `docs/agent/09_CODING_HANDOFF.md` — This file.
- `docs/agent/11_AGENT_STATE.md` — Updated phase and owner.
- `docs/agent/12_AGENT_BOARD.md` — Updated recipient and message.

## Validation Results

- `uv run pytest tests/test_tushare_security.py tests/test_postgres_store.py -q` → 34 passed in 0.52s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Constraints

- Read-only; no database writes, no schema changes.
- `docs/legacy/**` untouched.
- `uv.lock`, `pyproject.toml` untouched.
- `src/quant_research_engine/data/postgres.py` untouched.
- Smoke harness preserved and refactored behind the reusable source adapter.
- Blocked real-metadata task (`QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001`) untouched.

## Git State

- Branch: `master`
- Last finalized implementation commit: `2da15bb`, `Preserve window_size and group_by selector parity under JSON strict mode`
- Current changes are uncommitted (code + tests + agent docs; awaiting Codex review).

## Next Suggested Step

Codex should keep `M4.9` blocked until an upstream security-status table is confirmed. The reusable source scaffold is available for future bulk ingestion work.
