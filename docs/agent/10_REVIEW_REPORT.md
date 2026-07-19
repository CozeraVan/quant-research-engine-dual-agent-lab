# Review Report

## Task ID

QRE-BATCH-FULL-VALIDATION-001 (M9.4) — pilot slice

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- Standing instruction honored exactly: handoff + small-sample pilot only; no full-scale execution.
- Handoff completeness verified: 7 requests match the known missing set across all 5 blocked strategies (sma_20/65 confirmed present — earlier notes over-listed).
- Known issue recorded: `qre preflight` crashes with UndefinedColumn on strategies whose factor columns are absent (instead of emitting missing-factor requests) — robustness follow-up, documented in 09.
- Feasibility estimate grounded in measured decompositions (1y full-market + 10y pilot), assumptions stated; R-QRE-008 caveat in the report.
- No runtime code changed; suite stays 1118 green.

## Behavior Verified

- Pilot 5/5 OK; stage durations from manifests; feasibility.md written; handoff file consistent with spec factor_fields × DB schema.

## Residual Risks

- 10y full-market extrapolation carries DB-read uncertainty (stated in the report).
- Eval stage excluded from pilot; full validation may want it (+~20-30s/strategy).

## Next Step

Full-scale full-history batch (106 strategies × full market × 2015-2025, ~3h) is ready to trigger on user approval; upstream factor delivery (`outputs/handoff/missing_factor_requests.json`) unblocks the remaining 5.

# Review Report (archive: M10.3)

## Task ID

QRE-CONTINUOUS-REFRESH-001 (M10.3)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- Scope matches `08_IMPLEMENTATION_BRIEF.md`: refresh module, script, systemd units, manifest registration, tests — all delivered; no full-scale execution (small-sample only, per standing instruction).
- Two defects caught and fixed during implementation: `BatchRunConfig` was briefly constructed with a non-existent `jobs` field (removed — jobs belongs to `execute_batch`), and delta directories collided at second-resolution timestamps on rapid successive runs (now `<timestamp>_<batch_id>`).
- One test-hygiene fix: removed two leftover no-op assertion lines in the script e2e test.
- Script behavior verified end-to-end on real data: first run executes (106 ok / 111 with the 5 known missing-factor errors), check-only is side-effect free, same-watermark run no-ops, watermark bump refreshes with delta vs previous batch.
- LOCKED requirements intact: R-QRE-005 (read-only), R-QRE-007 (manifest/audit parity), R-QRE-008 (caveat in delta report), R-QRE-009 (small-sample verification only), no new dependencies, systemd not installed by agent.
- R-CORE-003: 9 new tests incl. script-level e2e; full suite 1118 green.

## Behavior Verified

- `uv run pytest -q` → 1118 passed.
- Real-data e2e: watermark 2026-07-17; state written with batch id, counts, config; delta manifest passes `qre report-audit` (0 issues).
- `scripts/check-progress-docs.sh` → passed; `git diff --check` → clean (re-run before commit).

## Residual Risks

- Refresh window ends at the data watermark; strategies whose factors lag the market table (upstream indicator refresh delay) would be evaluated against partially-stale factor columns — mitigated by preflight being skippable but not yet re-verified per refresh (a `--with-preflight` refresh policy is a possible follow-up).
- The 5 missing-factor strategies will keep erroring on every refresh until upstream delivers the columns; the delta report surfaces this as persistent `error` transitions.
- Timer runs as the user; DB URL comes from the unit's Environment line — secrets stay out of the repo (R-CORE-004).

## Next Step

Phase → `AWAITING_GIT_APPROVAL`. Proposed commit message presented to the user; commit only after explicit approval.
