# Coding Handoff

## Task ID

QRE-REPORT-AUDIT-JSON-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Implemented

- Added `--json` flag to `report_audit_parser` in `cli.py`.
- When `--json` is set, `report-audit` emits a single JSON object to stdout with: `manifest_kind`, `matched_files`, `missing_files`, `validation_issues`, `status`, `issues`.
- `issues` is a list of objects with `key`, `code`, `path`, `message`.
- Zero-match with `--require-match` adds a `no_matches` issue to the JSON issues list and preserves the existing stderr message.
- Fatal exceptions still print to stderr and exit 2 in JSON mode.
- Existing text output behavior is unchanged when `--json` is absent.
- Added 3 CLI tests: valid JSON output, JSON with issues, JSON with `--require-match` zero-matches.

## Fixed (from 10_REVIEW_REPORT.md Required Fixes)

- Reverted `AGENTS.md` to HEAD — restored content and `100644` mode.
- Reverted `docs/agent/02_LOCKED_REQUIREMENTS.md` to HEAD — restored content and `100644` mode.
- Both files are no longer in the working diff.

## Modified Files

- `src/quant_research_engine/apps/cli.py`
- `tests/test_cli.py`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Not Implemented

- None. All brief items are implemented.

## Deviations from Brief

- None. Implementation follows the brief strictly.

## Validation Commands Run

```bash
uv run pytest -q
# 171 passed in 1.43s

scripts/check-progress-docs.sh
# passed

git diff --check
# passed
```

## Validation Results

All 171 tests pass. No regression. No forbidden files modified.

## Known Risks

- JSON output on stdout in JSON mode means scripts should not mix `--json` with human-readable parsing of stdout.
- The `no_matches` issue is included in the JSON issues list but also printed to stderr to preserve existing behavior; this is intentional and documented.

## Questions for Reviewer

- None.

## Git Status at Handoff

```
M docs/agent/04_TASK_HANDOFF.md
M docs/agent/05_PROGRESS.md
M docs/agent/09_CODING_HANDOFF.md
M docs/agent/10_REVIEW_REPORT.md
M docs/agent/11_AGENT_STATE.md
M docs/agent/12_AGENT_BOARD.md
M src/quant_research_engine/apps/cli.py
M tests/test_cli.py
```

No new files. No forbidden files modified. AGENTS.md and 02_LOCKED_REQUIREMENTS.md are clean.

## Next Suggested Step

Codex should re-review the implementation and run One-Shot Review-Finalize-Next.

## Next Agent State After Fix

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
