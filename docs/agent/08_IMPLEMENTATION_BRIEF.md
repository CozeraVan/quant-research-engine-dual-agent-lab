# Implementation Brief

## Task ID

QRE-CLI-WINDOW-SIZE-METADATA-TYPE-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Rolling batch and shared artifacts now support manifest-level `window_size` filtering, and `ReportManifest.from_path()` already rejects malformed manifest file entries whose `window_size` is neither an integer nor `null`. Direct parser tests exist in `tests/test_portfolio_report_manifest.py`, but `tests/test_cli.py` still lacks command-boundary regression coverage for malformed manifests that use string or boolean `window_size`.

## Goal

Add focused `report-files` / `report-audit` CLI regression coverage for invalid manifest `window_size` metadata types.

## Non-Goals

- Do not change parser behavior, manifest schema version, filenames, or roles unless a tiny CLI error-surface fix is genuinely required.
- Do not broaden this into new filtering behavior or documentation work.
- Do not edit parser tests that already cover direct `ReportManifest.from_path()` rejection unless a narrow fixture reuse is useful.
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

- Preserve the currently shipped CLI and manifest semantics exactly as implemented in `da7b38c`.
- Reuse the existing manifest-specific invalid-field error wording for malformed `window_size` values.
- Keep the task narrowly scoped to CLI regression coverage for string and boolean `window_size`.
- Preserve archived legacy docs.
- Keep the task narrowly scoped to tests unless a tiny runtime fix is required to make the CLI surface deterministic.

## Implementation Steps

1. Inspect the existing direct parser coverage for invalid `window_size` types in `tests/test_portfolio_report_manifest.py`.
2. Add focused `tests/test_cli.py` coverage for malformed manifest file entries with:
   - `window_size: "20"`
   - `window_size: true`
3. Exercise both command boundaries:
   - `qre report-files <manifest>`
   - `qre report-audit <manifest>`
4. Assert the commands fail with exit code `2` and surface the manifest-specific `window_size` error message on stderr.
5. Update handoff/progress docs.

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

- [ ] `tests/test_cli.py` covers malformed string `window_size` at the `report-files` command boundary.
- [ ] `tests/test_cli.py` covers malformed boolean `window_size` at the `report-files` command boundary.
- [ ] `tests/test_cli.py` covers malformed string `window_size` at the `report-audit` command boundary.
- [ ] `tests/test_cli.py` covers malformed boolean `window_size` at the `report-audit` command boundary.
- [ ] The CLI continues surfacing the existing manifest-specific invalid-field message for `window_size`.
- [ ] Legacy archived docs are untouched.
- [ ] `uv run pytest tests/test_cli.py -q`, `scripts/check-progress-docs.sh`, and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid changing runtime behavior when the current parser/CLI path already rejects malformed `window_size`.
- Keep stderr assertions stable without overfitting unrelated text.
- Avoid duplicating direct parser coverage instead of covering the CLI boundary.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep this test-focused unless a tiny runtime fix is required to preserve deterministic CLI error behavior.
3. Avoid editing `docs/legacy/**`.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if the current CLI error surface for malformed `window_size` is inconsistent in a way that cannot be locked down cleanly.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
