# Implementation Brief

## Task ID

QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Current Brief Type

Implementation brief. Documentation-focused implementation with light schema/validation examples if needed.

## Background

`QRE-REPORT-MT5-TV-FULL-MARKET-001` is finalized. The next highest-priority gap is still strategy entry standardization.

User has repeatedly clarified:

- QRE should not rewrite `research-notes` / `strategy-research`.
- QRE should define a standard, understandable strategy entry contract.
- `indicators_tushare` remains the factor-calculation/upstream project.
- Goal workflow should be simplified to:
  - write strategy
  - check factor library
  - run backtest
  - request missing factors upstream when needed

Current low-level `StrategySpec` YAML is usable but hard to scale across many factors, many periods, and many strategy families.

## Canonical Design Sources

- `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md`
- `docs/superpowers/specs/2026-05-21-full-market-backtest-report-design.md`

This task implements the strategy-entry authoring standard docs from the design, not the compiler itself.

## Goal

Create a clear, modular, user-facing strategy entry contract document set under QRE docs so humans, Codex, Claude Code, and external strategy projects can author entries consistently and quickly.

Deliverables:

- strategy entry standard document
- factor requirements document
- missing-factor request document
- experiment plan and run metadata document
- at least 3 concrete strategy-entry examples (different strategy families) using the new standard format

## Required Output Documents

Target location: `docs/strategy_entry/` (create if absent).

Required files:

1. `README.md`
2. `strategy_card.md`
3. `factor_requirements.md`
4. `missing_factor_request.md`
5. `experiment_plan.md`
6. `examples.md`

## Content Requirements

`README.md` must include:

- purpose and scope
- relation to QRE engine and upstream projects
- end-to-end authoring flow
- minimal “quick start” example

`strategy_card.md` must include:

- required fields and optional fields
- entry/exit/risk/position sizing sections
- period/frequency semantics for daily data
- naming/versioning conventions

`factor_requirements.md` must include:

- factor identifier format
- source table/column expectations
- period handling and parameterization rules
- factor dependency declaration examples

`missing_factor_request.md` must include:

- request payload schema for upstream `indicators_tushare`
- required vs optional fields
- examples for missing indicator and missing period

`experiment_plan.md` must include:

- run metadata standard (`run_id`, strategy version, universe, date range)
- backtest mode options
- acceptance checklist for “entry is runnable”

`examples.md` must include at least 3 strategy families:

- trend-following sample
- mean-reversion sample
- breakout or momentum sample

Each example should provide:

- human-readable strategy summary
- standardized entry fields
- mapped low-level fields for current QRE usage

## Non-Goals

- Do not implement strategy compiler/preflight runtime code in this task.
- Do not modify external repositories.
- Do not compute indicators inside QRE.
- Do not rewrite portfolio/evaluation engines.
- Do not treat sample examples as alpha conclusions.

## Acceptance Criteria

- [ ] `docs/strategy_entry/` exists with all required files.
- [ ] Documents are consistent with approved design boundaries.
- [ ] Three strategy-family examples are included and readable.
- [ ] Missing-factor request schema is explicit and actionable for upstream projects.
- [ ] Existing docs and progress/state files are updated to point to this task.
- [ ] `docs/agent/09_CODING_HANDOFF.md` records changed files and validation evidence.

## Validation Commands

```bash
scripts/check-progress-docs.sh
git diff --check
```

If markdown lint or doc build tooling exists locally, run the smallest relevant subset and record it in `09_CODING_HANDOFF.md`.

## Risks

- Over-designing entry schema beyond current daily-data scope.
- Mixing “authoring standard” and “runtime compiler” concerns.
- Leaving ambiguous factor identifiers that upstream automation cannot interpret.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
