# Review Report

## Task ID

QRE-SHARED-CASH-METADATA-OUTPUTS-001

## Written By

CODEX

## Review Outcome

PASS

## Reviewed Implementation

Claude Code implementation and collision fix in the current working tree.

Changed files reviewed:

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_shared.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Review Summary

Review passed.

Shared-cash backtests now support request-driven metadata columns for order, trade, and failed-order output rows. The Codex-required collision fix is complete: metadata keys are merged only when the key is not already present in the canonical row, so requested metadata cannot overwrite fields such as `trade_date`, `exit_reason`, or `failure_reason`.

## Compliance with Implementation Brief

Compliant.

- `SharedCashBacktestRequest.metadata_columns` is available and defaults to `None`.
- `_build_metadata_lookup()` builds symbol-keyed metadata from requested columns only.
- Requested non-colliding metadata is appended to `orders`, `trades`, and `failed_orders`.
- Missing requested metadata columns are skipped without schema guessing.
- CLI `backtest-shared --metadata-columns ...` passes requested columns to the engine.
- `run_manifest.json` records `metadata_columns` when `--output-dir` is used.
- No shared-cash group-by reports, data writes, benchmark wiring, or time-varying status semantics were added.
- Shared-cash simulation math and market validation were not changed.

## Locked Requirements Check

No locked-requirement violation found.

- R-CORE-001: Existing shared-cash output fields are preserved by default and protected from metadata collision.
- R-CORE-002: Change is scoped to shared-cash metadata output passthrough and tests.
- R-CORE-003: Focused and full validation passed.
- R-CORE-004 / R-QRE-006: No sensitive values added.
- R-QRE-002: No internal indicator computation added.
- R-QRE-005: Data access remains read-only.
- R-QRE-007: Existing report artifacts and manifests remain intact.
- R-GIT-002: No push performed.

## Code Quality Review

The implementation is request-driven and additive. Collision handling is explicit in each row builder through per-key `key not in row` guards. One minor style issue remains in the `_execute_rebalance()` call indentation; it is non-blocking because behavior and tests are unaffected.

## Test Review

Validation commands run by Codex:

```bash
uv run pytest tests/test_portfolio_shared.py tests/test_cli.py tests/test_portfolio_io.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

Additional reproduction rerun by Codex:

```bash
uv run python - <<'PY'
from tests.test_portfolio_shared import make_shared_frame
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.shared import SharedCashBacktestEngine, SharedCashBacktestRequest

result = SharedCashBacktestEngine(AShareMarketProfile()).run(
    make_shared_frame().copy(),
    SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=["trade_date"],
    ),
)
print(result.orders[["symbol", "side", "trade_date"]].head().to_string(index=False))
PY
```

Results:

- Collision reproduction now preserves order dates: buys on `2026-01-06`, sells on `2026-01-08`.
- `uv run pytest tests/test_portfolio_shared.py tests/test_cli.py tests/test_portfolio_io.py -q`: `142 passed in 2.18s`
- `uv run pytest -q`: `293 passed in 2.80s`
- `scripts/check-progress-docs.sh`: passed
- `git diff --check`: passed

Coverage is adequate:

- metadata appears in orders, trades, and failed orders when requested;
- missing metadata columns are skipped;
- default output schemas are unchanged when metadata is omitted;
- collision regressions cover order `trade_date`, trade `exit_reason`, and failed-order `failure_reason`;
- CLI output-dir flow persists metadata columns and records `metadata_columns` in `run_manifest.json`.

## Required Fixes

None.

## Recommended Improvements

- Clean up the `_execute_rebalance()` call indentation during the next nearby shared-cash edit.

## Follow-up Tasks

- Finalize the accepted implementation locally.
- Next planning should choose an unblocked follow-up; real benchmark wiring and time-varying status metadata remain blocked by source-table confirmation.

## Final Recommendation

Accept locally. Do not push.

## Next Agent State

- Phase: `DONE`
- Owner: `USER`
