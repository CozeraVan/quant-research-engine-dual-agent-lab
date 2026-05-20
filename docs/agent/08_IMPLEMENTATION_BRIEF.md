# Implementation Brief

## Task ID

QRE-RUN-ID-MANIFEST-LINKAGE-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Evaluation and portfolio output directories now write durable artifacts and run manifests. Preflight can write JSON output. The remaining reproducibility gap is linking a preflight, evaluation, and backtest run under one operator-supplied research-run identifier without inventing a larger orchestration framework.

## Goal

Add an optional `--run-id` CLI argument to the durable run surfaces and persist that identifier in their machine-readable outputs.

## Non-Goals

- Do not add a new pipeline/orchestrator command.
- Do not create a database table or write upstream database state.
- Do not change report artifact filenames.
- Do not require `--run-id`; existing commands must work unchanged.
- Do not change evaluation or portfolio math.
- Do not wire real index benchmark tables or real regime classification.

## Affected Modules

Expected:

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/io.py`
- `tests/test_cli.py`
- `tests/test_portfolio_io.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

Update only additional files if the current code shape clearly requires it.

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

- Keep data access read-only.
- Preserve existing CLI behavior when `--run-id` is omitted.
- Keep report manifests compatible with `report-files` and `report-audit`.
- Do not expose credentials or environment values in run IDs or manifests.

## Implementation Steps

1. Inspect current CLI parser and output writers for:
   - `qre preflight --output-json`
   - `qre eval-config --output-dir`
   - `qre backtest-single --output-dir`
   - `qre backtest-batch --output-dir`
   - `qre backtest-shared --output-dir`
2. Add optional `--run-id` to those commands.
3. For `preflight --output-json`, include top-level `"run_id": <value or null>` in the written JSON payload. Stdout does not need a new line unless local style clearly expects it.
4. For `eval-config --output-dir`, include top-level `"run_id": <value or null>` in `run_manifest.json`.
5. For portfolio output writers, include top-level `"run_id": <value or null>` in `portfolio_backtest_run_manifest`.
6. Pass `args.run_id` from `backtest-single`, `backtest-batch`, and `backtest-shared` into the existing run-request structure without duplicating it inside the nested `"request"` object.
7. Preserve the current `"artifacts"` list behavior and report-manifest entries.
8. Add tests proving:
   - `eval-config --run-id ... --output-dir ...` writes the run ID to `run_manifest.json`.
   - `preflight --run-id ... --output-json ...` writes the run ID to the JSON payload.
   - At least one portfolio writer or CLI path writes the run ID to `portfolio_backtest_run_manifest`.
   - Omitting `--run-id` preserves successful output and writes `null`/`None` or omits only where existing helper style strongly prefers omission. Prefer a stable explicit `null`.
9. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- JSON output schemas gain optional/stable `run_id` fields.
- Report manifest file-entry schemas should remain unchanged.

## API / Interface Changes

- New optional CLI argument:
  - `qre preflight --run-id <id>`
  - `qre eval-config --run-id <id>`
  - `qre backtest-single --run-id <id>`
  - `qre backtest-batch --run-id <id>`
  - `qre backtest-shared --run-id <id>`
- Run manifest JSON payloads include top-level `run_id`.
- Preflight JSON payload includes top-level `run_id`.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_cli.py tests/test_portfolio_io.py -q
```

Run full checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `preflight --output-json --run-id` writes the supplied run ID in the output JSON.
- [ ] `eval-config --output-dir --run-id` writes the supplied run ID in evaluation `run_manifest.json`.
- [ ] Portfolio output manifests for single, batch, and shared can carry the supplied run ID.
- [ ] Existing command behavior remains compatible when `--run-id` is omitted.
- [ ] Report manifest discovery/audit behavior is unchanged.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid putting `run_id` into manifest file entries; it belongs to run-level JSON payloads.
- Avoid making `run_id` a required field for existing workflows.
- Do not turn this into a broad workflow orchestrator; this is only linkage metadata.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep the implementation small and metadata-only.
3. Preserve existing evaluation, preflight, and portfolio behavior.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
