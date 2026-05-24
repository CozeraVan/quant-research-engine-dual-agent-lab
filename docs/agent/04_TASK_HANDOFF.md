# Task Handoff

## Current Task

QRE-RESEARCH-RUN-STAGE-ARTIFACT-PARITY-001: Make `qre research-run` persist and link stage-scoped preflight, evaluation, and backtest artifacts.

## Task ID

QRE-RESEARCH-RUN-STAGE-ARTIFACT-PARITY-001

## Current Status

DONE. Codex re-reviewed all fixes, updated `10_REVIEW_REPORT.md` to PASS, and completed local git finalization. No remote push was requested.

## Current Owner

USER

## Problem Summary

`qre research-run` is documented as a complete preflight -> eval -> backtest bundle, but the current implementation does not persist evaluation artifacts from the orchestrator and writes backtest outputs directly into the run root. This weakens report discovery/audit parity and makes the documented `eval/report_manifest.json` and `backtest/report_manifest.json` layout inaccurate.

## Handoff To User

Read:

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/10_REVIEW_REPORT.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

The task is complete. Choose the next project direction.

## Fix Summary

1. **Required Fix 1**: `_run_eval()` now uses correct `EvaluationRequest(signal_expression=..., forward_horizons=..., factor_columns=..., quantiles=...)` + `EvaluationEngine().evaluate(frame, eval_req)`. Added regression test with real `_run_eval()` via fake store — confirms `forward_return_1` appears in events.
2. **Required Fix 2**: `_write_preflight_artifact()` uses `report.to_dict()` when available, preserving `market_rows`, `latest_market_date`, `factor_coverages`, `checks`, etc. Added regression test with real `PreflightReport`.
3. **Required Fix 3**: `evaluation/io.py` confirmed present and importable. Untracked (Codex must `git add` during finalization per R-GIT-001).
4. **Recommended**: `market_profile` provenance passed to `write_evaluation_output()`.
5. **Recommended**: Top-level `artifacts` now stage-qualified (`preflight:`, `eval:`, `backtest:`) to avoid ambiguous duplicates.
