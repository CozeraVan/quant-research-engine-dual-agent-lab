# Implementation Brief

## Task ID

QRE-CLI-WINDOW-SIZE-STRICT-JSON-PARITY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Rolling batch and shared artifacts now support manifest-level `window_size` filtering. `tests/test_cli.py` already covers the basic `report-files` / `report-audit --window-size` selector path, `report-files --json` exposure of `window_size`, and malformed string/boolean `window_size` manifest metadata at both CLI command boundaries. Generic strict/JSON selector coverage also exists for other filters. What is still missing is focused parity coverage when the active selector is `--window-size` and the commands are asked to enforce `--require-match` or return JSON payloads.

## Goal

Add focused `report-files` / `report-audit` CLI regression coverage for `--window-size` combined with strict no-match and JSON output modes.

## Non-Goals

- Do not change parser behavior, manifest schema version, filenames, or roles unless a tiny CLI bug is genuinely required to preserve consistent selector behavior.
- Do not broaden this into new filtering features, manifest helpers, or documentation work.
- Do not touch direct parser tests that already cover malformed `window_size` type rejection unless a narrow fixture reuse is useful.
- Do not edit legacy archived docs under `docs/legacy`.

## Affected Modules

Expected runtime/tests:

- `tests/test_cli.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `docs/legacy/**`
- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- `README.md`
- `docs/modules/**`
- `src/quant_research_engine/**` unless a tiny CLI error-surface normalization fix is genuinely required

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve the currently shipped CLI and manifest semantics exactly as implemented in `06d2b4b`.
- Keep the task narrowly scoped to `--window-size` selector parity with `--require-match` and `--json`.
- Preserve archived legacy docs.
- Keep the task narrowly scoped to tests unless a tiny runtime fix is required to make the CLI surface deterministic.

## Implementation Steps

1. Inspect the existing generic `--json --require-match` CLI coverage and the current `--window-size` filter tests in `tests/test_cli.py`.
2. Add focused `tests/test_cli.py` coverage for `report-files` with `--window-size` combined with `--json --require-match`:
   - one matched-entry case
   - one zero-match failure case
3. Add focused `tests/test_cli.py` coverage for `report-audit` with `--window-size` combined with `--json --require-match`:
   - one matched-entry case
   - one zero-match failure case that preserves the existing `no_matches` JSON issue payload
4. Update handoff/progress docs.

## Data / Schema Changes

- No data or schema changes.
- No schema/version changes.

## API / Interface Changes

- No API changes. This task adds regression coverage only.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_cli.py -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `tests/test_cli.py` covers `report-files --window-size ... --json --require-match` with one matched entry.
- [ ] `tests/test_cli.py` covers `report-files --window-size ... --json --require-match` zero-match failure behavior.
- [ ] `tests/test_cli.py` covers `report-audit --window-size ... --json --require-match` with one matched entry.
- [ ] `tests/test_cli.py` covers `report-audit --window-size ... --json --require-match` zero-match failure behavior and the existing `no_matches` JSON issue payload.
- [ ] Legacy archived docs are untouched.
- [ ] `uv run pytest tests/test_cli.py -q`, `scripts/check-progress-docs.sh`, and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid changing runtime behavior when the current selector plumbing already works and only coverage is missing.
- Keep JSON payload assertions specific enough to lock `window_size` selector semantics without overfitting unrelated fields.
- Avoid duplicating generic no-match tests without anchoring them to `--window-size`.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep this test-focused unless a tiny runtime fix is required to preserve deterministic selector behavior.
3. Avoid editing `docs/legacy/**`.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if `--window-size` behaves inconsistently with the already-shipped generic strict/JSON CLI patterns.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
