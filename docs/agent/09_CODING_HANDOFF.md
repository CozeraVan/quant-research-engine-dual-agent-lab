# Coding Handoff

## Task ID

QRE-DATA-REAL-METADATA-ADAPTERS-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Accepted locally.

## Implementation Summary

- Extended `_load_security_metadata_table()` to select passthrough columns beyond the 6 expected fixed columns (`ts_code`, `list_date`, `board`, `is_st`, `is_risk_warning`, `is_suspended`). Any additional columns the configured source table exposes are now preserved in the SELECT query.
- Updated `_normalize_security_metadata()` to keep all columns instead of truncating to only the 6 fixed ones. Fixed columns still receive their existing normalization (list_date → datetime, board → derive_board fallback, status flags → bool). Passthrough columns pass through untouched in sorted order after the fixed columns.
- `_derive_security_metadata_from_daily()` is unchanged — when no metadata table is configured, only the 6 fixed columns are produced.
- `ResearchFrameAssembler` and `PreflightRunner` require no changes; their left-merge and column-access patterns handle extra columns naturally.

## Files Changed

- `src/quant_research_engine/data/postgres.py` — extended `_load_security_metadata_table()` with passthrough column selection; updated `_normalize_security_metadata()` to preserve all columns
- `tests/test_postgres_store.py` — 2 new tests: passthrough columns preserved, fallback normalization when no extra columns
- `tests/test_data_assembler.py` — 1 new test: assembler merge includes passthrough metadata columns
- `tests/test_preflight.py` — 1 new test: universe diagnostics work with extra metadata columns

## Validation Results

```bash
uv run pytest tests/test_postgres_store.py tests/test_data_assembler.py tests/test_preflight.py -q  # 23 passed
uv run pytest -q                                                                                       # 278 passed in 2.59s
scripts/check-progress-docs.sh                                                                         # passed
git diff --check                                                                                       # passed
```

## Constraints

- Preserve existing metadata fallback behavior when optional source columns are missing. ✅
- Keep the adapter additive and optional. ✅ passthrough only; no new logic.
- Keep data access read-only. ✅ no writes to upstream databases.
- Avoid benchmark table guesses. ✅ not touched.
- Keep the implementation deterministic. ✅ passthrough order is sorted, fixed columns stable.

## Git State

- Branch: `master`
- Codex review passed.
- Local finalization in progress.
