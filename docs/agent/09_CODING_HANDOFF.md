# Coding Handoff

## Task ID

QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-PASS-COUNT-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Objective

Add `--status-pass-count` to include passed-strategy count in status-only outputs.

## Implementation Summary

- `src/quant_research_engine/apps/cli.py`:
  - add `--status-pass-count` parser flag
  - requires `--status-only` (invalid combo => stderr + exit 2)
  - derives pass count from already-computed `summary_pass` (strategies where all stages are `pass`)
  - text status-only: appends `\tpass_count=<int>`
  - json status-only: adds `"pass_count": <int>` (integer type)
  - preserves compatibility with all existing status flags (`--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-manifest-path`, `--status-manifest-exists`, `--status-artifact-count`, `--status-strategy-count`, `--status-fail-count`, `--status-skip-count`, `--status-format`, `--quiet`, `--status-file`)
- `tests/test_cli.py`:
  - add 4 tests: text pass_count (=2 for fixture), JSON pass_count (integer type assertion), requires-status-only validation, quiet + status-file behavior
- `docs/strategy_entry/three_strategy_smoke_report.md`:
  - add usage examples and description paragraph for `--status-pass-count`
  - update compatibility lists and exit codes line

## Validation

```bash
uv run pytest tests/test_cli.py -q --tb=short -k "smoke_files"
# 114 passed in 2.13s

uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py -q
# 466 passed, 2 warnings in 4.86s

scripts/check-progress-docs.sh
# passed

git diff --check
# passed
```
