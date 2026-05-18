# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-SCHEMA-DOCS-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Report manifests now include deterministic `schema_version: 1`, and JSON report tooling exposes the optional schema version as `schema_version` with `null` for older manifests. The README and portfolio workflow docs should document this stable field so downstream users know how to consume it.

## Goal

Document report manifest `schema_version` behavior in user-facing and workflow documentation.

## Non-Goals

- Do not change business code.
- Do not change tests unless a documentation example requires a small fixture adjustment.
- Do not change CLI flags, CLI behavior, or generated artifacts.
- Do not change manifest schema beyond documentation.
- Do not add timestamps, command lines, git SHAs, hostnames, usernames, or environment-dependent metadata.
- Do not add database access.
- Do not modify old root progress docs.

## Affected Modules

Expected:

- `README.md`
- `docs/modules/portfolio_workflow.md`

Docs/handoff:

- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `src/**`
- `tests/**` unless a documentation example requires a minimal matching adjustment
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
- Keep documentation factual and deterministic.
- Do not present smoke outputs as research conclusions.

## Implementation Steps

1. Inspect the existing report artifact sections in `README.md`.
2. Add concise documentation that newly generated batch and shared-cash manifests include top-level `"schema_version": 1`.
3. Document that old manifests without the field remain readable and appear as `null` in JSON CLI output.
4. Update the JSON CLI description so `report-files --json` and `report-audit --json` list `schema_version` among top-level fields.
5. Update `docs/modules/portfolio_workflow.md` to record the implemented manifest schema version and JSON exposure behavior.
6. Keep examples short; do not add new operational claims, performance claims, or data-source assumptions.
7. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This is a documentation-only task.

## API / Interface Changes

None. This task documents existing behavior.

## Validation Plan

Run documentation checks:

```bash
rg -n "schema_version" README.md docs/modules/portfolio_workflow.md
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

- [ ] README documents top-level `schema_version: 1` in new manifests.
- [ ] README documents that old manifests without the field remain readable and expose JSON `null`.
- [ ] README JSON CLI field lists include `schema_version`.
- [ ] `docs/modules/portfolio_workflow.md` records manifest schema versioning and JSON exposure.
- [ ] No business code is modified.
- [ ] Full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Avoid overstating reproducibility guarantees. `schema_version` is a schema marker, not a full experiment archive.
- Avoid changing examples in a way that implies new CLI flags or behavior.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Avoid unrelated documentation rewrites.
3. Avoid modifying forbidden files.
4. Stop and ask if the brief conflicts with existing docs.
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
