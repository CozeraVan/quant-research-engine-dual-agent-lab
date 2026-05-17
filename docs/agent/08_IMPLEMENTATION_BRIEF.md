# Implementation Brief

## Task ID

QRE-REPORT-AUDIT-FAILED-ORDERS-SCHEMA-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`QRE-PORTFOLIO-FAILED-ORDER-DIAGNOSTICS-001` added richer failed-order diagnostics to shared-cash portfolio summaries and reports. The next low-risk reporting robustness task is to make `failed_orders.csv` output structurally reliable and auditable.

Current report content validation checks required CSV columns for several roles, but `failed_orders` has no required columns. Empty failed-order outputs can therefore be hard to inspect or audit consistently.

## Goal

Standardize failed-order report CSV schema and strengthen manifest content validation so `qre report-audit` can catch malformed `failed_orders.csv` artifacts.

## Non-Goals

- Do not change portfolio execution semantics.
- Do not change order validation rules.
- Do not add database access or upstream data writes.
- Do not add benchmark wiring.
- Do not add real suspension/ST/risk-warning metadata adapters.
- Do not rewrite report manifest architecture.
- Do not change CLI command names.
- Do not modify old root progress docs.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_io.py`
- `tests/test_cli.py`

Maybe:

- `src/quant_research_engine/portfolio/single_symbol.py`
- `src/quant_research_engine/portfolio/shared.py`
- `tests/test_portfolio_shared.py`

Only touch engine modules if needed to produce stable empty-result schemas. Prefer IO-layer normalization if that preserves runtime result objects more cleanly.

## Files Likely to Change

- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_io.py`
- `tests/test_cli.py`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- upstream data producer projects
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve simulation behavior.
- No lookahead bias.
- No hidden indicator recomputation.
- No upstream database writes.
- Preserve existing report manifest discovery behavior.
- Keep changes narrowly scoped to report output/schema validation.

## Implementation Steps

1. Inspect current failed-order row shapes for single-symbol and shared-cash results.
2. Define a stable failed-order CSV column set. Expected baseline:
   - `symbol`
   - `trade_date`
   - `side`
   - `quantity`
   - `price`
   - `notional`
   - `reason`
3. If shared-cash uses `failure_reason`, preserve it as an additional column. Do not remove existing `reason` or `failure_reason` fields from outputs.
4. Ensure `write_single_symbol_result()` and `write_shared_cash_result()` write `failed_orders.csv` with stable headers even when there are zero failed orders.
5. Update report manifest content validation so role `failed_orders` requires the stable baseline columns.
6. Add tests that:
   - single-symbol output with no failed orders still writes `failed_orders.csv` with stable headers;
   - shared-cash output with no failed orders still writes `failed_orders.csv` with stable headers;
   - `qre report-audit` passes for a valid `failed_orders.csv`;
   - `qre report-audit` fails with `missing_columns` when `failed_orders.csv` is malformed.
7. Update `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and `docs/agent/12_AGENT_BOARD.md` after implementation.

## Data / Schema Changes

No database schema changes.

Report artifact schema change:

- `failed_orders.csv` should consistently include stable headers.
- Existing row-level fields must not be removed.

## API / Interface Changes

Allowed:

- Strengthen report content validation for `failed_orders.csv`.
- Add helper functions in `portfolio/io.py` for stable CSV output.

Avoid:

- Changing CLI command names or required arguments.
- Changing manifest JSON shape.
- Renaming existing failed-order columns.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_io.py tests/test_cli.py -q
```

Run the full suite:

```bash
uv run pytest -q
```

Run workflow checks:

```bash
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `failed_orders.csv` has stable headers when no failed orders exist.
- [ ] Existing failed-order row fields remain available.
- [ ] `qre report-audit` detects missing required failed-order CSV columns.
- [ ] Valid report manifests with valid failed-order files still pass audit.
- [ ] No portfolio simulation behavior changes.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Tightening validation may expose previously weak report artifacts. Keep the required baseline minimal to avoid unnecessary breakage.
- Single-symbol and shared-cash failed-order rows are not identical. Preserve both shapes while enforcing only shared baseline columns.
- Empty DataFrames can produce CSV files with no headers unless explicitly normalized.

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
   - `docs/agent/12_AGENT_BOARD.md`
7. If architecture changes, also update:
   - `docs/agent/06_DECISION_LOG.md`

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
