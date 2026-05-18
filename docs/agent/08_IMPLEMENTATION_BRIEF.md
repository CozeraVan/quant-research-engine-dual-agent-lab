# Implementation Brief

## Task ID

QRE-REPORT-CLI-INVALID-MANIFEST-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Manifest loader validation has been tightened for schema version and required file entry fields. The CLI commands `qre report-files` and `qre report-audit` already catch loader exceptions and print errors, but that command-level behavior is not yet explicitly covered for malformed manifests.

## Goal

Add focused CLI regression tests for malformed manifests so command-boundary behavior is locked in.

## Non-Goals

- Do not change valid-manifest behavior.
- Do not change CLI flags.
- Do not change report writer output.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not modify old root progress docs.

## Affected Modules

Expected:

- `tests/test_cli.py`
- `src/quant_research_engine/apps/cli.py` only if a tiny error-path adjustment is needed

Docs/handoff:

- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `src/**` unless a tiny error-path adjustment is strictly needed
- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve report artifact and manifest discovery contracts for valid manifests.
- Keep malformed-manifest CLI errors deterministic and clear.
- No database writes or credential handling.

## Implementation Steps

1. Inspect existing invalid-manifest CLI tests in `tests/test_cli.py`.
2. Add focused CLI tests that verify malformed-manifest loader errors propagate cleanly through:
   - `report-files`;
   - `report-audit`.
3. Cover at least:
   - unsupported `schema_version`;
   - missing required file entry field such as `path`.
4. Expected command behavior:
   - exit code `2`;
   - no traceback assertions needed;
   - stderr contains the clear loader error text.
5. If current CLI behavior already satisfies this without code changes, keep the task test-only.
6. If a tiny CLI error-path adjustment is required to make messages clear and deterministic, keep it narrowly scoped.
7. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task only adds CLI regression coverage.

## API / Interface Changes

None intended. This task verifies existing CLI behavior for malformed manifests.

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

- [ ] `report-files` malformed-manifest tests verify exit code `2` and clear stderr.
- [ ] `report-audit` malformed-manifest tests verify exit code `2` and clear stderr.
- [ ] Unsupported `schema_version` is covered at the CLI boundary.
- [ ] Missing required file entry field is covered at the CLI boundary.
- [ ] No valid-manifest CLI behavior changes.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Avoid changing current CLI behavior for valid manifests.
- Keep CLI malformed-manifest assertions resilient to formatting, but specific enough to catch regressions.

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
