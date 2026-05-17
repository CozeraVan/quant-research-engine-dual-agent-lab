# Implementation Brief

## Task ID

QRE-REPORT-FILES-REQUIRE-MATCH-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`qre report-audit` already supports `--require-match`, which makes filtered manifest checks fail when no entries match. `qre report-files` currently allows zero matches by default and has no equivalent strict mode.

Adding `--require-match` to `report-files` is a small reporting workflow improvement that helps scripts fail fast when a caller expects a specific role, symbol, window, or group output to exist.

## Goal

Add a `--require-match` option to `qre report-files` that returns a non-zero exit code when the selected filters match no manifest entries.

## Non-Goals

- Do not change `report-audit` behavior.
- Do not change manifest JSON shape.
- Do not change report artifact generation.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not modify old root progress docs.

## Affected Modules

Expected:

- `src/quant_research_engine/apps/cli.py`
- `tests/test_cli.py`

Docs/handoff:

- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Files Likely to Change

- `src/quant_research_engine/apps/cli.py`
- `tests/test_cli.py`
- agent handoff docs listed above

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- upstream data producer projects
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve existing default `report-files` behavior when `--require-match` is not provided.
- Preserve existing `report-audit --require-match` behavior.
- Preserve manifest discovery and filtering semantics.
- No database writes or credential handling.

## Implementation Steps

1. Inspect current `report-files` and `report-audit` CLI handling.
2. Add `--require-match` to the `report-files` parser.
3. In the `report-files` command branch, if `--require-match` is set and filtered entries are empty:
   - print `no manifest entries matched filters` to stderr;
   - return exit code `2`;
   - print no stdout.
4. Preserve existing behavior when `--require-match` is absent.
5. Add CLI tests:
   - zero matches without `--require-match` still exits `0` with empty stdout/stderr;
   - zero matches with `--require-match` exits `2`, writes the clear stderr message, and emits no stdout;
   - matching entries with `--require-match` still print paths or keys normally.
6. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None.

## API / Interface Changes

Allowed:

- Add optional CLI flag:
  - `qre report-files MANIFEST --require-match`

Avoid:

- Changing existing positional arguments.
- Changing existing output format for successful matches.
- Changing default zero-match behavior.

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

- [ ] `qre report-files` supports `--require-match`.
- [ ] Default zero-match behavior remains exit `0`.
- [ ] `--require-match` zero-match behavior exits `2` with a clear stderr message.
- [ ] Successful matches with `--require-match` still print expected paths/keys.
- [ ] Existing report-audit behavior is unchanged.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- `report-files` is used by scripts; default behavior must remain unchanged.
- Error output should match `report-audit --require-match` wording for consistency.

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
