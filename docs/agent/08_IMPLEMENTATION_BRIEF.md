# Implementation Brief

## Task ID

QRE-DOCS-EVAL-GROUP-BY-MANIFEST-PARITY-USAGE-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Evaluation outputs now emit both the combined `group_summary.csv` and per-column grouped files such as `group_summary_by_board.csv`. The manifest also carries `group_by=<col>` metadata so `qre report-files` and `qre report-audit` can filter grouped evaluation artifacts with `--group-by`. Current docs still describe only the combined evaluation grouped artifact and do not explain the new per-column discovery/audit workflow.

## Goal

Update user-facing documentation for evaluation group-by manifest parity and per-column grouped-artifact usage.

## Non-Goals

- Do not change runtime code.
- Do not change tests unless a doc example is executable and current test conventions require coverage.
- Do not edit legacy archived docs under `docs/legacy`.
- Do not imply per-column grouped evaluation artifacts replace the combined `group_summary.csv`.
- Do not present grouped evaluation outputs as attribution, causal explanation, or proof of strategy quality.

## Affected Modules

Expected:

- `README.md`
- `docs/modules/data_layer.md`
- `docs/modules/portfolio_workflow.md`

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
- runtime code files unless a documentation reference reveals an actual typo in generated command names

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Keep examples credential-free and avoid real database URLs.
- Preserve the documented existence of the combined `group_summary.csv`.
- Document per-column files as an additional grouped-artifact surface, not a replacement.
- Keep docs clear that grouped diagnostics are structural research aids, not proof of strategy quality.
- Preserve archived legacy docs.

## Implementation Steps

1. Inspect current evaluation artifact and metadata-grouping sections in:
   - `README.md`
   - `docs/modules/data_layer.md`
   - `docs/modules/portfolio_workflow.md`
2. Update evaluation-grouping docs to explain that `qre eval-config --group-by <cols>` now writes:
   - combined `group_summary.csv`
   - per-column files such as `group_summary_by_board.csv`
3. Document manifest/discovery behavior:
   - combined file uses role `evaluation_group_summary` without manifest `group_by` metadata
   - per-column files use the same role plus manifest `group_by=<col>`
4. Include concise examples for:
   - `qre report-files <manifest> --role evaluation_group_summary`
   - `qre report-files <manifest> --role evaluation_group_summary --group-by board`
   - `qre report-audit <manifest> --role evaluation_group_summary --group-by board --require-match`
5. Keep wording precise:
   - combined and per-column files can coexist
   - grouped outputs support segmentation and structural inspection only
   - these outputs do not prove factor effectiveness or strategy quality
6. Update handoff/progress docs.

## Data / Schema Changes

- No data or schema changes.
- Documentation should describe the existing grouped-artifact and manifest behavior only.

## API / Interface Changes

- No new API changes in this task.
- Documentation should reflect the existing evaluation grouped-artifact filenames and manifest filtering behavior.

## Validation Plan

Run documentation checks:

```bash
scripts/check-progress-docs.sh
git diff --check
```

Run focused tests only if code or executable examples are changed:

```bash
uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q
```

## Acceptance Criteria

- [ ] README explains combined plus per-column evaluation grouped artifacts.
- [ ] Module docs explain evaluation `report-files` / `report-audit --group-by` parity for grouped artifacts.
- [ ] Docs clearly state per-column files supplement, not replace, `group_summary.csv`.
- [ ] Docs clearly state grouped diagnostics do not prove factor/strategy effectiveness.
- [ ] Legacy archived docs are untouched.
- [ ] `scripts/check-progress-docs.sh` and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid over-claiming grouped evaluation diagnostics.
- Avoid describing the combined grouped file as filterable by manifest `group_by` when the per-column files are the filter-targeted artifacts.
- Keep filenames and role names aligned with the implemented CLI behavior.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep this as a documentation-only task unless a blocker requires otherwise.
3. Avoid editing `docs/legacy/**`.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if the brief conflicts with the current docs.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
