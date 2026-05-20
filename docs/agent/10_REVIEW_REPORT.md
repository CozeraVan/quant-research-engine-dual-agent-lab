# Review Report

## Task ID

QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001

## Written By

CODEX

## Review Outcome

PASS

## Reviewed Implementation

Claude Code implementation and empty no-column fix in the current working tree.

Changed files reviewed:

- `src/quant_research_engine/portfolio/analytics.py`
- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_analytics.py`
- `tests/test_portfolio_io.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Review Summary

Review passed.

Shared-cash backtests now support row-based metadata group summaries for orders, trades, and failed orders. The Codex-required empty no-column fix is complete: all three grouped summarizers return stable empty DataFrames with headers before checking group-column membership, while non-empty frames still fail clearly if the requested group column is absent.

## Compliance with Implementation Brief

Compliant.

- `backtest-shared --group-by ...` is available.
- Group-by columns are unioned into `metadata_columns` so row outputs can carry requested group metadata.
- `write_shared_cash_result(..., group_by=...)` writes grouped order, trade, and failed-order CSV artifacts.
- Report manifest entries include new shared-cash grouped roles and `group_by` metadata.
- `report-files` / `report-audit` can filter and validate the new grouped artifacts.
- Default shared-cash output behavior is preserved when `group_by` is omitted.
- Group summaries are row-based diagnostics only; no return attribution, holdings exposure, or group equity curves were added.

## Locked Requirements Check

No locked-requirement violation found.

- R-CORE-001: Existing shared-cash behavior is preserved without `group_by`; empty no-column row artifacts no longer break grouped output.
- R-CORE-002: Change is scoped to shared-cash grouped reporting and tests.
- R-CORE-003: Focused and full validation passed.
- R-CORE-004 / R-QRE-006: No sensitive values added.
- R-QRE-005: Data access remains read-only.
- R-QRE-007: Report manifest discovery and validation are preserved.
- R-GIT-002: No push performed.

## Test Review

Validation commands run by Codex:

```bash
uv run pytest tests/test_portfolio_analytics.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

Additional reproduction rerun by Codex:

```bash
uv run python - <<'PY'
import tempfile
from pathlib import Path
from tests.test_portfolio_shared import make_shared_frame
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.shared import SharedCashBacktestEngine, SharedCashBacktestRequest
from quant_research_engine.portfolio.io import write_shared_cash_result

frame = make_shared_frame().copy()
frame["board"] = ["main_board"] * 5 + ["star_market"] * 5
result = SharedCashBacktestEngine(AShareMarketProfile()).run(
    frame,
    SharedCashBacktestRequest(
        symbols=["000001.SZ", "000002.SZ"],
        initial_cash=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=2,
        max_positions=2,
        metadata_columns=["board"],
    ),
)
with tempfile.TemporaryDirectory() as tmp:
    paths = write_shared_cash_result(result, Path(tmp), group_by=["board"])
    print(sorted(k for k in paths if "_by_" in k))
    print((Path(tmp) / "failed_orders_by_board.csv").read_text(encoding="utf-8").strip())
PY
```

Results:

- Empty no-column failed orders now write stable header: `group_by,group_value,failed_order_count,failed_notional`
- `uv run pytest tests/test_portfolio_analytics.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q`: `179 passed in 2.31s`
- `uv run pytest -q`: `315 passed in 3.00s`
- `scripts/check-progress-docs.sh`: passed
- `git diff --check`: passed

## Required Fixes

None.

## Final Recommendation

Accept locally. Do not push.

## Next Agent State

- Phase: `DONE`
- Owner: `USER`
