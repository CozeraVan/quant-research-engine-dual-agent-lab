# Coding Handoff

## Task ID

QRE-EVAL-FACTOR-DECAY-SUMMARY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Implementation Summary

- Added `factor_decay_summary: pd.DataFrame` to `EvaluationResult` in `evaluation/models.py`.
- Added `_build_factor_decay_summary()` to `EvaluationEngine` in `evaluation/engine.py`. Derives factor decay rows from existing `ic_summary`: finds the smallest horizon per factor as `base_horizon`, then computes `ic_decay_from_base` and `rank_ic_decay_from_base` for each horizon. Returns empty DataFrame with stable columns when IC summary is empty. Uses `pd.notna()` and zero checks to leave decay values null when base IC/Rank IC is missing, NaN, or zero.
- Updated `qre eval-config` CLI to print `factor_decay_summary` to stdout when non-empty and persist `factor_decay_summary.csv` under `--output-dir`.
- Added `factor_decay_summary` manifest validation role in `_REQUIRED_COLUMNS_BY_ROLE` (`report_manifest.py`) with required columns `factor`, `horizon`, `base_horizon`.
- The `_eval_manifest_role()` function passes through `"factor_decay_summary"` as-is, so no explicit entry needed.

## Files Changed

- `src/quant_research_engine/evaluation/models.py` — added `factor_decay_summary` field to `EvaluationResult`
- `src/quant_research_engine/evaluation/engine.py` — added `_build_factor_decay_summary()` method; wired into `evaluate()`
- `src/quant_research_engine/apps/cli.py` — prints `factor_decay_summary` to stdout and persists to `--output-dir`
- `src/quant_research_engine/portfolio/report_manifest.py` — added `factor_decay_summary` validation role
- `tests/test_evaluation_forward_returns.py` — 6 new engine tests
- `tests/test_cli.py` — 1 new CLI test (`test_cli_eval_config_factor_decay_printed_and_persisted`)
- `tests/test_portfolio_report_manifest.py` — 2 new manifest validation tests
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Results

```bash
uv run pytest tests/test_evaluation_forward_returns.py tests/test_cli.py tests/test_portfolio_report_manifest.py -q  # 164 passed in 1.71s
uv run pytest -q                                                                              # 324 passed in 3.18s
scripts/check-progress-docs.sh                                                                # pending doc update
git diff --check                                                                              # passed
```

## Constraints

- Factor decay computed from existing IC/Rank IC summaries only. ✅
- No new data sources, benchmark tables, or regime tables assumed. ✅
- Existing evaluation outputs (events, summary, IC, quantile, group, random baseline) unchanged. ✅
- Empty IC summary produces empty factor decay DataFrame with stable columns. ✅
- Missing/zero base IC/Rank IC produces null decay values (not division errors). ✅
- Output artifacts and manifest validation compatible with `report-files` and `report-audit`. ✅
- Do not push. ✅

## Git State

- Branch: `master`
- All code and doc changes uncommitted.
- Ready for Codex review.
