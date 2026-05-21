# Implementation Brief

## Task ID

QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Current Brief Type

Implementation brief. Build minimal linkage from high-level strategy entry format to current preflight/runtime-compatible `StrategySpec`.

## Background

Completed baselines:

- Full-market report contract implemented and finalized.
- Strategy-entry authoring docs implemented under `docs/strategy_entry/`.
- Missing-factor handoff operationalized via `missing_factor_requests.json`.

Current gap:

- High-level strategy entry format is documented, but not yet linked to executable preflight/runtime flow.

## Canonical Sources

- `docs/strategy_entry/README.md`
- `docs/strategy_entry/strategy_card.md`
- `docs/strategy_entry/factor_requirements.md`
- `docs/strategy_entry/experiment_plan.md`
- `docs/strategy_entry/examples.md`
- `docs/strategy_entry/missing_factor_request.md`

## Goal

Implement a minimal compiler/preflight linkage layer that can:

1. Parse high-level strategy entry YAML.
2. Resolve declared factor requirements into current low-level `StrategySpec.factor_fields` targets where possible.
3. Produce preflight-compatible input and actionable errors for unresolved aliases/fields.
4. Keep runtime engine behavior unchanged.

## Scope

In scope:

- New linkage module(s) for high-level entry parsing and conversion.
- CLI entry point (new command or extension) for validation/compile-to-low-level preview.
- Integration with existing preflight path.
- Tests for valid/invalid mapping scenarios.

Out of scope:

- Automatic indicator computation.
- Database writes.
- External project invocation.
- GUI integration.
- Full strategy runtime compiler for every advanced rule operator.

## Required Deliverables

1. High-level entry parser

- Supports sections:
  - `strategy` / `rules`
  - `factor_requirements`
  - `experiment`
- Validates required fields and basic types.

2. Factor linkage

- Convert requirement alias definitions to low-level factor targets where deterministic mapping exists.
- If mapping is unavailable, return structured validation issues and keep missing-factor flow usable.

3. Preflight linkage command

- Provide a CLI surface to:
  - load high-level entry
  - compile/link to low-level preflight input
  - run existing preflight checks
  - emit missing-factor artifact through current standard flow

4. Artifact/preview output

- Optional output file: compiled low-level preview (YAML or JSON) for debugging.
- Must not replace current strategy file behavior.

5. Tests

- Valid high-level example compiles and preflights.
- Missing required fields fail with clear message.
- Alias mismatch fails with clear message.
- Unresolved factor mapping fails deterministically and still supports missing-factor artifact path where applicable.

## Suggested File Surface

- `src/quant_research_engine/strategies/...` (new linkage/parser module)
- `src/quant_research_engine/apps/cli.py` (CLI wiring)
- `tests/test_*.py` for linkage + CLI
- `docs/strategy_entry/*.md` (small clarifications if behavior constraints require)

## Non-Goals

- Do not modify existing portfolio/evaluation engine logic.
- Do not alter full-market report outputs.
- Do not remove low-level `StrategySpec` support.
- Do not broaden to minute-bar or ML workflows.

## Acceptance Criteria

- [ ] High-level strategy entry can be validated and linked to preflight flow.
- [ ] Failure modes are explicit and actionable.
- [ ] Missing-factor workflow remains compatible with current JSON contract.
- [ ] Existing low-level strategy workflow remains unaffected.
- [ ] Tests cover success and failure paths.
- [ ] `docs/agent/09_CODING_HANDOFF.md` updated with changed files and validation evidence.

## Validation Commands

At minimum:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

If full suite is too broad, run focused subset and record exact commands in `09_CODING_HANDOFF.md`.

## Risks

- Over-coupling doc format and runtime format too early.
- Ambiguous alias-to-column mapping rules.
- Introducing compatibility regressions in existing low-level strategy path.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
