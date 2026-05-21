# Coding Handoff

## Task ID

QRE-GUI-LOCAL-BACKTEST-CONSOLE-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

DONE. The local browser backtest console is complete and finalized locally in commit `766dc98`.

## Implementation Summary

Built a lightweight local browser-based backtest console with:

- **Flask web app** (`src/quant_research_engine/gui/app.py`): server-rendered templates with routes for the YAML editor, run history, run detail with artifact/stdout/stderr viewing, and REST API endpoints for validate, run, templates, and runs.
- **Execution engine** (`src/quant_research_engine/gui/engine.py`): direct module execution mirroring the CLI flow (PostgresDataStore → ResearchFrameAssembler → StrategySpec.from_yaml → engine.run), CLI subprocess fallback, local filesystem run history under `outputs/gui-console/runs/`, and template CRUD.
- **HTML templates** (`src/quant_research_engine/gui/templates/`): base layout with nav, YAML editor with file upload/template support/validate, parameter panel (mode, dates, codes, cash, max positions, output dir, DB URL, market profile, executor), run history table, run detail with rerun/artifacts/stdout/stderr.
- **CSS** (`src/quant_research_engine/gui/static/style.css`): minimal system-ui stylesheet for layout, forms, tables, code blocks, and status indicators.
- **CLI wiring** (`src/quant_research_engine/apps/cli.py`): `qre gui` subcommand with `--host`, `--port`, `--debug` flags that calls `launch_gui()`.
- **Tests**: 43 tests total (23 engine tests, 19 app tests, 1 CLI integration test) covering validate, templates, run history, build CLI command, run backtest with module/CLI executor, Flask routes, and `qre gui --help`.

## Files Changed

- `pyproject.toml` — added `flask>=3.0.0` dependency
- `src/quant_research_engine/apps/cli.py` — added `gui` subparser and handler
- `src/quant_research_engine/gui/__init__.py` — new package init
- `src/quant_research_engine/gui/engine.py` — new execution engine and history management
- `src/quant_research_engine/gui/app.py` — new Flask app factory
- `src/quant_research_engine/gui/templates/base.html` — new base layout
- `src/quant_research_engine/gui/templates/index.html` — new editor page
- `src/quant_research_engine/gui/templates/runs.html` — new run history page
- `src/quant_research_engine/gui/templates/run_detail.html` — new run detail page
- `src/quant_research_engine/gui/templates/error.html` — new error page
- `src/quant_research_engine/gui/static/style.css` — new stylesheet
- `tests/test_gui_engine.py` — new engine tests (23 tests)
- `tests/test_gui_app.py` — new app tests (24 tests, including artifact and rerun coverage)

## Fixes Applied

1. **Rerun restoration** — Added sessionStorage reader to `index.html` (lines 86-91) that checks for stored YAML on page load and populates the editor textarea. Removed the ineffective reader from `run_detail.html` (it targeted `#strategy-yaml` which doesn't exist on that page).
2. **Result viewer** — Added `GET /api/runs/<run_id>/artifact/<path>` endpoint to `app.py` that parses CSV files into structured JSON (`{"type": "csv", "headers": [...], "rows": [[...], ...]}`) and JSON files into `{"type": "json", "data": ...}`. Updated `run_detail.html` to fetch priority artifacts and render them as HTML tables or formatted JSON.
3. **Single-symbol summary.json** — Added `summary.json`, `summary_metrics.json`, and `summary_markdown.md` to the priorityFiles array in `run_detail.html` so single-symbol and shared-cash runs (which write `summary.json` instead of `summary.csv`) render their summary content.

## Validation Results (after all fixes)

- `uv run pytest tests/ -q` → 464 passed, 2 warnings (pre-existing numpy warnings) in 4.64s
- `scripts/check-progress-docs.sh` → passed
- `git diff --check` → passed

## Constraints

- No changes to existing engine contracts, market profiles, or evaluation/portfolio logic.
- YAML text stays the primary strategy editing surface.
- Local filesystem history only, no PostgreSQL persistence for runs.
- `docs/legacy/**` untouched.
- Read-only data access preserved.

## Git State

- Branch: `master`
- Last accepted implementation commit: `2da15bb`, `Preserve window_size and group_by selector parity under JSON strict mode`
- Working tree contains all GUI implementation files plus agent doc updates.

## Next Suggested Step

None.
