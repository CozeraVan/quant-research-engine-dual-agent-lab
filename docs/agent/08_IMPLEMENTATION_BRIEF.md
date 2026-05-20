# Implementation Brief

## Task ID

QRE-EVAL-GROUP-BY-MANIFEST-PARITY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Evaluation outputs already support `--group-by` and emit a combined `group_summary.csv` with a `group_by` column in file contents. Batch and shared-cash outputs go one step further: they also expose per-group-column artifacts and manifest metadata that work cleanly with `qre report-files` and `qre report-audit --group-by`. Evaluation outputs do not yet have that parity.

## Goal

Add per-column evaluation grouped artifacts and manifest metadata so evaluation grouped outputs can be discovered and audited with `--group-by` the same way batch and shared-cash grouped outputs can.

## Non-Goals

- Do not change evaluation math or group-summary calculations.
- Do not remove or rename the existing combined `group_summary.csv`.
- Do not change report-manifest schema version.
- Do not add new external data dependencies.
- Do not edit legacy archived docs under `docs/legacy`.

## Affected Modules

Expected runtime/tests:

- `src/quant_research_engine/apps/cli.py`
- `tests/test_cli.py`
- `tests/test_portfolio_report_manifest.py`

Possible docs:

- `README.md`
- `docs/modules/data_layer.md`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `docs/legacy/**`
- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve existing `group_summary.csv` output and current CLI compatibility.
- Keep `report_manifest.json` schema compatible with existing readers; use the existing optional `group_by` string metadata field where appropriate.
- Do not weaken batch/shared report-manifest filtering behavior while extending evaluation parity.
- Keep docs and examples credential-free if documentation is updated.

## Implementation Steps

1. Inspect current evaluation output writing in `src/quant_research_engine/apps/cli.py` and current manifest/filter behavior in `ReportManifest` plus CLI tests.
2. Preserve the existing combined evaluation grouped artifact:
   - `group_summary.csv`
   - report role `evaluation_group_summary`
3. When `result.group_summary` is non-empty and contains one or more `group_by` values, also emit one CSV per group column:
   - `group_summary_by_<col>.csv`
   - each file contains only rows for that `group_by` value
4. Add matching report-manifest entries for those per-column files:
   - role `evaluation_group_summary`
   - metadata `group_by=<col>`
   - stable key names such as `group_summary_by_board`
5. Ensure `qre report-files ... --role evaluation_group_summary --group-by board` and `qre report-audit ... --role evaluation_group_summary --group-by board` match the per-column evaluation file.
6. Keep `ReportManifest.validate_contents()` compatibility for both the combined evaluation grouped file and the new per-column grouped files.
7. Update minimal user-facing docs if needed so the new per-column files and `--group-by` filtering behavior are discoverable.
8. Update handoff/progress docs.

## Data / Schema Changes

- No database or upstream schema changes.
- No report-manifest schema-version change.
- This task may add additional evaluation artifact entries and file names within the existing schema.

## API / Interface Changes

- No new top-level CLI commands.
- Existing `eval-config --group-by` behavior stays intact.
- `report-files` / `report-audit` should gain practical `--group-by` parity for evaluation grouped artifacts through new manifest entries.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q
```

Run documentation/diff checks:

```bash
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `eval-config --group-by board industry --output-dir <dir>` keeps writing the combined `group_summary.csv`.
- [ ] The same run also writes per-column files such as `group_summary_by_board.csv` and `group_summary_by_industry.csv`.
- [ ] Per-column evaluation grouped files are listed in `report_manifest.json` with role `evaluation_group_summary` and `group_by` metadata.
- [ ] `qre report-files <manifest> --role evaluation_group_summary --group-by board` matches the board-specific file.
- [ ] `qre report-audit <manifest> --role evaluation_group_summary --group-by board --require-match` validates the board-specific file.
- [ ] Existing manifest validation still passes for the combined evaluation grouped file.
- [ ] `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q`, `scripts/check-progress-docs.sh`, and `git diff --check` pass.

## Risks

- Avoid breaking existing scripts that expect `group_summary.csv`.
- Avoid introducing manifest key/role ambiguity between the combined grouped file and the per-column grouped files.
- Keep evaluation artifact naming aligned with current batch/shared grouping conventions where possible.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep the change scoped to evaluation output artifact emission, manifest entries, targeted docs, and tests.
3. Preserve backward compatibility for the existing combined evaluation grouped CSV.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if the manifest/filter contract cannot be extended without a schema decision.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
