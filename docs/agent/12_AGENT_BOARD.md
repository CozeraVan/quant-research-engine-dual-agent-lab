# Agent Board

## Current Task ID

QRE-DOCS-EVAL-ARTIFACTS-USAGE-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

Update README and module docs for evaluation artifacts and diagnostics.

## Implementation Brief

Read `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

Core requirements:

1. Document `qre eval-config --output-dir` artifacts. ✅ target
2. Document evaluation report roles for `report-files` / `report-audit`. ✅ target
3. Include concise examples for output-dir, group-by, random baseline, and factor decay discovery/audit. ✅ target
4. Explain factor decay is derived from existing IC/Rank IC horizons. ✅ target
5. Explain random baseline is deterministic when a seed is provided. ✅ target
6. State diagnostics do not prove factor or strategy effectiveness. ✅ constraint
7. Keep examples credential-free. ✅ constraint
8. Do not edit `docs/legacy/**`. ✅ constraint
9. Keep this documentation-only unless blocked. ✅ constraint

## Required Validation

- `scripts/check-progress-docs.sh`
- `git diff --check`
- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` only if code or executable examples are changed

## Expected Changed Files

- `README.md`
- `docs/modules/data_layer.md`
- `docs/modules/portfolio_workflow.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Next Step

Claude Code should implement the brief and write `09_CODING_HANDOFF.md` for Codex review.
