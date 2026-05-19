# Implementation Brief

## Task ID

QRE-EVAL-RANDOM-BASELINE-COMPARISON-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`qre eval-config` now has durable output artifacts and report manifests. The next useful step is to add a deterministic random-baseline comparison so evaluation runs can answer a simple quality question: does the signal beat a fixed random selection of the same shape?

Real index benchmark wiring remains blocked until the index table/schema are confirmed, so this brief scopes the unblocked part first.

## Goal

Add deterministic random-baseline comparison to evaluation results and `qre eval-config`, with seed-controlled behavior and regression tests.

## Non-Goals

- Do not wire a real index benchmark table in this brief.
- Do not add new upstream data adapters or database writes.
- Do not change existing forward-return or IC math.
- Do not change `eval-smoke`.
- Do not compute technical indicators inside QRE.
- Do not record sensitive connection values.

## Affected Modules

Expected:

- `src/quant_research_engine/evaluation/models.py`
- `src/quant_research_engine/evaluation/engine.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_evaluation_forward_returns.py`
- `tests/test_cli.py`

Docs/handoff:

- `docs/agent/01_CURRENT_STATUS.md`
- `docs/agent/03_ROADMAP.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/06_DECISION_LOG.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve existing stdout behavior for `eval-config` unless the new random-baseline section is enabled.
- Keep the new comparison additive and optional.
- Keep data access read-only.
- Avoid benchmark table guesses while the real source remains unconfirmed.
- Keep the comparison deterministic under a fixed seed.

## Implementation Steps

1. Inspect the current evaluation result model and engine summary builders.
2. Add a random-baseline comparison summary to the evaluation result model.
3. Compute a deterministic baseline using a configurable seed and the current event population.
4. Surface the comparison in `qre eval-config` stdout without removing existing sections.
5. If `--output-dir` is present, persist the random-baseline summary alongside the other evaluation artifacts and register it in the report manifest if needed.
6. Add regression tests for deterministic output, empty-input behavior, and CLI printing.
7. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- No new upstream tables.
- Optional new report-manifest role only if the baseline summary is persisted to disk.

## API / Interface Changes

- `EvaluationRequest` gains an optional random-baseline seed or toggle.
- `EvaluationResult` gains a random-baseline summary frame if persisted in results.
- `qre eval-config` may accept a seed flag for reproducible comparison.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_evaluation_forward_returns.py -q
uv run pytest tests/test_cli.py -q
```

Run full checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `qre eval-config` can print a deterministic random-baseline comparison section.
- [ ] The comparison is reproducible under a fixed seed.
- [ ] Existing evaluation summaries remain unchanged unless the new feature is enabled.
- [ ] If the baseline summary is written to disk, it is included in the report manifest and validates correctly.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Randomness must be seed-controlled so the comparison does not drift across runs.
- Keep the implementation additive; do not disturb existing stdout summaries.
- Do not overreach into real benchmark wiring before the index schema is confirmed.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep the comparison deterministic and small.
3. Reuse existing evaluation patterns rather than adding a new framework.
4. Update `01`, `03`, `04`, `05`, `06`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
