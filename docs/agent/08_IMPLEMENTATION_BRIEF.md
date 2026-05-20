# Implementation Brief

## Task ID

QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

The CLI now supports optional `--run-id` linkage across preflight, evaluation, and portfolio durable outputs. Report audit also validates `run_manifest` content for required fields, supported kinds, null handling, and artifact list shape. The user-facing README and module docs still describe older report manifest behavior and do not explain the current run-ID and run-manifest audit workflow.

## Goal

Update user-facing documentation for `--run-id`, run manifests, and `report-audit --role run_manifest` content validation.

## Non-Goals

- Do not change runtime code.
- Do not change tests unless a doc example is executable and current test conventions require coverage.
- Do not edit legacy archived docs under `docs/legacy`.
- Do not document smoke outputs as factor or strategy effectiveness.
- Do not add new workflow promises beyond the current CLI behavior.

## Affected Modules

Expected:

- `README.md`
- `docs/modules/portfolio_workflow.md`
- `docs/modules/portfolio_layer.md`

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
- Keep docs clear that audit validates artifact structure, not research quality.
- Preserve archived legacy docs.

## Implementation Steps

1. Inspect current README report-manifest/report-audit section and relevant `docs/modules` pages.
2. Document that durable commands can accept `--run-id`:
   - `qre preflight --output-json ... --run-id <id>`
   - `qre eval-config --output-dir ... --run-id <id>`
   - `qre backtest-single --output-dir ... --run-id <id>`
   - `qre backtest-batch --output-dir ... --run-id <id>`
   - `qre backtest-shared --output-dir ... --run-id <id>`
3. Document where `run_id` is written:
   - preflight JSON output
   - evaluation `run_manifest.json`
   - portfolio `run_manifest.json`
4. Document that `run_id` may be `null` when omitted.
5. Document `report-audit --role run_manifest` and, where appropriate, `--json`.
6. Document the run-manifest fields currently validated:
   - `schema_version`
   - `kind`
   - `run_id`
   - `command`
   - `strategy_path`
   - `artifacts`
7. Mention valid run-manifest kinds:
   - `evaluation_run_manifest`
   - `portfolio_backtest_run_manifest`
8. Keep command examples concise and avoid requiring real database credentials.
9. Update handoff/progress docs.

## Data / Schema Changes

- No data or schema changes.
- Documentation should describe existing JSON payload fields only.

## API / Interface Changes

- No new API changes in this task.
- Documentation should reflect existing CLI arguments and audit behavior.

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

- [ ] README describes `--run-id` linkage and run-manifest audit usage.
- [ ] `docs/modules/portfolio_workflow.md` describes run-manifest content validation.
- [ ] `docs/modules/portfolio_layer.md` references run-ID capable durable outputs or points to the workflow docs.
- [ ] Docs clearly state audit validates artifact structure, not factor/strategy effectiveness.
- [ ] Legacy archived docs are untouched.
- [ ] `scripts/check-progress-docs.sh` and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid over-documenting future orchestration that does not exist yet.
- Keep examples generic and credential-free.
- Do not imply `run_id` makes separate commands transactional; it is linkage metadata only.

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
