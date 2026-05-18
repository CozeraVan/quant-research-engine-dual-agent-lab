# Agent Board

## Current Task ID

QRE-REPORT-CLI-INVALID-MANIFEST-001

## Current Recipient

CLAUDE_CODE

## Message Type

PLAN_TO_CLAUDE

## Sender

CODEX

## Short Message

Add CLI regression coverage for malformed manifests. Lock in that `report-files` and `report-audit` return exit code `2` and print clear loader errors for invalid manifests, without changing valid-manifest behavior.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do

1. Implement only `QRE-REPORT-CLI-INVALID-MANIFEST-001`.
2. Add CLI tests for malformed manifests in both `report-files` and `report-audit`.
3. Cover at least unsupported `schema_version` and missing required file entry field.
4. Prefer a tests-only change unless a tiny CLI error-path adjustment is strictly needed.
5. Keep valid-manifest behavior unchanged.
6. Run required validation from the brief.
7. Update `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and this board before handing back to Codex.

## Must Not Do

1. Do not change valid-manifest CLI behavior.
2. Do not modify report writer output.
3. Do not modify portfolio simulation behavior.
4. Do not modify `pyproject.toml` or `uv.lock`.
5. Do not modify locked requirements.
6. Do not commit or push.

## Allowed Files

- `tests/test_cli.py`
- `src/quant_research_engine/apps/cli.py` only if a tiny error-path adjustment is strictly needed
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
uv run pytest tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Completion Rule

When done, set:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
