# Implementation Brief

## Task ID

QRE-REPORT-ROLLING-WINDOW-SIZE-FILTER-PARITY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Batch and shared report manifests already emit numeric `window_size` metadata on rolling artifacts such as `rolling_summary_20.csv`, `rolling_summary_20_by_board.csv`, and `rolling_metrics_20.csv`. But `ReportFile` does not parse that metadata, `ReportManifest.files()` / `paths()` / `validate_contents()` cannot filter on it, and the CLI surfaces only `--role`, `--symbol`, `--window`, and `--group-by`. As a result, the manifest metadata exists in JSON but is not usable through `qre report-files`, `qre report-audit`, or `report-files --json`.

## Goal

Add rolling-artifact `window_size` filter parity across report-manifest helpers and report CLI commands so existing manifest metadata becomes queryable and visible through discovery output.

## Non-Goals

- Do not change report-manifest schema version.
- Do not change rolling artifact filenames, roles, or output-generation logic.
- Do not replace or overload existing string `window` filters.
- Do not change grouped-artifact `group_by` validation logic from `a3768fb` / `de37afd`.
- Do not edit legacy archived docs under `docs/legacy`.

## Affected Modules

Expected runtime/tests:

- `src/quant_research_engine/portfolio/report_manifest.py`
- `src/quant_research_engine/apps/cli.py`
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
- evaluation or portfolio engine math/output-generation modules unless a narrow manifest-metadata helper fix is genuinely required

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve existing `report-files` / `report-audit` role, symbol, window, and `group_by` filter behavior.
- Preserve rolling artifact filenames and existing role mapping.
- Keep manifest schema version unchanged.
- Preserve current rolling output generation; manifests already contain the needed metadata.
- Preserve archived legacy docs.
- Keep the task narrowly scoped to report-manifest parsing/filtering, CLI plumbing, and targeted tests.

## Implementation Steps

1. Inspect current report-manifest helpers and the rolling artifact families that already carry manifest `window_size` metadata:
   - `rolling_summary`
   - `rolling_ranked_symbols`
   - `rolling_metrics`
2. Extend `ReportFile` parsing to accept optional numeric `window_size` metadata from manifest entries:
   - absent or explicit `null` remains allowed
   - non-integer values should fail with a manifest-specific `ValueError`
   - do not silently accept boolean or string values
3. Thread optional `window_size` filtering through:
   - `ReportManifest.files()`
   - `ReportManifest.paths()`
   - `ReportManifest.validate_contents()`
4. Add `--window-size` to:
   - `qre report-files`
   - `qre report-audit`
   Use integer parsing at the CLI boundary and preserve all existing filter semantics.
5. Surface `window_size` in `report-files --json` file entries when present.
6. Add focused coverage in:
   - `tests/test_portfolio_report_manifest.py` for parsing and filtering behavior
   - `tests/test_cli.py` for CLI filtering and JSON output behavior
7. Update handoff/progress docs.

## Data / Schema Changes

- No data or schema changes.
- Manifest schema version must remain unchanged.

## API / Interface Changes

- No new commands.
- Add optional `--window-size <int>` filter to `qre report-files` and `qre report-audit`.
- `report-files --json` should include numeric `window_size` on matched file entries when present.

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

- [ ] Manifest entries with `window_size: 20` parse into `ReportFile.window_size == 20`.
- [ ] Manifest entries with invalid `window_size` types such as `"20"` or `true` fail with a manifest-specific `ValueError`.
- [ ] `ReportManifest.files()` / `paths()` / `validate_contents()` can filter rolling artifacts by `window_size`.
- [ ] `qre report-files --window-size 20` and `qre report-audit --window-size 20` match only the rolling artifacts with that metadata.
- [ ] `qre report-files --json` includes numeric `window_size` fields when present.
- [ ] Existing `role`, `symbol`, `window`, and `group_by` filters keep their current behavior.
- [ ] Legacy archived docs are untouched.
- [ ] `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q`, `scripts/check-progress-docs.sh`, and `git diff --check` pass.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Keep numeric `window_size` metadata distinct from string `window` metadata.
- Avoid widening the task into rolling output-generation changes; manifests already emit `window_size`.
- Keep CLI JSON payloads backward-compatible aside from the additive `window_size` field.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep this scoped to report-manifest parsing/filtering, CLI plumbing, and targeted tests unless a blocker requires otherwise.
3. Avoid editing `docs/legacy/**`.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if current rolling-manifest metadata shapes make `window_size` filtering ambiguous.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
