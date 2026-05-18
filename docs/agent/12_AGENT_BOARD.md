# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-SCHEMA-VALIDATION-001

## Current Recipient

CLAUDE_CODE

## Message Type

PLAN_TO_CLAUDE

## Sender

CODEX

## Short Message

Add explicit manifest schema-version validation. Accept old manifests with no `schema_version` and current manifests with `schema_version: 1`; reject unsupported present values with a clear error. Keep valid manifest CLI output unchanged.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do

1. Implement only `QRE-REPORT-MANIFEST-SCHEMA-VALIDATION-001`.
2. Validate top-level `schema_version` in `ReportManifest.from_path(...)`.
3. Accept missing version and integer `1`.
4. Reject unsupported present values, including `2` and `"1"`, with a clear `ValueError`.
5. Preserve existing kind validation, file-entry loading, filtering, path resolution, and valid-manifest CLI behavior.
6. Add focused tests from the brief.
7. Run required validation from the brief.
8. Update `docs/agent/09_CODING_HANDOFF.md`, `docs/agent/04_TASK_HANDOFF.md`, `docs/agent/05_PROGRESS.md`, `docs/agent/11_AGENT_STATE.md`, and this board before handing back to Codex.

## Must Not Do

1. Do not modify report writer output.
2. Do not change CLI flags or valid-manifest text/JSON output.
3. Do not modify portfolio simulation behavior.
4. Do not modify `pyproject.toml` or `uv.lock`.
5. Do not modify locked requirements.
6. Do not commit or push.

## Allowed Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py` only if useful for CLI error behavior
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
