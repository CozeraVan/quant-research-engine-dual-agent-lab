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

### 2026-05-20: Select run-ID manifest linkage as next Claude task

- Decision: The next Claude Code task is optional `--run-id` metadata for preflight, evaluation, and portfolio durable outputs.
- Reason: This advances multi-stage research-run reproducibility without adding a new orchestrator, data source, or database write path.
- Alternatives: Start real index benchmark wiring; build a full research-run pipeline command; implement real regime classification.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-RUN-ID-MANIFEST-LINKAGE-001`. Larger orchestration remains future work, while benchmark and real regime work remain blocked by source confirmation.
- Owner: CODEX

### 2026-05-20: Select run-manifest content validation as next Claude task

- Decision: The next Claude Code task is stricter `run_manifest` JSON validation through existing report audit tooling.
- Reason: Durable outputs now expose run-level IDs, but `run_manifest` content validation still only checks that the file is a JSON object. A focused validation step improves reproducibility checks without new data dependencies.
- Alternatives: Build a full research-run orchestrator; start real benchmark wiring; implement real regime classification.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-RUN-MANIFEST-CONTENT-VALIDATION-001`. Report manifest file-entry schema should remain unchanged.
- Owner: CODEX

### 2026-05-20: Select run-manifest audit usage docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for optional `--run-id` linkage and run-manifest audit usage.
- Reason: The CLI and audit validation now support run IDs and stricter run-manifest checks, but README/module docs do not yet explain the current workflow.
- Alternatives: Start another validation feature; build a full research-run orchestrator; start real benchmark wiring.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-20: Select evaluation artifact usage docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for evaluation artifacts and diagnostics.
- Reason: Evaluation artifacts, metadata grouping, random baselines, and factor decay are implemented, but README/module docs do not yet clearly explain the current artifact set and report roles.
- Alternatives: Start another reporting validation feature; start real benchmark wiring; build a broader research-run orchestrator.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-EVAL-ARTIFACTS-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-20: Select metadata grouping usage docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for metadata grouping and passthrough usage across evaluation, batch backtest, and shared-cash outputs.
- Reason: Metadata-aware grouping features are implemented, but current docs do not yet show how `--group-by`, `--metadata-columns`, and report-manifest role filters fit together across the CLI surfaces.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; build a larger research-run orchestrator.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-METADATA-GROUPING-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-20: Select evaluation group-by manifest parity as next Claude task

- Decision: The next Claude Code task is evaluation grouped-artifact manifest parity for per-column discovery and `--group-by` filtering.
- Reason: Evaluation outputs currently write a combined `group_summary.csv`, but batch and shared outputs already expose per-group-column manifest metadata that works cleanly with `report-files` and `report-audit --group-by`. Aligning evaluation artifact emission closes that workflow gap without needing new external data sources.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; build a larger research-run orchestrator.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-EVAL-GROUP-BY-MANIFEST-PARITY-001`. Existing `group_summary.csv` compatibility should be preserved while adding per-column grouped artifact entries.
- Owner: CODEX

### 2026-05-20: Select evaluation group-by parity docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for evaluation per-column grouped artifacts and `--group-by` discovery/audit parity.
- Reason: The code now emits `group_summary_by_<col>.csv` files and supports evaluation `report-files` / `report-audit --group-by`, but current docs still describe only the combined evaluation grouped artifact.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger research-run orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-EVAL-GROUP-BY-MANIFEST-PARITY-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-21: Select grouped-artifact group_by audit consistency as next Claude task

- Decision: The next Claude Code task is audit hardening for manifest `group_by` metadata versus grouped CSV contents.
- Reason: Evaluation and shared grouped artifacts now support per-column manifest filtering, but `ReportManifest.validate_contents()` still checks only required columns. A file can claim manifest `group_by=board` while containing mismatched grouped rows and still pass audit.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to larger run-bundle orchestration.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-REPORT-GROUP-BY-CONTENT-CONSISTENCY-001`. The task should stay inside report-manifest validation and targeted CLI/tests without changing manifest schema version.
- Owner: CODEX

### 2026-05-21: Select batch grouped-artifact group_by header consistency as next Claude task

- Decision: The next Claude Code task is audit hardening for batch grouped-artifact manifest `group_by` metadata versus batch CSV header columns.
- Reason: Batch grouped artifacts still pass audit when manifest `group_by=board` points at a CSV whose header uses another column such as `sector`, because current validation checks only required summary/ranking columns. This is now the remaining obvious manifest/content consistency gap on the reporting path.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger run-bundle orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-REPORT-BATCH-GROUP-BY-HEADER-CONSISTENCY-001`. The task should stay inside report-manifest validation and targeted CLI/tests without changing manifest schema version.
- Owner: CODEX

### 2026-05-21: Select rolling window_size filter parity as next Claude task

- Decision: The next Claude Code task is report-manifest and CLI parity for rolling-artifact `window_size` metadata.
- Reason: Batch and shared manifest writers already emit `window_size` on rolling entries, but `ReportFile`, `ReportManifest`, `qre report-files`, and `qre report-audit` still cannot filter or surface that metadata. The gap is self-contained and stays on the reporting/reproducibility path.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger run-bundle orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-REPORT-ROLLING-WINDOW-SIZE-FILTER-PARITY-001`. The task should stay inside report-manifest parsing/filtering, CLI plumbing, and targeted tests without changing manifest schema version or output-generation logic.
- Owner: CODEX

### 2026-05-21: Select rolling window_size usage docs as next Claude task

- Decision: The next Claude Code task is user-facing documentation for rolling-artifact `window_size` report filtering.
- Reason: The CLI and manifest helpers now support `--window-size` and additive `window_size` JSON metadata, but README and portfolio docs still describe report-file optional metadata as only `symbol`, `window`, and `group_by`, and they do not explain when to use `--window-size` instead of `--window`.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger run-bundle orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DOCS-ROLLING-WINDOW-SIZE-FILTER-USAGE-001`. This is documentation-only and should avoid legacy archived docs.
- Owner: CODEX

### 2026-05-21: Select CLI regression coverage for invalid window_size metadata as next Claude task

- Decision: The next Claude Code task is CLI regression coverage for malformed manifest file entries that use invalid `window_size` types.
- Reason: `ReportManifest.from_path()` already rejects string and boolean `window_size` values, but the `report-files` / `report-audit` command boundary is not yet covered in `tests/test_cli.py`. This is the remaining narrow regression gap after the feature and docs landed.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; jump to a larger run-bundle orchestration feature.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-CLI-WINDOW-SIZE-METADATA-TYPE-REGRESSION-001`. The task should stay test-focused and avoid runtime changes unless the current CLI error surface is inconsistent.
- Owner: CODEX

### 2026-05-21: Select CLI strict/JSON parity for window_size filters as next Claude task

- Decision: The next Claude Code task is focused CLI regression coverage for `--window-size` when combined with `--require-match` and `--json`.
- Reason: Basic `--window-size` filter coverage and malformed-metadata boundary coverage already exist, and generic strict/json selector coverage exists for other filters, but the `window_size` selector itself still lacks locked no-match and JSON-path parity at both `report-files` and `report-audit` boundaries.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; widen the task into runtime CLI refactoring.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-CLI-WINDOW-SIZE-STRICT-JSON-PARITY-001`. The task should stay test-focused and avoid runtime changes unless a narrow command-surface bug is exposed.
- Owner: CODEX

### 2026-05-21: Select CLI strict/JSON parity for window_size plus group_by as next Claude task

- Decision: The next Claude Code task is focused CLI regression coverage for `--window-size` when combined with `--group-by`, `--json`, and `--require-match`.
- Reason: Independent `--window-size` and `--group-by` selector coverage already exists, but their intersection is still untested. Locking the combined selector behavior extends the reporting parity without touching runtime code.
- Alternatives: Start real benchmark wiring; start time-varying suspension/ST metadata; widen the task into parser or manifest refactoring.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-CLI-WINDOW-SIZE-GROUP-BY-PARITY-001`. The task should stay test-focused and avoid runtime changes unless a concrete selector bug appears.
- Owner: CODEX

### 2026-05-21: Choose a local browser console as the first GUI form

- Decision: The first GUI release will be a local browser-based console launched by `qre gui`.
- Reason: The existing engine already runs in Python, and a local web console is the simplest cross-platform way to expose strategy editing, run controls, and artifact inspection without building a desktop app.
- Alternatives: Native desktop packaging; a remote web app; keep the workflow CLI-only.
- Impact: The GUI task should use server-rendered pages or similarly lightweight browser UI, and it should stay focused on the existing engine contract rather than adding heavy front-end machinery.
- Owner: USER/CODEX

### 2026-05-21: Make YAML text the first-class strategy editing surface

- Decision: The GUI will treat strategy YAML as the primary input, with inline text editing and file upload/save support.
- Reason: The engine already accepts YAML strategy specs. A form-only builder would duplicate the strategy contract and slow the first release.
- Alternatives: Drag-and-drop strategy composition; form-generated strategies; code editor as the only input.
- Impact: Claude Code should implement validation and save/reopen flows around YAML text, not a separate visual strategy language.
- Owner: USER/CODEX

### 2026-05-21: Keep run history local on disk for v1

- Decision: Version 1 of the GUI will store run history in the local filesystem, not PostgreSQL.
- Reason: The engine already writes durable output directories and report manifests. Keeping history local first reduces implementation risk and keeps the first release cross-platform.
- Alternatives: Write history directly to PostgreSQL; add distributed job storage; keep history ephemeral only.
- Impact: The GUI should persist run requests, strategy snapshots, status, logs, and artifact pointers under the repository outputs directory, with PostgreSQL migration deferred.
- Owner: USER/CODEX

### 2026-05-21: Prefer direct module execution with CLI fallback in the GUI

- Decision: The GUI will call the existing Python backtest modules directly by default and keep the `qre` CLI as a fallback execution path.
- Reason: Direct module execution is faster and easier to inspect during local development, while the CLI fallback preserves a stable escape hatch if the module boundary needs debugging.
- Alternatives: CLI-only orchestration; subprocess-only execution; build a separate job queue first.
- Impact: Claude Code should wire the GUI around the existing engine APIs, but keep a CLI fallback option in the run controls and error handling.
- Owner: USER/CODEX

### 2026-05-21: Select real suspension/ST/risk-warning metadata as next Claude task

- Decision: The next Claude Code task is real suspension/ST/risk-warning metadata for the security metadata loader.
- Reason: `load_security_metadata()` still falls back to static `False` flags when no confirmed upstream table is available. Preflight and portfolio realism already consume these flags, so this is the next data-layer realism gap after the CLI reporting work.
- Alternatives: Jump to benchmark/index wiring; expand into broader regime grouping; invent a schema without confirming the source table.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now describes `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001`. Claude should confirm the upstream table/schema first and write a blocker if no confirmed table exists.
- Owner: CODEX

### 2026-05-21: Use Tushare suspend_d as the first available security-status smoke source

- Decision: The first concrete security-status smoke path should use Tushare `suspend_d`, while `stock_st` and `stk_alert` remain future tasks gated by account permissions.
- Reason: The configured Tushare credential can fetch `stock_basic` and `suspend_d`, but not `stock_st` or `stk_alert`. That lets us validate the downloader shape now without pretending the full metadata set is available.
- Alternatives: Wait for higher permissions on `stock_st`/`stk_alert`; postpone all smoke work until the full upstream table exists.
- Impact: A small read-only smoke utility can be used to validate `suspend_d` samples now. ST and risk-warning remain explicit TODO items, not implicit fallbacks.
- Owner: CODEX

### 2026-05-21: Add a Tushare security-status smoke harness

- Decision: Add a local read-only smoke utility for `stock_basic`, `suspend_d`, `stock_st`, and `stk_alert` so the team can probe source availability before bulk ingestion work.
- Reason: The available Tushare credential can validate `stock_basic` and `suspend_d`, while `stock_st` and `stk_alert` remain permission-blocked. That makes a manual smoke harness the right near-term step.
- Alternatives: Wait for full permissions; start a bulk ingester without source verification; keep the blocker as prose only.
- Impact: `scripts/tushare_security_smoke.py` now exists as a repeatable source-shape probe. It should stay read-only and avoid mutating PostgreSQL.
- Owner: CODEX

### 2026-05-21: Real suspension/ST/risk-warning metadata blocked — no source table

- Decision: Claude Code confirmed no security-status metadata table exists in the local `tushare_data` database. The data layer adapter code is already complete, so this is purely a data-availability blocker.
- Reason: Investigation found only `stock_daily` (market data without status flags) and `stock_holder_number` in the public schema. No `QRE_SECURITY_METADATA_TABLE` env var is configured. The existing adapter code (`_load_security_metadata_table`, `_normalize_security_metadata`) already handles all needed columns and passthrough fields.
- Alternatives: Invent a synthetic status table (rejected — violates "do not invent schemas" constraint); implement time-varying status from `stock_daily` patterns (rejected — no status data exists in that table); mark as blocked and wait for upstream.
- Impact: Task `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001` and roadmap item `M4.9` are blocked. To unblock, provide a table name via `QRE_SECURITY_METADATA_TABLE` with columns: `ts_code` (required), plus any of `list_date`, `board`, `is_st`, `is_risk_warning`, `is_suspended`.
- Owner: CLAUDE_CODE (investigation), CODEX (review and next steps)

### 2026-05-21: Canonical Tushare security snapshot contract completed

- Decision: Accept the reusable Tushare security snapshot contract implementation in `src/quant_research_engine/data/tushare_security.py` and finalize it locally.
- Reason: The source scaffold now provides a canonical snapshot shape, deterministic board inference, passthrough preservation, and read-only probe behavior that aligns with the existing PostgreSQL metadata normalization contract. Validation passed, and no locked requirements were violated.
- Alternatives: Request more changes to the contract helper; merge the snapshot contract into the blocked real-metadata task; leave the work in review despite green validation.
- Impact: `QRE-DATA-TUSHARE-SECURITY-SNAPSHOT-CONTRACT-001` is complete. The next active state returns to the still-blocked real metadata task `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001`.
- Owner: CODEX

### 2026-05-21: Extract a reusable Tushare security source adapter

- Decision: Move Tushare security probing into `src/quant_research_engine/data/tushare_security.py` and keep the smoke script as a thin wrapper.
- Reason: The same read-only Tushare probes will be reused for future bulk ingestion, source-shape checks, and endpoint-specific debugging. Centralizing the calls avoids duplicating endpoint names, fields, and formatting logic across scripts or future loaders.
- Alternatives: Leave the logic only in `scripts/tushare_security_smoke.py`; wire the code directly into the blocked data-layer task; introduce a broader ingestion framework before the source boundary is settled.
- Impact: The smoke path stays read-only, but the source boundary is now reusable for later bulk loading. The blocker on real security-status metadata remains unchanged.
- Owner: CODEX

### 2026-05-21: Keep the Tushare smoke harness as a thin CLI shell

- Decision: The smoke harness should only parse arguments, read the configured Tushare credential from the environment, and print results. It should not own endpoint definitions or frame formatting.
- Reason: The CLI shell is easier to keep stable if all Tushare-specific behavior lives in one importable data module. That also makes the smoke path easier to test without network access.
- Alternatives: Keep endpoint logic inside the script; add a separate command layer before the source adapter exists.
- Impact: `scripts/tushare_security_smoke.py` now delegates to the shared source adapter and remains safe to run in read-only environments.
- Owner: CODEX

### 2026-05-21: Allow strategy-level exit expressions for daily-bar backtests

- Decision: Strategy YAML may now carry `signal.exit`, and the portfolio engines interpret it as a next-bar exit trigger so strategies can model explicit sell rules without lookahead.
- Reason: The EMA200 + Bollinger strategy needs a true upper-band exit rule in addition to risk controls. The existing engines already supported entry expressions and stop controls, but not a strategy-scoped exit signal.
- Alternatives: Encode upper-band exits as a fixed-holding workaround; add an ad hoc CLI-only override; leave exits to stop controls alone.
- Impact: `StrategySpec`, single-symbol backtests, batch backtests, and shared-cash backtests all accept the exit expression; the user-requested EMA200 + Bollinger backtest now runs end-to-end on the existing data model.
- Validation: `uv run pytest tests/test_strategy_spec.py tests/test_portfolio_single_symbol.py tests/test_portfolio_shared.py -q` → 46 passed in 1.01s; chunked full-market backtest over `2010-01-04` to `2026-05-20` completed across 5,522 symbols.
- Owner: CODEX

## Open / To Confirm

- Which real index table should replace temporary stock benchmark wiring: table name, code column values, value column, and available date range.
- Which source table should provide time-varying suspension, ST, and risk-warning metadata.
- Whether legacy root-level progress docs should be archived after the user reviews the migrated `docs/agent` files.
- Whether larger multi-stage research-run bundles should link preflight, evaluation, and backtest artifacts under one run identifier.

### 2026-05-21: Define QRE as the strategy IO contract and reporting engine

- Decision: QRE should standardize strategy entry, factor availability validation, backtest execution, and full-market report outputs. It should not rewrite external strategy repositories or compute indicators internally.
- Reason: The long-term workflow spans multiple projects. `research-notes` / `strategy-research` own strategy knowledge, `indicators_tushare` owns technical indicator calculation and period expansion, and QRE owns the executable contract between strategy ideas, factor availability, backtests, and reports.
- Alternatives: Put all classic strategy definitions directly into QRE; make the GUI own strategy semantics; let users continue hand-writing low-level `factors.table.column` YAML. These were rejected because they would make strategy expansion slower and keep the current YAML/debug bottleneck.
- Impact: `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md` defines the first strategy IO contract. Entry strategy work is documentation-first, and future implementation should compile that standard into current QRE backtest tasks.
- Owner: USER/CODEX

### 2026-05-21: Use MT5 plus TradingView as the full-market QRE report baseline

- Decision: QRE report output should combine the provided MT5 workbook and TradingView strategy tester screenshots, then add A-share research fields. Reports should be full-market artifacts with `symbol` columns, not one report per stock.
- Reason: QRE normally backtests thousands of A-share symbols in one run. MT5 contributes detailed transaction/result-accounting structure, while TradingView contributes benchmark comparison, risk-adjusted metrics, trade analysis, capital usage, run-up, and drawdown sections. A unified transaction ledger, round-trip table, symbol performance table, strategy summary, equity curve, and manifest are better suited to later GUI display, ranking, clustering, and group analysis.
- Alternatives: Keep only current engineering artifacts; generate one report per symbol; build visual reports before stabilizing the file contract. These were rejected because they do not support broad research comparison cleanly.
- Impact: Task `QRE-REPORT-MT5-TV-FULL-MARKET-001` should produce `backtest_report.xlsx`, `trades_ledger.csv`, `round_trips.csv`, `symbol_performance.csv`, `strategy_performance.json`, `equity_curve.csv`, `drawdown_curve.csv`, `trade_analysis.json`, `capital_usage.json`, and manifest roles for report discovery/audit.
- Owner: USER/CODEX

### 2026-05-21: Send full-market report bundle implementation to Claude Code

- Decision: The next Claude Code implementation task is `QRE-REPORT-MT5-TV-FULL-MARKET-001`.
- Reason: The user approved moving from brainstorm/design into normal dual-agent workflow for the report-output contract. This is the highest-value QRE engine improvement before returning to strategy-entry standardization because it defines the final research-facing output of a backtest.
- Alternatives: Start the strategy-entry compiler first; continue only documenting strategy-entry rules; implement GUI form controls first. These remain future work because a stable report output contract is needed for GUI display and downstream research comparison.
- Impact: `08_IMPLEMENTATION_BRIEF.md`, `11_AGENT_STATE.md`, and `12_AGENT_BOARD.md` now route implementation to Claude Code. Codex will review after Claude writes `09_CODING_HANDOFF.md`.
- Owner: CODEX

### 2026-05-21: Start strategy-entry contract docs implementation as the next slice

- Decision: The next active task is `QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001`, assigned to Claude Code.
- Reason: Full-market report output has been finalized locally. The next bottleneck identified by the user is strategy authoring complexity and non-standard entry structure. Documentation-first standardization is the fastest low-risk step before runtime compiler work.
- Alternatives: Start compiler/preflight runtime changes immediately; start GUI parameter expansion first. These were deferred because authoring contract docs must be stable first.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now defines a docs-focused deliverable under `docs/strategy_entry/` with examples and missing-factor request schema; `11_AGENT_STATE.md` and `12_AGENT_BOARD.md` route execution to Claude Code.
- Owner: CODEX

### 2026-05-21: Finalize strategy-entry contract docs before compiler work

- Decision: Accept and finalize `QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001` as complete after review pass.
- Reason: The delivered docs provide the required authoring contract modules and three strategy-family examples while preserving project boundaries. This reduces strategy writing/debug churn before runtime compiler changes.
- Alternatives: Keep docs task open and mix in compiler implementation immediately. Rejected to avoid coupling documentation baseline with runtime behavior changes.
- Impact: `docs/strategy_entry/` becomes the baseline contract for follow-up tasks, and next slice should focus on operational missing-factor handoff and compiler/preflight linkage.
- Owner: CODEX

### 2026-05-21: Start operational missing-factor handoff standardization

- Decision: Activate `QRE-FACTOR-MISSING-HANDOFF-STANDARD-001` as the next implementation slice.
- Reason: Strategy-entry docs are complete; the next practical bottleneck is converting missing-factor definitions into stable, durable, machine-readable handoff artifacts and lifecycle steps.
- Alternatives: Jump directly to compiler runtime work; start GUI controls first. Deferred to avoid coupling multiple moving parts before request workflow is stable.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now scopes artifact emission (`missing_factor_requests.json`), lifecycle semantics (`pending/fulfilled/blocked`), and targeted tests; execution routed to Claude Code.
- Owner: CODEX

### 2026-05-21: Finalize missing-factor handoff standard before compiler linkage

- Decision: Accept and finalize `QRE-FACTOR-MISSING-HANDOFF-STANDARD-001` after review pass.
- Reason: The implementation delivers durable missing-factor request output, deterministic empty-case behavior, CLI status reporting, and regression coverage without widening into compiler/runtime scope.
- Alternatives: Start compiler linkage in the same slice. Rejected to keep the handoff contract stable and independently verifiable first.
- Impact: `missing_factor_requests.json` output is now operational baseline; next slice should focus on compiler/preflight linkage from high-level strategy entry format to current executable spec.
- Owner: CODEX

### 2026-05-21: Start high-level strategy entry compiler/preflight linkage

- Decision: Activate `QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001` as the next implementation slice.
- Reason: Strategy-entry docs and missing-factor handoff are now both stable; the next bottleneck is executable linkage from high-level entry format into current preflight/runtime-compatible low-level spec.
- Alternatives: Expand GUI parameters first; jump to advanced runtime compiler. Deferred to keep the linkage layer small, testable, and backward-compatible.
- Impact: `08_IMPLEMENTATION_BRIEF.md` now scopes parser/linkage/CLI/test work while preserving existing low-level workflow and report behavior.
- Owner: CODEX

### 2026-05-22: Finalize high-level entry compiler/preflight linkage after runtime fix

- Decision: Accept and finalize `QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001` after the alias-expression runtime compatibility fix.
- Reason: The blocking incompatibility between compiler-emitted expressions and the existing signal evaluator was resolved, and end-to-end compatibility tests now validate the compile-to-runtime path.
- Alternatives: Keep task open for additional crossover/runtime enhancements. Deferred to keep this slice focused on baseline linkage correctness.
- Impact: High-level strategy entries now have a runnable bridge into current preflight/runtime-compatible low-level `StrategySpec` flow via `qre compile`.
- Owner: CODEX
