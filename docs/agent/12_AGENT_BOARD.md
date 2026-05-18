# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-SCHEMA-JSON-001

## Current Recipient

CLAUDE_CODE

## Message Type

PLAN_TO_CLAUDE

## Sender

CODEX

## Short Message

Expose manifest `schema_version` through `ReportManifest` and the two JSON report tooling commands. Keep this additive: old manifests should show `schema_version: null`, text output must remain unchanged, and report filtering/validation behavior must not change.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do

1. Implement only `QRE-REPORT-MANIFEST-SCHEMA-JSON-001`.
2. Add optional `ReportManifest.schema_version`.
3. Include top-level `schema_version` in `qre report-files --json`.
4. Include top-level `schema_version` in `qre report-audit --json`.
5. Preserve old manifests without the field as readable and represented as JSON `null`.
6. Add focused tests from the brief.
7. Run required validation from the brief.
8. Update `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and this board before handing back to Codex.

## Must Not Do

1. Do not change text output for `report-files` or `report-audit`.
2. Do not change filtering, path resolution, validation, or exit-code behavior.
3. Do not add timestamps, command lines, git SHAs, hostnames, usernames, or environment-dependent metadata.
4. Do not modify `pyproject.toml` or `uv.lock`.
5. Do not modify locked requirements.
6. Do not commit or push.

## Allowed Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Completion Rule

When done, set:

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
