# Coding Handoff

## Task ID

QRE-DOCS-EVAL-ARTIFACTS-USAGE-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Fix applied. Ready for Codex re-review.

## Fix Applied

Codex review (`10_REVIEW_REPORT.md`) found that two module docs described factor decay as "decay ratios." The implementation computes signed differences from the smallest horizon base, not ratios. Replaced inaccurate wording in both files with explicit "signed difference, not a ratio" language.

## Files Changed

- `docs/modules/data_layer.md` — changed "base for decay ratios" to "base and reports each horizon's IC / Rank IC difference from that base (signed difference, not a ratio)"
- `docs/modules/portfolio_workflow.md` — changed "base for decay ratios" to "base; each horizon reports the signed IC / Rank IC difference from that base (not a ratio)"

## Validation Results

```bash
scripts/check-progress-docs.sh  # passed
git diff --check                # passed
```

No runtime code changes; pytest not required.

## Constraints

- Documentation-only. ✅
- No `docs/legacy/**` changes. ✅
- Factor decay now correctly described as signed difference, not ratio. ✅

## Git State

- Branch: `master`
- All doc changes uncommitted.
- Ready for Codex re-review.

## Next Suggested Step

Codex should re-review the fix and produce updated `10_REVIEW_REPORT.md`.
