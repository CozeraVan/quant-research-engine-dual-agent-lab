# Coding Handoff

## Task ID

QRE-CLI-WINDOW-SIZE-STRICT-JSON-PARITY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Implementation Summary

Test-only task. Added 4 CLI regression tests to lock `--window-size` selector behavior when combined with `--json --require-match` across `report-files` and `report-audit`:

- `test_cli_report_files_window_size_json_require_match_matched_entry`: `--window-size 20 --json --require-match` correctly selects the matched entry, returns `matched_files=1` with `window_size: 20` in JSON.
- `test_cli_report_files_window_size_json_require_match_zero_matches`: `--window-size 20 --json --require-match` fails with exit code 2, stderr `"no manifest entries matched filters"`, and `matched_files=0` JSON payload.
- `test_cli_report_audit_window_size_json_require_match_matched_entry`: `--window-size 20 --json --require-match` audit returns `status=ok`, `matched_files=1`, `validation_issues=0`.
- `test_cli_report_audit_window_size_json_require_match_zero_matches`: `--window-size 20 --json --require-match` audit fails with exit code 2 and the existing `no_matches` JSON issue payload (`{"key": "manifest", "code": "no_matches", ...}`).

All tests use a `batch_backtest_report_manifest` with two `rolling_summary` entries at different `window_size` values (20 and 60). No runtime or parser code was changed.

## Files Changed

- `tests/test_cli.py` — Added 4 CLI regression tests in a new `# --- window_size --json --require-match parity ---` section.
- `docs/agent/04_TASK_HANDOFF.md` — Updated for task completion.
- `docs/agent/05_PROGRESS.md` — Updated progress table, phase, and verification state.
- `docs/agent/09_CODING_HANDOFF.md` — This file.
- `docs/agent/11_AGENT_STATE.md` — Updated phase and owner.
- `docs/agent/12_AGENT_BOARD.md` — Updated recipient and message.

## Validation Results

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 205 passed in 1.94s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed
- `scripts/git-finalize-check.sh` → passed (from `06d2b4b`)

## Constraints

- Test-only; no runtime, parser, schema, or behavior changes.
- `docs/legacy/**` untouched.
- `uv.lock`, `pyproject.toml` untouched.
- JSON payload assertions use existing manifest contract fields — no new keys or codes invented.

## Git State

- Branch: `master`
- Last finalized implementation commit: `06d2b4b`, `Preserve report CLI rejection of malformed window_size metadata`
- Current changes are uncommitted (test + agent docs; awaiting Codex review).

## Next Suggested Step

Codex should review the test additions, run validation, and finalize.
