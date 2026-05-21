# Task Handoff

## Current Task

Build a local browser-based backtest console for the existing QRE engine. The first release is YAML-first, local-filesystem-first, and intentionally plain: the goal is to make backtest setup, execution, and result inspection direct and readable.

## Task ID

QRE-GUI-LOCAL-BACKTEST-CONSOLE-001

## Current Status

REVIEW PASSED. The local browser console meets the approved first-release scope and is ready for user acceptance.

## Current Owner

CODEX

## Completed

- Product direction approved:
  - local browser console, not a native desktop app
  - YAML strategy text as the first-class input
  - `qre gui` as the launch path
  - direct module execution by default, CLI fallback retained
  - single-symbol, batch, and shared-cash backtests exposed in the GUI
  - local filesystem history first, PostgreSQL later
  - full artifact viewer for summary, orders, trades, equity, and manifest outputs
- Brainstorm design captured in `docs/superpowers/specs/2026-05-21-local-backtest-console-design.md`.
- Change request recorded in `docs/agent/change_requests/CR-0001-local-backtest-console.md`.
- Implementation completed:
  - Flask web app (`src/quant_research_engine/gui/app.py`) with all routes
  - Execution engine (`src/quant_research_engine/gui/engine.py`) with module and CLI executors
  - HTML templates (base, index, runs, run_detail, error) and CSS
  - `qre gui` CLI command with `--host`, `--port`, `--debug` flags
  - 43 focused GUI tests (engine + app + CLI integration)
  - `uv run pytest tests/ -q` → 460 passed
  - `scripts/check-progress-docs.sh` → passed
  - `git diff --check` → passed
- Fixes completed:
  - Rerun restoration: sessionStorage reader added to `index.html`, ineffective reader removed from `run_detail.html`
  - Result viewer: artifact content API endpoint (`/api/runs/<run_id>/artifact/<path>`) added to `app.py`; `run_detail.html` renders CSV tables and JSON for priority artifacts
  - Single-symbol summary: `summary.json`, `summary_metrics.json`, `summary_markdown.md` added to priority artifact list in `run_detail.html`
  - `docs/agent/04_TASK_HANDOFF.md`
  - `docs/agent/05_PROGRESS.md`
  - `docs/agent/09_CODING_HANDOFF.md`
  - `docs/agent/11_AGENT_STATE.md`
  - `docs/agent/12_AGENT_BOARD.md`

## Expected Files

Implementation surfaces changed:

- `pyproject.toml` — Flask dependency added
- `src/quant_research_engine/apps/cli.py` — `gui` subcommand added
- `src/quant_research_engine/gui/__init__.py` — new
- `src/quant_research_engine/gui/engine.py` — new
- `src/quant_research_engine/gui/app.py` — new
- `src/quant_research_engine/gui/templates/base.html` — new
- `src/quant_research_engine/gui/templates/index.html` — new
- `src/quant_research_engine/gui/templates/runs.html` — new
- `src/quant_research_engine/gui/templates/run_detail.html` — new
- `src/quant_research_engine/gui/templates/error.html` — new
- `src/quant_research_engine/gui/static/style.css` — new
- `tests/test_gui_engine.py` — new
- `tests/test_gui_app.py` — new
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Fixes validated and passing:

- `uv run pytest tests/ -q` → 464 passed, 2 warnings (pre-existing numpy) in 4.29s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Known Risks

- Long-running backtests need background execution or the browser page will feel blocked.
- A form-driven strategy builder would duplicate the existing strategy spec; YAML text should stay primary in v1.
- A heavy frontend framework would slow the first release and make cross-platform behavior harder to keep simple.

## Next Suggested Step

User acceptance and any requested git finalization.
