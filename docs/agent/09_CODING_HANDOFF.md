# Coding Handoff

## Task ID

QRE-CLI-WINDOW-SIZE-GROUP-BY-PARITY-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Implementation Summary

Test-only task. Added 4 CLI regression tests to lock `--window-size` + `--group-by` combined selector behavior with `--json --require-match` across `report-files` and `report-audit`:

- `test_cli_report_files_window_size_group_by_json_require_match_matched_entry`: Combined `--window-size 20 --group-by board` selects only the entry matching both criteria from a 3-entry manifest (one matches both, one wrong window_size, one wrong group_by). Returns `matched_files=1`, `window_size=20`, `group_by=board` in JSON.
- `test_cli_report_files_window_size_group_by_json_require_match_zero_matches`: Mismatch entries (one has window_size=20+group_by=sector, other has window_size=60+group_by=board) fail with exit code 2 and `matched_files=0` JSON payload.
- `test_cli_report_audit_window_size_group_by_json_require_match_matched_entry`: Audit returns `status=ok`, `matched_files=1`, `validation_issues=0` for the combined selector match.
- `test_cli_report_audit_window_size_group_by_json_require_match_zero_matches`: Audit fails with exit code 2 and the existing `no_matches` JSON issue payload.

All tests prove the AND-intersection semantics of `--window-size` and `--group-by`. No runtime or parser code was changed.

## Files Changed

- `tests/test_cli.py` — Added 4 CLI regression tests in a new `# --- window_size + group_by combined selector parity ---` section.
- `docs/agent/04_TASK_HANDOFF.md` — Updated for task completion.
- `docs/agent/05_PROGRESS.md` — Updated progress table, phase, and verification state.
- `docs/agent/09_CODING_HANDOFF.md` — This file.
- `docs/agent/11_AGENT_STATE.md` — Updated phase and owner.
- `docs/agent/12_AGENT_BOARD.md` — Updated recipient and message.

## Validation Results

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 209 passed in 2.02s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed
- `scripts/git-finalize-check.sh` → passed (from `ec7a1d0`)

## Constraints

- Test-only; no runtime, parser, schema, or behavior changes.
- `docs/legacy/**` untouched.
- `uv.lock`, `pyproject.toml` untouched.
- Zero-match tests verify AND-intersection: each entry matches one selector but not both.

## Git State

- Branch: `master`
- Last finalized implementation commit: `ec7a1d0`, `Preserve window_size selector parity under JSON strict mode`
- Current changes are uncommitted (test + agent docs; awaiting Codex review).

## Next Suggested Step

Codex should review the test additions, run validation, and finalize.
