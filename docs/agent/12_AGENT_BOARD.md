# Agent Board

## Current Task ID

QRE-RUN-MANIFEST-CONTENT-VALIDATION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

Implement stricter `run_manifest` content validation for report audit.

## Implementation Brief

Read `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

Core requirements:

1. Add role-specific content validation for `role == "run_manifest"`. ✅ target
2. Validate required top-level fields: `schema_version`, `kind`, `run_id`, `command`, `strategy_path`, `artifacts`. ✅ target
3. Allow `run_id` to be string or null. ✅ constraint
4. Validate `artifacts` is a list of strings. ✅ target
5. Permit `portfolio_backtest_run_manifest` and `evaluation_run_manifest` kinds. ✅ target
6. Preserve generic JSON object validation for summary JSON. ✅ constraint
7. Preserve report manifest file-entry schema and CLI audit issue shape. ✅ constraint

## Required Validation

- `uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Expected Changed Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Next Step

Claude Code should implement the brief and write `09_CODING_HANDOFF.md` for Codex review.
