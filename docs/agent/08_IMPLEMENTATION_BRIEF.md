# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-SCHEMA-VERSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Report manifests are now the stable entry point for report discovery, audit, strict matching, and JSON CLI output. `docs/modules/module_boundaries.md` says reports should include enough metadata to reproduce an experiment. A small first step is to add a stable manifest schema marker to newly generated manifests without changing file discovery behavior.

## Goal

Add a top-level `schema_version` field to newly generated batch and shared-cash `report_manifest.json` files, while keeping existing manifests without this field readable.

## Non-Goals

- Do not add timestamps, command lines, git SHAs, hostnames, usernames, or other environment-dependent metadata.
- Do not change manifest file entry shape.
- Do not change `qre report-files` or `qre report-audit` output semantics beyond continuing to read the manifest.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not modify old root progress docs.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py` only if needed for explicit version handling
- `tests/test_portfolio_io.py`
- `tests/test_portfolio_report_manifest.py` or `tests/test_cli.py` only if needed

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

1. Inspect current manifest generation in `portfolio/io.py`.
2. Add top-level `schema_version: 1` to:
   - batch manifest payloads;
   - shared-cash manifest payloads.
3. Keep existing `kind` and `files` keys unchanged.
4. Ensure `ReportManifest.from_path(...)` continues to load manifests that do not include `schema_version`.
5. If explicit version validation is added, accept only missing version or `1`; keep error messages clear. If no validation is needed, document that the helper treats the field as optional metadata.
6. Add/update focused tests:
   - generated batch manifest includes `schema_version == 1`;
   - generated shared-cash manifest includes `schema_version == 1`;
   - old manifest JSON without `schema_version` still loads and filters.
7. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

Additive report artifact schema change:

```json
{
  "schema_version": 1,
  "kind": "...",
  "files": []
}
```

Existing manifests without `schema_version` must remain readable.

## API / Interface Changes

No CLI flag changes.

No changes to generated CSV/Markdown/summary fields.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py -q
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

- [ ] New batch `report_manifest.json` includes top-level `schema_version: 1`.
- [ ] New shared-cash `report_manifest.json` includes top-level `schema_version: 1`.
- [ ] Existing manifest fixtures without `schema_version` still load through `ReportManifest.from_path(...)`.
- [ ] Existing manifest filtering and path resolution behavior is preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Avoid making old manifests invalid.
- Avoid introducing nondeterministic metadata into report artifacts.

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
