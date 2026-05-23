# Implementation Brief

## Task ID

QRE-STRATEGY-SMOKE-DISCOVERY-STATUS-PASS-COUNT-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Add `--status-pass-count` to include passed-strategy count in status-only outputs.

## Required Changes

1. Add parser flag `--status-pass-count` (bool) to `smoke-files`.
2. Validation:
- `--status-pass-count` requires `--status-only`; otherwise stderr + exit `2`.
3. Behavior with `--status-only --status-pass-count`:
- derive count from filtered `strategies` where all stages are `pass`.
- text mode: append `\tpass_count=<int>` after status payload.
- json mode: include additive key `"pass_count": <int>`.
4. Compatibility:
- preserve existing behavior when `--status-pass-count` absent.
- keep `--quiet` suppression and `--status-file` persistence behavior.
5. Tests:
- text status-pass-count output shape.
- json status-pass-count output shape.
- invalid usage without status-only => exit 2.
- quiet + status-file + status-pass-count path.
6. Docs:
- update `docs/strategy_entry/three_strategy_smoke_report.md`
- update `docs/agent/09_CODING_HANDOFF.md`

## Validation Commands

```bash
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py -q
scripts/check-progress-docs.sh
git diff --check
```
