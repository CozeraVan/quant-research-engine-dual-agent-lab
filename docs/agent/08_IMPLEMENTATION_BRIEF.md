# Implementation Brief

## Task ID

QRE-REFERENCE-MARKET-CAP-LIQUIDITY-METADATA-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Standardize latest-available market-cap and liquidity metadata from `reference.daily_basic` so QRE grouped evaluation and portfolio outputs can use consistent cross-sectional columns.

QRE already reads `reference.index_daily` for benchmarks and composes security metadata from `reference.stock_basic` plus status tables. This slice stays read-only and extends the composed metadata path with market-cap/liquidity fields derived from `reference.daily_basic`.

## Scope

Implement a narrow QRE read-side metadata slice:

1. Add latest-available `reference.daily_basic` enrichment to the read-side metadata path.
2. Expose raw market-cap and liquidity columns that are useful for grouping and diagnostics.
3. Add deterministic bucket columns for downstream grouping.
4. Preserve explicit metadata-table priority and the existing daily-derived fallback behavior.

## Required Behavior

- If `QRE_SECURITY_METADATA_TABLE` / `SR_SECURITY_METADATA_TABLE` is configured, keep the current explicit-table behavior unchanged.
- When the composed `reference.*` metadata path is active, enrich it with the latest available `reference.daily_basic` snapshot per `ts_code`.
- When the daily-derived fallback path is active, keep the existing board/list-date/status behavior and enrich it only if `reference.daily_basic` is available.
- Preserve read-only behavior. No upserts, repairs, or DDL.
- Keep unsafe SQL identifier protections in place.
- Do not require any new CLI flags for existing commands.

## Suggested Columns

At minimum, expose the following if `reference.daily_basic` provides them:

- `total_mv`
- `circ_mv`
- `turnover_rate`
- `turnover_rate_f`
- `volume_ratio`

And add deterministic grouping helpers:

- `market_cap_bucket`
- `liquidity_bucket`

Suggested bucket semantics for a first pass:

- `market_cap_bucket`
  - `small` for low total market value
  - `mid` for medium total market value
  - `large` for high total market value
- `liquidity_bucket`
  - `low` for low turnover/liquidity
  - `mid` for moderate turnover/liquidity
  - `high` for high turnover/liquidity

Use stable thresholds in code and document them in tests or comments. Keep the thresholds deterministic and easy to reason about.

## Non-Goals

- Do not add Tushare API clients, tokens, download commands, or ingestion code to QRE.
- Do not modify `../quant_ts` in this task.
- Do not implement benchmark membership or regime classification in this slice.
- Do not redesign preflight, strategy specs, or portfolio simulation.
- Do not implement full time-travel/as-of metadata throughout the engine.

## Suggested Implementation Notes

- Prefer a small private helper such as `_load_reference_daily_basic_snapshot(ts_codes)` or similar.
- Reuse the existing `reference_engine` for reference-table reads.
- Keep `_normalize_security_metadata()` as the final normalization boundary.
- If `reference.daily_basic` is absent or missing required columns, omit the enrichment rather than failing the metadata load.
- Keep tests deterministic by monkeypatching `pd.read_sql_query`, `table_exists()`, and `get_table_columns()` where appropriate.

## Expected Tests

Add or update targeted tests in `tests/test_postgres_store.py`:

- composed reference metadata can be enriched with latest-available `reference.daily_basic` columns;
- market-cap bucket mapping is deterministic for low/mid/high inputs;
- liquidity bucket mapping is deterministic for low/mid/high inputs;
- explicit `security_metadata_table` still takes precedence and does not get silently overridden;
- missing `reference.daily_basic` keeps the previous metadata behavior intact;
- fallback from daily bars still works when `reference.stock_basic` is absent.

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

- QRE can read latest market-cap and liquidity metadata from `reference.daily_basic` without adding producer code.
- The enrichment is read-only and deterministic.
- Explicit metadata table priority and fallback behavior remain backward-compatible.
- Targeted tests pass.
- Progress docs and handoff files are updated by Claude Code after implementation.
