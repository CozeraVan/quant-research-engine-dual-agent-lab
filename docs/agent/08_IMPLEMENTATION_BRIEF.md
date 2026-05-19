# Implementation Brief

## Task ID

QRE-REPORT-FILES-JSON-VALIDATE-CONTENTS-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`qre report-files --validate-contents` already has non-JSON CLI coverage for valid report files and structural content issues. JSON mode also supports `--validate-contents`: it emits the normal JSON payload to stdout, then returns exit code `2` and writes validation issues to stderr when matched files have structural problems. That JSON-mode behavior is useful for script consumers but is not directly locked by regression tests.

## Goal

Add CLI regression coverage for `report-files --json --validate-contents` while preserving existing JSON output and validation-issue stderr behavior.

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
- Preserve validation-issue stderr and exit-code behavior.
- No database writes or credential handling.
- No unrelated CLI or reporting refactors.

## Implementation Steps

1. Inspect existing `report-files --validate-contents` and `report-files --json` tests in `tests/test_cli.py`.
2. Add coverage for `report-files --json --validate-contents` when matched report files are structurally valid: exit code `0`, no stderr, JSON payload includes matched file metadata.
3. Add coverage for `report-files --json --validate-contents` when a matched report file has a structural issue: exit code `2`, stdout remains the normal JSON payload, and stderr contains the validation issue fields.
4. Do not modify CLI or loader code unless the tests expose a real bug that must be fixed.
5. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task adds regression coverage only unless a tiny bugfix is required.

## API / Interface Changes

Valid CLI behavior should remain unchanged.

`report-files --json --validate-contents` should continue emitting JSON stdout before returning non-zero for validation issues.

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

- [ ] `report-files --json --validate-contents` exits `0` with no stderr when matched report files are valid.
- [ ] `report-files --json --validate-contents` exits `2` and writes validation issue fields to stderr when a matched report file has structural issues.
- [ ] Validation-failure JSON mode still emits the normal stdout payload with `matched_files` and `files`.
- [ ] Existing non-JSON `--validate-contents` behavior remains unchanged.
- [ ] Existing JSON `--check-exists` and `--require-match` behavior remains unchanged.
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
