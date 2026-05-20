# Review Report

## Task ID

QRE-RUN-MANIFEST-CONTENT-VALIDATION-001

## Written By

CODEX

## Review Outcome

PASS

## Reviewed Implementation

Claude Code implementation and follow-up fix in the current working tree.

Changed files reviewed:

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Review Summary

Review passed.

`ReportManifest.validate_contents()` now dispatches `role == "run_manifest"` JSON artifacts to a dedicated `_validate_run_manifest()` validator. The validator checks required top-level fields, rejects invalid field types, allows only `portfolio_backtest_run_manifest` and `evaluation_run_manifest` kinds, keeps `run_id: null` valid, and rejects present-null values for all other required non-null fields.

## Compliance with Implementation Brief

Compliant.

- Role-specific validation for `role == "run_manifest"` was added.
- Summary JSON validation remains generic JSON-object validation.
- Required fields are validated: `schema_version`, `kind`, `run_id`, `command`, `strategy_path`, `artifacts`.
- `schema_version` must be integer `1`.
- `kind` must be one of the supported run-manifest kinds.
- `run_id` may be string or null.
- `command` and `strategy_path` must be strings.
- `artifacts` must be a list of strings.
- Missing fields produce `missing_run_manifest_field`.
- Invalid fields produce `invalid_run_manifest_field`.
- `report-audit --role run_manifest --json` reports malformed run manifests through the existing issue payload.

## Required Fix Follow-up

The prior Codex review requested a fix for present-null required fields. The fix is complete:

- `schema_version: null` now returns `invalid_run_manifest_field`.
- `kind: null` now returns `invalid_run_manifest_field`.
- `command: null` now returns `invalid_run_manifest_field`.
- `strategy_path: null` now returns `invalid_run_manifest_field`.
- `artifacts: null` now returns `invalid_run_manifest_field`.
- `run_id: null` remains valid.

Codex reran the previous reproduction case and received 4 `invalid_run_manifest_field` issues instead of 0.

## Locked Requirements Check

No locked-requirement violation found.

- R-CORE-001: Existing report discovery and audit behavior is preserved except for stricter malformed run-manifest issues.
- R-CORE-002: Change is scoped to report-manifest validation and tests.
- R-CORE-003: Focused and full validation passed.
- R-QRE-005: Data access remains read-only.
- R-QRE-007: Report manifest contracts are preserved; file-entry schema is unchanged.
- R-GIT-002: No push performed.

## Test Review

Validation commands run by Codex:

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

Results:

- `uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q`: `158 passed, 2 warnings in 1.78s`
- `uv run pytest -q`: `346 passed, 2 warnings in 3.30s`
- `scripts/check-progress-docs.sh`: passed
- `git diff --check`: passed

Additional reproduction run by Codex:

```bash
uv run python - <<'PY'
import json, tempfile
from pathlib import Path
from quant_research_engine.portfolio.report_manifest import ReportManifest

with tempfile.TemporaryDirectory() as d:
    base = Path(d)
    (base / "run_manifest.json").write_text(
        json.dumps({
            "schema_version": None,
            "kind": "portfolio_backtest_run_manifest",
            "run_id": None,
            "command": None,
            "strategy_path": None,
            "artifacts": None,
        }),
        encoding="utf-8",
    )
    (base / "report_manifest.json").write_text(
        json.dumps({
            "kind": "shared_cash_backtest_report_manifest",
            "files": [{
                "key": "run_manifest",
                "path": "run_manifest.json",
                "filename": "run_manifest.json",
                "role": "run_manifest",
            }],
        }),
        encoding="utf-8",
    )
    issues = ReportManifest.from_path(base / "report_manifest.json").validate_contents(role="run_manifest")
    print(len(issues))
    for issue in issues:
        print(issue.code, issue.message)
PY
```

Result: 4 `invalid_run_manifest_field` issues for `schema_version`, `command`, `strategy_path`, and `artifacts`.

## Required Fixes

None.

## Final Recommendation

Accept locally. Do not push.

## Next Agent State

- Phase: `DONE`
- Owner: `USER`
