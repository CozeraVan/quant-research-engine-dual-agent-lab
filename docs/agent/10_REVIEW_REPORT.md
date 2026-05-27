# Review Report

## Task ID

QRE-REFERENCE-ASOF-METADATA-SNAPSHOT-001

## Reviewer

CODEX

## Review Status

PASS

## Findings

No blocking findings.

## Behavior Expected

- QRE remains read-only with respect to upstream data production.
- `metadata_as_of` controls every metadata snapshot used by eval/preflight/research-run, including the backtest stage of research-run.
- Historical risk-warning membership is derived as of the requested snapshot date, not `CURRENT_DATE`.
- Direct backtest artifacts and manifests also record `metadata_as_of` so the same snapshot can be reproduced across all entry points.
- Existing evaluation outputs remain unchanged.
- No Tushare/producer code was added.

## Validation Evidence

```bash
uv run pytest -q tests/test_cli.py tests/test_research_run.py tests/test_preflight.py tests/test_data_assembler.py tests/test_postgres_store.py
# 410 passed, 2 warnings

scripts/check-progress-docs.sh
# Progress docs check passed.

git diff --check
# clean
```

## Residual Risks

- The run-manifest metadata_as_of behavior is implied by the shared manifest writer path; no separate manifest assertion test was added in this slice.
