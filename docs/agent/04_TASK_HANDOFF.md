# Task Handoff

## Task ID

QRE-BATCH-PERF-SLIM-001

## Current Status

PLANNING (brief drafted in `08_IMPLEMENTATION_BRIEF.md`; parent CR-0002 drafted; both pending user approval)

## Current Owner

KIMI_CODE

## Problem Summary

The 106-strategy smoke batch proved the pipeline works but took ~11.5h serial (~6.5 min/strategy) and wrote ~3M output files for a 2-month window. Quick (1-year) and full (2015-2025) validation batches are impractical until the runner is parallelized and outputs are slimmed. This slice is the enabler for the Strategy Research Validation phase (CR-0002 / Milestone 9).

## Implementation Summary

Planning only so far:

1. `docs/agent/change_requests/CR-0002-strategy-research-validation.md` — phase proposal (M9.1 performance/slimming, M9.2 statistical validation, M9.3 research report, M9.4 full-mode + blocked strategies).
2. `docs/agent/08_IMPLEMENTATION_BRIEF.md` — first slice: profiling baseline, runner core into `src/quant_research_engine/orchestration/batch_runner.py`, `--jobs N` process-pool parallelism, `--compact` strategy-level output mode with manifest/audit parity, conditional data-load reuse, quick-mode batch of 106 strategies.
3. Previous task `QRE-SINGLE-AGENT-MIGRATION-001` finalized in commit `12880e1` (includes the earlier uncommitted batch work products and the single-agent workflow docs).

## Hard Constraints

- No engine trading-rule/cost/signal changes; no indicators inside QRE; read-only DB.
- No new dependencies; CSV/JSON outputs only.
- Compact mode must stay discoverable/auditable via `qre report-files` / `qre report-audit` (R-QRE-007).
- Full pytest suite stays green; no behavior change in standard (non-compact) mode.

## Validation Evidence

```bash
# Planning slice — docs only, no code changed yet
scripts/check-progress-docs.sh → to be run before commit
```
