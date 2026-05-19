# Agent Board

## Current Task ID

QRE-EVAL-METADATA-GROUP-SUMMARY-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

New implementation task is ready. Please implement evaluation metadata group summaries from `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

## Implementation Summary

Codex has prepared the next self-contained task from roadmap M3.5:

1. Add optional grouping columns to evaluation requests.
2. Preserve requested group labels in signal events.
3. Add `EvaluationResult.group_summary`.
4. Summarize event forward returns by group column, group value, and horizon.
5. Expose grouping through `qre eval-config --group-by ...`.
6. Add focused engine and CLI regression tests.

## Constraints Check

- Scope should stay in evaluation models/engine, eval-config CLI, and focused tests.
- Existing evaluation behavior must remain unchanged when grouping is omitted.
- Group columns must already exist in the research frame.
- No new database schema, new data adapter, benchmark comparison, or factor-decay work.
- Do not push.

## Expected Changed Files

- `src/quant_research_engine/evaluation/models.py`
- `src/quant_research_engine/evaluation/engine.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_evaluation_forward_returns.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
uv run pytest tests/test_evaluation_forward_returns.py -q
uv run pytest tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```
