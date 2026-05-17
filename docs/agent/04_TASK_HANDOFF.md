# Task Handoff

## Current Task

Migrate legacy project documentation into the dual-agent `docs/agent` system and prepare the next Claude Code task.

## Task ID

DOC-MIGRATION-2026-05-17

## Current Status

Done. New `docs/agent` files are now the preferred entry point for future Codex and Claude Code work.

## Current Owner

USER

## Completed

- Read the current agent state before editing.
- Read existing agent docs.
- Migrated effective content from legacy docs into the new `docs/agent` system.
- Preserved old Markdown files in place.
- Added Archived Note banners to legacy planning/progress Markdown files without deleting them.
- Did not modify business code, tests, configs, examples, `pyproject.toml`, or `uv.lock`.
- Selected a self-contained next Claude Code task: shared-cash failed-order diagnostics.

## Information Migrated From

- `README.md`
- `AGENTS.md`
- `进度.md`
- `progress.md`
- `findings.md`
- `task_plan.md`
- `docs/mvp_plan.md`
- `docs/design/overview.md`
- `docs/design/architecture_mindmap.md`
- `docs/modules/module_boundaries.md`
- `docs/modules/data_layer.md`
- `docs/modules/evaluation_layer.md`
- `docs/modules/portfolio_layer.md`
- `docs/modules/portfolio_workflow.md`
- `docs/modules/portfolio_agent.md`
- `docs/modules/ashare_first_market_profile.md`
- `docs/superpowers/plans/2026-05-11-project-skeleton.md`
- read-only code structure checks under `src`, `tests`, `configs`, `examples`, and `scripts`

## In Progress

No coding is in progress.

The next implementation task is waiting for user approval:

- `QRE-PORTFOLIO-FAILED-ORDER-DIAGNOSTICS-001`

## Modified Files

- Legacy docs annotated as archived:
  - `进度.md`
  - `progress.md`
  - `findings.md`
  - `task_plan.md`
  - `docs/mvp_plan.md`
- Agent docs updated:
  - `docs/agent/04_TASK_HANDOFF.md`
  - `docs/agent/05_PROGRESS.md`

## Validation

Required before final response:

- `git status --short`
- `git diff --name-only HEAD`
- `scripts/check-progress-docs.sh`

Code tests were not required for this documentation-only migration. The latest legacy-recorded full test result is:

- `uv run pytest -q`
- `156 passed in 1.30s`

## Known Risks

- Legacy docs contain older test counts such as `145 passed`, `147 passed`, `154 passed`, and `156 passed`. The latest migrated status uses `156 passed`; rerun tests before claiming current code pass status.
- `docs/modules/evaluation_layer.md` says portfolio/account-level simulation is not implemented in evaluation scope. This is not a conflict: portfolio simulation exists in the portfolio layer, not in evaluation.
- `task_plan.md` says Phase 5 reporting is pending, while portfolio/reporting docs say many reporting features are implemented. Interpreted as larger research-run reproducibility still pending, not basic reporting.
- Real index benchmark wiring is partially implemented as an interface/skeleton and temporary stock benchmark path, but real index table wiring remains blocked pending data-source confirmation.
- Real suspension/ST/risk-warning metadata is not fully wired; fallback metadata may be static.

## Suggested Legacy Archive Candidates

Do not delete automatically. If the user wants cleanup later, these can be moved under an archive folder after review:

- `task_plan.md`
- `findings.md`
- `progress.md`
- `进度.md`
- `docs/superpowers/plans/2026-05-11-project-skeleton.md`

Keep as reference or consolidate carefully:

- `README.md`
- `AGENTS.md`
- `docs/mvp_plan.md`
- `docs/design/*`
- `docs/modules/*`

## Next Suggested Step

User reviews the migrated docs and either approves `08_IMPLEMENTATION_BRIEF.md` for Claude Code, or asks Codex to revise the brief or roadmap.
