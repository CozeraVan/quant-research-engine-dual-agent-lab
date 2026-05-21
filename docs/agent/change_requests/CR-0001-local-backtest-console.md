# CR-0001: Local Backtest Console

## 1. Background

The current QRE engine already supports YAML strategies, CLI backtests, PostgreSQL-backed market data, and durable result artifacts. The remaining gap is the user experience: strategy iteration still happens mostly through terminal commands and Codex-driven verification.

The project owner wants a local GUI that makes the backtest flow easier to understand and use without changing the underlying engine contract.

## 2. Goal

Build a local browser-based backtest console that lets a user edit YAML strategy files, configure backtest parameters, run single-symbol / batch / shared-cash simulations, inspect full results, and reopen prior runs.

## 3. User Scenario

A user opens a local web console, loads a strategy YAML file, edits the strategy text, selects dates, symbols, backtest mode, and risk controls, then runs the backtest. The console shows the result summary and the generated artifacts, and the user can later reopen the same run from local history and rerun it.

## 4. Scope

### In Scope

- Local browser-based console.
- YAML text editing as the primary strategy input.
- Upload / save / reopen strategy templates.
- Single-symbol, batch, and shared-cash backtest execution.
- Result views for summary, orders, trades, equity, and report manifest.
- Local filesystem run history.
- Re-run from historical configurations.
- Direct module execution with CLI fallback.

### Out of Scope

- Visual polish.
- Multi-user workflows.
- Authentication.
- PostgreSQL history storage in v1.
- Strategy drag-and-drop authoring.
- Distributed / queued execution.

## 5. Affected Requirements

- Backtest commands must remain reproducible.
- The GUI must not replace the engine contract.
- The GUI should eventually support the same file-based run artifacts that the CLI already produces.

## 6. Protected Requirements

- Read `docs/agent/02_LOCKED_REQUIREMENTS.md`

## 7. Suggested Tasks

| Task ID | Task | Priority | Status |
|---|---|---|---|
| QRE-GUI-LOCAL-BACKTEST-CONSOLE-001 | Build the local browser console shell, file store, and runner orchestration | High | TODO |
| QRE-GUI-RUN-HISTORY-001 | Implement local run history, filters, and rerun support | Medium | TODO |
| QRE-GUI-RESULT-VIEWER-001 | Render the full artifact set from completed backtests | Medium | TODO |

## 8. Acceptance Criteria

- [ ] The GUI can load and edit YAML strategy files.
- [ ] The GUI can launch single/batch/shared backtests.
- [ ] The GUI can use direct module execution and CLI fallback.
- [ ] The GUI saves run history locally on disk.
- [ ] The GUI can reopen and rerun a prior configuration.
- [ ] The GUI shows summary, orders, trades, equity, and manifest outputs.

## 9. Risks

- The first version may become too large if it tries to become a full desktop product instead of a simple browser console.
- A form-driven strategy builder would duplicate the current strategy spec and slow implementation; YAML text should remain the first-class input.
- Long-running backtests need background execution and status tracking so the browser does not freeze.

## 10. Implementation Notes

Recommended first-release shape:

- `qre gui` launches a local web server.
- The server renders a console page with a YAML editor, parameter panel, run controls, history list, and result viewer.
- The GUI stores local history under the repository outputs directory first.
- The GUI invokes the existing Python backtest modules by default and keeps the `qre` CLI as a fallback.

## 11. Proposed Agent State Transition

- Next Phase: `CLAUDE_IMPLEMENTING`
- Next Owner: `CLAUDE_CODE`
