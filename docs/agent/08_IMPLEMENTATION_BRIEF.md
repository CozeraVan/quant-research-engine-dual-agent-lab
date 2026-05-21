# Implementation Brief

## Task ID

QRE-DOCS-ROLLING-WINDOW-SIZE-FILTER-USAGE-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Rolling batch and shared artifacts now support manifest-level `window_size` filtering through `qre report-files --window-size`, `qre report-audit --window-size`, and additive `window_size` metadata in `report-files --json`. Current docs still describe optional report-file metadata as only `symbol`, `window`, and `group_by`, and they do not explain the difference between string `--window` calendar-window summaries and numeric `--window-size` rolling artifacts.

## Goal

Update README and portfolio module docs so users can discover and correctly use rolling-artifact `window_size` report filtering and JSON metadata.

## Non-Goals

- Do not change CLI behavior, manifest schema version, filenames, or roles.
- Do not change tests or implementation code unless a narrow doc-example fix requires it.
- Do not rewrite unrelated report-manifest documentation.
- Do not edit legacy archived docs under `docs/legacy`.

## Affected Modules

Expected docs:

- `README.md`
- `docs/modules/portfolio_workflow.md`
- `docs/modules/portfolio_layer.md`

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
- `src/quant_research_engine/**`
- `tests/**`

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve the currently shipped CLI and manifest semantics exactly as implemented in `da7b38c`.
- Explain `--window-size` as additive to existing filters rather than a replacement for `--window`.
- Keep wording consistent with existing report-manifest role terminology.
- Preserve archived legacy docs.
- Keep the task narrowly scoped to documentation.

## Implementation Steps

1. Update README report-artifact sections so they mention:
   - `qre report-files --window-size <int>`
   - `qre report-audit --window-size <int>`
   - additive `window_size` metadata in `report-files --json`
2. Add at least one concrete rolling-artifact example for:
   - shared `rolling_metrics`
   - batch `rolling_summary` or `rolling_ranked_symbols`
3. Explicitly explain the difference between:
   - `--window` for calendar-window summaries such as `M`, `Q`, `Y`
   - `--window-size` for trailing rolling artifacts such as `20`
4. Update portfolio module docs so rolling artifact sections and report-manifest sections are consistent with the shipped CLI behavior.
5. Update handoff/progress docs.

## Data / Schema Changes

- No data or schema changes.
- No schema/version wording changes beyond documenting current behavior.

## API / Interface Changes

- No API changes. This task documents the current CLI/report-manifest surface.

## Validation Plan

Run focused tests:

```bash
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] README documents `report-files` / `report-audit --window-size` with at least one concrete rolling example.
- [ ] README JSON-output wording includes optional `window_size` metadata.
- [ ] Portfolio docs explain when to use `--window-size` instead of `--window`.
- [ ] Rolling batch/shared artifact sections mention that rolling manifest entries carry `window_size`.
- [ ] Legacy archived docs are untouched.
- [ ] `scripts/check-progress-docs.sh` and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid ambiguous wording that suggests `--window` and `--window-size` are interchangeable.
- Avoid drifting into implementation or test edits.
- Keep examples consistent with current role names and manifest metadata semantics.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep this documentation-only unless a concrete doc inconsistency requires a tiny non-behavioral fix.
3. Avoid editing `docs/legacy/**`.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if current docs and current shipped CLI behavior materially disagree in a way that cannot be documented cleanly.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
