# Implementation Brief

## Task ID

QRE-REPORT-GROUP-BY-CONTENT-CONSISTENCY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Grouped evaluation and shared-cash artifacts now use manifest `group_by=<col>` metadata so `qre report-files` and `qre report-audit --group-by` can target per-column files. Current audit validation checks required columns only. That means a file can claim `group_by=board` in the manifest while its CSV rows contain another grouping column and still pass `validate_contents()`.

## Goal

Harden report-manifest content validation so grouped artifact files with manifest `group_by` metadata must agree with their CSV contents.

## Non-Goals

- Do not change report-manifest schema version.
- Do not change grouped artifact filenames, roles, or CLI flags.
- Do not force combined grouped files without manifest `group_by` metadata to contain a single grouping column.
- Do not broaden the task into batch grouped files that use the actual group column name instead of a literal `group_by` CSV column.
- Do not edit legacy archived docs under `docs/legacy`.

## Affected Modules

Expected runtime/tests:

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`

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
- evaluation or portfolio engine math/output-generation modules unless a narrow validation helper change is genuinely required

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve existing `report-files` / `report-audit` role and `group_by` filter behavior.
- Preserve combined evaluation `group_summary.csv` compatibility.
- Keep manifest schema version unchanged.
- Preserve archived legacy docs.
- Keep the task narrowly scoped to audit/content validation rather than output-generation changes.

## Implementation Steps

1. Inspect current `ReportManifest.validate_contents()` flow and grouped artifact roles that already write a literal `group_by` column in CSV contents:
   - `evaluation_group_summary`
   - `shared_orders_group_summary`
   - `shared_trades_group_summary`
   - `shared_failed_orders_group_summary`
2. After required-column validation passes for those grouped roles, add a consistency check for manifest entries with `group_by=<col>` metadata:
   - read the CSV rows
   - ignore fully empty files that already pass structural validation
   - verify every non-empty `group_by` cell equals the manifest entry's `group_by`
3. Emit a stable validation issue when content mismatches manifest metadata:
   - use one clear code for this failure mode
   - include the manifest value and observed mismatched CSV values in the message
4. Do not apply this check to entries without manifest `group_by` metadata, including the combined evaluation `group_summary.csv`.
5. Add focused coverage in:
   - `tests/test_portfolio_report_manifest.py` for direct `validate_contents()` behavior
   - `tests/test_cli.py` for `qre report-audit` surface behavior
6. Update handoff/progress docs.

## Data / Schema Changes

- No data or schema changes.
- Manifest schema version must remain unchanged.

## API / Interface Changes

- No new commands or flags.
- `report-audit` may surface a new issue code/message when grouped CSV content disagrees with manifest `group_by` metadata.

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

- [ ] A grouped evaluation file with manifest `group_by=board` fails audit if CSV rows contain another `group_by` value.
- [ ] A grouped shared-cash file with manifest `group_by=board` fails audit if CSV rows contain another `group_by` value.
- [ ] Matching grouped evaluation/shared files still pass audit.
- [ ] Combined evaluation `group_summary.csv` without manifest `group_by` metadata still passes unchanged.
- [ ] `qre report-audit` surfaces the mismatch through existing validation output.
- [ ] Legacy archived docs are untouched.
- [ ] `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q`, `scripts/check-progress-docs.sh`, and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid false positives on combined evaluation grouped files that intentionally have no manifest `group_by`.
- Avoid applying the check to batch grouped outputs that use the actual grouping column name rather than a literal `group_by` column.
- Keep the new validation issue readable in both direct `validate_contents()` and CLI audit output.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep this scoped to report-manifest validation plus targeted tests unless a blocker requires otherwise.
3. Avoid editing `docs/legacy/**`.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if the current grouped artifact shapes make this validation rule ambiguous.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
