# Implementation Brief

## Task ID

QRE-RESEARCH-RUN-STAGE-ARTIFACT-PARITY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Make `qre research-run` persist the same stage artifacts that the README and report-system contract imply: preflight output, evaluation output, backtest output, and a top-level `research_run_manifest.json` that links those stage manifests.

This is a contract-parity fix, not a new research feature. The current implementation runs preflight and evaluation in memory, then persists only backtest artifacts under the root output directory. README examples already document:

```text
outputs/research/<run>/preflight_report.json
outputs/research/<run>/eval/report_manifest.json
outputs/research/<run>/backtest/report_manifest.json
outputs/research/<run>/research_run_manifest.json
```

The implementation should make that true or update docs only where the existing documented contract is deliberately narrowed. Prefer making the code match the documented contract.

## Evidence From Codex Probe

- `src/quant_research_engine/orchestration/research_run.py::_run_eval()` returns an `EvaluationResult` but never calls the existing evaluation artifact writer.
- `src/quant_research_engine/orchestration/research_run.py::_run_preflight()` returns a report object but `run_research_run()` does not write a preflight artifact.
- `_run_backtest()` currently writes batch/shared artifacts directly into `request.output_dir`, not into a stage-scoped `backtest/` directory.
- `_write_research_manifest()` records only `backtest_artifacts` and `artifacts`; it does not link `preflight_report`, `eval/report_manifest.json`, or `backtest/report_manifest.json`.
- `tests/test_cli.py` has only help/missing-DB coverage for `research-run`; there is no successful orchestrated run regression. The file also ends with an unused `ResearchRunStrategySpec` helper, which suggests the success-path test was started but not finished.

## Required Behavior

1. Stage-scoped output layout
   - Preflight artifact: write a durable JSON artifact for the preflight stage when preflight is not skipped.
   - Evaluation artifacts: write evaluation CSVs, `run_manifest.json`, and `report_manifest.json` under `<output_dir>/eval/` when eval is not skipped.
   - Backtest artifacts: write batch/shared backtest artifacts under `<output_dir>/backtest/`.
   - Top-level research manifest remains at `<output_dir>/research_run_manifest.json`.
   - Skipped stages should be represented explicitly in the top-level manifest without requiring their directories to exist.

2. Reuse existing artifact contracts
   - Reuse existing evaluation output logic instead of duplicating CSV/manifest writer behavior.
   - If the existing evaluation writer is private to `cli.py`, move or wrap it cleanly so orchestration can use it without circular imports.
   - Preserve existing `eval-config` output behavior and tests.
   - Preserve existing `backtest-batch` and `backtest-shared` output behavior outside `research-run`.

3. Research manifest linkage
   - Extend `research_run_manifest.json` to include stage-level artifact links, at minimum:
     - `preflight_artifacts` or equivalent for the preflight JSON.
     - `eval_artifacts` including `eval/report_manifest.json` and `eval/run_manifest.json` when eval runs.
     - `backtest_artifacts` with paths relative to the research run root.
   - Keep required run-manifest fields intact: `schema_version`, `kind`, `run_id`, `command`, `strategy_path`, `artifacts`.
   - The top-level `artifacts` list should remain deterministic and should not include non-existent skipped-stage files.

4. CLI visibility
   - `qre research-run` stdout should print enough stage manifest paths for operators to immediately run `qre report-files` / `qre report-audit`.
   - At minimum, print `research_manifest=...`.
   - Prefer additive lines such as `eval_report_manifest=...` and `backtest_report_manifest=...` when those files exist.
   - Preserve existing exit-code behavior: `0` on complete success, `2` on setup/stage error.

5. Report discovery and audit parity
   - Ensure `qre report-files <output_dir>/eval/report_manifest.json` works for evaluation artifacts emitted by `research-run`.
   - Ensure `qre report-files <output_dir>/backtest/report_manifest.json` works for backtest artifacts emitted by `research-run`.
   - Ensure `ReportManifest.validate_contents()` accepts the emitted evaluation/backtest run manifests.
   - If top-level `research_run_manifest.json` is referenced from a report manifest in future, do not break existing `research_run_manifest` validation.

6. Tests
   - Add a successful unit-level `run_research_run()` test with monkeypatched store/spec/stage functions or small fake data so it does not require a real database.
   - Add CLI regression coverage for a successful `qre research-run` path using monkeypatching; assert stdout includes stage manifest paths and files exist.
   - Add manifest payload tests for skipped preflight/eval and for successful all-stage runs.
   - Clean up or complete the dangling `ResearchRunStrategySpec` helper at the end of `tests/test_cli.py`.
   - Add regression coverage that backtest artifacts are written under `backtest/`, not directly in the run root.

## Non-Goals

- Do not add database writes.
- Do not compute technical indicators inside QRE.
- Do not change strategy semantics, signal timing, or portfolio execution rules.
- Do not implement real benchmark wiring, real regime classification, or time-varying ST/risk-warning metadata.
- Do not change report-manifest schema incompatibly.
- Do not run or document smoke outputs as research conclusions.

## Suggested Implementation Notes

- Consider extracting `_write_evaluation_output()` and its helper functions from `apps/cli.py` into a reusable module, for example `evaluation/io.py`, while keeping `eval-config` behavior unchanged.
- Use stage directories:
  - `preflight_dir = output_dir / "preflight"` or a root `preflight_report.json`; README currently says root `preflight_report.json`. If choosing `preflight/preflight_report.json`, update README and docs consistently.
  - `eval_dir = output_dir / "eval"`
  - `backtest_dir = output_dir / "backtest"`
- Backtest `run_request_payload` should keep `run_id` and strategy provenance as it does today.
- Manifest relative paths should be relative to the top-level research run directory for the top-level manifest.

## Validation Commands

Run at least:

```bash
uv run pytest tests/test_research_run.py tests/test_cli.py -q
uv run pytest tests/test_portfolio_report_manifest.py tests/test_portfolio_io.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

If a database is available, also run a small real `qre research-run` using `strategies/low_level/bollinger_mean_reversion.yaml` with a narrow date range and two symbols, then verify:

```bash
uv run qre report-files <run-dir>/eval/report_manifest.json --check-exists --validate-contents
uv run qre report-files <run-dir>/backtest/report_manifest.json --check-exists --validate-contents
uv run qre report-audit <run-dir>/eval/report_manifest.json --require-match
uv run qre report-audit <run-dir>/backtest/report_manifest.json --require-match
```

If no database is configured, document that as a validation gap in `09_CODING_HANDOFF.md`.
