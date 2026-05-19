# Coding Handoff

## Task ID

QRE-EVAL-METADATA-GROUP-SUMMARY-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Reviewed and accepted locally.

## Implementation Summary

- Added `group_by: list[str] | None = None` to `EvaluationRequest` in `models.py`.
- Added `group_summary: pd.DataFrame` to `EvaluationResult` in `models.py`.
- Extended `_validate_frame()` in `engine.py` to validate `group_by` columns exist in the research frame, raising `ValueError` with "missing requested group columns" when absent.
- Modified `evaluate()` to include group columns in signal events and pass them through to `_build_group_summary()`.
- Added `_build_group_summary()` method that computes per-group per-horizon statistics: `event_count`, `mean_forward_return`, `median_forward_return`, `win_rate`, and optional adjusted variants when `round_trip_cost_rate` is set.
- Added `--group-by` CLI argument to `eval-config` subcommand in `cli.py`.
- Wired `include_metadata=True` into `ResearchFrameAssembler.build()` when `--group-by` is used, so metadata columns like `board` join into the research frame.
- Added `group_summary` CSV output in the eval-config handler.

## Files Changed

- `src/quant_research_engine/evaluation/models.py` — `EvaluationRequest.group_by` and `EvaluationResult.group_summary`
- `src/quant_research_engine/evaluation/engine.py` — `_validate_frame()` group column check; `evaluate()` group column inclusion; `_build_group_summary()` method
- `src/quant_research_engine/apps/cli.py` — `--group-by` argument; `include_metadata` wiring; `group_summary` output
- `tests/test_evaluation_forward_returns.py` — 6 new tests
- `tests/test_cli.py` — 2 new tests

## Validation Results

```bash
uv run pytest tests/test_evaluation_forward_returns.py -q  # 14 passed in 0.34s
uv run pytest tests/test_cli.py -q                          # 93 passed in 1.25s
uv run pytest -q                                            # 255 passed in 2.41s
scripts/check-progress-docs.sh                              # passed
git diff --check                                            # passed
```

## Constraints

- Preserve existing evaluation behavior when grouping is omitted. ✅ `group_by` defaults to `None`; group summary is empty DataFrame.
- Use only columns already present in the research frame. ✅ `_validate_frame()` checks before evaluation.
- Keep data access read-only. ✅ no writes to upstream databases.
- Do not compute technical indicators inside QRE. ✅ group columns come from metadata join.
- Do not push. ✅ not pushed.

## Git State

- Branch: `master`
- Accepted by Codex review.
- Local checkpoint pending.
