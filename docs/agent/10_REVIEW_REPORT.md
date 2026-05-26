# Review Report

## Task ID

QRE-BENCHMARK-MEMBERSHIP-INDUSTRY-ADAPTERS-001

## Reviewer

CODEX

## Review Status

PASS

## Findings

No blocking findings.

The fix pass aligns the benchmark membership loader with the real `quant_ts` `reference.index_weight.con_code` schema, threads `benchmark_code` through preflight metadata loading, and preserves the read-only QRE boundary with explicit-table precedence intact.

## Behavior Expected

- QRE remains read-only with respect to upstream data production.
- `load_security_metadata()` enriches composed reference metadata with latest-available benchmark membership from `reference.index_weight` when benchmark context is available.
- `PreflightRunner.run()` threads benchmark context through to `load_security_metadata()` when the request already includes a benchmark code.
- `industry_group` is normalized from raw industry metadata while preserving the raw passthrough.
- Explicit `QRE_SECURITY_METADATA_TABLE` behavior remains first priority and is not silently overridden.
- Missing `reference.index_weight` keeps the previous metadata behavior intact.

## Validation Evidence

```bash
uv run pytest -q tests/test_postgres_store.py
# 41 passed in 0.60s

uv run pytest -q tests/test_preflight.py tests/test_data_assembler.py
# 8 passed in 0.32s

uv run pytest -q
# 889 passed, 2 warnings

scripts/check-progress-docs.sh
# Progress docs check passed.

git diff --check
# clean
```

## Residual Risks

- The benchmark membership snapshot is still latest-available rather than full as-of history. That is acceptable for this slice, but deeper time-varying semantics remain a later enhancement.
