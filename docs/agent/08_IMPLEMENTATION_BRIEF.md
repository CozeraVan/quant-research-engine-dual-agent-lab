# Implementation Brief

## Task ID

QRE-BENCHMARK-MEMBERSHIP-INDUSTRY-ADAPTERS-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Add read-only benchmark membership and industry classification adapters to QRE so cross-sectional grouping can use stable metadata columns without restoring any Tushare producer code.

QRE already reads benchmark bars from `reference.index_daily` and security metadata from `reference.stock_basic` plus status tables. The next read-side slice is to consume `reference.index_weight` for benchmark membership and to normalize industry metadata into a stable grouping column.

## Scope

Implement a narrow read-side metadata slice:

1. Add latest-available `reference.index_weight` enrichment for benchmark membership when benchmark context is available.
2. Expose stable benchmark membership columns for downstream grouping and diagnostics.
3. Add a normalized industry grouping column while preserving the raw `industry` passthrough.
4. Preserve explicit metadata-table priority and existing fallback behavior.

## Required Behavior

- If `QRE_SECURITY_METADATA_TABLE` / `SR_SECURITY_METADATA_TABLE` is configured, keep the current explicit-table behavior unchanged.
- When the composed `reference.*` metadata path is active, enrich it with the latest available `reference.index_weight` snapshot for the requested benchmark code, if benchmark context is available.
- When the daily-derived fallback path is active, keep the existing board/list-date/status behavior and add the industry normalization only if an industry source column exists.
- Preserve read-only behavior. No upserts, repairs, or DDL.
- Keep unsafe SQL identifier protections in place.
- Do not require any new CLI flags for existing commands.

## Suggested Columns

At minimum, expose the following benchmark membership fields when benchmark context is available:

- `benchmark_code`
- `benchmark_weight`
- `is_benchmark_member`

And add a stable industry grouping column:

- `industry_group`

Suggested semantics for the first pass:

- `is_benchmark_member` is `True` when the latest available `reference.index_weight` row exists for the requested benchmark code and `ts_code`.
- `benchmark_weight` is the latest available weight for the requested benchmark code and `ts_code`; null when unavailable.
- `industry_group` is the normalized version of the raw `industry` passthrough, with whitespace trimmed and empty strings converted to null.

Use stable, deterministic logic and document it in tests or comments. Keep the implementation easy to reason about.

## Non-Goals

- Do not add Tushare API clients, tokens, download commands, or ingestion code to QRE.
- Do not modify `../quant_ts` in this task.
- Do not implement benchmark membership history beyond the latest available snapshot.
- Do not implement real regime classification in this slice.
- Do not redesign preflight, strategy specs, or portfolio simulation.
- Do not implement full time-travel/as-of metadata throughout the engine.

## Suggested Implementation Notes

- Prefer a small private helper such as `_load_reference_index_weight_snapshot(index_code, ts_codes)` or similar.
- Reuse the existing `reference_engine` for reference-table reads.
- Keep `_normalize_security_metadata()` as the final normalization boundary.
- If `reference.index_weight` is absent or missing required columns, omit the enrichment rather than failing the metadata load.
- Keep tests deterministic by monkeypatching `pd.read_sql_query`, `table_exists()`, and `get_table_columns()` where appropriate.
- Thread benchmark context through existing read-only paths only where the benchmark code is already known.

## Expected Tests

Add or update targeted tests in `tests/test_postgres_store.py` and `tests/test_preflight.py`:

- composed reference metadata can be enriched with latest-available `reference.index_weight` rows for a benchmark code;
- benchmark membership selection is deterministic for the latest available snapshot;
- explicit `security_metadata_table` still takes precedence and does not get silently overridden;
- missing `reference.index_weight` keeps the previous metadata behavior intact;
- `industry_group` is normalized from raw industry values without mutating the raw `industry` column;
- preflight benchmark handling passes benchmark context through when it is already available.

## Validation Commands

Run at minimum:

```bash
uv run pytest -q tests/test_postgres_store.py
uv run pytest -q tests/test_preflight.py tests/test_data_assembler.py
scripts/check-progress-docs.sh
git diff --check
```

If time permits:

```bash
uv run pytest -q
```

## Acceptance Criteria

- QRE can read latest benchmark membership metadata from `reference.index_weight` without adding producer code.
- Industry metadata is normalized into a stable grouping column while preserving the raw passthrough.
- Explicit metadata table priority and fallback behavior remain backward-compatible.
- Targeted tests pass.
- Progress docs and handoff files are updated by Claude Code after implementation.
