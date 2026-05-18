# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-SCHEMA-DOCS-001

## Current Recipient

CLAUDE_CODE

## Message Type

PLAN_TO_CLAUDE

## Sender

CODEX

## Short Message

Document manifest `schema_version` behavior in README and portfolio workflow docs. This is a docs-only task: no business code, no CLI behavior changes, no generated artifact changes.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do

1. Implement only `QRE-REPORT-MANIFEST-SCHEMA-DOCS-001`.
2. Document that new report manifests include top-level `schema_version: 1`.
3. Document that old manifests without the field remain readable and emit JSON `null`.
4. Update JSON CLI field descriptions for `report-files --json` and `report-audit --json`.
5. Update `docs/modules/portfolio_workflow.md` with the implemented behavior.
6. Run required validation from the brief.
7. Update `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and this board before handing back to Codex.

## Must Not Do

1. Do not modify business code.
2. Do not change CLI behavior, flags, tests, or generated artifacts unless a documentation example strictly requires it.
3. Do not overstate reproducibility guarantees.
4. Do not modify `pyproject.toml` or `uv.lock`.
5. Do not modify locked requirements.
6. Do not commit or push.

## Allowed Files

- `README.md`
- `docs/modules/portfolio_workflow.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
rg -n "schema_version" README.md docs/modules/portfolio_workflow.md
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Completion Rule

When done, set:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
