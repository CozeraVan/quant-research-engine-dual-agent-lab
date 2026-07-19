# Agent State

This file is the source of truth for single-agent workflow recovery.

## Current Phase

AWAITING_GIT_APPROVAL

## Current Owner

KIMI_CODE (sole development agent; user is final approver)

## Current Task

QRE-VECTORIZED-ENGINE-001 / M9.1b (implementation DONE, self-review PASS — awaiting user-approved git finalization)

Parent change request: `docs/agent/change_requests/CR-0002-strategy-research-validation.md` (Milestone 9: Strategy Research Validation).

## Last Completed Step

**QRE-BATCH-PERF-SLIM-001 / M9.1 (DONE, finalized 2026-07-19, commit `24699ce`):**

1. Batch runner core moved into `orchestration/batch_runner.py`; `--jobs N` process-pool parallelism; `--compact` output mode (9 files vs ~26k per strategy, metrics byte-identical).
2. Per-stage timing in research-run manifests; `PostgresDataStore.close()` engine disposal; resume scan fixed (both directory levels).
3. Profiling baseline: tf01a quick mode serial = 1742.5s (backtest stage 98.6%); data-load reuse ruled out by evidence.
4. Quick batch `f365c8a07b33` (2026-07-19 06:32 +08): **106 OK / 5 error** (known missing-factor strategies), wall time **11.1h** with 4 jobs (vs ~51h serial), per-strategy mean 1459s (-16%), **2,013 files / 2.8GB** (~99.9% fewer files, ~89% fewer bytes); `qre report-audit` on compact manifests → ok.
5. Milestone 10 planned (CR-0003): M10.1 strategy-fit clustering, M10.2 parameter overrides, M10.3 continuous refresh, M10.4 optional ML clustering; M9.2/M9.3 merged into M10.1.
6. R-QRE-009 locked (user standing instruction): small-sample validation before any full-scale run.

## Git State

- Current branch: `master`
- Last commit: `24699ce` Add parallel compact batch runner and complete quick-mode catalog batch (20 files)
- Working tree: clean except untracked `.claude/scheduled_tasks.lock` (lock file, intentionally untracked) and uncommitted docs/infra updates (R-QRE-009, M9.1b brief, outputs externalization: `.gitignore`, Makefile, README, runner `QRE_OUTPUT_DIR`, `04/05/06/11`).
- **Run outputs now live outside the repo**: `outputs` → symlink to `/home/van/qre-outputs/` (all 19GB preserved there); `QRE_OUTPUT_DIR` env var overrides the batch runner output root.
- Remote: none configured.

## Latest Validation Evidence

```
uv run pytest -q → 967 passed, 2 warnings (2026-07-19, M9.1 final)
scripts/check-progress-docs.sh → passed
git diff --check → clean
qre report-audit on compact quick-batch manifests → status=ok, 0 issues
```

## Pending Decisions (user)

1. ~~Approve or adjust CR-0002 / 08 brief~~ — APPROVED 2026-07-18; QRE-BATCH-PERF-SLIM-001 done.
2. **Commit approval for QRE-BATCH-PERF-SLIM-001** — implementation DONE, review PASS, quick batch verified; commit message proposed 2026-07-19.
3. Whether to commission upstream factor computation (`atr_10`, `sma_7/9/20/26/50/52/65`) in `indicators_tushare` / `quant_ts` to unblock the 5 remaining catalog strategies (needed for M9.4).
4. ~~Engine-loop optimization slice~~ — ADOPTED 2026-07-19 as M9.1b (`QRE-VECTORIZED-ENGINE-001`), next slice after the M9.1 commit.
5. ~~F1/F2/F3 granularity~~ — ALIGNED 2026-07-19, recorded in CR-0003 and decision log: M9.1b → M10.1 (F3) → M10.2 (F1) → M10.3 (F2); enrichment analysis first, ML clustering (M10.4) needs separate dependency approval.

## Quick Batch In Flight

- `outputs/backtests/quick_batch_106/f365c8a07b33/`, launched 2026-07-18 ~18:40, `--jobs 4 --compact --skip-preflight --resume`.
- Per-strategy ≈ 27-30 min (CPU-bound engine loop); expected total ≈ 13h. User decided to let it finish at `--jobs 4`.
- On completion: record batch results in `09`, verify compact output size reduction, then propose commit.

## Quick Batch Final (2026-07-19 06:32 +08)

- 106 OK / 5 error (only the known missing-factor strategies); wall time 11.1h; per-strategy mean 1459s (-16% vs baseline); 2,013 files / 2.8GB (≈99.9% fewer files, ≈89% fewer bytes vs standard mode); report-audit on compact manifests → status=ok, 0 issues.
- Remaining before commit: user approval.

## Phase Vocabulary (single-agent, since 2026-07-18)

- `PLANNING`: writing/updating `08_IMPLEMENTATION_BRIEF.md`
- `IMPLEMENTING`: executing the brief; records go to `09_CODING_HANDOFF.md`
- `SELF_REVIEW`: writing `10_REVIEW_REPORT.md`; Required Fixes send the task back to `IMPLEMENTING`
- `AWAITING_GIT_APPROVAL`: review passed, commit message proposed, waiting for user approval
- `DONE`: finalized (or docs-only task completed without commit need)
- `USER_DIRECTED`: no active workflow task; user decides the next move

## Standing Approvals

None. Every git commit requires explicit user approval in the current session.

## Completion Status

Engine feature-complete (947 tests green); single-agent workflow active; batch pipeline committed. Next phase (Strategy Research Validation) planned and awaiting user go-ahead: CR-0002 + first-slice brief `QRE-BATCH-PERF-SLIM-001` are drafted in `docs/agent/`.
