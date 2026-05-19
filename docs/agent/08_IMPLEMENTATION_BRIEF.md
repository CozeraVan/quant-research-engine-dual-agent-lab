# Implementation Brief

## Task ID

QRE-PORTFOLIO-BACKTEST-RUN-MANIFEST-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

The portfolio backtest outputs already include result files, summary files, and report manifests, but they do not yet record the run inputs that produced them. That makes it hard to reconstruct an old research run without recovering CLI arguments from chat or shell history.

The next self-contained step is to write a run manifest alongside portfolio backtest output directories so single-symbol, batch, and shared-cash runs carry a reproducible metadata record without changing simulation behavior.

## Goal

Add a safe portfolio backtest run manifest to output directories so each run records its command, strategy path, resolved request parameters, and emitted artifacts.

## Non-Goals

- Do not change single-symbol, batch, or shared-cash simulation logic.
- Do not change order generation, fills, risk controls, or benchmark math.
- Do not add database writes or new data-source wiring.
- Do not store sensitive connection values in the manifest.
- Do not rework the existing report-manifest schema beyond adding a run-manifest artifact if needed.
- Do not add new CLI commands or flags unless the current backtest entry points need them to pass run metadata into the writer layer.

## Affected Modules

Expected:

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/io.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_io.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `src/**` outside the modules listed above
- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve portfolio execution behavior.
- Preserve existing report-manifest behavior and file discovery.
- Keep payloads additive and serializable.
- Do not record sensitive connection values.
- Keep the new manifest compatible with current output directories.

## Implementation Steps

1. Inspect the current backtest output writers and report-manifest roles.
2. Add a run-manifest payload and writer for single-symbol, batch, and shared-cash outputs.
3. Capture safe request metadata: command name, strategy path, and serializable request fields.
4. Include the run manifest among emitted artifacts and, where applicable, in the report manifest and output-file summary.
5. Treat run-manifest JSON as a valid JSON object in content validation.
6. Add regression tests for single, batch, and shared output dirs plus validation/discovery coverage if needed.
7. Update handoff and progress docs.

## Data / Schema Changes

- New `run_manifest.json` beside backtest outputs.
- Suggested schema fields: `schema_version`, `kind`, `command`, `strategy_path`, `request`, `artifacts`.
- Suggested `kind`: `portfolio_backtest_run_manifest`.
- Batch/shared report manifests should include the run-manifest artifact when output directories are written.

## API / Interface Changes

- `write_single_symbol_result`, `write_batch_result`, and `write_shared_cash_result` should accept or build safe run metadata.
- Output directories should include `run_manifest.json`.
- `report-files` and `report-audit` should continue to work for the existing report manifest, and `run_manifest.json` should validate as a JSON object where it is surfaced through report manifests.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_io.py -q
uv run pytest tests/test_portfolio_report_manifest.py -q
```

Run CLI and full checks:

```bash
uv run pytest tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `run_manifest.json` is written for portfolio backtest output-dir code paths.
- [ ] The run manifest records command, strategy path, request inputs, and artifact list.
- [ ] Existing result files and report manifests remain intact.
- [ ] `report-files` and `report-audit` continue to work, and the new manifest is accepted where it appears through report manifests.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Keep the new manifest additive only.
- Avoid duplicating logic across single, batch, and shared writers unless it removes real complexity.
- Do not include sensitive connection values in the manifest.
- Preserve report-manifest validation behavior except for the new run-manifest JSON object path.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Reuse existing output-writer patterns.
3. Keep payloads serializable and limited to safe run metadata.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and ask only if the brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
