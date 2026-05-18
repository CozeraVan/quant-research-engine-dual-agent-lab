# Agent Board

## Current Task ID

QRE-REPORT-DOCS-JSON-CLI-001

## Current Recipient

CLAUDE_CODE

## Message Type

PLAN_TO_CLAUDE

## Sender

CODEX

## Short Message

Update README Report Artifact Checks so users can discover `report-files --require-match`, `report-files --json`, and `report-audit --json`. This is docs-only; do not modify business code.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do

1. Implement only `QRE-REPORT-DOCS-JSON-CLI-001`.
2. Update README Report Artifact Checks with concise examples for strict matching and JSON output.
3. Preserve existing examples.
4. Run required validation from the brief.
5. Update `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and this board before handing back to Codex.

## Must Not Do

1. Do not modify `src/**`.
2. Do not modify `tests/**` unless a doc validation test requires it.
3. Do not modify `pyproject.toml` or `uv.lock`.
4. Do not modify locked requirements.
5. Do not commit or push.

## Allowed Files

- `README.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
scripts/check-progress-docs.sh
git diff --check
```

Optional:

```bash
uv run pytest -q
```

## Completion Rule

When done, set:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
