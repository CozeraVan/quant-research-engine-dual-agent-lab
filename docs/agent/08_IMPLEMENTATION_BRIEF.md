# Implementation Brief

## Task ID

QRE-FACTOR-MISSING-HANDOFF-STANDARD-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Current Brief Type

Implementation brief. Documentation-first plus minimal read-only tooling surface for missing-factor handoff.

## Background

`QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001` is finalized. The strategy entry standard now exists under `docs/strategy_entry/`.

The next bottleneck is operational handoff: missing factors are specified in docs but not yet standardized as a durable workflow artifact that can be consumed by upstream `indicators_tushare`.

We need a practical, minimal, and non-invasive slice that closes the loop:

- write strategy
- validate factors
- emit missing-factor request file
- upstream computes/backfills
- re-run validation/backtest

## Canonical Design Sources

- `docs/strategy_entry/missing_factor_request.md`
- `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md`

## Goal

Operationalize missing-factor handoff with a stable output contract and minimal CLI/tool support in QRE.

Deliverables:

1. Standardized output file contract:
   - `missing_factor_requests.json`
2. Stable write location conventions.
3. Minimal read-only CLI/tool command to emit request artifacts from a strategy entry validation flow.
4. Tests for schema shape and edge cases.
5. Documentation updates describing lifecycle states and retry workflow.

## Scope

In scope:

- Strategy validation path and artifact writing logic.
- Missing-factor request schema enforcement at QRE boundary.
- Documentation and examples for pending/fulfilled/blocked flow.
- CLI surface update (new or extended command) that does not mutate database data.

Out of scope:

- Running `indicators_tushare` from QRE.
- Writing factors into PostgreSQL from QRE.
- Runtime strategy compiler for full high-level entry format.
- GUI integration.

## Required Implementation Items

1. Artifact emission

- Emit `missing_factor_requests.json` when required factors are absent.
- When nothing is missing, emit either:
  - empty array file `[]`, or
  - no file but explicit status output.
  Choose one behavior and document it clearly.

2. Output path convention

- Define deterministic output path relative to `--output-dir` or run folder.
- Keep path consistent across repeated runs.

3. Schema guarantees

- Required keys must match `docs/strategy_entry/missing_factor_request.md`.
- Include `required` flag and reason fields.
- Include date range context from experiment input when available.

4. Status semantics

- Document lifecycle states:
  - `pending` (request emitted, waiting upstream)
  - `fulfilled` (validation passes after data availability)
  - `blocked` (upstream unavailable/permission/data contract mismatch)

5. Tests

- Missing-factor request file is written for missing-required factors.
- Optional factors behavior is covered.
- Multi-factor and multi-strategy aggregation/serialization behavior is deterministic.
- Empty-request behavior is covered.

## Suggested File Surface

Adjust based on actual code layout:

- `src/quant_research_engine/...` validation/strategy entry module(s)
- `src/quant_research_engine/apps/cli.py` (or nearest CLI command wiring)
- `tests/...` for strategy validation and CLI regression
- `docs/strategy_entry/missing_factor_request.md` (small clarifications only)
- `docs/strategy_entry/README.md` and/or workflow docs for lifecycle

## Non-Goals

- Do not add DB writes.
- Do not invoke external projects directly.
- Do not alter completed full-market report behavior.
- Do not refactor unrelated engine modules.

## Acceptance Criteria

- [ ] Missing-factor request artifact is emitted with stable schema.
- [ ] CLI/tool output clearly indicates missing-factor status.
- [ ] Tests cover required, optional, empty, and multi-item cases.
- [ ] Documentation explains lifecycle and rerun flow.
- [ ] `docs/agent/09_CODING_HANDOFF.md` updated with evidence.

## Validation Commands

At minimum:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

If full test suite is too broad, run a targeted subset and record exact commands in `09_CODING_HANDOFF.md`.

## Risks

- Scope creep into strategy compiler/runtime.
- Ambiguous behavior when no missing factors are present.
- Inconsistent schema fields between docs and emitted JSON.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
