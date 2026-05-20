# Task Handoff

## Current Task

Add shared-cash metadata group summary reports for orders, trades, and failed orders.

## Task ID

QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex finalized `QRE-SHARED-CASH-METADATA-OUTPUTS-001`.
- Codex selected the next unblocked follow-up: grouped shared-cash diagnostics over requested row metadata.
- Codex prepared `08_IMPLEMENTATION_BRIEF.md`.

## In Progress

- Claude Code should implement the brief and write `09_CODING_HANDOFF.md`.

## Expected Files

- `src/quant_research_engine/portfolio/analytics.py`
- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_analytics.py`
- `tests/test_portfolio_io.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Last finalized implementation baseline:

- `uv run pytest tests/test_portfolio_shared.py tests/test_cli.py tests/test_portfolio_io.py -q` -> `142 passed in 2.18s`
- `uv run pytest -q` -> `293 passed in 2.80s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

Required validation for this task:

- `uv run pytest tests/test_portfolio_analytics.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Known Risks

- Do not implement shared-cash return attribution, holdings exposure, or group equity curves in this task.
- Do not change shared-cash simulation math or row-level metadata passthrough.
- Group summaries must be based only on existing output rows and requested group columns.
- Missing requested group columns should fail clearly for grouped summaries.
- Report manifest roles and validation must remain compatible with `report-files` and `report-audit`.

## Next Suggested Step

Claude Code should read `11_AGENT_STATE.md`, `12_AGENT_BOARD.md`, and `08_IMPLEMENTATION_BRIEF.md`, then implement `QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001`.
