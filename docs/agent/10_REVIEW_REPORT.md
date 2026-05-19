# Review Report

## Task ID

QRE-REPORT-MANIFEST-CLI-OPTIONAL-NULL-METADATA-REGRESSION-001

## Written By

CODEX

## Review Outcome

PASS

## Reviewed Implementation

Claude Code implementation in the current working tree.

Changed files reviewed:

- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Review Summary

Review passed.

`report-files --json` and `report-audit --json` now both have CLI regression coverage for manifest entries that explicitly set optional `symbol`, `window`, and `group_by` metadata to `null`. The implementation stays test-only and preserves current JSON serialization behavior: optional metadata keys whose value resolves to `None` are omitted from entry payloads.

## Compliance with Implementation Brief

Compliant.

- `report-files --json` now locks explicit `null` optional file-entry metadata with exit code `0`.
- `report-audit --json` now locks explicit `null` optional file-entry metadata with exit code `0` when the referenced file exists.
- Current JSON serialization behavior for `None` optional metadata is preserved.
- Existing valid-manifest CLI behavior is unchanged.
- Existing malformed optional metadata type-error coverage remains intact.
- No CLI or loader code changes were introduced.

## Locked Requirements Check

No locked-requirement violation found.

- R-CORE-001: Existing valid-manifest behavior is preserved.
- R-CORE-002: No unrelated rewrite observed.
- R-CORE-003: Focused and full validation passed.
- R-CORE-004 / R-QRE-006: No credentials or sensitive values added.
- R-QRE-003: No signal, execution, or portfolio decision logic changed.
- R-QRE-005: No database access or writes added.
- R-QRE-007: Report-manifest CLI contracts remain intact and the valid side of the optional metadata contract is now covered at the CLI boundary.
- R-DUAL-002: Claude Code implemented within the approved brief.

## Code Quality Review

The coverage is added next to the existing malformed optional metadata tests in `tests/test_cli.py`, which keeps the regression surface easy to audit. The tests assert both successful command completion and the important serialization invariant for `None` optional fields.

## Test Review

Validation commands run by Codex:

```bash
uv run pytest tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
scripts/git-finalize-check.sh
```

Results:

- `uv run pytest tests/test_cli.py -q`: `85 passed in 1.07s`
- `uv run pytest -q`: `229 passed in 2.14s`
- `scripts/check-progress-docs.sh`: passed
- `git diff --check`: passed
- `scripts/git-finalize-check.sh`: passed

Coverage is adequate:

- explicit `null` optional `symbol`, `window`, and `group_by` metadata is covered through `report-files --json`;
- explicit `null` optional `symbol`, `window`, and `group_by` metadata is covered through `report-audit --json`;
- existing non-string optional metadata type-error CLI regressions remain covered;
- valid manifest flows continue to pass in the full suite.

## Required Fixes

None.

## Recommended Improvements

Next low-risk hardening step: add CLI regression coverage for explicit `null` top-level `schema_version` so the accepted optional schema-version path is locked at the same command boundary as existing schema-version type-error coverage.

## Follow-up Tasks

- Create the local checkpoint for this accepted implementation.
- Prepare the next brief around CLI regression coverage for explicit `null` `schema_version`.
- Keep the next task narrowly scoped and test-first.

## Final Recommendation

Accept and commit locally. Do not push.

## Next Agent State

After local checkpoint and next planning:

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
