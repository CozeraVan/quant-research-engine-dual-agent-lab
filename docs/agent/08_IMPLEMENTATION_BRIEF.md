# Implementation Brief

## Task ID

QRE-DOCS-EVAL-ARTIFACTS-USAGE-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Recent evaluation work added durable `eval-config --output-dir` artifacts, metadata group summaries, deterministic random-baseline comparison, and factor decay summaries. User-facing docs still focus more heavily on report-manifest mechanics and portfolio workflows. The evaluation CLI surface needs concise usage documentation so users know which artifacts are emitted and how to audit/discover them.

## Goal

Update user-facing documentation for evaluation output artifacts and diagnostics.

## Non-Goals

- Do not change runtime code.
- Do not change tests unless a doc example is executable and current test conventions require coverage.
- Do not edit legacy archived docs under `docs/legacy`.
- Do not document smoke outputs as factor or strategy effectiveness.
- Do not add benchmark or regime claims beyond current implemented behavior.

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

Update only additional non-legacy docs if the current documentation layout clearly requires it.

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

- Do not expose credentials or real database URLs.
- Use placeholder output paths and run IDs.
- Keep docs clear that evaluation diagnostics are structural/research aids, not proof of strategy quality.
- Preserve archived legacy docs.

## Implementation Steps

1. Inspect current README and relevant `docs/modules` evaluation/reporting sections.
2. Document `qre eval-config --output-dir <dir>` emitted files:
   - `events.csv`
   - `summary.csv`
   - `ic_summary.csv`
   - `quantile_summary.csv`
   - `group_summary.csv` when `--group-by` is used
   - `random_baseline_summary.csv` when `--random-baseline-seed` is used
   - `factor_decay_summary.csv` when IC summaries are available
   - `run_manifest.json`
   - `report_manifest.json`
3. Document evaluation artifact roles that can be used with `report-files` / `report-audit`:
   - `events`
   - `evaluation_summary`
   - `ic_summary`
   - `quantile_summary`
   - `evaluation_group_summary`
   - `random_baseline_summary`
   - `factor_decay_summary`
   - `run_manifest`
4. Include concise examples for:
   - `eval-config --output-dir`
   - `eval-config --group-by`
   - `eval-config --random-baseline-seed`
   - discovering or auditing `factor_decay_summary`
5. Mention factor decay is derived from existing IC/Rank IC horizons and uses the smallest horizon per factor as base.
6. Mention random-baseline comparison is deterministic when a seed is provided.
7. Keep examples credential-free and avoid real database URLs.
8. Update handoff/progress docs.

## Data / Schema Changes

- No data or schema changes.
- Documentation should describe existing artifacts only.

## API / Interface Changes

- No new API changes in this task.
- Documentation should reflect existing CLI arguments and report-manifest roles.

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

- [ ] README documents `eval-config --output-dir` artifacts and evaluation report roles.
- [ ] Module docs describe metadata grouping, random baseline, and factor decay as evaluation diagnostics.
- [ ] Docs include report discovery/audit examples for at least one evaluation artifact role.
- [ ] Docs clearly state diagnostics do not prove factor/strategy effectiveness.
- [ ] Legacy archived docs are untouched.
- [ ] `scripts/check-progress-docs.sh` and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid over-documenting future real benchmark or regime features.
- Keep examples generic and credential-free.
- Do not imply evaluation diagnostics are investment conclusions.

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
