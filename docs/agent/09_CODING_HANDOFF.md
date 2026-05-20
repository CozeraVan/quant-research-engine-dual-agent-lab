# Coding Handoff

## Task ID

QRE-RUN-ID-MANIFEST-LINKAGE-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Implementation Summary

Added optional `--run-id` CLI argument to `preflight`, `eval-config`, `backtest-single`, `backtest-batch`, and `backtest-shared`. The run ID is persisted as a top-level `"run_id"` field in JSON outputs: preflight `--output-json`, evaluation `run_manifest.json`, and portfolio `portfolio_backtest_run_manifest`. When `--run-id` is omitted, the field is `null`. The implementation is metadata-only — no new orchestrator, database writes, or math changes.

## Files Changed

- `src/quant_research_engine/apps/cli.py` — added `--run-id` to 5 parsers; pass `args.run_id` to `_write_evaluation_output`, preflight JSON payload, and portfolio writers
- `src/quant_research_engine/portfolio/io.py` — `_write_run_manifest`, `write_single_symbol_result`, `write_shared_cash_result`, `write_batch_result` accept optional `run_id` and persist it in run manifest payload
- `tests/test_cli.py` — 4 new tests: eval-config run_id in manifest, eval-config null when omitted, preflight run_id in output JSON, preflight null when omitted
- `tests/test_portfolio_io.py` — 2 new tests: single-symbol run_id in manifest, single-symbol null when omitted

## Validation Results

```bash
uv run pytest tests/test_cli.py tests/test_portfolio_io.py -q  # 127 passed in 2.49s
uv run pytest -q                                                # 330 passed in 3.16s
scripts/check-progress-docs.sh                                  # passed (after doc update)
git diff --check                                                # passed
```

## Constraints

- Keep `run_id` optional and metadata-only. ✅
- Preserve existing CLI behavior when `--run-id` is omitted. ✅
- Do not change evaluation or portfolio math. ✅
- Do not add database writes or a broad orchestration command. ✅
- Do not wire benchmark/regime. ✅
- Stable explicit `null` when omitted. ✅

## Git State

- Branch: `master`
- All code and doc changes uncommitted.
- Ready for Codex review.

## Next Suggested Step

Codex should review the implementation and produce `10_REVIEW_REPORT.md`.
