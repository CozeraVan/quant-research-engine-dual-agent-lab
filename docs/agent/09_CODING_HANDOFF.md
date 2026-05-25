# Coding Handoff

## Task ID

QRE-BENCHMARK-MEMBERSHIP-INDUSTRY-ADAPTERS-001

## Written By

CODEX

## Status

READY_FOR_IMPLEMENTATION

## Current Owner

CLAUDE_CODE

## Problem Summary

QRE now has benchmark/reference routing, `reference.daily_basic` enrichment, and read-only security metadata composition in place. The next non-deferred data-layer gap is to standardize benchmark membership and industry classification metadata so grouped evaluation and portfolio outputs can use stable cross-sectional columns.

The upstream source for benchmark membership already exists in sibling `quant_ts` as `reference.index_weight`. QRE should consume that table read-only and keep all producer/ingest work out of this repository.

## Overall Project Completion

QRE is still in advanced experimental MVP / user-acceptance state. Most core engine work is complete:

- Data layer and preflight: complete for the current MVP slice, with benchmark membership and industry grouping as the next read-side adapter task.
- Evaluation engine: complete for the current MVP; real regime classification remains future work.
- Portfolio engine: complete for the current MVP.
- Reporting, manifests, audit, research-run, strategy IO, smoke tooling, and GUI: complete for the current MVP.
- Upstream data production: intentionally out of QRE and owned by `../quant_ts`.

Practical completion estimate: QRE remains roughly 90%+ complete for the current MVP scope. Larger items such as deeper benchmark membership history, real regime grouping, and full time-varying/as-of metadata are future enhancements rather than current blockers.

## Implementation Assignment For Claude Code

Read and implement:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

Primary code task:

- add a read-only `reference.index_weight` adapter for benchmark membership;
- normalize industry metadata into a stable grouping column without mutating the raw passthrough;
- preserve explicit metadata-table priority and existing fallback behavior;
- thread benchmark context through existing read-side paths only where it is already known;
- add targeted tests and concise docs.

## Suggested Step-by-Step Execution

1. Extend the read-side metadata adapter to load the latest `reference.index_weight` snapshot for a benchmark code when benchmark context is present.
2. Add benchmark membership columns for downstream grouping and diagnostics.
3. Add a normalized `industry_group` column while preserving the raw `industry` passthrough.
4. Keep explicit metadata tables first-priority and skip enrichment when the source table is missing.
5. Add focused tests for latest-snapshot selection, fallback behavior, and normalization.
6. Update the agent/doc state files so the next handoff is unambiguous.

## Hard Constraints

- Do not add Tushare download, token, sync, or ingestion code to QRE.
- Do not modify `../quant_ts` for this task.
- Do not change portfolio execution semantics.
- Do not broaden into real regime classification or full time-varying/as-of metadata.
- Keep QRE read-only against upstream databases.

## Validation Expected From Claude Code

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

## Handoff Back To Codex

After implementation, Claude Code should update `09_CODING_HANDOFF.md` with files changed, behavior summary, and validation output, then return to Codex for review in `10_REVIEW_REPORT.md`.
