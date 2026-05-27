# Implementation Brief

## Task ID

QRE-REFERENCE-ASOF-METADATA-SNAPSHOT-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Thread an optional as-of date into read-side metadata loading so evaluation and preflight paths use metadata snapshots aligned with the run date rather than always using the latest available snapshot. The current latest-snapshot fallback should remain intact when no as-of date is supplied.

Codex review found no remaining blocking fixes before acceptance.

## Scope

Implement a narrow consumer-side wiring slice:

1. Extend read-side metadata loading helpers to accept an optional as-of date.
2. Thread the run date through eval/preflight/research-run paths so metadata joins use the latest snapshot at or before that date.
3. Preserve the current latest-snapshot fallback when as-of is omitted.
4. Keep the work consumer-side only. Do not touch `quant_ts`, Tushare download/ingest code, or any producer-side schema.

## Required Behavior

- When an as-of date is provided, metadata loaders should choose the latest available snapshot not after that date.
- Current latest-snapshot behavior should remain available when no as-of date is supplied.
- Historical risk-warning membership must be evaluated as of the requested date, not the host clock.
- `research-run` backtest artifacts and manifests must remain reproducible with the same metadata snapshot inputs.
- Direct single backtest commands accept `metadata_as_of` and carry it through the same read-side metadata loader path.
- `ResearchFrameAssembler.build()` receives `metadata_as_of` from the direct single backtest entry point.
- Direct single backtest run-request payloads and manifests record `metadata_as_of`.
- Existing event summary, IC/Rank IC, quantile, random-baseline, factor-decay, and regime summary outputs must remain unchanged.
- No producer-side code or new database tables may be introduced.

## Suggested Implementation Notes

- Prefer adding as-of selection to the shared metadata loader or a small helper used by both preflight and evaluation assembly.
- Reuse the existing read-only metadata and benchmark load paths already available in the data store.
- Ensure the as-of selection is deterministic and aligns on the run date or metadata request date.
- Keep the existing eval-config / CLI / manifest wiring pattern so the new metadata selection does not alter report schemas.

## Non-Goals

- Do not change single-symbol, batch-summary, or shared-cash execution semantics beyond metadata snapshot plumbing.
- Do not redesign the report schema beyond the benchmark plumbing needed for the eval frame.
- Do not add new data ingestion or producer-side code.
- Do not touch `quant_ts`.
- Do not change portfolio benchmark math.

## Expected Tests

Add or update targeted tests in:

- `tests/test_postgres_store.py`
- `tests/test_data_assembler.py`
- `tests/test_preflight.py`
- `tests/test_cli.py`
- `tests/test_research_run.py`

Targeted coverage should prove:

- metadata loaders honor an optional as-of date when present;
- evaluation/preflight/research-run paths pass the correct as-of date through;
- empty or missing-as-of paths still fall back cleanly without breaking current outputs;
- existing event summary, IC/Rank IC, quantile, random-baseline, and factor-decay outputs remain unchanged.

## Validation Commands

Run at minimum:

```bash
uv run pytest -q tests/test_postgres_store.py tests/test_data_assembler.py tests/test_preflight.py tests/test_cli.py tests/test_research_run.py
scripts/check-progress-docs.sh
git diff --check
```

If time permits:

```bash
uv run pytest -q
```

## Acceptance Criteria

- Metadata snapshots are selected as-of the run date when the new parameter is supplied.
- Existing latest-snapshot behavior remains unchanged when the parameter is omitted.
- Risk-warning membership respects the requested as-of date.
- `research-run` backtest and manifest artifacts record the same metadata snapshot inputs used during execution.
- Direct `backtest-single` artifacts record the same metadata snapshot inputs used during execution.
- Existing evaluation outputs remain unchanged.
- Targeted tests pass.
- Progress docs and handoff files are updated by Claude Code after implementation.
