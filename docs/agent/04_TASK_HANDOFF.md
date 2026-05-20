# Task Handoff

## Current Task

Extend security metadata adapters to preserve optional upstream status/industry/membership columns.

## Task ID

QRE-DATA-REAL-METADATA-ADAPTERS-001

## Current Status

Accepted locally.

## Current Owner

USER

## Completed

- Extended `_load_security_metadata_table()` to select passthrough columns beyond the 6 expected fixed columns (`ts_code`, `list_date`, `board`, `is_st`, `is_risk_warning`, `is_suspended`). Any additional columns the configured source table exposes are now preserved.
- Updated `_normalize_security_metadata()` to keep all columns instead of truncating to the fixed set. Fixed columns receive their existing normalization; passthrough columns pass through untouched in sorted order.
- `_derive_security_metadata_from_daily()` unchanged — fallback path produces only the 6 fixed columns.
- `ResearchFrameAssembler` and `PreflightRunner` unchanged — left-merge and column-access patterns handle extra columns naturally.
- Added 2 postgres store tests (passthrough preservation + fallback without extra columns).
- Added 1 assembler test (passthrough columns flow through merge).
- Added 1 preflight test (universe diagnostics work with extra metadata columns).

## In Progress

None.

## Expected Files

- `src/quant_research_engine/data/postgres.py` (modified)
- `tests/test_postgres_store.py` (2 new tests)
- `tests/test_data_assembler.py` (1 new test)
- `tests/test_preflight.py` (1 new test)

## Validation Baseline

- `uv run pytest tests/test_postgres_store.py tests/test_data_assembler.py tests/test_preflight.py -q` -> `23 passed`
- `uv run pytest -q` -> `278 passed in 2.58s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

## Known Risks

- Passthrough columns come from the configured source table schema; different environments may have different columns.
- No schema guesses — only columns actually present in the source table are included.
- Fallback normalization remains identical when source columns are absent.

## Next Suggested Step

None. Await user acceptance or next request.
