# Implementation Brief

## Task ID

QRE-RESEARCH-RUN-ROOT-REPORT-MANIFEST-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Make a completed `qre research-run` bundle have one top-level report manifest entry point that existing `qre report-files` and `qre report-audit` can consume directly.

The previous task made stage artifacts real (`preflight/`, `eval/`, `backtest/`) and kept `research_run_manifest.json` as the run-level provenance manifest. The remaining contract gap is operator discovery: `qre report-files <run>/research_run_manifest.json` currently exits `2` because `research_run_manifest` is a run-manifest kind, not a report-manifest kind. The project docs also still contain stale root-level `preflight_report.json` examples while the implementation writes `preflight/preflight_report.json`.

This task should add a report-manifest entry point for the whole research-run directory, not turn `research_run_manifest.json` itself into a report manifest.

## Evidence From Codex Probe

Direct probe:

```bash
tmp=$(mktemp -d)
cat > "$tmp/research_run_manifest.json" <<'JSON'
{"schema_version":1,"kind":"research_run_manifest","run_id":"r1","command":"research-run","strategy_path":"s.yaml","artifacts":[]}
JSON
uv run qre report-files "$tmp/research_run_manifest.json"
# manifest kind must be one of: batch_backtest_report_manifest, evaluation_report_manifest, shared_cash_backtest_report_manifest, strategy_smoke_report_manifest
# exit=2
```

Additional doc drift:

- `README.md` still documents `outputs/research/<run>/preflight_report.json`.
- Current implementation writes `outputs/research/<run>/preflight/preflight_report.json`.
- `docs/agent/01_CURRENT_STATUS.md` says `research_run_manifest` is discoverable through `qre report-files` / `qre report-audit`, but there is no top-level report manifest for a research-run bundle.
- Codex found `docs/agent/03_ROADMAP.md` still marked M8.46 as `WAITING_USER_APPROVAL` even though the stage artifact parity task is finalized; this handoff syncs that roadmap state and opens M8.47.

## Required Behavior

1. Top-level research-run report manifest
   - `qre research-run` should write `<output_dir>/report_manifest.json` for the whole bundle.
   - Add a supported report-manifest kind such as `research_run_report_manifest`.
   - The manifest must follow the existing report manifest schema: `schema_version`, `kind`, and `files` list.
   - The manifest must include `research_run_manifest.json` with role `run_manifest` so `ReportManifest.validate_contents(role="run_manifest")` validates the run provenance payload.
   - Include stage entry points when they exist:
     - preflight report JSON: role can be `preflight_report` or another explicit stable role.
     - eval report manifest: role can be `stage_report_manifest` or another explicit stable role with stage metadata if the schema supports it.
     - backtest report manifest: same pattern as eval.
   - Do not include skipped-stage files that do not exist.

2. CLI/operator behavior
   - `qre research-run` stdout should print `report_manifest=<path>` in addition to existing `research_manifest=...` and stage manifest lines.
   - `qre report-files <run>/report_manifest.json --check-exists --validate-contents` should exit `0` for a monkeypatched successful research run.
   - `qre report-audit <run>/report_manifest.json --role run_manifest --require-match` should exit `0`.
   - `qre report-files <run>/research_run_manifest.json` may continue to exit `2`; if so, docs must clearly point users to `<run>/report_manifest.json` for discovery and `<run>/research_run_manifest.json` for provenance.

3. Manifest validation
   - Keep existing report manifest validation behavior for batch/shared/evaluation/smoke manifests unchanged.
   - Keep existing run manifest validation behavior for `research_run_manifest` unchanged.
   - Add regression coverage that a `research_run_report_manifest` loads through `ReportManifest.from_path()` and validates its `run_manifest` entry.
   - If adding new JSON roles, do not over-validate their internal payloads unless a stable schema already exists. Existence plus run-manifest validation is enough for this slice.

4. Documentation sync
   - Update README research-run examples to show:
     - `<run>/preflight/preflight_report.json`
     - `<run>/eval/report_manifest.json`
     - `<run>/backtest/report_manifest.json`
     - `<run>/research_run_manifest.json`
     - `<run>/report_manifest.json`
   - Preserve the agent-doc state that marks M8.46 DONE and this task as the active implementation handoff.
   - Remove or clarify claims that `research_run_manifest.json` itself is a report manifest.

## Non-Goals

- Do not add database writes.
- Do not change evaluation, preflight, or backtest calculation semantics.
- Do not compute indicators inside QRE.
- Do not implement real benchmark wiring, real regime classification, or time-varying suspension/ST/risk-warning metadata.
- Do not make `research_run_manifest.json` masquerade as a report manifest if that would weaken the existing schema distinction.
- Do not break `qre report-files` / `qre report-audit` for existing report manifest kinds.

## Suggested Implementation Notes

- Add a small writer helper near `orchestration/research_run.py`, for example `_write_research_report_manifest(result, request) -> Path`.
- Extend `ResearchRunResult` with `report_manifest_path: Path | None` if needed.
- Top-level report manifest entries should use paths relative to `<output_dir>`.
- Consider entry keys such as:
  - `research_run_manifest`
  - `preflight_report`
  - `eval_report_manifest`
  - `backtest_report_manifest`
- If a `stage` metadata field is useful, confirm `ReportFile.from_mapping()` tolerates or ignores extra fields before relying on it. If it does not preserve extra metadata, keep stage encoded in key/role names for this slice.
- Keep the top-level `research_run_manifest.json` as the provenance source with `stages`, `preflight_artifacts`, `eval_artifacts`, `backtest_artifacts`, and stage-qualified `artifacts`.

## Tests Required

Add or update tests for:

1. `ReportManifest.from_path()` accepts `research_run_report_manifest`.
2. `ReportManifest.validate_contents(role="run_manifest")` accepts the top-level `research_run_manifest.json` entry.
3. A successful monkeypatched `run_research_run()` writes both `research_run_manifest.json` and `report_manifest.json`.
4. `qre research-run` successful CLI path prints `report_manifest=...`.
5. `qre report-files <run>/report_manifest.json --check-exists --validate-contents` succeeds for the monkeypatched run.
6. `qre report-audit <run>/report_manifest.json --role run_manifest --require-match` succeeds.
7. Skipped preflight/eval do not produce nonexistent entries in the top-level report manifest.
8. README example paths match the actual output layout.

## Validation Commands

Run at least:

```bash
uv run pytest tests/test_research_run.py tests/test_cli.py tests/test_portfolio_report_manifest.py -q
uv run pytest tests/test_portfolio_io.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

If a real database URL is configured, also run a narrow real `qre research-run` and then:

```bash
uv run qre report-files <run-dir>/report_manifest.json --check-exists --validate-contents
uv run qre report-audit <run-dir>/report_manifest.json --role run_manifest --require-match
uv run qre report-files <run-dir>/eval/report_manifest.json --check-exists --validate-contents
uv run qre report-files <run-dir>/backtest/report_manifest.json --check-exists --validate-contents
```

If no database is configured, document that as a validation gap in `09_CODING_HANDOFF.md`.
