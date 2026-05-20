# Implementation Brief

## Task ID

QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Shared-cash output rows can now carry explicitly requested static metadata columns without overwriting canonical fields. The next useful reporting step is grouped diagnostics over those rows.

This task should summarize shared-cash orders, closed trades, and failed orders by requested metadata columns. It should not attempt holdings exposure, group equity curves, or return attribution because shared-cash positions and cash are portfolio-level.

## Goal

Add shared-cash group summary CSV artifacts and CLI output for requested metadata columns:

- order group summaries from `result.orders`
- trade group summaries from `result.trades`
- failed-order group summaries from `result.failed_orders`

## Non-Goals

- Do not add shared-cash group return attribution or equity curves.
- Do not infer holdings exposure by metadata group.
- Do not add new upstream tables or database writes.
- Do not guess metadata schemas, table names, or column meanings.
- Do not implement time-varying suspension/ST/risk-warning semantics.
- Do not change shared-cash simulation math, market validation, risk exits, rebalancing, or row-level metadata passthrough.
- Do not change batch or single-symbol behavior unless required by shared utilities or tests.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/analytics.py`
- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_analytics.py`
- `tests/test_portfolio_io.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Keep data access read-only.
- Preserve existing shared-cash outputs by default when no group columns are requested.
- Keep group summaries based on existing row outputs only.
- Do not change shared-cash simulation behavior or row-level metadata semantics.
- Keep report manifests discoverable and auditable.

## Implementation Steps

1. Inspect existing batch group summary helpers in `portfolio/analytics.py`, shared output writer behavior in `portfolio/io.py`, and manifest role validation in `portfolio/report_manifest.py`.
2. Add shared-cash group summary helpers. Recommended shapes:
   - `summarize_shared_orders_by(orders, group_column)`
   - `summarize_shared_trades_by(trades, group_column)`
   - `summarize_shared_failed_orders_by(failed_orders, group_column)`
3. Recommended output columns:
   - common: `group_by`, `group_value`
   - orders: `order_count`, `buy_order_count`, `sell_order_count`, `total_notional`, `buy_notional`, `sell_notional`, `total_cost`
   - trades: `trade_count`, `win_rate`, `gross_pnl`, `net_pnl`, `total_cost`
   - failed orders: `failed_order_count`, `failed_notional`, optional side counts/notional if straightforward
4. Missing group column behavior should be clear and explicit, e.g. `ValueError("shared-cash orders must include <column>")`.
5. Add `backtest-shared --group-by ...` CLI support. It should request those metadata columns from the engine, either by unioning them into `metadata_columns` or by documenting that `--group-by` implies row metadata passthrough.
6. Update `write_shared_cash_result()` to accept `group_by: list[str] | None = None` and write grouped CSV artifacts only when requested:
   - `orders_by_<column>.csv`
   - `trades_by_<column>.csv`
   - `failed_orders_by_<column>.csv`
7. Add manifest entries and validation roles for the new shared-cash group summary artifacts. Keep `report-files --group-by ...` and `report-audit --group-by ...` compatible.
8. Include `group_by` in `run_manifest.json` request payload for `backtest-shared --output-dir`.
9. Preserve existing default outputs when `--group-by` is omitted.
10. Add focused tests for analytics helpers, output files/manifests, manifest filtering/validation, and CLI behavior.
11. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- No new upstream tables.
- No hardcoded metadata schema.

## API / Interface Changes

- CLI `backtest-shared` may gain `--group-by`.
- `write_shared_cash_result()` may gain an optional `group_by` argument.
- Report manifests may gain new shared-cash group summary roles.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_analytics.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
```

Run full checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] Existing shared-cash outputs are unchanged when no group columns are requested.
- [ ] `backtest-shared --group-by <metadata_column>` can print and persist grouped order/trade/failed-order summaries when the column exists.
- [ ] Grouped summaries are based on row-level outputs and do not alter simulation math.
- [ ] Missing group columns fail clearly.
- [ ] Report manifests include the grouped artifacts with filterable `group_by` metadata.
- [ ] `report-files` and `report-audit` can discover and validate the new grouped artifacts.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Shared-cash portfolio performance is portfolio-level, so group summaries must stay diagnostic and row-based.
- Avoid naming these outputs as return attribution or group equity performance.
- Keep manifest roles narrowly scoped to artifact validation needs.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep grouped shared-cash summaries row-based and diagnostic.
3. Preserve default shared-cash output behavior when `group_by` is omitted.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
