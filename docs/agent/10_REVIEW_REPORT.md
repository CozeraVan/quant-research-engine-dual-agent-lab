# Review Report

## Task ID

QRE-VECTORIZED-ENGINE-001 (M9.1b)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS (with one acceptance line recorded as narrowly missed: speed target)

## Findings

- Equality gate (the hard requirement) is fully met with layered evidence: 61 synthetic equality tests (all documented edge semantics incl. dead-pending deadlock, rejection retry, exit-signal reschedule), 40 seeded randomized frames, 3×50 real-DB parity, **106/106 catalog strategies × 50 symbols byte-identical**, tf01a full-market artifacts byte-identical to the simulator baseline (`summary.csv`, metrics, window M/Q/Y, rolling 20).
- Profiling corrected an earlier wrong assumption (recorded honestly): the wall-clock hog was never file IO — it was the per-window analytics computation (~850s of the 1,718.9s baseline); the vectorized engine alone is ~190× faster (0.52s/300 symbols). Analytics collectors were then vectorized with `risk.py` kept as the untouched oracle.
- Speed acceptance line (backtest stage ≤30s): **MISSED at 40.2s** — decomposition recorded in `09`; remaining levers (cross-symbol-concatenated analytics, groupby-aware signals) deliberately deferred as follow-up micro-slices to avoid equality-risk churn past the point of diminishing returns. Effective outcome: 42.8× stage speedup, quick batch estimate 11.1h → ~25-30 min.
- Shared research frame introduced post-brief (same-frame reuse between eval and backtest); 4 existing tests updated with the new monkeypatch seam — interface evolution, no behavior change.
- Scope compliance: shared-cash engine untouched; no new dependencies; simulator preserved and selectable (`--engine-impl simulator`); library defaults conservative (runner CLI default flipped to `vectorized` only after the evidence above).
- LOCKED requirements intact: R-QRE-001/002/003/005/007/009 all respected — notably R-QRE-009 was followed (synthetic → 3×50 → 106×50 → full-market benchmark ladder).

## Behavior Verified

- `uv run pytest -q` → **1034 passed** (967 baseline + 67 new: 61 engine equality + 6 analytics equality), zero regressions.
- R-QRE-009 ladder: STEP1 3×50 identical; STEP2 106×50 identical (106/106); STEP3 full-market artifacts identical, backtest stage 40.2s (42.8×).
- Runner `--engine-impl vectorized` default; `--position-sizing fixed_cash` validated to require vectorized.
- `scripts/check-progress-docs.sh` → passed; `git diff --check` → clean (re-run before commit).

## Residual Risks

- Equality is proven for the catalog's expression shapes and the documented edge cases; exotic future expressions go through the same shared signal evaluator used by both engines, so divergence risk is minimal.
- `fixed_cash` semantics (fixed notional = initial_cash, affordability still on current cash) is documented but new — user-facing docs updated.
- The 5 missing-factor strategies remain blocked (upstream, M9.4).

## Next Step

Phase → `AWAITING_GIT_APPROVAL`. Proposed commit message presented to the user; commit only after explicit approval.
