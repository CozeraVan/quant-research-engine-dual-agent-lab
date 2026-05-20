# Implementation Brief

## Task ID

QRE-DOCS-METADATA-GROUPING-USAGE-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Recent work added evaluation metadata group summaries, batch metadata passthrough grouping, shared-cash metadata passthrough columns, and shared-cash grouped order/trade/failed-order artifacts. Those capabilities are implemented, but current user-facing docs describe them only partially and do not show how `--group-by`, `--metadata-columns`, and report-manifest role filters fit together.

## Goal

Update user-facing documentation for metadata-aware grouping and passthrough usage.

## Non-Goals

- Do not change runtime code.
- Do not change tests unless a doc example is executable and current test conventions require coverage.
- Do not edit legacy archived docs under `docs/legacy`.
- Do not present grouped outputs as exposure attribution, causal explanation, or proof of factor or strategy effectiveness.
- Do not add benchmark or regime claims beyond current implemented behavior.

## Affected Modules

Expected:

- `README.md`
- `docs/modules/data_layer.md`
- `docs/modules/portfolio_layer.md`
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
- Use placeholder output paths and metadata columns such as `board`, `sector`, or `industry`.
- Keep docs clear that grouped diagnostics are structural research aids, not proof of strategy quality.
- Do not claim per-group portfolio return attribution where the implementation only emits row/group summaries.
- Preserve archived legacy docs.

## Implementation Steps

1. Inspect current README and relevant `docs/modules` sections for:
   - `eval-config --group-by`
   - `backtest-batch --group-by`
   - `backtest-shared --metadata-columns`
   - `backtest-shared --group-by`
   - `report-files` / `report-audit --group-by`
2. Document evaluation grouping usage:
   - `qre eval-config --group-by <cols>`
   - `group_summary.csv`
   - report role `evaluation_group_summary`
   - grouping works on available research-frame metadata columns
3. Document batch grouping usage:
   - `qre backtest-batch --group-by <cols>`
   - grouped outputs such as `group_by_board.csv`
   - grouping can use passthrough metadata columns when present in the assembled frame
   - report-manifest filtering with `--role group_summary --group-by <col>`
4. Document shared-cash metadata passthrough and grouped summary usage:
   - `qre backtest-shared --metadata-columns <cols>` copies requested metadata into row outputs
   - `qre backtest-shared --group-by <cols>` writes grouped CSV artifacts such as `orders_by_board.csv`, `trades_by_board.csv`, and `failed_orders_by_board.csv`
   - report roles `shared_orders_group_summary`, `shared_trades_group_summary`, and `shared_failed_orders_group_summary`
5. Include concise examples for:
   - evaluation group-by
   - batch group-by on a passthrough metadata column
   - shared-cash metadata passthrough plus group-by
   - `report-files` / `report-audit` with `--group-by`
6. State that grouped outputs support segmentation and structural inspection only. They do not provide exposure decomposition, causal attribution, or proof of strategy quality.
7. Keep examples credential-free and avoid real database URLs.
8. Update handoff/progress docs.

## Data / Schema Changes

- No data or schema changes.
- Documentation should describe existing grouping and passthrough behavior only.

## API / Interface Changes

- No new API changes in this task.
- Documentation should reflect existing CLI arguments, grouped artifact names, and report-manifest roles.

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

- [ ] README documents metadata-aware grouping usage across evaluation, batch, and shared-cash workflows.
- [ ] Module docs describe evaluation grouping, batch grouping, and shared-cash metadata passthrough/group summaries.
- [ ] Docs include report discovery/audit examples using `--group-by`.
- [ ] Docs clearly state grouped diagnostics do not provide attribution or prove factor/strategy effectiveness.
- [ ] Legacy archived docs are untouched.
- [ ] `scripts/check-progress-docs.sh` and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid over-documenting future real benchmark or regime features.
- Keep examples generic and credential-free.
- Do not imply grouped outputs are investment conclusions or per-group portfolio attribution.

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
