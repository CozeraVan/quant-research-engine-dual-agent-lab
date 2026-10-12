# Current Status

## Current Stage

Research-validation (M9) and strategy-operations (M10) phases delivered, under single-agent development since 2026-07-18.

The base engine was already feature-complete (see roadmap M1-M8). Since 2026-07-18 the following phases landed (details in `03_ROADMAP.md` and `06_DECISION_LOG.md`):

- **M9 Strategy Research Validation**: parallel compact batch runner (`--jobs`/`--compact`); vectorized trade-level single-symbol engine with metric-identical results (backtest stage 1,718.9s → 25.852s, **66.5×**; `position_sizing` full_compound/fixed_cash); cross-symbol vectorized analytics; shared research frame; quick-mode batch of 106 catalog strategies (2024) completed; full-history pilot (2015-2025) with ~3h full-scale estimate.
- **M10 Strategy Operations**: strategy-fit analysis with significance tiers (binomial 90/99/99.9%, meta-test vs false-positive expectation, enrichment, BH-FDR, free-rider accounting) + v1.1 time stability (`symbol_month_returns.csv` + stability metric); runtime parameter overrides (cost rates) + backtest-time universe filtering; stop_loss/take_profit/trailing_stop in batch engines (dual-engine equality, opt-in `--apply-stops`); continuous refresh machinery (watermark + idempotent re-run + delta report + documented systemd units).
- **Missing-factor lifecycle**: preflight robustness (no crash on missing columns), durable request queue with pending→fulfilled recheck, batch shelve-and-continue semantics, `docs/handoff.md` upstream contract for `indicators_tushare` (7 pending requests).

Current delivery state: **1137 tests green**（注：此处为历史口径；2026-09 后 SaaS 阶段累计 2300+ 测试，以 `uv run pytest` 实测为准）; run outputs externalized to `~/qre-outputs` (repo `outputs` symlink).

## 2026-09 ~ 2026-10 SaaS 内测阶段交付摘要（详见 11/14/15/18/19 号文档）

- **SaaS 网站（aguhuice.com，ECS 47.119.127.40）**：三入口策略创建（自然语言 NL→YAML / 快速向导 / 策略代码）、Authing 手机验证码登录、游客/注册两级权限、回测记录与详情页（收益曲线/磨损/归因热力图/FRM 风险模块/K线重播）、策略库与买卖点信号、意见反馈与因子申请页、后台管理台（9090，SSH 隧道访问）、SEO（百度/Google 已收录）、PWA、移动端适配。
- **Worker 架构**：ECS 只跑 Web/API/任务队列；WSL 本机 worker 轮询取任务、跑 QRE 回测、两阶段（meta/files）回传产物。轻/重槽位分类调度。
- **数据底座（2026-10-11~12 方案A）**：stock_daily 切换原始价口径 + 读取层复权（前复权混合锚点问题根治）；分钟线 stock_minute_1m 全量入库 4313 天（TimescaleDB 压缩）；因子 10 表 + alpha191 全历史重算完成。
- **2026-10-12**：run 级 FRM 风险报告回传修复上线；板块榜单列排序；个股级 FRM + 个股详情按需生成（symbol_detail 任务）上线；NaN 序列化卡死修复。
- **关键纪律**：产出给前端 fetch 的 JSON 必须过 `_json_sanitize`（NaN→None）；表重建必须随迁 GRANT；大批量写入前先 `df -h /`。

## Completed

- Python src-layout package under `src/quant_research_engine`.
- CLI entry point `qre`.
- Market profile loading, including A-share daily default YAML.
- Read-only PostgreSQL data access for daily bars, factors, metadata fallback, calendar, and benchmark-bar skeleton.
- Research-frame assembly from market bars plus declared factor fields.
- Read-only preflight checks for market/factor/join/metadata/universe/liquidity/benchmark availability.
- Safe expression evaluation, forward returns, event summaries, IC, Rank IC, quantile returns, rough friction-adjusted screening, metadata group summaries, deterministic random-baseline comparison, and factor decay summaries.
- Single-symbol, independent batch, and shared-cash portfolio backtests.
- A-share costs, lot sizing, price-limit validation, percent slippage, risk exits, rebalance, FIFO lot accounting, and T+1 sellable inventory in shared-cash simulation.
- Portfolio analytics, benchmark-relative analytics interface, Markdown/CSV/JSON outputs, report manifests, report discovery, and report audit.
- Shared-cash failed-order diagnostics and summary analysis.
- Portfolio backtest run manifests for reproducible output directories.
- Deterministic random-baseline comparison for evaluation output quality.
- Full-market workbook `Performance` sheet parity with `strategy_perf`.
- Real security metadata passthrough adapters for optional upstream status, industry, and membership-style columns.
- Batch backtest metadata group-by passthrough for optional upstream columns.
- Shared-cash metadata output passthrough for requested static metadata columns.
- Shared-cash row-level metadata group summaries for orders, trades, and failed orders.
- Evaluation factor decay summaries from existing IC and Rank IC outputs, including eval-config stdout, CSV artifact, and report-manifest validation.
- Real regime classification and regime summary outputs.
- Benchmark-aware regime source preference (`benchmark_close` / `benchmark_return` precedence when present in-frame).
- Optional run-level identifiers across preflight JSON, evaluation run manifests, and portfolio run manifests.
- Run manifest content validation in report audit, including required-field, kind, type, artifacts, and present-null checks.
- Local browser backtest console (`qre gui`) with YAML strategy editor, run history, rerun support, and artifact viewer.
- Strategy entry authoring standard (`docs/strategy_entry/`): strategy card, factor requirements, missing-factor request, experiment plan, and examples.
- Operational missing-factor handoff: `missing_factor_requests.json` emission, CLI preflight wiring, lifecycle docs.
- High-level strategy entry compiler: `qre compile` with alias-based expression resolution, indicator catalog, and preflight integration.
- Three-strategy entry validation: RSI2, EMA200+Bollinger, MACD entries compile and smoke-tested.
- Smoke runner automation: `qre strategy-smoke` one-command orchestration with deterministic `smoke_summary.json`.
- Smoke manifest/audit integration: `smoke_report_manifest.json` with report discovery/audit parity.
- Smoke discovery CLI: `qre smoke-files` with text/JSON modes, selectors, and 22 status enrichment flags.
- Full-market MT5/TradingView-aligned report bundle: `backtest_report.xlsx` (10 sheets), trades ledger, round trips, symbol/strategy performance, equity/drawdown curves, trade analysis, capital usage.
- Research-run CLI orchestrator: `qre research-run` chains preflight → eval → backtest under one `--run-id` with `research_run_manifest.json`.
- Research-run manifest integration: `research_run_manifest` registered in `_RUN_MANIFEST_KINDS`, with a top-level `report_manifest.json` (kind `research_run_report_manifest`) for whole-run discovery and audit through `qre report-files` / `qre report-audit`.
- Shared-cash full-market report: `engine_mode` parameter on all 6 builders and entry point in `full_market_report.py`; wired into `write_shared_cash_result()` with updated manifest helpers; 19 new tests (6 test classes + 2 integration tests).
- Full-market report charts: equity curve and drawdown chart PNGs generated via matplotlib Agg backend; embedded as new Excel sheets via openpyxl; both batch and shared_cash modes produce charts; 10 new tests.
- Portfolio baseline comparison outputs: single-symbol, batch, CLI, and full-market summary wiring expose buy-and-hold comparison metrics and optional benchmark-relative summary fields.
- Benchmark report-artifact propagation: `strategy_performance.json` now carries the batch benchmark section through to the durable report payload.
- GUI Strategy Builder (M8.6): form-based high-level strategy entry builder with compile-to-spec endpoint, indicator catalog, and run flow integration; 16 new tests.
- HTML backtest report: self-contained HTML report with embedded base64 charts, metric cards, PnL distribution, trade analysis, symbol performance, trades ledger, and round trips; integrated into batch and shared_cash report pipeline with direct tests.
- Research-run stage manifest recursive audit: `validate_contents()` on `research_run_report_manifest` now recursively validates nested eval/backtest stage report manifests via `_validate_nested_report_manifest()`; 7 unit + 4 CLI tests added; full suite at 814 passed.
- Research-run preflight report content audit: `validate_contents()` on `research_run_report_manifest` now validates `preflight_report` JSON content via `_validate_preflight_report()`; checks `status` (non-empty string), `checks` and `missing_factor_requests` (lists if present); 9 unit + 3 CLI tests added; full suite at 826 passed.
- Research-run audit role selector parity: 10 CLI regression tests lock `report-files` / `report-audit` role behavior for root research-run manifests across JSON/text output and `--require-match`; full suite at 836 passed.
- Strategy entry/exit standardization: `strategies/high_level/` and `strategies/low_level/` directories; Bollinger Band mean reversion template strategy; default strategy-smoke and GUI template paths migrated from deleted `examples/`; EMA200 typical source maps to the upstream `typical_price` table; chunked full-market backtest runner now writes `aggregate_summary.json`; README and active docs synced.
- Research-run preflight report shape audit: `_validate_preflight_report()` hardened to validate `status` values (`ok`, `warning`, `error`) and `checks[]` item object shape (`name`, `status`, `message`); new issue codes `invalid_preflight_report_check` and `missing_preflight_report_check_field`; 13 new tests; review PASS.
- Research-run preflight missing-factor shape audit: `_validate_preflight_report()` hardened to validate `missing_factor_requests[]` item object shape (`strategy_id`, `alias`, `indicator`, `expected_table`, `expected_column`, `date_range`, `reason`, `required`); new issue codes `invalid_preflight_report_missing_factor_request` and `missing_preflight_report_missing_factor_field`; 14 new tests; review PASS; full suite at 863 passed.
- Reference-data ingestion ownership migrated to sibling `quant_ts`; QRE reads populated reference tables only.
- Backtest-smoke truthiness reconciliation: `_try_backtest_smoke()` executes real `BatchBacktestEngine` runs; tracker entry moved from IMPLEMENTED to DONE; all agent docs aligned.
- `QRE-NEXT-55` tracker reconciliation: roadmap M4.9 was already DONE; progress row reconciled from IMPLEMENTED to DONE; all agent docs aligned.
- Strategy catalog batch backtest (`QRE-STRATEGY-CATALOG-BATCH-BACKTEST-001`, user-directed): 111 low-level strategy YAMLs across 7 categories under `strategies/catalog/`; `scripts/batch_preflight_check.py` and `scripts/batch_backtest_runner.py` built; expression parser in `signals.py` extended (`&`/`|`, method chaining, arithmetic); `research_run.py` bugs fixed; smoke-mode batch of 106 strategies completed 2026-05-30 (~11.5h, batch `61e67b53b644`): 106 OK / 5 error (missing factor columns `atr_10`, `sma_50`, `sma_9/26/52`, `sma_7/20/65`). Results: mean return -0.79% (2-month smoke window, not a research conclusion). **Uncommitted.**

## In Progress

- `QRE-SINGLE-AGENT-MIGRATION-001`: migration of the workflow documentation from dual-agent to single-agent (Kimi Code) mode.

## Known Gaps

- `reference.stock_basic` is EMPTY upstream (0 rows): industry/industry_group metadata unavailable (`unknown` in fit analysis); board comes from ts_code derivation, cap/liquidity buckets from `daily_basic`. ST status only within `stock_st` coverage; `is_risk_warning` mapped to ST board (documented approximation).
- 5 catalog strategies are shelved on missing factor columns (`atr_10` ×2, `sma_50`, `sma_9/26/52`, `sma_7`); requests queued at `outputs/handoff/missing_factor_requests.json` — upstream `indicators_tushare` computation is a user decision.
- Full-scale full-history batch (106 strategies × full market × 2015-2025, ~3h estimate in `outputs/full_history_pilot/feasibility.md`) is ready but awaits an explicit user trigger.
- 2024 catalog strategies show no strategy-level effectiveness at the 90% meta tier (M10.1 screening evidence); older batches lack `symbol_month_returns.csv` (blank stability until re-run/refresh).
- The GUI console (`qre gui`) is implemented but unused (CLI-first decision); refresh systemd units are documented but not installed.
- M10.4 (ML clustering) and GPU use (RTX 5070 Ti recorded) require separate dependency approvals.

## Current Technical Stack

- Language: Python 3.10+
- Hardware: local PC with NVIDIA RTX 5070 Ti GPU available (2026-07-19 user note). GPU acceleration is NOT used by the current engine; see decision log entry of 2026-07-19 for the assessment (CPU vectorization + process pool suffices for the current roadmap; GPU becomes relevant for future ML-scale work such as M10.4).
- Packaging: `pyproject.toml`, uv
- Database: PostgreSQL through SQLAlchemy and pandas
- CLI: argparse-based `qre`
- Config: YAML
- Test tools: pytest
- Frontend: local Flask browser console
- Deployment: local CLI/research workflows
- Development workflow: single-agent (Kimi Code) with `docs/agent/` as long-term memory

## Current Repository Condition

- Git initialized: yes
- Current branch: `master`
- Remote configured: no remote shown by `git remote -v`
- Recent commits: `ed2b304` (M10.1 v1.1 stability), `b72b9af` (analytics concat, 25.9s), `77b8897` (trailing stop), `5c60b8b` (factor queue), `6628631` (preflight robustness), `f90567c` (M9.4 pilot), `1345471` (M10.3 refresh), `24c284d` (M10.2b stops), `a16d6c5` (M10.2a params), `d514c4c` (M10.1 fit), `c86441b` (M9.1b vectorized engine), `24699ce` (M9.1 batch runner)
- Uncommitted: none (working tree clean except intentionally untracked `.claude/scheduled_tasks.lock`)
- Test command: `uv run pytest -q`
- Progress-doc check: `scripts/check-progress-docs.sh`
- Git finalization check: `scripts/git-finalize-check.sh`
- Last verified full test run: `1137 passed` (2026-07-19)

## Current CLI Surface

- `qre profile`
- `qre db-smoke`
- `qre factor-smoke`
- `qre metadata-smoke`
- `qre benchmark-smoke`
- `qre preflight`
- `qre eval-smoke`
- `qre eval-config`
- `qre compile`
- `qre strategy-smoke`
- `qre smoke-files`
- `qre backtest-single`
- `qre backtest-batch`
- `qre backtest-shared`
- `qre report-files`
- `qre report-audit`
- `qre gui`
- `qre research-run`

## Next Recommended Step

All roadmap slices through M10.1 v1.1 are delivered. Remaining items are user decisions:

1. **Trigger the full-scale full-history batch** (106 strategies × full market × 2015-2025, ~3h estimate, feasibility report in `outputs/full_history_pilot/feasibility.md`) — optionally with `--with-eval` for IC/quantile artifacts.
2. **Commission upstream factor computation** (`indicators_tushare`): 7 queued requests (`atr_10`, `sma_50`, `sma_9/26/52`, `sma_7`); after ingestion, `factor_request_queue.py recheck` marks fulfillment and the 5 shelved strategies can re-run.
3. **Decide on M10.4** (ML clustering phase 2; scikit-learn dependency approval; RTX 5070 Ti available) and on installing the refresh systemd timer.
4. Optional follow-ups: re-run the 2024 quick batch to backfill `symbol_month_returns.csv` stability columns; runner-level cross-strategy frame caching; groupby-aware signal evaluation (further ~10-15s/strategy).
