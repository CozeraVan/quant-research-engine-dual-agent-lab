# Task Handoff

## Current Task

Add request-driven metadata passthrough columns to shared-cash order, trade, and failed-order outputs.

## Task ID

QRE-SHARED-CASH-METADATA-OUTPUTS-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex selected this task because real index benchmark wiring and time-varying status metadata remain blocked by unconfirmed source tables.
- Codex inspected the shared-cash engine, CLI, and output writer surfaces.
- Codex prepared `08_IMPLEMENTATION_BRIEF.md`.

## In Progress

- Claude Code should implement the brief and write `09_CODING_HANDOFF.md`.

## Expected Files

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_shared.py`
- `tests/test_cli.py`
- `tests/test_portfolio_io.py` if output-file behavior needs direct coverage
- `docs/agent/01_CURRENT_STATUS.md`
- `docs/agent/03_ROADMAP.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Last completed implementation baseline:

- `uv run pytest tests/test_portfolio_batch.py tests/test_cli.py -q` -> `105 passed`
- `uv run pytest -q` -> `283 passed in 2.67s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

Required validation for this task:

- `uv run pytest tests/test_portfolio_shared.py tests/test_cli.py tests/test_portfolio_io.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Known Risks

- Do not add shared-cash group-by reports in this task.
- Do not change shared-cash portfolio math, order selection, cash accounting, risk exits, rebalancing, or market validation.
- Metadata propagation must be request-driven. Do not copy all factor or market columns into output rows.
- Missing requested columns should be skipped rather than guessed.
- Treat requested metadata columns as static symbol metadata for this task; time-varying metadata semantics remain future work.

## Next Suggested Step

Claude Code should read `11_AGENT_STATE.md`, `12_AGENT_BOARD.md`, and `08_IMPLEMENTATION_BRIEF.md`, then implement `QRE-SHARED-CASH-METADATA-OUTPUTS-001`.
