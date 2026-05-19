# Implementation Brief

## Task ID

QRE-EVAL-CONFIG-OUTPUT-ARTIFACTS-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`qre eval-config` now prints summary, IC, quantile, and optional metadata group-summary tables to stdout. Portfolio backtests already support output directories, report manifests, and run manifests, but evaluation runs still lack durable artifacts.

The next self-contained step is to add an optional output directory for `eval-config` so evaluation results can be saved, discovered, and audited like portfolio outputs. This advances research-run reproducibility without new data-source wiring.

## Goal

Add `qre eval-config --output-dir` support that writes evaluation result artifacts plus report/run manifests.

## Non-Goals

- Do not change evaluation calculations.
- Do not add new database tables or upstream data adapters.
- Do not implement benchmark/random-baseline comparison.
- Do not implement factor decay or real regime classification.
- Do not add output-dir support to `eval-smoke`.
- Do not store sensitive connection values in the run manifest.

## Affected Modules

Expected:

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/evaluation/models.py` if helper typing requires it
- `src/quant_research_engine/portfolio/report_manifest.py`
- new or existing evaluation IO helper module if that keeps CLI small
- `tests/test_cli.py`
- `tests/test_portfolio_report_manifest.py` or a new evaluation-report-manifest test file

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve existing stdout behavior for `eval-config`.
- Keep the output-dir feature additive and optional.
- Keep report-manifest compatibility with existing portfolio manifests.
- Keep data access read-only.
- Do not compute technical indicators inside QRE.
- Do not record sensitive connection values.

## Implementation Steps

1. Inspect current `eval-config` CLI flow and existing portfolio output/manifest helpers.
2. Add `--output-dir` to `qre eval-config`.
3. When `--output-dir` is provided, create the directory and write:
   - `events.csv`
   - `summary.csv` when non-empty
   - `ic_summary.csv` when non-empty
   - `quantile_summary.csv` when non-empty
   - `group_summary.csv` when non-empty
   - `run_manifest.json`
   - `report_manifest.json`
4. Extend report-manifest support to accept an evaluation manifest kind, suggested `evaluation_report_manifest`.
5. Add required-column validation for evaluation artifact roles:
   - `events`: `ts_code`, `trade_date`
   - `evaluation_summary`: `horizon`, `event_count`
   - `ic_summary`: `factor`, `horizon`, `observation_dates`
   - `quantile_summary`: `factor`, `horizon`, `quantile`, `row_count`
   - `evaluation_group_summary`: `group_by`, `group_value`, `horizon`, `event_count`
6. Make `run_manifest.json` record safe run inputs:
   - schema version and kind;
   - command name;
   - strategy path;
   - start/end dates;
   - requested codes;
   - round-trip cost value or market-profile path if provided;
   - requested group columns;
   - emitted artifact keys.
7. Ensure report manifests include `run_manifest` with role `run_manifest`.
8. Preserve stdout output exactly apart from any existing deterministic text already printed by the command.
9. Add CLI and manifest validation regression tests.
10. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- New optional output directory files for `eval-config`.
- New report-manifest kind: `evaluation_report_manifest`.
- Suggested run-manifest kind: `evaluation_run_manifest`.

## API / Interface Changes

- `qre eval-config` accepts `--output-dir PATH`.
- `ReportManifest.from_path()` accepts `evaluation_report_manifest`.
- `ReportManifest.validate_contents()` validates evaluation artifact roles.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_cli.py -q
uv run pytest tests/test_portfolio_report_manifest.py -q
```

Run full checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `qre eval-config --output-dir <dir>` writes durable evaluation artifacts.
- [ ] Artifacts include only non-empty result tables except `events.csv`, `run_manifest.json`, and `report_manifest.json`, which should always be present for successful output-dir runs.
- [ ] Existing stdout behavior remains compatible.
- [ ] `report_manifest.json` uses kind `evaluation_report_manifest` and can be loaded by `ReportManifest.from_path()`.
- [ ] `ReportManifest.validate_contents()` validates emitted evaluation artifacts.
- [ ] `run_manifest.json` records safe run inputs and emitted artifact keys while omitting sensitive connection values.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid mixing portfolio-specific artifact role semantics with evaluation roles.
- Keep the manifest extension backward-compatible for existing portfolio report manifests.
- Do not write empty optional CSVs unless that matches an existing local pattern and is covered by tests.
- Keep CLI output deterministic for downstream scripts.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Reuse existing manifest patterns where they fit, but do not force portfolio role names onto evaluation outputs.
3. Keep the implementation small and regression-tested.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
