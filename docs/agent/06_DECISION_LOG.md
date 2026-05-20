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

### 2026-05-19: Select evaluation random-baseline comparison as next Claude task

- Decision: The next Claude Code task is deterministic random-baseline comparison for evaluation output quality.
- Reason: It advances evaluation realism without waiting on a confirmed benchmark table/schema, and it can be scoped without upstream data-source changes.
- Alternatives: Start real index benchmark wiring immediately; start real suspension/ST/risk-warning metadata.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-EVAL-RANDOM-BASELINE-COMPARISON-001` and keeps real index benchmark wiring marked blocked.
- Owner: CODEX, pending USER approval

### 2026-05-20: Select real metadata adapters as next Claude task

- Decision: The next Claude Code task is real status/industry/membership metadata adapters for security metadata loading.
- Reason: This advances data realism without needing benchmark table confirmation and uses the existing read-only metadata merge path.
- Alternatives: Jump straight to real index benchmark wiring; start regime grouping before the metadata source is clarified.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DATA-REAL-METADATA-ADAPTERS-001`. Real index benchmark wiring remains blocked until table/schema confirmation.
- Owner: CODEX

### 2026-05-20: Select batch metadata group-by passthrough as next Claude task

- Decision: The next Claude Code task is to let `backtest-batch --group-by` use optional metadata columns that already flow through the data layer.
- Reason: The previous task preserves upstream metadata columns, but `BatchBacktestEngine` still copies only a fixed metadata whitelist into its summary, so portfolio grouped reports cannot use new columns such as liquidity buckets or membership flags.
- Alternatives: Wire real index benchmark data first; standardize time-varying status tables first.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-PORTFOLIO-BATCH-METADATA-GROUPBY-001`. Real index benchmark wiring and time-varying status tables remain blocked by source confirmation.
- Owner: CODEX

### 2026-05-20: Select shared-cash metadata output passthrough as next Claude task

- Decision: The next Claude Code task is request-driven metadata passthrough for shared-cash order, trade, and failed-order output rows.
- Reason: Batch reports can now group by optional metadata columns, but shared-cash outputs still do not carry requested metadata into row-level artifacts. This is a small prerequisite for later shared-cash attribution without inventing per-symbol shared-cash report semantics.
- Alternatives: Add shared-cash group-by reports immediately; wire real index benchmark data first; implement time-varying suspension/ST/risk-warning metadata first.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-SHARED-CASH-METADATA-OUTPUTS-001`. Shared-cash group attribution remains future work, while real benchmark and time-varying status tasks remain blocked by source confirmation.
- Owner: CODEX

### 2026-05-20: Select shared-cash metadata group summaries as next Claude task

- Decision: The next Claude Code task is grouped shared-cash order, trade, and failed-order summaries over requested metadata columns.
- Reason: Shared-cash row outputs now carry requested metadata safely, so grouped diagnostics can be built without new data-source assumptions or portfolio-math changes.
- Alternatives: Start real index benchmark wiring; implement time-varying suspension/ST/risk-warning metadata; attempt shared-cash return attribution by metadata group.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-SHARED-CASH-METADATA-GROUP-SUMMARY-001`. Return attribution and exposure-level group performance remain future work.
- Owner: CODEX

### 2026-05-20: Select evaluation factor decay summary as next Claude task

- Decision: The next Claude Code task is factor decay summaries for evaluation outputs.
- Reason: Factor decay is a documented evaluation gap, can be computed from existing IC/Rank IC by horizon, and does not require benchmark tables or new data sources.
- Alternatives: Start real index benchmark wiring; implement real regime classification; start time-varying suspension/ST metadata.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-EVAL-FACTOR-DECAY-SUMMARY-001`. Benchmark and real regime work remain blocked by source confirmation.
- Owner: CODEX

## Open / To Confirm

- Which real index table should replace temporary stock benchmark wiring: table name, code column values, value column, and available date range.
- Which source table should provide time-varying suspension, ST, and risk-warning metadata.
- Whether legacy root-level progress docs should be archived after the user reviews the migrated `docs/agent` files.
- Whether larger multi-stage research-run bundles should link preflight, evaluation, and backtest artifacts under one run identifier.
