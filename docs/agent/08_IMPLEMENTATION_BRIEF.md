# Implementation Brief

## Task ID

QRE-GUI-LOCAL-BACKTEST-CONSOLE-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

The backtest engine already supports YAML strategy specs, single-symbol / batch / shared-cash runs, durable report artifacts, and read-only PostgreSQL market data. The missing piece is the operator experience: strategy editing, parameter entry, run orchestration, local history, and result inspection still happen mostly through CLI and Codex-driven verification.

The user approved a first-release GUI that is:

- a local browser console, not a desktop app
- YAML text first for strategy editing
- direct module execution by default, with CLI fallback retained
- local filesystem history first, PostgreSQL later
- focused on clarity rather than polish
- cross-platform, with Ubuntu as the first target environment

## Goal

Build a local browser-based console that lets a user load, edit, validate, and save YAML strategies; configure backtest parameters; run single-symbol / batch / shared-cash simulations; inspect full output artifacts; and reopen or rerun prior runs from local history.

## Non-Goals

- Do not turn the GUI into a native desktop app.
- Do not implement authentication or multi-user workflows.
- Do not store run history in PostgreSQL in v1.
- Do not build a drag-and-drop strategy composer.
- Do not rewrite the backtest engine to fit the GUI.
- Do not add distributed execution or queue infrastructure in v1.
- Do not edit `docs/legacy/**`.

## Affected Modules

Expected implementation surfaces:

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/gui/**`
- `tests/test_gui_*.py`
- `tests/test_cli.py` if GUI launch or orchestration touches the CLI contract

Docs/handoff:

- `docs/agent/03_ROADMAP.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/06_DECISION_LOG.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Implementation Shape

Use the lightest Python web stack that keeps the UI local, simple, and cross-platform. Prefer server-rendered pages or similarly lightweight browser UI. The console should expose:

- YAML strategy editor
- backtest parameter panel
- execution mode selector for single/batch/shared-cash
- run controls
- local history list
- rerun action from history
- result viewer for summary, orders, trades, equity, report manifest, and artifact pointers

The GUI should keep the engine contract intact and adapt to the existing CLI/module surfaces rather than inventing a parallel strategy language.

## Local Storage Contract

Version 1 should persist run records under a repository-local outputs directory, with enough data to reopen and rerun a prior configuration:

- strategy YAML snapshot
- resolved parameters
- run mode
- timestamps and status
- stdout/stderr or equivalent execution log
- output directory path
- artifact pointers and summary metadata

## Validation Plan

Use focused tests for the new GUI surfaces and keep the existing engine contract intact:

```bash
uv run pytest tests/test_gui_*.py tests/test_cli.py -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] The user can open a local browser console and edit a YAML strategy.
- [ ] The user can upload, save, reopen, and rerun strategy YAML files.
- [ ] The GUI can launch single-symbol, batch, and shared-cash backtests.
- [ ] The GUI can use direct module execution and CLI fallback.
- [ ] The GUI stores run history locally on disk.
- [ ] The GUI shows summary, orders, trades, equity, manifest, and artifact pointers.
- [ ] The implementation remains cross-platform and avoids Ubuntu-only assumptions.
- [ ] The engine contract remains the source of trading logic.

## Risks

- Long-running backtests need background execution or progress tracking so the browser page does not appear frozen.
- A form-driven strategy builder would duplicate the existing YAML strategy contract and slow delivery.
- A heavy frontend framework would make the first release harder to keep simple and portable.

## Instructions for Claude Code

Claude Code must:

1. Implement `QRE-GUI-LOCAL-BACKTEST-CONSOLE-001` as a local browser console.
2. Keep YAML text as the primary strategy input.
3. Preserve the existing engine contract and CLI fallback.
4. Store run history locally on disk in v1.
5. Update `09_CODING_HANDOFF.md`, `11_AGENT_STATE.md`, and `12_AGENT_BOARD.md` when implementation is ready for review.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
