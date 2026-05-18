# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-SCHEMA-JSON-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Newly generated batch and shared-cash report manifests now include top-level `schema_version: 1`. The manifest helper and JSON CLI outputs are used by scripts for report discovery and audit checks. Exposing the manifest schema version through those structured paths gives downstream automation a stable way to inspect versioned manifests without parsing raw JSON separately.

## Goal

Expose the optional manifest `schema_version` through `ReportManifest` and include it in `qre report-files --json` and `qre report-audit --json` output.

## Non-Goals

- Do not change text output for `qre report-files` or `qre report-audit`.
- Do not change report file selection, filtering, path resolution, or validation behavior.
- Do not change generated manifest file entry shape.
- Do not change portfolio simulation behavior.
- Do not add timestamps, command lines, git SHAs, hostnames, usernames, or other environment-dependent metadata.
- Do not add database access.
- Do not modify old root progress docs.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/report_manifest.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`

Docs/handoff:

- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve report artifact and manifest discovery contracts.
- Preserve old manifest readability.
- Keep the change additive and deterministic.
- No database writes or credential handling.

## Implementation Steps

1. Inspect `ReportManifest.from_path(...)` and the `report-files` / `report-audit` JSON branches in `apps/cli.py`.
2. Add an optional `schema_version` attribute to `ReportManifest`.
3. Load top-level `schema_version` from the manifest payload when present.
4. Preserve old manifest compatibility by setting `schema_version` to `None` when the field is missing.
5. Add `"schema_version": manifest.schema_version` to:
   - `qre report-files --json`;
   - `qre report-audit --json`.
6. Do not add the field to text-mode output.
7. Add/update focused tests:
   - `ReportManifest.from_path(...)` exposes `schema_version == 1` when present;
   - old manifest JSON without `schema_version` exposes `schema_version is None`;
   - `report-files --json` includes `"schema_version": 1`;
   - `report-audit --json` includes `"schema_version": 1`;
   - one JSON CLI path with an old manifest includes `"schema_version": null`.
8. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

No generated report file schema change is required by this task. This task only exposes an already-generated optional manifest field through helper and CLI JSON output.

Structured CLI JSON output should become additive:

```json
{
  "manifest_kind": "...",
  "schema_version": 1
}
```

For old manifests without the field:

```json
{
  "schema_version": null
}
```

## API / Interface Changes

Additive Python helper field:

- `ReportManifest.schema_version: int | None`

Additive CLI JSON field:

- `schema_version`

No text CLI output changes.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q
```

Run full tests:

```bash
uv run pytest -q
```

Run workflow checks:

```bash
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `ReportManifest.from_path(...)` exposes `schema_version == 1` for versioned manifests.
- [ ] `ReportManifest.from_path(...)` exposes `schema_version is None` for old manifests without the field.
- [ ] `qre report-files --json` includes top-level `"schema_version"`.
- [ ] `qre report-audit --json` includes top-level `"schema_version"`.
- [ ] Text-mode `report-files` and `report-audit` output is unchanged.
- [ ] Existing filtering, path resolution, validation, and exit-code behavior is preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Avoid treating old manifests as invalid.
- Avoid changing text output used by existing shell workflows.
- Avoid renaming existing JSON keys.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Avoid unrelated refactors.
3. Avoid modifying forbidden files.
4. Stop and ask if the brief conflicts with existing code.
5. Run validation commands where possible.
6. Update:
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/12_AGENT_BOARD.md`

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
