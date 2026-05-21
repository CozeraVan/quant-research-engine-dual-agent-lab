# Implementation Brief

## Task ID

QRE-REPORT-BATCH-GROUP-BY-HEADER-CONSISTENCY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Batch grouped artifacts already carry manifest `group_by=<col>` metadata for `group_by_<col>.csv`, `group_by_<col>_ranked_symbols.csv`, `window_summary_<window>_by_<col>.csv`, and `rolling_summary_<n>_by_<col>.csv`. Current audit validation still checks only the generic required summary/ranking columns. That means a manifest entry can claim `group_by=board` while the batch CSV header actually uses another grouping column such as `sector`, and `validate_contents()` still passes.

## Goal

Harden report-manifest content validation so batch grouped artifact files with manifest `group_by` metadata must expose the same group column name in their CSV headers.

## Non-Goals

- Do not change report-manifest schema version.
- Do not change grouped artifact filenames, roles, or CLI flags.
- Do not change evaluation/shared grouped consistency rules added in `QRE-REPORT-GROUP-BY-CONTENT-CONSISTENCY-001`.
- Do not validate batch row values against manifest `group_by`; this task is header-level consistency only.
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
- Preserve batch grouped artifact filenames and existing role mapping.
- Keep manifest schema version unchanged.
- Preserve archived legacy docs.
- Keep the task narrowly scoped to audit/content validation rather than output-generation changes.

## Implementation Steps

1. Inspect current `ReportManifest.validate_contents()` flow and the batch grouped artifact families that carry manifest `group_by` metadata:
   - `group_summary`
   - `group_ranked_symbols`
   - `window_summary`
   - `window_ranked_symbols`
   - `rolling_summary`
   - `rolling_ranked_symbols`
2. After required-column validation passes for batch grouped entries with manifest `group_by=<col>` metadata, add a header-level consistency check:
   - read the CSV header
   - verify the header contains a column named exactly the manifest entry's `group_by`
3. Emit a stable validation issue when header and manifest metadata disagree:
   - use one clear code for this failure mode
   - include the manifest `group_by` value and the observed header columns in the message
4. Do not apply this new check to evaluation/shared grouped roles, which already use literal `group_by` CSV columns and are covered by the previous task.
5. Add focused coverage in:
   - `tests/test_portfolio_report_manifest.py` for direct `validate_contents()` behavior
   - `tests/test_cli.py` for `qre report-audit` surface behavior
6. Update handoff/progress docs.

## Data / Schema Changes

- No data or schema changes.
- Manifest schema version must remain unchanged.

## API / Interface Changes

- No new commands or flags.
- `report-audit` may surface a new issue code/message when a batch grouped CSV header disagrees with manifest `group_by` metadata.

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

- [ ] A batch `group_summary` file with manifest `group_by=board` fails audit if the CSV header uses another group column such as `sector`.
- [ ] A batch grouped window/rolling/ranked file with manifest `group_by=board` fails audit if the CSV header lacks `board`.
- [ ] Matching batch grouped files still pass audit.
- [ ] Evaluation/shared grouped consistency checks remain unchanged.
- [ ] `qre report-audit` surfaces the batch header mismatch through existing validation output.
- [ ] Legacy archived docs are untouched.
- [ ] `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q`, `scripts/check-progress-docs.sh`, and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid false positives on non-batch grouped roles that also carry manifest `group_by` metadata.
- Avoid interpreting batch group values as if they were literal `group_by` CSV cells; this task should stay at header validation.
- Keep the new validation issue readable in both direct `validate_contents()` and CLI audit output.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep this scoped to report-manifest validation plus targeted tests unless a blocker requires otherwise.
3. Avoid editing `docs/legacy/**`.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if the current batch grouped artifact header shapes make this validation rule ambiguous.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
