# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-SCHEMA-VERSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

PLAN_TO_CLAUDE

## Sender

CODEX

## Short Message

Add a deterministic top-level `schema_version: 1` to newly generated batch and shared-cash `report_manifest.json` files. Keep old manifests without this field readable. This is a small reporting/reproducibility task.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do

1. Implement only `QRE-REPORT-MANIFEST-SCHEMA-VERSION-001`.
2. Add top-level `schema_version: 1` to generated batch and shared-cash report manifests.
3. Preserve existing `kind` and `files` behavior.
4. Keep older manifests without `schema_version` readable.
5. Add/update focused tests from the brief.
6. Run required validation from the brief.
7. Update `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and this board before handing back to Codex.

## Must Not Do

1. Do not add timestamps, command lines, git SHAs, hostnames, usernames, or environment-dependent metadata.
2. Do not change CLI flags or output semantics.
3. Do not modify `pyproject.toml` or `uv.lock`.
4. Do not modify locked requirements.
5. Do not commit or push.

## Allowed Files

- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py` if needed
- `tests/test_portfolio_io.py`
- `tests/test_portfolio_report_manifest.py` or `tests/test_cli.py` if needed
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
uv run pytest tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Completion Rule

When done, set:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
