# Implementation Brief

## Task ID

QRE-EVAL-FACTOR-DECAY-SUMMARY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

The evaluation engine already computes IC and Rank IC summaries for each factor and forward horizon. The project status still lists factor decay as a gap. This can be addressed without new data sources by deriving a horizon-by-horizon decay table from existing IC/Rank IC outputs.

## Goal

Add a factor decay summary to evaluation results, CLI output, and eval-config output artifacts.

## Non-Goals

- Do not add real benchmark data wiring.
- Do not add real regime classification.
- Do not add new upstream tables or database writes.
- Do not recompute technical indicators inside QRE.
- Do not change existing IC, Rank IC, quantile, group, or random-baseline semantics.

## Affected Modules

Expected:

- `src/quant_research_engine/evaluation/models.py`
- `src/quant_research_engine/evaluation/engine.py`
- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_evaluation_forward_returns.py`
- `tests/test_cli.py`
- `tests/test_portfolio_report_manifest.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
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

- Keep data access read-only.
- Do not compute indicators internally.
- Do not change existing evaluation summary semantics.
- Keep output artifacts discoverable and auditable through report manifests.

## Implementation Steps

1. Inspect `EvaluationResult`, `EvaluationEngine._build_ic_summary()`, CLI eval-config stdout/output-dir behavior, and report manifest validation roles.
2. Add `factor_decay_summary: pd.DataFrame` to `EvaluationResult`.
3. Add a small factor decay builder derived from `ic_summary`. Recommended output columns:
   - `factor`
   - `horizon`
   - `base_horizon`
   - `observation_dates`
   - `mean_ic`
   - `mean_rank_ic`
   - `ic_decay_from_base`
   - `rank_ic_decay_from_base`
4. Use the smallest configured horizon per factor as `base_horizon`. If base mean IC or Rank IC is missing or zero, leave the corresponding decay value null.
5. Preserve empty behavior: when no factor columns are requested or IC summary is empty, return an empty DataFrame with stable columns.
6. Print `factor_decay_summary` in `qre eval-config` stdout when non-empty.
7. Persist `factor_decay_summary.csv` under `eval-config --output-dir` when non-empty.
8. Add a manifest role, e.g. `factor_decay_summary`, with required columns in `report_manifest.py`.
9. Include the artifact in evaluation `run_manifest.json` artifact list through existing output-dir artifact handling.
10. Add focused engine tests, CLI stdout/output-dir tests, and manifest validation tests.
11. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- No new upstream tables.

## API / Interface Changes

- `EvaluationResult` gains `factor_decay_summary`.
- `eval-config --output-dir` may emit `factor_decay_summary.csv`.
- Report manifests may gain `factor_decay_summary` role validation.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_evaluation_forward_returns.py tests/test_cli.py tests/test_portfolio_report_manifest.py -q
```

Run full checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] Factor decay summary is produced for factor columns across multiple horizons when IC summary exists.
- [ ] Decay values compare each horizon against the smallest horizon for the same factor.
- [ ] Missing or zero base IC/Rank IC produces null decay instead of division errors.
- [ ] Existing evaluation outputs are unchanged except for the new optional summary/artifact.
- [ ] `qre eval-config` prints `factor_decay_summary` when available.
- [ ] `eval-config --output-dir` writes `factor_decay_summary.csv` and records it in `report_manifest.json` and `run_manifest.json`.
- [ ] Report manifest validation covers the new artifact role.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- IC can be negative. Use signed ratios only if tests make the behavior explicit; otherwise prefer null on zero/missing base and document signed behavior.
- Do not overstate factor decay as strategy effectiveness; it is an evaluation diagnostic.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep factor decay derived from existing IC/Rank IC summaries.
3. Preserve existing evaluation behavior and output artifacts.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
