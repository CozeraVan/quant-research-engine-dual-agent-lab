# Decision Log

Use this file for decisions that affect architecture, data, safety, compliance, prompts, schema, deployment, or dual-agent workflow.

## Format

### YYYY-MM-DD: Decision title

- Decision:
- Reason:
- Alternatives:
- Impact:
- Owner:

---

### Initial: Use dual-agent workflow

- Decision: This project uses Codex as Planner/Reviewer/Git Finalizer and Claude Code as Implementer.
- Reason: This separates planning, implementation, review, and final git operations.
- Alternatives: Single-agent coding; manual-only workflow.
- Impact: All tasks should pass through `08_IMPLEMENTATION_BRIEF.md`, `09_CODING_HANDOFF.md`, `10_REVIEW_REPORT.md`, and `11_AGENT_STATE.md`.
- Owner: USER

### 2026-05-17: Scope project memory to quant-research-engine

- Decision: The authoritative `docs/agent` system describes only the current `quant-research-engine` directory and not the larger `quant-workspace` program.
- Reason: The user explicitly corrected the focus to this independent backtesting-engine experiment.
- Alternatives: Preserve broader workspace status in QRE docs.
- Impact: Upstream projects such as `quant_ts` and `indicators_tushare` are referenced only as data producers.
- Owner: USER/CODEX

### 2026-05-17: Treat QRE as read-only consumer of upstream data

- Decision: QRE should read market, factor, metadata, benchmark, and reference data. It should not write upstream database state during standard evaluation/backtest flows.
- Reason: Existing docs and code position QRE above `quant_ts` and `indicators_tushare`; indicators are produced upstream.
- Alternatives: Let QRE repair or recompute data.
- Impact: Future QRE tasks should avoid database writes unless explicitly authorized in a brief.
- Owner: CODEX

### 2026-05-17: Do not compute indicators inside QRE

- Decision: Evaluation and portfolio engines must consume declared factor columns from `factors.*` tables instead of recomputing technical indicators.
- Reason: Old docs repeatedly state that `indicators_tushare` owns technical factor generation.
- Alternatives: Add engine-local indicator implementations.
- Impact: New strategies must declare factor inputs; data layer loads them from configured tables.
- Owner: CODEX

### 2026-05-17: Select failed-order diagnostics as next Claude task

- Decision: The next recommended Claude Code task is richer shared-cash failed-order diagnostics, not real index benchmark wiring.
- Reason: Benchmark/index wiring depends on confirming real index table availability and schema. Failed-order diagnostics is self-contained and directly improves portfolio realism.
- Alternatives: Start real index wiring immediately; start evaluation grouping/regime work.
- Impact: `08_IMPLEMENTATION_BRIEF.md` is prepared for failed-order diagnostics. Real index wiring is marked blocked pending data-source confirmation.
- Owner: CODEX, pending USER approval

### 2026-05-19: Select portfolio run-manifest reproducibility as next Claude task

- Decision: The next Claude Code task is a portfolio backtest run manifest for reproducible research runs.
- Reason: Run-level reproducibility is self-contained, does not require new data-source confirmation, and builds directly on the completed report-manifest and audit work.
- Alternatives: Start real index benchmark wiring immediately; start evaluation grouping/regime work.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes a run-manifest workflow for single, batch, and shared backtests. `M5.5` is marked ready for Claude Code.
- Owner: CODEX

### 2026-05-19: Select evaluation metadata group summaries as next Claude task

- Decision: The next Claude Code task is grouped evaluation summaries over existing research-frame metadata columns.
- Reason: This advances roadmap M3.5 without requiring new upstream data-source confirmation, benchmark wiring, or database schema changes.
- Alternatives: Start real index benchmark wiring immediately; start real suspension/ST/risk-warning metadata.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `EvaluationRequest.group_by`, `EvaluationResult.group_summary`, and `qre eval-config --group-by ...`.
- Owner: CODEX

### 2026-05-19: Select eval-config output artifacts as next Claude task

- Decision: The next Claude Code task is durable output artifacts and manifests for `qre eval-config`.
- Reason: Evaluation grouping is complete, but evaluation runs still only print to stdout. Output artifacts are a self-contained reproducibility step and reuse existing report-manifest patterns.
- Alternatives: Start real index benchmark wiring; start real suspension/ST/risk-warning metadata.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `eval-config --output-dir`, `evaluation_report_manifest`, and `evaluation_run_manifest`.
- Owner: CODEX

## Open / To Confirm

- Which real index table should replace temporary stock benchmark wiring: table name, code column values, value column, and available date range.
- Which source table should provide time-varying suspension, ST, and risk-warning metadata.
- Whether legacy root-level progress docs should be archived after the user reviews the migrated `docs/agent` files.
- Whether larger multi-stage research-run bundles should link preflight, evaluation, and backtest artifacts under one run identifier.
