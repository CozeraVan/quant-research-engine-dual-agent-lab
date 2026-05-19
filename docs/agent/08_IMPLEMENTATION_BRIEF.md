# Implementation Brief

## Task ID

QRE-SHARED-FAILED-ORDER-SIDE-SUMMARY-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Shared-cash backtests already emit failed-order rows and summary counts by reason and failure_reason. The current summary does not surface side-level breakdowns, so users cannot quickly see whether failed orders cluster on buys or sells. `docs/agent/01_CURRENT_STATUS.md` calls out richer reason categorization and summary analysis as the next self-contained implementation task.

## Goal

Add richer shared-cash failed-order diagnostics and summary analysis, with side-level aggregate metrics surfaced in summary JSON and Markdown, while preserving existing failed-order behavior.

## Non-Goals

- Do not change order-generation, fill, or blocking logic.
- Do not change single-symbol or batch backtests.
- Do not change benchmark or data-source wiring.
- Do not add database writes.
- Do not broaden this into a new reporting framework.
- Do not modify CLI flags or output formats outside the existing summary artifacts.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/portfolio/io.py`
- `tests/test_portfolio_shared.py`
- `tests/test_portfolio_io.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `src/**` outside `shared.py` and `io.py`
- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve shared-cash execution behavior.
- Preserve existing failed-order reason and failure_reason breakdowns.
- Keep output persistence and Markdown formatting compatible with current report artifacts.
- No database writes or credential handling.
- No unrelated portfolio refactors.

## Implementation Steps

1. Inspect existing failed-order aggregation and Markdown rendering.
2. Add side-level failed-order diagnostics to shared-cash summary, including counts and notional by `side`.
3. Keep existing `reason` and `failure_reason` aggregates unchanged.
4. Surface the new side breakdown in Markdown summary output when failed orders exist.
5. Keep empty-result summaries stable with zero counts and empty mappings.
6. Add regression tests for non-empty and empty failed-order summary cases.
7. Update handoff and progress docs.

## Data / Schema Changes

None.

## API / Interface Changes

Shared-cash summary JSON should continue exposing existing failed-order keys and additionally include side-level diagnostics, likely:

- `failed_order_count_by_side`
- `failed_order_notional_by_side`

Markdown summary should render the side breakdown in a human-readable way.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_shared.py -q
uv run pytest tests/test_portfolio_io.py -q
```

Run full tests and workflow checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] Shared-cash summary JSON includes side-level failed-order count and notional breakdowns.
- [ ] Markdown summary surfaces the side breakdown when failed orders exist.
- [ ] Existing failed-order reason and failure_reason summaries remain unchanged.
- [ ] Empty-result summaries still expose stable zero / empty failed-order diagnostics.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep new diagnostics additive only.
- Avoid altering failed-order row generation or the meanings of existing reason strings.
- Do not introduce CLI changes beyond the summary artifacts already written by the portfolio layer.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Avoid unrelated refactors.
3. Avoid modifying forbidden files.
4. Stop and ask if the brief conflicts with existing code.
5. Run validation commands where possible.
6. Update `04`, `05`, `09`, `11`, and `12`.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
