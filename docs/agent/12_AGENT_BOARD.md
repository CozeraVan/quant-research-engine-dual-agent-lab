# Agent Board

## Current Task ID

QRE-REPORT-FILES-REQUIRE-MATCH-001

## Current Recipient

USER

## Message Type

REVIEW_TO_USER

## Sender

CODEX

## Short Message

Review passed for `QRE-REPORT-FILES-REQUIRE-MATCH-001`. Codex will commit locally and prepare the next Claude Code task. No push.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do

1. Implement only `QRE-REPORT-FILES-REQUIRE-MATCH-001`.
2. Add the optional `--require-match` flag to `report-files`.
3. Return exit code `2` and stderr `no manifest entries matched filters` when the flag is set and filters match zero entries.
4. Preserve existing default zero-match behavior.
5. Add focused CLI tests and run the validation commands in the brief.
6. Update `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and this board before handing back to Codex.

## Must Not Do

1. Do not change report artifact generation.
2. Do not change manifest JSON shape.
3. Do not change `report-audit` behavior.
4. Do not modify `pyproject.toml` or `uv.lock`.
5. Do not commit or push.

## Allowed Files

- `src/quant_research_engine/apps/cli.py`
- `tests/test_cli.py`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- `.env`
- `.env.*`
- upstream data producer projects
- old root progress docs

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
