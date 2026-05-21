# Task Handoff

## Current Task

Add strict/JSON CLI regression coverage for rolling-artifact `window_size` + `group_by` combined filters.

## Task ID

QRE-CLI-WINDOW-SIZE-GROUP-BY-PARITY-001

## Current Status

Accepted locally by Codex review. Ready for local git finalization.

## Current Owner

CODEX

## Completed

- Claude Code added 4 CLI regression tests in `tests/test_cli.py` for combined `--window-size` + `--group-by` selector parity:
- Claude Code added 4 CLI regression tests in `tests/test_cli.py` for combined `--window-size` + `--group-by` selector parity:
  - `test_cli_report_files_window_size_group_by_json_require_match_matched_entry`: `--window-size 20 --group-by board --json --require-match` selects the sole matching entry (window_size=20, group_by=board) from a 3-entry manifest.
  - `test_cli_report_files_window_size_group_by_json_require_match_zero_matches`: mismatch entries (one wrong window_size, one wrong group_by) fail with exit code 2 + `matched_files=0` JSON payload.
  - `test_cli_report_audit_window_size_group_by_json_require_match_matched_entry`: audit returns `status=ok`, `matched_files=1`, `validation_issues=0` for the combined selector match.
  - `test_cli_report_audit_window_size_group_by_json_require_match_zero_matches`: audit fails with exit code 2 and the existing `no_matches` JSON issue payload.
- No runtime or parser code changes; the existing selector intersection plumbing already works.

## Expected Files

- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 209 passed in 2.02s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed
- `scripts/git-finalize-check.sh` → passed (from `ec7a1d0`)

## Known Risks

- Test-only; no runtime or parser behavior changed.
- Zero-match tests use orthogonal non-matching combinations (one entry with wrong window_size, one with wrong group_by) to verify the AND-intersection.
- Legacy archived docs untouched.

## Next Suggested Step

Codex should run final git checks and create the local completion commit.
