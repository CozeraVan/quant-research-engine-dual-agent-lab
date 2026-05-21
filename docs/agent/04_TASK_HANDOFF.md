# Task Handoff

## Current Task

Add strict/JSON CLI regression coverage for rolling-artifact `window_size` filters.

## Task ID

QRE-CLI-WINDOW-SIZE-STRICT-JSON-PARITY-001

## Current Status

Accepted locally by Codex review. Ready for local git finalization.

## Current Owner

CODEX

## Completed

- Claude Code added 4 CLI regression tests in `tests/test_cli.py`:
  - `test_cli_report_files_window_size_json_require_match_matched_entry`: `--window-size 20 --json --require-match` finds the correct entry and returns `window_size: 20` in JSON.
  - `test_cli_report_files_window_size_json_require_match_zero_matches`: `--window-size 20 --json --require-match` fails with exit code 2, stderr message, and `matched_files=0` JSON payload when no entries match.
  - `test_cli_report_audit_window_size_json_require_match_matched_entry`: `--window-size 20 --json --require-match` audit returns `status=ok` with `matched_files=1` and `validation_issues=0` for the matched entry.
  - `test_cli_report_audit_window_size_json_require_match_zero_matches`: `--window-size 20 --json --require-match` audit fails with exit code 2 and the existing `no_matches` JSON issue payload.
- No runtime or parser code changes; the existing selector plumbing already works correctly.

## Expected Files

- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 205 passed in 1.94s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed
- `scripts/git-finalize-check.sh` → passed (from `06d2b4b`)

## Known Risks

- Test-only; no runtime or parser behavior changed.
- JSON payload assertions use existing manifest fields (`matched_files`, `status`, `issues`, `no_matches` code) — stable unless the CLI reporting layer changes its JSON shape.
- Legacy archived docs untouched.

## Next Suggested Step

Codex should review the test additions, run validation, and finalize.
