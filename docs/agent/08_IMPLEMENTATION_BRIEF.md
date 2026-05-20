# Implementation Brief

## Task ID

QRE-SHARED-CASH-METADATA-OUTPUTS-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

The data layer preserves optional upstream security metadata columns, and batch backtests can now request metadata columns for grouped summaries. Shared-cash backtests already assemble research frames with metadata, but the shared-cash row outputs only include trade/order fields.

That means output artifacts such as `orders.csv`, `trades.csv`, and `failed_orders.csv` cannot carry requested metadata columns like industry, liquidity bucket, membership flags, or other static source metadata.

## Goal

Let shared-cash backtests attach explicitly requested metadata columns to order, trade, and failed-order output rows while preserving current behavior when no metadata columns are requested.

## Non-Goals

- Do not add shared-cash group-by reports or attribution summaries.
- Do not add new upstream tables or database writes.
- Do not guess specific metadata schemas, table names, or column meanings.
- Do not implement time-varying suspension/ST/risk-warning semantics.
- Do not change portfolio execution, order selection, risk, cost, cash, rebalancing, or return math.
- Do not change batch or single-symbol behavior unless required by imports or tests.
- Do not compute technical indicators inside QRE.
- Do not record sensitive connection values.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_shared.py`
- `tests/test_cli.py`
- `tests/test_portfolio_io.py` if direct output-file assertions are useful

Docs/handoff:

- `docs/agent/01_CURRENT_STATUS.md`
- `docs/agent/03_ROADMAP.md`
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

- Preserve shared-cash output schemas by default when no metadata columns are requested.
- Keep metadata propagation explicit and request-driven.
- Keep data access read-only.
- Avoid benchmark and time-varying-status table guesses.
- Do not change shared-cash simulation math or market validation.

## Implementation Steps

1. Inspect `SharedCashBacktestRequest`, `SharedCashBacktestEngine.run()`, shared row builders (`_order_row`, `_trade_row`, `_failed_order_row`), CLI `backtest-shared`, and `write_shared_cash_result()`.
2. Add an optional request field such as `metadata_columns: list[str] | None = None` to `SharedCashBacktestRequest`.
3. Build a small request-driven metadata lookup from the prepared frame. Recommended semantics for this task:
   - Key by `ts_code` / output `symbol`.
   - For each requested column present in the frame, use the first non-null value for the symbol.
   - Skip requested columns that are absent from the frame.
   - Do not copy unrequested market, factor, or signal columns.
4. Attach that lookup to shared-cash `orders`, `trades`, and `failed_orders` rows. Existing row fields and row order should remain stable; append metadata columns after existing fields.
5. Add a CLI flag to `backtest-shared`, preferably `--metadata-columns` with zero or more column names, and pass it to `SharedCashBacktestRequest`.
6. Include the requested `metadata_columns` value in `backtest-shared` `run_manifest.json` request payload when `--output-dir` is used.
7. Preserve existing behavior when `--metadata-columns` is omitted.
8. Add focused regression tests:
   - Engine-level output rows include requested metadata columns on orders/trades/failed_orders when available.
   - Missing requested metadata columns are skipped.
   - Default shared-cash output rows are unchanged when metadata columns are omitted.
   - CLI `backtest-shared --metadata-columns <column> --output-dir ...` persists requested metadata in relevant CSV artifacts and records the request.
9. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- No new upstream tables.
- No hardcoded new metadata schema.
- Columns are request-driven and optional.

## API / Interface Changes

- `SharedCashBacktestRequest` may gain an optional `metadata_columns` list.
- CLI `backtest-shared` should accept requested metadata columns, preferably via `--metadata-columns`.
- Shared-cash output rows may include requested metadata columns when those columns exist in the assembled research frame.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_shared.py tests/test_cli.py tests/test_portfolio_io.py -q
```

Run full checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] Existing shared-cash outputs are unchanged when no metadata columns are requested.
- [ ] Requested metadata columns appear in non-empty shared-cash orders/trades/failed_orders rows when present in the research frame.
- [ ] Missing requested metadata columns are skipped without schema guessing.
- [ ] `qre backtest-shared --metadata-columns <column> --output-dir ...` persists metadata columns in CSV outputs and records the requested columns in `run_manifest.json`.
- [ ] Portfolio math, market validation, risk exits, rebalancing, and cash accounting are unchanged.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Copying too many frame columns into outputs could leak factor columns into report artifacts. Keep propagation request-driven.
- Per-trade time-varying metadata semantics can be ambiguous. Treat this task as static symbol metadata passthrough only.
- Keep the implementation small; do not create shared-cash group reports in this task.
- Do not overreach into real benchmark wiring or time-varying status metadata before source schemas are confirmed.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep metadata propagation explicit, additive, and request-driven.
3. Preserve default shared-cash behavior when `metadata_columns` is omitted.
4. Update `01`, `03`, `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
