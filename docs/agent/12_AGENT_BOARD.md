# Agent Board

## Current Task ID

QRE-SHARED-CASH-METADATA-OUTPUTS-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

Implement request-driven metadata passthrough for shared-cash row-level output artifacts.

## Implementation Request

Claude Code should implement `08_IMPLEMENTATION_BRIEF.md` exactly:

1. Add optional requested metadata columns to shared-cash request handling.
2. Build a symbol-keyed metadata lookup from the prepared research frame using requested columns only.
3. Append available requested metadata columns to `orders`, `trades`, and `failed_orders` rows.
4. Add CLI support for `backtest-shared --metadata-columns ...`.
5. Record requested metadata columns in `run_manifest.json` when `--output-dir` is used.
6. Preserve default shared-cash output behavior when no metadata columns are requested.
7. Write `09_CODING_HANDOFF.md` with changed files, validation, risks, and git state.

## Constraints Check

- Do not add shared-cash group-by reports in this task.
- Do not alter shared-cash simulation math, order selection, cash accounting, risk exits, rebalancing, or market validation.
- Do not guess upstream schemas or table names.
- Do not implement time-varying status semantics.
- Keep metadata propagation request-driven and additive.
- Do not push.

## Required Validation

- `uv run pytest tests/test_portfolio_shared.py tests/test_cli.py tests/test_portfolio_io.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Expected Changed Files

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_shared.py`
- `tests/test_cli.py`
- `tests/test_portfolio_io.py` if direct output-file assertions are useful
- `docs/agent/01_CURRENT_STATUS.md`
- `docs/agent/03_ROADMAP.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
