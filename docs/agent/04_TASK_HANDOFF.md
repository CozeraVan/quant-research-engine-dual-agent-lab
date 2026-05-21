# Task Handoff

## Current Task

Wire real suspension/ST/risk-warning metadata into the data layer, starting from the existing security-metadata fallback path.

## Task ID

QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001

## Current Status

BLOCKED. The reusable Tushare source scaffold and canonical snapshot contract are complete, but the required upstream security-status metadata table still does not exist in the local `tushare_data` database. The data-layer adapter path remains blocked on source availability only.

## Current Owner

CODEX (blocker review and next steps)

## Completed

- `SNAPSHOT_FIXED_COLUMNS` — canonical column list (`ts_code`, `list_date`, `board`, `is_st`, `is_risk_warning`, `is_suspended`) matching `_normalize_security_metadata` in `postgres.py`.
- `SecuritySnapshot` — dataclass for one security's normalized metadata with typed fields and a `passthrough` dict for extra source columns.
- `derive_board()` — standalone board inference utility matching the logic in `postgres.py` (main_board, chinext, star_market, beijing).
- `normalize_snapshot_frame()` — builds a canonical DataFrame from Tushare source data: merges `stock_basic` with `suspend_d` for the given trade date, probes ST/risk-warning endpoints (treating permission blocks as `False`), applies board inference, and preserves passthrough columns.
- `_probe_bool_endpoint()` — internal helper that returns a boolean Series for endpoint-filtered ts_codes, falling back to `False` on permission errors.
- Smoke path (`TushareSecuritySource`, `SmokeResult`, `probe()`, `format_frame()`, `TushareProClient`, `scripts/tushare_security_smoke.py`) preserved unchanged.
- Tests: 17 targeted tests (up from 3) covering `derive_board`, `SecuritySnapshot`, `normalize_snapshot_frame` with full, empty, and permission-blocked endpoint scenarios, plus passthrough column preservation.
- The blocked real-metadata task (`QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001` / `QRE-NEXT-55`) remains parked separately.

## Expected Files

Code and agent docs updated:
- `src/quant_research_engine/data/tushare_security.py`
- `tests/test_tushare_security.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

- `uv run pytest tests/test_tushare_security.py tests/test_postgres_store.py -q` → 34 passed in 0.52s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Known Risks

- `normalize_snapshot_frame()` depends on `TushareSecuritySource` at runtime. If the configured Tushare credential is invalid or the network is unavailable, all endpoints fail and the frame will have `is_st=False`, `is_risk_warning=False`, and `is_suspended=False` for every security — matching the current fallback behavior.
- The canonical contract deliberately treats `stock_st` and `stk_alert` permission blocks as `False`, which is the same conservative default the data layer uses.

## Next Suggested Step

Codex should review the blocker, consult the user about whether an upstream security-status table is planned, and either provide the source table name or keep `M4.9` blocked until it is created upstream.
