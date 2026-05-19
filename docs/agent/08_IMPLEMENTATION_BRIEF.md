# Implementation Brief

## Task ID

QRE-REPORT-FILES-JSON-CHECK-EXISTS-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`qre report-files --check-exists` already has non-JSON CLI coverage for existing and missing matched files. JSON mode also supports `--check-exists`: it emits the normal JSON payload to stdout, then returns exit code `2` and writes missing paths to stderr when matched files are absent. That JSON-mode behavior is useful for script consumers but is not directly locked by regression tests.

## Goal

Add CLI regression coverage for `report-files --json --check-exists` while preserving existing JSON output and missing-path behavior.

## Non-Goals

- Do not change valid-manifest behavior.
- Do not change CLI flags or normal CLI output for valid manifests.
- Do not change report writer output.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not broaden this into report-files redesign.
- Do not modify CLI or loader code unless a tiny adjustment is strictly necessary.

## Affected Modules

Expected:

- `tests/test_cli.py`

Optional only if strictly needed:

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/report_manifest.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `src/**` outside `apps/cli.py` and `portfolio/report_manifest.py`
- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve report-files path resolution and JSON output behavior.
- Preserve missing-path stderr and exit-code behavior.
- No database writes or credential handling.
- No unrelated CLI or reporting refactors.

## Implementation Steps

1. Inspect existing `report-files --check-exists` and `report-files --json` tests in `tests/test_cli.py`.
2. Add coverage for `report-files --json --check-exists` when matched files exist: exit code `0`, no stderr, JSON payload includes matched file metadata.
3. Add coverage for `report-files --json --check-exists` when a matched file is missing: exit code `2`, stdout remains the normal JSON payload, and stderr contains the missing path.
4. Do not modify CLI or loader code unless the tests expose a real bug that must be fixed.
5. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task adds regression coverage only unless a tiny bugfix is required.

## API / Interface Changes

Valid CLI behavior should remain unchanged.

`report-files --json --check-exists` should continue emitting JSON stdout before returning non-zero for missing files.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_cli.py -q
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

- [ ] `report-files --json --check-exists` exits `0` with no stderr when matched files exist.
- [ ] `report-files --json --check-exists` exits `2` and writes the missing path to stderr when a matched file is absent.
- [ ] Missing-file JSON mode still emits the normal stdout payload with `matched_files` and `files`.
- [ ] Existing non-JSON `--check-exists` behavior remains unchanged.
- [ ] Existing JSON `--require-match` behavior remains unchanged.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep the new work scoped to CLI regression coverage.
- Avoid changing stdout/stderr ordering in JSON mode.
- Do not introduce CLI behavior changes for valid manifests.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Avoid unrelated refactors.
3. Avoid modifying forbidden files.
4. Stop and ask if the brief conflicts with existing code.
5. Run validation commands where possible.
6. Update:
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/12_AGENT_BOARD.md`

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
