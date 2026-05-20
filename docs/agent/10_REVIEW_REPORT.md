# Review Report

## Task ID

QRE-PORTFOLIO-BATCH-METADATA-GROUPBY-001

## Written By

CODEX

## Review Outcome

PASS

## Reviewed Implementation

Claude Code implementation in the current working tree.

Changed files reviewed:

- `src/quant_research_engine/portfolio/batch.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_batch.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Review Summary

Review passed.

Batch backtests can now request additional metadata columns for `BatchBacktestResult.summary`. CLI `backtest-batch --group-by ...` passes those requested group columns to the engine, so existing grouped stdout and report writers can use optional metadata columns preserved by the data layer.

## Compliance with Implementation Brief

Compliant.

- Existing default batch summary metadata columns are preserved.
- Requested passthrough metadata columns can appear in `BatchBacktestResult.summary`.
- `backtest-batch --group-by <column>` passes requested columns into the engine.
- Missing requested columns remain absent from summary and downstream grouped summary code raises the existing clear `ValueError`.
- No portfolio simulation math, benchmark wiring, or data access behavior changed.

## Locked Requirements Check

No locked-requirement violation found.

- R-CORE-001: Existing batch behavior is preserved when no extra metadata is requested.
- R-CORE-002: Change is scoped to batch metadata propagation and focused tests.
- R-CORE-003: Focused and full validation passed.
- R-CORE-004 / R-QRE-006: No sensitive values added.
- R-QRE-005: Data access remains read-only.
- R-QRE-002: No indicator computation added.
- R-GIT-002: No push performed.

## Code Quality Review

The implementation is small and request-driven. `summary_metadata_columns` avoids copying arbitrary frame/factor columns into summaries by default, and duplicate requested metadata columns are ignored.

## Test Review

Validation commands run by Codex:

```bash
uv run pytest tests/test_portfolio_batch.py tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

Results:

- `uv run pytest tests/test_portfolio_batch.py tests/test_cli.py -q`: `105 passed`
- `uv run pytest -q`: `283 passed in 2.67s`
- `scripts/check-progress-docs.sh`: passed
- `git diff --check`: passed

Coverage is adequate:

- default summary metadata columns are still present;
- requested extra metadata columns flow into summary;
- absent requested columns are skipped;
- duplicate default metadata requests do not duplicate output columns;
- CLI grouped output works with a passthrough metadata column.

## Required Fixes

None.

## Recommended Improvements

Future work can add output-dir regression coverage for passthrough group-by artifacts if grouped report schemas expand further. Not required for this task.

## Follow-up Tasks

- Finalize the accepted implementation locally.

## Final Recommendation

Accept locally. Do not push.

## Next Agent State

- Phase: `DONE`
- Owner: `USER`
