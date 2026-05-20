# Task Handoff

## Current Task

Add deterministic random-baseline comparison for `qre eval-config`.

## Task ID

QRE-EVAL-RANDOM-BASELINE-COMPARISON-001

## Current Status

Accepted locally and committed.

## Current Owner

USER

## Completed

- Added `random_baseline_seed: int | None = None` to `EvaluationRequest` in `models.py`.
- Added `random_baseline_summary: pd.DataFrame` to `EvaluationResult` in `models.py`.
- Added `_build_random_baseline_summary()` method in `engine.py` using seeded `numpy.random.default_rng` for deterministic random entry-point selection.
- Added `--random-baseline-seed` CLI argument to `eval-config` subcommand in `cli.py`.
- Wired `random_baseline_summary` into stdout output and `_write_evaluation_output()` for CSV persistence and `run_manifest.json`.
- Added `random_baseline_seed` to `run_manifest.json` payload.
- Added `random_baseline_summary` role with `horizon`/`event_count` column requirements to `_REQUIRED_COLUMNS_BY_ROLE` in `report_manifest.py`.
- Added 6 engine regression tests (empty when no seed, deterministic output, different seeds differ, correct shape, multi-horizon, null when no events).
- Added 2 CLI regression tests (stdout section printed, persisted to output-dir with manifest validation).
- Added 1 manifest validation test (missing columns in baseline CSV).

## In Progress

None.

## Expected Files

- `src/quant_research_engine/evaluation/models.py` (modified)
- `src/quant_research_engine/evaluation/engine.py` (modified)
- `src/quant_research_engine/apps/cli.py` (modified)
- `src/quant_research_engine/portfolio/report_manifest.py` (modified)
- `tests/test_evaluation_forward_returns.py` (6 new tests)
- `tests/test_cli.py` (2 new tests)
- `tests/test_portfolio_report_manifest.py` (1 new test)

## Validation Baseline

- `uv run pytest tests/test_evaluation_forward_returns.py -q` -> `20 passed`
- `uv run pytest tests/test_cli.py -q` -> `97 passed`
- `uv run pytest tests/test_portfolio_report_manifest.py -q` -> `35 passed`
- `uv run pytest -q` -> `274 passed in 3.19s`
- `scripts/check-progress-docs.sh` -> passed (after doc update)
- `git diff --check` -> passed

## Known Risks

- Random baseline is opt-in via seed; default behavior unchanged when seed omitted.
- Deterministic output under fixed seed for regression stability.
- No real index benchmark wiring yet — blocked until index schema confirmed.
- No evaluation math changed outside the new baseline computation.

## Next Suggested Step

None. Await user acceptance or the next request.
