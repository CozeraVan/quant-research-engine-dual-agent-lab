# Implementation Brief

## Task ID

QRE-PORTFOLIO-FAILED-ORDER-DIAGNOSTICS-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`quant-research-engine` already has an advanced portfolio MVP: single-symbol, batch, and shared-cash backtests; A-share market profile validation; costs, slippage, lot sizing, price-limit checks; risk exits, rebalance, FIFO lot accounting, and T+1 sellable inventory; failed order output and some failed rebalance summary fields.

The next self-contained improvement is to make failed-order diagnostics more useful for research acceptance and debugging without changing simulation semantics.

## Goal

Enhance shared-cash failed-order diagnostics and summary/report output so users can quickly see why orders failed, how often each reason occurred, and whether failures came from entry, exit, risk-control, or rebalance paths.

## Non-Goals

- Do not change order execution semantics.
- Do not add real index benchmark wiring.
- Do not add real metadata adapters for suspension/ST/risk-warning.
- Do not alter indicator computation or factor loading behavior.
- Do not rewrite portfolio architecture.
- Do not modify old Markdown docs outside `docs/agent` unless explicitly asked.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/apps/cli.py` only if output display needs small additions
- portfolio tests related to shared-cash and report output

Maybe:

- `src/quant_research_engine/portfolio/analytics.py` if diagnostics are best implemented as reusable summary helpers
- `src/quant_research_engine/portfolio/report_manifest.py` only if new output files are added

## Files Likely to Change

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/portfolio/io.py`
- `tests/test_portfolio_shared.py`
- `tests/test_portfolio_io.py`
- `tests/test_cli.py`

## Forbidden Files

- `uv.lock`
- `pyproject.toml` unless dependency-free implementation becomes impossible
- upstream data producer projects
- database credentials or `.env*`
- old root progress docs unless the user separately requests archival or synchronization

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve simulation behavior unless a test demonstrates the current behavior is a diagnostics bug rather than execution semantics.
- No lookahead bias.
- No hidden indicator recomputation.
- No upstream database writes.
- Keep A-share market constraints in market/profile validation paths, not strategy rules.
- Preserve existing report manifest behavior.

## Implementation Steps

1. Inspect current failed order model/output in shared-cash backtests.
2. Write failing tests for the desired diagnostics before implementation.
3. Add or extend summary fields, such as:
   - total failed order count
   - failed order count by `reason`
   - failed order count by `failure_reason`
   - failed order attempted notional by `reason`
   - failed order attempted notional by `failure_reason`
   - separate rebalance failed counts must remain compatible with existing fields
4. Ensure `failed_orders.csv` continues to include enough fields for row-level debugging.
5. Include the new diagnostics in `summary.json`.
6. Include readable diagnostics in shared-cash `summary.md`.
7. If new files are added, include them in `report_manifest.json`; otherwise preserve manifest schema.
8. Update `09_CODING_HANDOFF.md`, `04_TASK_HANDOFF.md`, `05_PROGRESS.md`, and `11_AGENT_STATE.md` after implementation.

## Data / Schema Changes

No database schema changes. No upstream data writes.

## API / Interface Changes

Allowed:

- Add new keys to shared-cash summary output.
- Add new human-readable sections to shared-cash Markdown summary.

Avoid:

- Renaming existing summary keys.
- Removing existing columns from output files.
- Changing CLI command names or required arguments.

## Validation Plan

Run focused tests first:

```bash
uv run pytest tests/test_portfolio_shared.py tests/test_portfolio_io.py -q
```

Run related CLI/report tests:

```bash
uv run pytest tests/test_portfolio_shared.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
```

Run full test suite before handoff if practical:

```bash
uv run pytest -q
```

Optional smoke after tests, if local DB access is available:

```bash
QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' uv run qre backtest-shared \
  examples/rsi2_reversal_with_rebalance.yaml \
  --start 2026-05-11 \
  --end 2026-05-15 \
  --codes 000001.SZ 000002.SZ 600000.SH \
  --initial-cash 100000 \
  --max-positions 2 \
  --market-profile configs/market_profiles/ashare_daily_default.yaml \
  --output-dir outputs/smoke_shared_failed_order_diagnostics
```

## Acceptance Criteria

- [ ] Failed-order diagnostics are available in machine-readable `summary.json`.
- [ ] Shared-cash Markdown summary shows readable failed-order diagnostics.
- [ ] Existing failed rebalance summary fields are preserved.
- [ ] Existing report manifest behavior remains valid.
- [ ] Focused and related tests pass, or any unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` clearly lists changed files, validation, risks, and git status.

## Risks

- Overloading `reason` and `failure_reason` could create ambiguous summaries. Prefer explicit naming in new summary keys.
- Some failed order paths may not have attempted notional populated consistently. If so, record zero or `None` consistently and document the choice.
- Markdown output should remain concise; avoid turning reports into raw debug dumps.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Avoid unrelated refactors.
3. Avoid modifying forbidden files.
4. Stop and ask if the brief conflicts with existing code.
5. Run validation commands where possible.
6. Update:
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/11_AGENT_STATE.md`
7. If architecture changes, also update:
   - `docs/agent/06_DECISION_LOG.md`

## Next Agent State After Brief Is Approved

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
