# Review Report

## Task ID

QRE-BATCH-PERF-SLIM-001

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS (implementation); quick-mode batch operational run in progress

## Findings

Self-review checklist results:

- Scope matches `08_IMPLEMENTATION_BRIEF.md`: steps 1-4, 6-8 implemented; step 5 (data-load reuse) correctly gated out by the profiling baseline (DB load ≈ 1.2% of runtime, documented in `09_CODING_HANDOFF.md`).
- No engine behavior changes: single-symbol/batch/shared engines, cost model, and signal semantics untouched. Compact mode only skips output writing; metric parity proven.
- One pre-existing bug found and fixed in passing: old resume scan could never match a parent `--output-dir`, so `--resume` silently never skipped. New `completed_strategies()` handles both directory levels and is unit-tested.
- LOCKED requirements intact: R-QRE-001/002/003/005/007 respected (read-only DB, no internal indicators, no lookahead, manifest contracts preserved — compact manifest still parses and all referenced files exist, verified by test).
- R-CORE-003: 20 new unit tests including parallel-pool execution, compact-vs-standard parity, store-close guard, and stage-duration manifest persistence.

## Behavior Verified

- `uv run pytest -q` → 967 passed, 2 warnings (947 baseline + 20 new; zero regressions).
- Real-DB parity check (3 symbols, smoke window, tf01a): compact and standard modes produce byte-identical `summary.csv` and identical `summary_metrics.json`; compact backtest dir has 9 strategy-level files, no symbol trees, no workbook/HTML.
- Profiling baseline recorded: tf01a quick mode serial = 1742.5s (eval 21.3s / backtest 1718.9s), 26,312 files / 239MB for one strategy.
- `scripts/check-progress-docs.sh` → passed; `git diff --check` → clean (to be re-run before commit).
- Batch script `--dry-run` and discovery sanity covered by unit tests (`discover_strategies`, `completed_strategies`).

## Residual Risks

- ~~Quick-mode batch still running~~ — RESOLVED 2026-07-19: batch `f365c8a07b33` completed, 106 OK / 5 error (only the known missing-factor strategies); wall time 11.1h; 2,013 files / 2.8GB; `qre report-audit` on compact manifests → status=ok, 0 issues.
- The ≤6h wall-time acceptance line was MISSED (11.1h): profiling proved the per-symbol engine loop is ~98% of runtime, so `--jobs` and `--compact` alone cannot reach it. Recorded honestly in `09_CODING_HANDOFF.md`; the engine-loop optimization follow-up is listed as a pending user decision in `11_AGENT_STATE.md`.
- Parallel workers multiply DB connections (4 workers × 4 engines); mitigated by `close()` per run and read-only workloads. No pool sizing guard beyond user-chosen `--jobs`.
- Process-pool tests assume Linux `fork` start method (documented in test docstring); project targets Linux only.

## Next Step

Phase → `AWAITING_GIT_APPROVAL`. Proposed commit message presented to the user; commit only after explicit approval.
