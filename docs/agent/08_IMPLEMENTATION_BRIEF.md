# Implementation Brief

## Task ID

QRE-EVAL-METADATA-GROUP-SUMMARY-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

The evaluation engine already computes signal events, forward-return summaries, IC/Rank IC, quantile returns, and rough friction-adjusted event metrics. The roadmap still marks regime and metadata group summaries as a gap.

The next self-contained step is to add metadata grouping to evaluation results using columns that already exist in the research frame, such as `board` or `industry`. This should not require new upstream data-source wiring. The feature should summarize event forward returns by group so broad factor screens can identify whether a signal is concentrated in or dependent on a metadata bucket.

## Goal

Add optional evaluation group summaries keyed by existing research-frame columns, and expose them through the evaluation CLI path.

## Non-Goals

- Do not add new database tables or new upstream data adapters.
- Do not implement benchmark or random-baseline comparison.
- Do not implement factor decay analysis.
- Do not infer missing metadata or compute technical indicators inside QRE.
- Do not change existing summary, IC, or quantile semantics.
- Do not add report-manifest or portfolio-output changes in this task.

## Affected Modules

Expected:

- `src/quant_research_engine/evaluation/models.py`
- `src/quant_research_engine/evaluation/engine.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_evaluation_forward_returns.py`
- `tests/test_cli.py`

Possible if needed:

- `src/quant_research_engine/strategies/spec.py`
- `tests/test_strategy_spec.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `src/**` outside the modules listed above unless Claude Code records a concrete reason in `09_CODING_HANDOFF.md`
- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve existing evaluation behavior when grouping is not requested.
- Use only columns already present in the research frame.
- Keep data access read-only.
- Do not compute technical indicators inside the evaluation engine.
- Avoid lookahead behavior: group labels must come from the current event row, not future rows.
- Keep CLI output stable except for new optional `group_summary` output when requested.

## Implementation Steps

1. Inspect the current `EvaluationRequest`, `EvaluationResult`, and `EvaluationEngine.evaluate()` flow.
2. Add an optional grouping input, suggested name `group_by: list[str] | None`, to `EvaluationRequest`.
3. Add a `group_summary: pd.DataFrame` field to `EvaluationResult`.
4. Preserve requested group columns in `result.events` so each emitted signal event carries its group labels.
5. Build grouped event summaries from signal events:
   - one row per `group_by` column, group value, and horizon;
   - include `group_by`, `group_value`, `horizon`, `event_count`, `mean_forward_return`, `median_forward_return`, and `win_rate`;
   - if `round_trip_cost_rate` is set, include the same adjusted metrics used by the overall event summary.
6. Validate requested group columns exist in the input frame. Missing group columns should raise a clear `ValueError`.
7. Add CLI support for `eval-config --group-by ...`.
   - When group columns are requested, the research-frame assembler should include metadata so columns like `board` can be available.
   - Print a `group_summary` section only when it is non-empty.
8. Add focused engine and CLI regression tests.
9. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- No new files are required.
- In-memory `EvaluationResult` gains a new `group_summary` DataFrame.

Suggested `group_summary` columns:

- `group_by`
- `group_value`
- `horizon`
- `event_count`
- `mean_forward_return`
- `median_forward_return`
- `win_rate`
- optional adjusted fields when costs are configured:
  - `round_trip_cost_rate`
  - `mean_adjusted_forward_return`
  - `median_adjusted_forward_return`
  - `adjusted_win_rate`

## API / Interface Changes

- `EvaluationRequest` accepts optional `group_by`.
- `EvaluationResult` includes `group_summary`.
- `qre eval-config` accepts `--group-by` with one or more column names.
- Existing callers that do not pass grouping should keep working.

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

- [ ] `EvaluationRequest(group_by=[...])` validates group columns and preserves them in `result.events`.
- [ ] `EvaluationResult.group_summary` contains grouped event statistics by column, value, and horizon.
- [ ] Group summaries include adjusted-return metrics when `round_trip_cost_rate` is configured.
- [ ] Existing evaluation outputs remain unchanged when `group_by` is omitted.
- [ ] `qre eval-config --group-by board` loads metadata through the assembler and prints a `group_summary` table.
- [ ] Missing group columns raise a clear error.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Keep grouping additive and avoid changing existing result table schemas except for preserving requested group columns in `events`.
- Do not silently synthesize metadata groups if the research frame lacks the requested column.
- Avoid future leakage by using event-row group labels only.
- Keep CLI behavior deterministic and easy to parse.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Reuse the existing evaluation summary style before adding helpers.
3. Keep the implementation small and regression-tested.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
