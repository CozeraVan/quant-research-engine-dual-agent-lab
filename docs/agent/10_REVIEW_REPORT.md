# Review Report

## Task ID

QRE-RESEARCH-RUN-ORCHESTRATION-001

## Written By

CLAUDE_CODE (acting reviewer — Codex unavailable)

## Review Outcome

PASS

## Reviewed Implementation

Claude Code implementation of `qre research-run` orchestrator: a single CLI command that chains preflight → eval-config → backtest under a common `--run-id` with a `research_run_manifest.json`.

## Review Summary

Implementation meets the active task target and closes the "Larger research-run bundles beyond run-level identifier linkage" known gap.

Evidence:

- `src/quant_research_engine/orchestration/research_run.py` — ~200 lines with `ResearchRunRequest` + `ResearchRunResult` dataclasses, `run_research_run()` orchestrator, `_write_research_manifest()`, and per-stage helpers.
- `src/quant_research_engine/apps/cli.py` — `qre research-run` subparser with 16 flags, handler that builds `ResearchRunRequest`, calls `run_research_run()`, and prints results.
- `tests/test_research_run.py` — 7 unit tests (request construction, result construction, manifest writing with ok/error/skipped stages).
- `tests/test_cli.py` — 3 CLI tests (--help, missing required args, no-DB error).
- `docs/agent/03_ROADMAP.md` — M8.42 added, stale M7.x/M8.1/M8.3/M8.10 synced to DONE.
- `docs/agent/01_CURRENT_STATUS.md` — synced with current state, known gaps updated.

Key design decisions:

- Calls engine functions directly (same pattern as GUI), not via CLI subprocess.
- Auto-generates `run_id` (uuid4 hex[:12]) when not user-provided.
- Fail-fast: stops on preflight/eval error, writes partial manifest.
- Backtest mode defaults to `batch`; shared-cash available via `--backtest-mode shared`.

## Required Fixes

None.

## Compliance with Implementation Brief

Compliant with `docs/agent/08_IMPLEMENTATION_BRIEF.md` for `QRE-RESEARCH-RUN-ORCHESTRATION-001`.

## Validation

Commands run:

```bash
uv run pytest tests/test_research_run.py -q
uv run pytest tests/test_cli.py -q --tb=short -k "research_run"
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py tests/test_research_run.py -q
scripts/check-progress-docs.sh
git diff --check
```

Result:

- research-run unit tests: `7 passed in 0.46s`
- research-run CLI tests: `3 passed in 0.80s`
- full validation: `476 passed, 2 warnings in 5.01s`
- progress docs check passed
- `git diff --check` passed

## Final Recommendation

Accept and finalize. The research-run orchestrator addresses the last remaining known gap in `01_CURRENT_STATUS.md` ("Larger research-run bundles beyond run-level identifier linkage").

## Next Agent State

- Phase: `CODEX_GIT_FINALIZING`
- Owner: `CLAUDE_CODE` (acting git finalizer — Codex unavailable)
