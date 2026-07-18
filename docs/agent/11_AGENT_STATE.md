# Agent State

This file is the source of truth for single-agent workflow recovery.

## Current Phase

AWAITING_GIT_APPROVAL

## Current Owner

KIMI_CODE (sole development agent; user is final approver)

## Current Task

QRE-SINGLE-AGENT-MIGRATION-001 (implementation DONE, self-review PASS; awaiting user-approved git finalization)

## Last Completed Step

**QRE-STRATEGY-CATALOG-BATCH-BACKTEST-001 (DONE, 2026-05-30, user-directed, uncommitted):**

1. Generated 111 low-level strategy YAMLs under `strategies/catalog/` across 7 categories
2. Built `scripts/batch_preflight_check.py` — factor availability checker against DB
3. Built `scripts/batch_backtest_runner.py` — full research-run pipeline batch executor
4. Connected to `tushare_data` PostgreSQL, analyzed 362 factor columns across 11 tables
5. Cross-referenced all 111 strategies: **106 ready** (all factors exist), **5 missing**
6. Fixed factor column naming: `macd_signal` → `macds`, `williams_r` → `willr`
7. Fixed `research_run.py` bugs: `BatchBacktestRequest` kwarg names, missing `symbols` field
8. Extended expression parser in `signals.py`: `&`/`|` operators, method chaining, arithmetic
9. Added `--codes` support to `batch_backtest_runner.py`
10. Created `.env` with DB connection string
11. **Batch 61e67b53b644 completed at 2026-05-30 02:33 — 106 OK, 5 error (missing factors), ~11.5h runtime**
12. **Final aggregate**: 106 strategies, mean return -0.79% (smoke mode), 30 positive (28.3%), 66 negative (62.3%), 10 zero (9.4%)
13. **Top strategy**: cb01b (MACD+Cross+Volume) = +2.62% mean return, 2,391 trades, 40.7% positive
14. **Category rankings**: kline_pattern (-0.12%) > price_volume (-0.19%) > breakout (-0.25%) > cross_sectional (-0.39%) > composite (-0.48%) > trend_following (-1.46%) > mean_reversion (-1.51%)
15. **Best single-symbol**: bo06a (ATR anomaly momentum) → 301306.SZ = +62.3%
16. **5 blocked strategies**: bo02 (atr_10), mr02b (sma_50), tf04 (atr_10), tf05a (sma_9/26/52), tf07e (sma_7)

## Git State

- Current branch: `master`
- Last commits: `33bb175`, `9d41ce7`, `0c4bbcf`, `abac8de`, `c7353aa`
- Working tree — uncommitted changes (batch backtest work products):
  - **Modified**: `Makefile`, `src/quant_research_engine/evaluation/signals.py`, `src/quant_research_engine/orchestration/research_run.py`
  - **New**: `scripts/batch_backtest_runner.py`, `scripts/batch_preflight_check.py`, `scripts/generate_strategy_yamls.py`, `strategies/catalog/` (111 YAMLs + README), `.env` (gitignored)
  - **This migration task**: workflow docs under `docs/agent/`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `.agents/skills/`, `.claude/skills/`
- Remote: none configured. Push is not applicable unless a remote is added.

## Latest Validation Evidence

```
uv run pytest -q → 947 passed, 2 warnings (2026-05-30)
```

## Pending Decisions (user)

1. Approve git finalization of the uncommitted batch backtest work products (`signals.py` evaluator extension is a runtime dependency of 67/111 catalog strategies).
2. Whether to commission upstream factor computation (`atr_10`, `sma_7/9/20/26/50/52/65`) in `indicators_tushare` / `quant_ts` to unblock the 5 remaining catalog strategies.
3. Whether to run deeper validation batches (`--mode quick` 1-year / `--mode full` 2015-2025).

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

Engine is feature-complete (947 tests green). Migration task `QRE-SINGLE-AGENT-MIGRATION-001`: implementation and self-review complete (`10_REVIEW_REPORT.md` PASS); awaiting user approval for git finalization. Note: the working tree also still holds the uncommitted batch backtest work products — the user decides whether the migration docs and the batch work are committed separately or together.
