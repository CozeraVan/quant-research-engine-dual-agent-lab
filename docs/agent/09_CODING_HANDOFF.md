# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-INVALID-JSON-VALIDATION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Implemented. Ready for Codex review.

## Scope Summary

- Normalize invalid manifest JSON parse failures into manifest-specific `ValueError`.
- Add focused malformed-JSON tests.
- Preserve valid-manifest behavior and recent shape validation.

## Files Changed

- `src/quant_research_engine/portfolio/report_manifest.py` — wrapped `json.loads()` with try/except for `JSONDecodeError`
- `tests/test_portfolio_report_manifest.py` — added `test_report_manifest_rejects_incomplete_json_object` and `test_report_manifest_rejects_non_json_text`

## Validation Results

```bash
uv run pytest tests/test_portfolio_report_manifest.py -q  # 18 passed in 0.05s
uv run pytest -q                                           # 195 passed in 1.77s
scripts/check-progress-docs.sh                             # passed
git diff --check                                           # passed
```

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation To Run

```bash
uv run pytest tests/test_portfolio_report_manifest.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Constraints

- Do not change valid-manifest behavior. ✅ preserved
- Do not modify CLI code unless strictly necessary. ✅ no CLI changes
- Do not modify forbidden files from the brief. ✅ compliant
- Do not push. ✅ not pushed

## Git State

- Branch: `master`
- Uncommitted changes: 2 files, 22 insertions, 1 deletion
- Last commit: `950c814 feat: validate manifest root payload shape`
