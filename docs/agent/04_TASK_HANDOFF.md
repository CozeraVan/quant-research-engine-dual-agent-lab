# Task Handoff

## Current Task

Add GUI parameter surface for standard strategy IO — a form-based Strategy Builder tab alongside the existing YAML editor in the local browser console.

## Task ID

QRE-GUI-STRATEGY-BUILDER-001

## Current Status

DONE. Claude Code has implemented and self-reviewed: compile-to-spec endpoint, indicator catalog endpoint, builder tab with 4 form sections (strategy identity, entry/exit rules, factor requirements, experiment config), dynamic condition/factor row management, compile and run flows, 16 new tests (770 total pass). Review PASS. Awaiting git finalization.

## Current Owner

CLAUDE_CODE

## Scope Summary

- Add `compile_high_level_entry()` to `gui/engine.py` wrapping the existing compiler.
- Add 3 builder API routes to `gui/app.py`: compile, indicator-catalog, validate.
- Add "Strategy Builder" tab to `index.html` with collapsible form sections for all high-level entry fields.
- Add dynamic condition/factor row management in client-side JavaScript.
- Add form serialization to produce high-level entry dicts.
- Add Compile and Run buttons that bridge to the existing backtest flow.
- Keep existing YAML Editor tab unchanged.
- Update `gui/static/style.css` with tab, form, section, condition, and factor styles.

## Validation Baseline

```bash
uv run pytest tests/test_gui_app.py tests/test_gui_engine.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

Current: 770 passed, 2 warnings in ~11s.
