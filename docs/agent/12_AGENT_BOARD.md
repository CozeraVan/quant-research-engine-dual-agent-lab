# Agent Board

## Current Task ID

QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

Update README and module docs for optional `--run-id` linkage and run-manifest audit usage.

## Implementation Brief

Read `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

Core requirements:

1. Document `--run-id` on durable preflight/eval/backtest commands. ✅ target
2. Document where `run_id` is written. ✅ target
3. Document that omitted `run_id` is stored as null. ✅ target
4. Document `report-audit --role run_manifest` and JSON audit output. ✅ target
5. Document validated run-manifest fields and supported run-manifest kinds. ✅ target
6. Keep examples credential-free. ✅ constraint
7. Do not edit `docs/legacy/**`. ✅ constraint
8. Keep this documentation-only unless blocked. ✅ constraint

## Required Validation

- `scripts/check-progress-docs.sh`
- `git diff --check`
- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` only if code or executable examples are changed

## Expected Changed Files

- `README.md`
- `docs/modules/portfolio_workflow.md`
- `docs/modules/portfolio_layer.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Next Step

Claude Code should implement the brief and write `09_CODING_HANDOFF.md` for Codex review.
