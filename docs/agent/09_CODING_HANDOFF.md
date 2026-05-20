# Coding Handoff

## Task ID

QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Implementation Summary

Updated user-facing documentation for optional `--run-id` linkage and `report-audit --role run_manifest` content validation. Added sections to README, portfolio workflow docs, and portfolio layer docs describing run-ID acceptance, persistence locations, null-on-omit behavior, run-manifest validated fields, supported kinds, and audit issue codes.

## Files Changed

- `README.md` — added "Run Identity Linkage" and "Run Manifest Audit" sections after the existing JSON output docs; documents `--run-id` on 5 commands, `run_id` persistence points, validated run-manifest fields with nullable column, supported kinds, audit issue codes, and the structural-validation-only scope statement
- `docs/modules/portfolio_workflow.md` — added "Implemented run-ID linkage across durable outputs" and "Implemented run-manifest content validation in report audit" sections describing the full CLI interface, persistence locations, field validation details, and that audit validates structure not strategy quality
- `docs/modules/portfolio_layer.md` — added run-ID capability and run-manifest content validation to the "Current Scope" / "Implemented" list; includes command coverage, validated fields, supported kinds, and issue codes

## Validation Results

```bash
scripts/check-progress-docs.sh  # passed
git diff --check                # passed
```

No runtime code or executable examples were changed; `uv run pytest` is not required for this task.

## Constraints

- Documentation-only. ✅
- Do not edit `docs/legacy/**`. ✅
- Keep examples credential-free. ✅
- Do not imply run-ID linkage is a full orchestrator or transactional workflow. ✅
- State that audit validates artifact structure, not research quality. ✅

## Git State

- Branch: `master`
- All doc changes uncommitted.
- Ready for Codex review.

## Next Suggested Step

Codex should review the documentation changes and produce `10_REVIEW_REPORT.md`.
