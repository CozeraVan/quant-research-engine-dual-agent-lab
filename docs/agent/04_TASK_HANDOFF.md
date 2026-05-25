# Task Handoff

## Task ID

QRE-BENCHMARK-MEMBERSHIP-INDUSTRY-ADAPTERS-001

## Current Status

READY_FOR_CLAUDE_CODE

## Current Owner

CLAUDE_CODE

## Problem Summary

QRE has finished the read-side wiring needed to consume populated `reference.*` tables:

- benchmark reads now use `benchmark_db_url -> reference_db_url -> market_db_url`;
- security metadata now composes from `reference.stock_basic`, `reference.stock_suspend`, `reference.stock_st`, and `reference.stock_risk_warning`;
- latest-available `reference.daily_basic` enrichment is complete;
- the next non-deferred read-side gap is benchmark membership plus industry grouping normalization from `reference.index_weight` and the existing industry passthrough.

## Overall Project Completion

QRE is in advanced experimental MVP / user-acceptance state. Most core engine work is complete:

- Data layer and preflight: complete for the current MVP slice.
- Evaluation engine: complete for the current MVP; real regime classification remains future work.
- Portfolio engine: complete for the current MVP.
- Reporting, manifests, audit, research-run, strategy IO, smoke tooling, and GUI: complete for the current MVP.
- Upstream data production: intentionally out of QRE and owned by `../quant_ts`.

Practical completion estimate: QRE is roughly 90%+ complete for the current MVP scope. Larger items such as real regime grouping and deeper as-of metadata are future enhancements rather than current blockers.

## Implementation Assignment For Claude Code

Read and implement:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

Primary code task:

- add a read-only `reference.index_weight` adapter for benchmark membership;
- normalize industry metadata into a stable grouping column without mutating the raw passthrough;
- preserve explicit metadata-table priority and existing fallback behavior;
- thread benchmark context through existing read-side paths only where it is already known;
- add targeted tests and concise docs.

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

If a new slice is assigned later, Claude Code should update `09_CODING_HANDOFF.md` with files changed, behavior summary, and validation output, then return to Codex for review in `10_REVIEW_REPORT.md`.
