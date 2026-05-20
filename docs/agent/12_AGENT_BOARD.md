# Agent Board

## Current Task ID

QRE-DATA-REAL-METADATA-ADAPTERS-001

## Current Recipient

USER

## Message Type

CODEX_TO_USER

## Sender

CODEX

## Short Message

Review complete. Real metadata adapters that preserve optional upstream columns are accepted locally.

## Implementation Summary

Claude Code completed the implementation and Codex accepted it:

1. Extended `_load_security_metadata_table()` to select passthrough columns beyond the 6 expected fixed columns. Any additional columns the configured source table exposes are now preserved.
2. Updated `_normalize_security_metadata()` to keep all columns instead of truncating to the fixed set. Fixed columns receive existing normalization; passthrough columns pass through untouched in sorted order.
3. `_derive_security_metadata_from_daily()` unchanged — fallback path produces only the 6 fixed columns.
4. `ResearchFrameAssembler` and `PreflightRunner` require no changes.
5. Added 2 postgres store tests + 1 assembler test + 1 preflight test.

## Validation

- `uv run pytest tests/test_postgres_store.py tests/test_data_assembler.py tests/test_preflight.py -q` -> `23 passed`
- `uv run pytest -q` -> `278 passed in 2.58s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

## Constraints Check

- Preserve existing metadata fallback behavior. ✅ fallback normalization unchanged.
- Keep the adapter additive and optional. ✅ passthrough only.
- Keep data access read-only. ✅ no upstream writes.
- Avoid benchmark table guesses. ✅ not touched.
- Do not push. ✅

## Changed Files

- `src/quant_research_engine/data/postgres.py`
- `tests/test_postgres_store.py`
- `tests/test_data_assembler.py`
- `tests/test_preflight.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
