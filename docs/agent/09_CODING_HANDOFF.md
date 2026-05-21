# Coding Handoff

## Task ID

QRE-FACTOR-MISSING-HANDOFF-STANDARD-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED. The operational missing-factor handoff standard is complete and ready for Codex review.

## Implementation Summary

Implemented the missing-factor handoff pipeline from `docs/agent/08_IMPLEMENTATION_BRIEF.md`, operationalizing the contract defined in `docs/strategy_entry/missing_factor_request.md`:

- **new module `missing_factor.py`** (`src/quant_research_engine/strategies/missing_factor.py`, ~260 lines):
  - `MissingFactorRequest` — frozen dataclass matching the JSON schema with all required fields (`strategy_id`, `alias`, `indicator`, `category`, `source`, `period`, `params`, `output`, `expected_table`, `expected_column`, `date_range`, `reason`, `required`) and a `to_dict()` method.
  - `extract_missing_factors(report, spec, request)` — scans a `PreflightReport` for `factor_schema:*` checks with `status="error"`, maps them back to `FactorFieldRequest` metadata via `StrategySpec`, and returns a sorted list of `MissingFactorRequest` objects.
  - `emit_missing_factor_requests(requests, output_dir)` — writes `missing_factor_requests.json` to the output directory (creates it if needed), with an empty `[]` when no factors are missing.
  - `_parse_category(table_name)` — extracts semantic category from `stock_daily_{category}_{source}` table names.
  - `_parse_source(table_name)` — extracts price source from table names.
  - `_parse_column(column)` — heuristically parses factor column names into indicator/period/params/output. Handles known patterns: simple (`rsi_2`, `ema_200`), Bollinger (`bbu_20_2_0_2_0` → upper, `bbl_...` → lower), MACD (`macd_12_26_9`, `macd_signal_12_26_9`). Unknown columns use the full column name as the indicator with best-effort period extraction from trailing numbers.
  - `_build_missing_factor()` — assembles a `MissingFactorRequest` from a `FactorFieldRequest` plus strategy/request context.

- **Wired into CLI** (`src/quant_research_engine/apps/cli.py`):
  - Added `--output-dir` flag to `qre preflight` parser.
  - Preflight handler now calls `extract_missing_factors()` after the report is built.
  - When `--output-dir` is provided, `emit_missing_factor_requests()` writes the JSON file.
  - Stdout always prints `missing_factor_count`, `missing_factor_status` (`ok`/`pending`), and per-missing-factor lines with alias and expected table/column.

- **Tests** (`tests/test_missing_factor.py`, new, 25 tests):
  - `MissingFactorRequest.to_dict()` round-trip (2 tests)
  - Table name parsing (4 tests)
  - Column name parsing (8 tests)
  - `extract_missing_factors()` — no missing, warning-only, table missing, column missing, multi-factor sorted, unknown logical name, non-schema checks ignored (7 tests)
  - `emit_missing_factor_requests()` — writes JSON, empty array, creates dir (3 tests)
  - `_build_missing_factor()` (2 tests)

- **CLI tests** (`tests/test_cli.py`, 3 new tests):
  - `--output-dir` emits empty `[]` when all factors present
  - `--output-dir` emits requests when table is missing, with full schema assertions
  - no `--output-dir` prints status to stdout only, no file written

## Files Changed

- `src/quant_research_engine/strategies/missing_factor.py` — new
- `src/quant_research_engine/apps/cli.py` — added `--output-dir` flag and missing-factor extraction/emission in preflight handler
- `tests/test_missing_factor.py` — new (25 tests)
- `tests/test_cli.py` — 3 new CLI tests
- `docs/strategy_entry/missing_factor_request.md` — added lifecycle states section
- `docs/agent/04_TASK_HANDOFF.md` — updated status/owner/phase
- `docs/agent/05_PROGRESS.md` — updated phase/task entry/verified state
- `docs/agent/09_CODING_HANDOFF.md` — this file
- `docs/agent/11_AGENT_STATE.md` — phase to CODEX_REVIEWING, owner to CODEX
- `docs/agent/12_AGENT_BOARD.md` — message/recipient/next step updated

## Validation Results

```
uv run pytest tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py -q
168 passed, 2 warnings in 2.01s
```

- All 25 new missing-factor tests pass.
- All 3 existing preflight tests pass (no regression).
- All 5 existing strategy spec tests pass (no regression).
- All 135 CLI tests pass (no regression).
- 2 pre-existing numpy warnings (unrelated).

```
scripts/check-progress-docs.sh → passed
git diff --check → passed
```

## Design Decisions

- **Empty-request behavior**: when no factors are missing, `missing_factor_requests.json` is written as `[]` (empty array). This was chosen over omitting the file because a deterministic file presence makes upstream tooling simpler — `indicators_tushare` can always check for the file rather than needing to distinguish "no missing factors" from "no output directory configured."
- **`required` always `true`**: the current low-level `StrategySpec` format does not have optional factor semantics. All factors in `factor_fields` are treated as required. When the standard entry format matures, `required` can be driven by the `factor_requirements.required` field and optional factors that are missing can emit requests with `required: false`.
- **Column parsing is heuristic**: `_parse_column()` uses known indicator prefixes to extract structured metadata from factor column names. Unknown columns fall back to using the full column name as the indicator. This is explicitly documented as best-effort — the `expected_table` and `expected_column` fields are the authoritative fields for upstream consumption.
- **No `--output-dir` = no file, but stdout always shows status**: the CLI always prints `missing_factor_count` and `missing_factor_status` to stdout regardless of whether `--output-dir` is set. This keeps preflight output self-describing without requiring a file write.

## Residual Limitations

- **Optional factors**: all factors are treated as `required: true` because the current `StrategySpec` has no optional-factor concept. This aligns with the brief's scope.
- **Column parsing**: `_parse_column()` handles common known patterns (RSI, EMA, MACD, Bollinger) but falls back to raw column names for unrecognized patterns. The `expected_table` and `expected_column` fields are always correct regardless.
- **No factor catalog integration**: `category` is inferred from table name patterns rather than looked up from a factor catalog. This is consistent with the brief's "documentation-first" approach.
- **Single-strategy only**: each preflight run processes one strategy YAML. Multi-strategy batch missing-factor aggregation is future work noted in `docs/strategy_entry/missing_factor_request.md`.

## Constraints

- No database writes.
- No invocation of external projects (`indicators_tushare`).
- No changes to existing report behavior, manifest roles, or audit logic.
- Read-only data access preserved.
- Existing uncommitted GUI changes preserved (outside this task).

## Git State

- Branch: `master`
- Last finalized commit: `146acd2` (Codex finalized `QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001`)
- Working tree contains missing-factor module, CLI wiring, tests, and agent doc updates.

## Next Suggested Step

Codex reviews the implementation, runs validation, and writes `docs/agent/10_REVIEW_REPORT.md`.
