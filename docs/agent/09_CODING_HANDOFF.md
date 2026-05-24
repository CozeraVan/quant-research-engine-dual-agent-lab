# Coding Handoff

## Task ID

QRE-RESEARCH-RUN-ROOT-REPORT-MANIFEST-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

IMPLEMENTED

## Objective

Add a top-level `report_manifest.json` for `qre research-run` bundles so existing `qre report-files` and `qre report-audit` workflows can inspect the whole run directory. Previously, `qre report-files <run>/research_run_manifest.json` exited 2 because `research_run_manifest` is a run-manifest kind, not a report-manifest kind.

## Implementation Summary

### Change 1: Register new report-manifest kind

- Added `"research_run_report_manifest"` to `_SUPPORTED_MANIFEST_KINDS` in `src/quant_research_engine/portfolio/report_manifest.py`.
- New kind is accepted by `ReportManifest.from_path()` and all existing validation/audit infrastructure.

### Change 2: Research-run report manifest writer

- Added `_write_research_report_manifest(result, request) -> Path` to `src/quant_research_engine/orchestration/research_run.py`.
- Writes `<output_dir>/report_manifest.json` with kind `research_run_report_manifest`, `schema_version: 1`, and a `files` array.
- Files array always includes `research_run_manifest.json` with role `run_manifest`.
- Stage entry points included only when they exist:
  - `preflight/preflight_report.json` with role `preflight_report`
  - `eval/report_manifest.json` with role `eval_report_manifest`
  - `backtest/report_manifest.json` with role `backtest_report_manifest`
- Paths are relative to the output directory.

### Change 3: ResearchRunResult field

- Added `report_manifest_path: Path | None = None` to `ResearchRunResult` dataclass.

### Change 4: Writer called in run_research_run()

- `_write_research_report_manifest()` is called after `_write_research_manifest()` in all three paths: preflight error, eval error, and success.

### Change 5: CLI prints report_manifest path

- Updated research-run handler in `cli.py` to print `report_manifest=<path>`.

### Change 6: Tests

- `tests/test_portfolio_report_manifest.py`: +5 tests
  - `test_report_manifest_accepts_research_run_report_manifest_kind`
  - `test_research_run_report_manifest_validates_run_manifest_role`
  - `test_research_run_report_manifest_reports_missing_files`
  - `test_research_run_report_manifest_with_all_stage_entries`
  - `test_research_run_report_manifest_run_manifest_validation_reports_errors`
- `tests/test_research_run.py`: +5 tests in `TestWriteResearchReportManifest`
  - `test_writes_report_manifest_with_research_run_manifest`
  - `test_includes_preflight_report_when_present`
  - `test_includes_eval_report_manifest_when_present`
  - `test_includes_backtest_report_manifest_when_present`
  - `test_skipped_preflight_not_included`
- `tests/test_research_run.py`: updated existing orchestration tests to assert `report_manifest_path` and content
- `tests/test_cli.py`: +2 tests
  - `test_cli_report_files_research_run_report_manifest`
  - `test_cli_report_audit_research_run_report_manifest_role_run_manifest`
- `tests/test_cli.py`: updated `test_cli_research_run_success_prints_stage_paths` to assert `report_manifest=` line

### Change 7: Docs

- Updated `README.md` research-run example paths and added discovery/audit examples.
- Synced `docs/agent/01_CURRENT_STATUS.md`, `docs/agent/03_ROADMAP.md`.

## Validation

```bash
# Full test suite
uv run pytest -q
# 803 passed, 2 warnings in 12.93s (791 → 803: +12 tests)

# Targeted tests
uv run pytest tests/test_research_run.py tests/test_cli.py -q -k "research_run or research_run_report_manifest"
# 13 passed

uv run pytest tests/test_portfolio_report_manifest.py tests/test_portfolio_io.py -q
# 112 passed
```

## Files Changed

- `src/quant_research_engine/portfolio/report_manifest.py` — added `research_run_report_manifest` kind
- `src/quant_research_engine/orchestration/research_run.py` — new writer function, new result field, wired into orchestrator
- `src/quant_research_engine/apps/cli.py` — CLI prints `report_manifest=` path
- `tests/test_portfolio_report_manifest.py` — +5 tests
- `tests/test_research_run.py` — +5 tests, updated existing tests
- `tests/test_cli.py` — +2 tests, updated existing test
- `README.md` — synced paths and added discovery examples
- `docs/agent/01_CURRENT_STATUS.md` — synced status
- `docs/agent/03_ROADMAP.md` — M8.47 marked DONE

## Known Validation Gaps

- No database available for end-to-end `qre research-run` with a real strategy. Monkeypatched tests cover all code paths.
- `scripts/check-progress-docs.sh` and `git diff --check` should be run before handoff.

## Verification for Reviewer

```bash
# Reproduce the original probe gap
tmp=$(mktemp -d)
cat > "$tmp/report_manifest.json" <<'JSON'
{"kind":"research_run_report_manifest","files":[{"key":"research_run_manifest","path":"research_run_manifest.json","filename":"research_run_manifest.json","role":"run_manifest"}]}
JSON
cat > "$tmp/research_run_manifest.json" <<'JSON'
{"schema_version":1,"kind":"research_run_manifest","run_id":"r1","command":"research-run","strategy_path":"s.yaml","artifacts":[]}
JSON
uv run qre report-files "$tmp/report_manifest.json" --check-exists --validate-contents
# exit=0
uv run qre report-audit "$tmp/report_manifest.json" --role run_manifest --require-match
# exit=0
```
