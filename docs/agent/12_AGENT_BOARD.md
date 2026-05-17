# Agent Board

## Current Task ID

QRE-REPORT-AUDIT-FAILED-ORDERS-SCHEMA-001

## Current Recipient

CLAUDE_CODE

## Message Type

PLAN_TO_CLAUDE

## Sender

CODEX

## Short Message

Implement the approved brief to standardize failed-order CSV headers and strengthen report-audit validation. Keep the change narrow and do not alter portfolio simulation behavior.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do

1. Implement only `QRE-REPORT-AUDIT-FAILED-ORDERS-SCHEMA-001`.
2. Ensure empty `failed_orders.csv` files still have stable headers.
3. Add failed-order CSV column validation to report manifest content audit.
4. Add focused IO/CLI tests and run the validation commands in the brief.
5. Update `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and this board before handing back to Codex.

## Must Not Do

1. Do not change portfolio execution semantics.
2. Do not change order validation rules.
3. Do not add database writes or read credentials.
4. Do not modify `pyproject.toml` or `uv.lock`.
5. Do not commit or push.

## Allowed Files

- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `src/quant_research_engine/portfolio/single_symbol.py` only if stable empty schemas cannot be handled cleanly in IO
- `src/quant_research_engine/portfolio/shared.py` only if stable empty schemas cannot be handled cleanly in IO
- `tests/test_portfolio_io.py`
- `tests/test_cli.py`
- `tests/test_portfolio_shared.py` only if needed
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- `.env`
- `.env.*`
- upstream data producer projects
- old root progress docs

## Required Validation

```bash
uv run pytest tests/test_portfolio_io.py tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Completion Rule

When done, set:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
