# CR-0002: Strategy Research Validation Phase (Milestone 9)

## 1. Background

The QRE engine is feature-complete (947 tests green) and the 111-strategy catalog passed its plumbing validation: smoke-mode batch `61e67b53b644` (2026-05-30, 2-month window) ran 106 strategies OK, with 5 blocked on missing upstream factor columns. Per R-QRE-008, smoke results are not research conclusions — the 2-month window, the -0.79% mean return, and the strategy rankings prove only that the pipeline works.

Meanwhile the batch infrastructure has structural limits: serial single-process execution (~6.5 min/strategy), ~3M output files per batch, and every strategy reloading identical market data. Deeper windows (1-year quick, 2015-2025 full) are impractical until this is fixed.

## 2. Goal

Move the strategy catalog from "smoke-tested plumbing" to "research-grade evidence": longer history, statistically defensible rankings, and an auditable aggregate report — while keeping the engine's locked constraints intact.

## 3. User Scenario

The research lead wants to know which catalog strategy families (if any) show real, cost-adjusted, out-of-sample edge in A-share daily data — and which are noise from screening 111 variants. They need a defensible ranking they can drill into via the existing manifest/audit tooling, not a one-off spreadsheet.

## 4. Scope

### In Scope

- **M9.1 Batch performance & output slimming** (`QRE-BATCH-PERF-SLIM-001`): runner core into `src/`, `--jobs N` parallelism, `--compact` output mode, profiling-driven data-load reuse, quick-mode (1-year) batch of the 106 ready strategies.
- **M9.2 Statistical validation layer** (`QRE-EVAL-STATISTICAL-VALIDATION-001`): multiple-testing control across the 111-variant screen (e.g. deflated Sharpe ratio / FDR-adjusted significance), walk-forward or anchored out-of-sample splits at runner level, reuse of the existing deterministic random-baseline comparison.
- **M9.3 Research-grade aggregate report** (`QRE-RESEARCH-REPORT-001`): one ranked, adjustment-aware report over batch results (per-strategy adjusted metrics, category statistics, trade-count sufficiency flags), registered in `report_manifest.json` and auditable via `qre report-audit`.
- **M9.4 Full-mode validation & blocked strategies**: full-window (2015-2025) batch for the adjusted-top-N candidates; emit `missing_factor_requests.json` for `atr_10`, `sma_7/9/20/26/50/52/65` so upstream can unblock the 5 remaining strategies.

### Out of Scope

- Computing indicators inside QRE (R-QRE-002) — factor production stays in `indicators_tushare` / `quant_ts` (R-QRE-001).
- Engine trading-rule, cost-model, or signal-semantics changes.
- New strategy variants or catalog expansion.
- GUI features; production-trading anything.

## 5. Affected Requirements

- R-QRE-008 stays central: M9.1-M9.2 exist precisely to graduate results beyond "smoke plumbing" status.
- R-QRE-007: compact output mode must remain manifest-discoverable/auditable.
- R-CORE-003: every slice ships with tests; full suite stays green.

## 6. Protected Requirements

- Read `docs/agent/02_LOCKED_REQUIREMENTS.md` — especially R-QRE-001 (scope), R-QRE-002 (no internal indicators), R-QRE-003 (no lookahead: walk-forward splits must respect t/t+1 execution), R-QRE-005 (read-only DB).

## 7. Suggested Tasks

| Task ID | Task | Priority | Status |
|---|---|---|---|
| QRE-BATCH-PERF-SLIM-001 | Runner core into src + parallel jobs + compact output + quick batch | High | DONE (awaiting commit; batch `f365c8a07b33`: 106 OK/5 error, 11.1h, 2.8GB) |
| QRE-VECTORIZED-ENGINE-001 | **M9.1b** Vectorized trade-level single-symbol engine: full-frame signal eval, groupby pre-split, event-level trade loop, equity-curve reconstruction, `position_sizing` modes; metric equality vs bar simulator | High | READY_FOR_BRIEF (user-approved direction 2026-07-19) |
| QRE-EVAL-STATISTICAL-VALIDATION-001 | Multiple-testing control + walk-forward splits + random-baseline tie-in | High | MERGED into CR-0003 M10.1 (2026-07-19) |
| QRE-RESEARCH-REPORT-001 | Ranked adjustment-aware aggregate report with manifest/audit parity | Medium | MERGED into CR-0003 M10.1 (2026-07-19) |
| QRE-BATCH-FULL-VALIDATION-001 | Full-mode batch for top candidates + missing-factor requests for 5 blocked strategies | Medium | PILOT DONE (handoff emitted; small-sample pilot OK; ~3h full-scale estimate; full-scale + upstream factors are user decisions) |

## 8. Acceptance Criteria

- [ ] Quick-mode batch of 106 strategies completes ≤ 6h wall time with ≤ ~20 output files per strategy.
- [ ] Statistical layer reports adjusted significance per strategy and flags likely screening noise.
- [ ] Aggregate research report is discoverable and auditable through `qre report-files` / `qre report-audit`.
- [ ] Full-mode batch completed for adjusted-top-N candidates; results documented with window, costs, and caveats.
- [ ] `missing_factor_requests.json` emitted for the 5 blocked strategies and handed to upstream.

## 9. Risks

- Parallel workers multiply Postgres connection/IO load — cap `--jobs`, reuse engines per worker, keep read-only.
- Compact mode could silently break manifest audit contracts — explicit metric-equality and audit-parity tests required.
- Runtime estimates may be wrong — profiling baseline (step 1 of M9.1) gates the data-load reuse work.
- Walk-forward splits risk subtle lookahead — must reuse the engine's existing t/t+1 execution discipline (R-QRE-003).
- 5 blocked strategies depend on upstream factor delivery, which QRE cannot schedule.

## 10. Implementation Notes

- Batch evidence so far: `outputs/backtests/full_batch_106/61e67b53b644/batch_summary.json`.
- Runner: `scripts/batch_backtest_runner.py` (serial, 404 lines); research-run pipeline: `src/quant_research_engine/orchestration/research_run.py`.
- Random-baseline infrastructure already exists in the evaluation layer; statistical slice should extend it rather than reinvent.
- No new dependencies (CSV/JSON outputs only).

## 11. Proposed Agent State Transition

- Next Phase: `PLANNING`
- Next Owner: `KIMI_CODE`
