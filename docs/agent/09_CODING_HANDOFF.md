# Coding Handoff

## Task ID

QRE-EVAL-RANDOM-BASELINE-COMPARISON-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Accepted locally and committed.

## Implementation Summary

- Added `random_baseline_seed: int | None = None` to `EvaluationRequest` and `random_baseline_summary: pd.DataFrame` to `EvaluationResult`.
- Added `_build_random_baseline_summary()` method in `EvaluationEngine` that uses a seeded `numpy.random.default_rng(seed)` to pick the same number of random entry-points as actual signal events, then computes mean/median forward return and win rate per horizon.
- When seed is None, returns an empty DataFrame — preserving default behavior.
- Random sampling is from the valid pool of research-frame rows with non-NaN forward returns for each horizon.
- Added `--random-baseline-seed` CLI argument; printed `random_baseline_summary` section in stdout; persisted `random_baseline_summary.csv` in output-dir; recorded seed in `run_manifest.json`.
- Added `random_baseline_summary` role to `_eval_manifest_role()` and column requirements to `_REQUIRED_COLUMNS_BY_ROLE` (`horizon`, `event_count`).

## Files Changed

- `src/quant_research_engine/evaluation/models.py` — `EvaluationRequest.random_baseline_seed`, `EvaluationResult.random_baseline_summary`
- `src/quant_research_engine/evaluation/engine.py` — `import numpy`, `_build_random_baseline_summary()`, wired into `evaluate()`
- `src/quant_research_engine/apps/cli.py` — `--random-baseline-seed` argument; stdout printing; CSV persistence; run manifest seed; `_eval_manifest_role` update
- `src/quant_research_engine/portfolio/report_manifest.py` — `random_baseline_summary` role column requirements
- `tests/test_evaluation_forward_returns.py` — 6 new tests
- `tests/test_cli.py` — 2 new tests
- `tests/test_portfolio_report_manifest.py` — 1 new test

## Validation Results

```bash
uv run pytest tests/test_evaluation_forward_returns.py -q  # 20 passed
uv run pytest tests/test_cli.py -q                          # 97 passed
uv run pytest tests/test_portfolio_report_manifest.py -q    # 35 passed
uv run pytest -q                                            # 274 passed in 3.19s
scripts/check-progress-docs.sh                              # passed
git diff --check                                            # passed
```

## Constraints

- Preserve existing stdout behavior unless seed is provided. ✅ seed defaults to None.
- Deterministic under fixed seed. ✅ uses `np.random.default_rng(seed)`.
- Keep data access read-only. ✅ no writes to upstream databases.
- Avoid benchmark table guesses. ✅ random baseline works on research-frame data only.
- Do not push. ✅ not pushed.

## Git State

- Branch: `master`
- Working tree clean.
