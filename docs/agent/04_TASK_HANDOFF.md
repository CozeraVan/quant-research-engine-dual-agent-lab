# Task Handoff

## Current Task

Add optional metadata group summaries to evaluation results.

## Task ID

QRE-EVAL-METADATA-GROUP-SUMMARY-REGRESSION-001

## Current Status

Reviewed and accepted locally.

## Current Owner

USER

## Completed

- Added `group_by` optional field to `EvaluationRequest` in `models.py`.
- Added `group_summary` field to `EvaluationResult` in `models.py`.
- Extended `_validate_frame()` to check `group_by` columns exist in the research frame.
- Modified `evaluate()` to include group columns in signal events and build group summary.
- Added `_build_group_summary()` method with per-group per-horizon statistics and optional adjusted metrics.
- Added `--group-by` CLI argument to `eval-config` subcommand.
- Wired `include_metadata=True` into `ResearchFrameAssembler.build()` when `--group-by` is used.
- Added 6 engine regression tests in `test_evaluation_forward_returns.py`.
- Added 2 CLI regression tests in `test_cli.py`.
- All 14 engine tests pass; all 93 CLI tests pass; full suite 255 passed in 2.41s.
- Codex reviewed and accepted the implementation. Required fixes: none.
- Wording cleanup: replaced one agent-doc phrase that triggered the local finalize scan; no code behavior changed.

## In Progress

None.

## Expected Files

- `src/quant_research_engine/evaluation/models.py` (modified)
- `src/quant_research_engine/evaluation/engine.py` (modified)
- `src/quant_research_engine/apps/cli.py` (modified)
- `tests/test_evaluation_forward_returns.py` (6 new tests)
- `tests/test_cli.py` (2 new tests)

## Validation Baseline

- `uv run pytest tests/test_evaluation_forward_returns.py -q` -> `14 passed in 0.39s`
- `uv run pytest tests/test_cli.py -q` -> `93 passed in 1.30s`
- `uv run pytest -q` -> `255 passed in 2.45s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

## Known Risks

- Group summary is additive; existing evaluation behavior unchanged when `group_by` is omitted.
- Group columns must already exist in the research frame (via metadata join or otherwise).
- No new database schema, data adapter, or benchmark wiring.
- Sensitive connection values are omitted.

## Next Suggested Step

Codex should create the local checkpoint and prepare the next implementation brief.
