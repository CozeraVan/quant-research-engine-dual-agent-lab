# Agent State

This file is the source of truth for single-agent workflow recovery.

## Current Phase

AWAITING_GIT_APPROVAL

## Current Owner

KIMI_CODE (sole development agent; user is final approver)

## Current Task

QRE-RISK-CORE-001 (DONE — 1532 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R1 落地。新包 `src/quant_research_engine/risk/`
（纯函数 + pandas/numpy/arch/scipy，不读 DB、不依赖 QRE 内部状态，未来
cluster-ashare 独立 import）：tail（VaR/ES 三口径 + 偏度峰度 + JB +
分布摘要）、volatility（EWMA raw + shift(1) forecast + GARCH(1,1) arch
拟合含平稳性/V_L/半衰期 + regime 标记）、dependence（Spearman/Kendall +
正定性 + simple/log 换算）、performance（Sharpe/Treynor/Sortino/IR/Jensen，
Sharpe 与 portfolio/risk.py 同口径）、report（build_risk_report 机读骨架，
R3 再做 markdown 渲染）。公式以 docs/frm/FRM量化风控知识摘要.md 为准；
61 个新测试全为已知答案核对（教材式 1.7 例题 49.79/59.96、EWMA 手算、
GARCH 确定性模拟真值恢复、scipy 双口径对照、秩相关手算 0.5/⅓、绩效
手算值）。未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-GUI-DEEP-VALIDATE-001 (DONE — 1471 tests green；awaiting
git approval)。

2026-08-20: deep-validate 501 骨架落地为真功能。cluster-ashare 新增薄脚本
analysis/pool_from_conditions.py（条件 JSON→逐日池 parquet，DB 全留 cluster
侧，表达式求值复用 QRE evaluate_expression_signal；未走 factor_executor——
其分位/tag 语义与 QRE 布尔 DSL 不匹配）；QRE 新增 gui/deep_validate.py
（spec_to_conditions 纯函数转换器/locate_strategy_yaml/parse_report_summary/
start_deep_validate_job，复用 daily_jobs 基建，lock_key=deep-validate:<name>，
price/eval 缓存键含区间断点续跑）；app.py POST/GET deep-validate 真实现
（404/400×3/500/409 分层，缺因子自动入队）；index.html 沙箱行按钮+通用
入口+10s 轮询不设放弃上限。真实 E2E：mr01a 全历史 → NO-GO（gate3 净超额
-0.130% t=-10.75），报告落 cluster outputs/factor_mining/validation/。
未重启 qre-gui，GUI HTTP 链路待重启验证。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-GUI-PROMO-GATE-001。

2026-08-20: 全量回测结果成为晋升后的状态闸。晋升 mark 加 promotion_gate/
promotion_forced（线程启动前预合并）；engine 收尾新钩子 →
strategy_create.finalize_promotion_gate（写死判据：交易≥30 且超额>0 →
passed）原子写 outputs/refresh/gates/<name>.json（catalog 不动）；refresh_batch
日更跳过 gate=failed 非 forced（日志 + config.gate_skipped），refresh_overview
行加 gate 字段；admin.html 策略状态表加「全量回测闸」四态列（绿/红+tooltip/
灰/橙强制在库）；force 晋升评估照跑不阻止日更（API gate_note 注明）；新增
POST /api/strategies/<name>/deep-validate 501 骨架（策略→信号池转换器待实现）。
未重启 qre-gui，真实 E2E 待重启验证。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-GUI-CREATE-GAPS-001。

2026-08-20: GUI 新增策略/因子闭环四缺口补齐——①策略冒烟 sidecar 闭环
（engine 终态钩子 + mark 预合并消竞态 + list_sandbox 自愈 + 前端三色渲染）；
②晋升冒烟状态闸（promote/promote_factor 加 force，smoke_not_passed → 409）；
③因子冒烟同步改异步（复用 daily_jobs lock_key 机制，POST 返回 job_id +
GET 轮询端点 + 前端轮询）；④删 .p3c-hidden 死代码。未重启 qre-gui，
真实 E2E 待重启验证。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-ADMIN-FACTOR-FRESH-001。

2026-08-19: dashboard 新增「聚类分析」tab（只读展示 cluster-ashare 因子工厂
产出）：gui/cluster_admin.py（QRE_CLUSTER_REPO，分区降级+TTL 300s 缓存），
app.py +/api/admin/cluster 与 /api/admin/cluster/artifact/<path> 下载白名单，
admin.html 第 6 tab 四分区（38 因子注册表/M4 轨迹+traj13 成员/衰减监控
9-23-5/13 个产物链接）。重启 qre-gui 实测全 ok。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-M5C-MINED-FACTOR-STRAT-001。

2026-08-18: 因子工厂 Top3（cluster.mined_factors MF_001/002/003）转译为
cs07a/b/c（catalog/cross_sectional/），截面分位由 cluster-ashare 物化表
cluster.mined_factor_flags 承载（QRE 三段式寻址 cluster schema，零引擎改动）。
闭环：沙箱 3/3 → 冒烟 20 股×半年 3/3 → 晋升 → 全市场 3820 股×近 1 年
（成本/止损 8%/universe 过滤/基准 000300.SH，批次 b21f1008ec98）3/3 ok →
report-audit 6/6 ok。结论：近 1 年未复现 M3b 超额（-11.1/-11.3/-11.6% vs
基准），建议三因子转「衰减观察」（cluster 侧 status 调整待用户确认）。
详见 09_CODING_HANDOFF 顶部。上一任务：QRE-ADMIN-TIMERS-001。

2026-08-12: GUI 首页三 tab → 两 tab（新增策略一页三入口 + 新增因子路径 A/B，fc-create 迁入首页，tab-builder 删除，app.py 零改动）。详见 09_CODING_HANDOFF 顶部。上一任务：QRE-ADMIN-STRAT-INCREMENTAL-FIX-001（策略状态 tab 增量合并）。

2026-08-12: GUI 新因子创建闭环 P2（/api/factor-create/* + indicators sandbox 冒烟 + 晋升 validate→backfill job）。真实 E2E：vidya 因子 DeepSeek 生成 → 冒烟过 → 晋升 job 20260812T030850074330。详见 09_CODING_HANDOFF 顶部。上一任务：QRE-ADMIN-CONSOLE-P3A-001 + QRE-ADMIN-FACTOR-HEALTH-FIX-001 (1264 tests green)。

2026-07-28: admin console read-only slice (dashboard/timers/query) + factor-health fix (managed-table whitelist from indicators config; vortex orphan table demoted to informational). quant_ts upstream fix: normalize_reference_frame numeric coercion (daily_basic text→NUMERIC staging conflict), daily rerun completed, watermark 2026-07-27. Health: green.

Earlier 2026-07-27: GUI workbench P1 (params form/async/precheck/compare) + P1.5 (factor-first wizard + factor-admin panel) + P2 (NL→YAML compiler). Design docs: gui_backtest_workbench.md, gui_factor_first_wizard.md, gui_admin_console.md.

## Pending Decisions (user)

1. GUI acceptance on `http://localhost:8080` (+ `/admin`); NL channel needs QRE_NL_LLM_* env.
2. Optional: drop orphan empty table `factors.stock_daily_vortex_close` (destructive, needs explicit OK).
3. P3b: manual daily-trigger buttons + integration center (refresh registration) + timer log tail; P3c: maintenance tab. qre-refresh.timer install needs sudo (user runs command).
4. TimescaleDB hypertable re-registration project — unscheduled.

Then (user-directed): output-file optimization based on user inspection of `outputs/backtests/full_history_check2/ef8006cb8f4d/` (2 strategies × full market × 2010-2026).

Progress:
1. Verified canonical project `/home/van/quant-workspace/indicators_tushare` and systemd timers (quant-ts 16:30, indicators 16:40, both enabled; yaml-config factors auto-join daily updates).
2. Edits made (indicators repo, no git action): `config/factors.yaml` sma periods += 7/9/26/50/52 + `atrraw` entry; `factors/volatility_factors.py` new `ATRRawFactor` class (raw `atr_{n}` naming; same values as existing `atrr_10`).
3. Project flow: validate (success, 0 failures) → plan (all 7 target columns present; superset: other pending config columns in overlap/volatility categories also covered) → small-sample backfill of 000001.SZ → value parity vs hand-computed SMA/Wilder-ATR within storage rounding, 100% non-null.
4. Full-history backfill (`backfill --categories overlap volatility --execute --max-workers 4`) RUNNING in background.

Next when backfill completes: `factor_request_queue.py recheck` → fulfilled; small-sample re-run of the 5 shelved strategies (R-QRE-009); then user decides on full re-run.

## Standing Instructions (user)

- 2026-07-19: No full-scale backtest runs until the core engine work is mostly complete; after that, full-history (M9.4) runs start with small samples (R-QRE-009). Current slices (M10.1 analysis of existing artifacts) comply — zero backtest execution.

Parent change request: `docs/agent/change_requests/CR-0002-strategy-research-validation.md` (Milestone 9: Strategy Research Validation).

## Last Completed Step

**QRE-ANALYTICS-CONCAT-001 (DONE, finalized 2026-07-19, commit `b72b9af`):** backtest stage 25.852s — M9.1b ≤30s target MET (66.5×).

**QRE-TRAILING-STOP-BATCH-001 (DONE, finalized 2026-07-19, commit `77b8897`):** stop family complete in batch path.

**QRE-MISSING-FACTOR-QUEUE-001 (DONE, finalized 2026-07-19, commit `5c60b8b`):** queue store + shelve semantics + auto-queue + CLI + `docs/handoff.md`; 7 pending requests tracked.

**QRE-PREFLIGHT-MISSING-FACTOR-ROBUSTNESS-001 (DONE, finalized 2026-07-19, commit `6628631`).**

**QRE-BATCH-FULL-VALIDATION-001 / M9.4 pilot (DONE, finalized 2026-07-19, commit `f90567c`):** handoff emitted (7 requests); small-sample full-history pilot OK; ~3h full-scale estimate. Full-scale trigger + upstream factors remain user decisions.

**QRE-CONTINUOUS-REFRESH-001 / M10.3 (DONE, finalized 2026-07-19, commit `1345471`):**

1. `orchestration/refresh.py`: watermark query, RefreshState, rolling window, per-strategy delta computation, delta report writer with manifest.
2. `scripts/refresh_batch.py`: check-only/force/window/codes flags; idempotent vectorized re-run; state + delta persisted.
3. `deploy/qre-refresh.{service,timer}` documented (daily 18:30), NOT installed; README 7b-2 with install commands.
4. Small-sample e2e on real data: first run 106 ok/111; check-only side-effect free; same-watermark no-op; delta manifest audit ok.
5. 1118 tests green (9 new). No full-scale execution (standing instruction honored).

**QRE-STOPS-BATCH-ENGINE-001 / M10.2b (DONE, finalized 2026-07-19, commit `24c284d`):**

1. stop_loss_pct/take_profit_pct honored in both engines: close-based evaluation vs fill price, next-open execution, precedence pending retry > expiry > stop_loss > take_profit > exit_signal; dense candidates in vectorized engine when enabled.
2. Opt-in wiring: `apply_stops` + request overrides (None = spec values); shared mode passthrough incl. trailing_stop_pct; runner `--apply-stops/--stop-loss-pct/--take-profit-pct`.
3. Verification: 50 new tests (40 randomized-with-stops equality seeds); real-DB dual-engine identity (tf01a, mr04a); A/B effect + real stop_loss exit observed; default runs unchanged.
4. 1109 tests green. Trailing stop remains follow-up (shared engine already has it).

**QRE-PARAM-OVERRIDE-001 / M10.2a (DONE, finalized 2026-07-19, commit `a16d6c5`):**

1. `portfolio/universe.py`: metadata loader (stock_suspend/stock_st as-of, daily-derived list_date) + `apply_universe_filter` with complete drop accounting and honest `unavailable_rules`; `validate_profile_overrides`.
2. research_run: `profile_overrides` (dataclasses.replace + validation) and `universe_filter` (opt-in) wired for batch/shared modes; `universe_report.json` backtest artifact; manifest records overrides + flag.
3. Runner flags: `--universe-filter`, `--commission-rate/--min-commission/--stamp-tax/--transfer-fee/--slippage-buy/--slippage-sell`.
4. Small-sample verified: overrides measurably change results; unavailable rules honestly reported on real data; default runs unchanged.
5. 1059 tests green (14 new). Stops split to M10.2b (engine exit logic, dual-engine equality).

**QRE-STRATEGY-FIT-ANALYSIS-001 / M10.1 (DONE, finalized 2026-07-19, commit `d514c4c`):**

1. `analysis/strategy_fit.py`: exact binomial significance tiers (90/99/99.9%), magnitude gate (net + excess vs buy-hold), free-rider accounting, strategy meta-test vs false-positive expectation, hypergeometric enrichment, BH-FDR, deterministic outputs + manifest.
2. `scripts/strategy_fit_report.py` + `strategy_fit_report_manifest` kind registered (report-audit passes); runner `--metadata-columns` passthrough.
3. Metadata reality: `reference.stock_basic` EMPTY upstream — metadata composed from `daily_basic` snapshot + `derive_board`; `industry_group` = unknown (gap documented).
4. Real batch (2024, 106 strategies): **all below 90% meta tier** (significant-stock counts below false-positive expectation — hand-verified true result); 25 stocks at 99% tier recorded as leads in `strategy_fit_stocks.csv`.
5. 1045 tests green (11 new); R-QRE-008 screening-evidence caveat in report.

**QRE-VECTORIZED-ENGINE-001 / M9.1b (DONE, finalized 2026-07-19, commit `c86441b`):**

1. Vectorized trade-level single-symbol engine: event-level loop on candidate bars, one-pass groupby pre-split, vectorized equity reconstruction; `position_sizing` (`full_compound`/`fixed_cash`).
2. Vectorized window/rolling analytics collectors (`risk.py` untouched, used as equality oracle); shared research frame between eval and backtest stages.
3. Equality evidence: 61 synthetic + 40 randomized tests, 106/106 catalog × 50 symbols byte-identical, full-market artifacts identical to simulator baseline.
4. Benchmark: backtest stage 1,718.9s → 40.2s (**42.8×**); quick batch estimate 11.1h → ~25-30 min. Runner `--engine-impl` defaults to `vectorized` (simulator kept as fallback); 1034 tests green.

**QRE-BATCH-PERF-SLIM-001 / M9.1 (DONE, finalized 2026-07-19, commit `24699ce`):**

1. Batch runner core moved into `orchestration/batch_runner.py`; `--jobs N` process-pool parallelism; `--compact` output mode (9 files vs ~26k per strategy, metrics byte-identical).
2. Per-stage timing in research-run manifests; `PostgresDataStore.close()` engine disposal; resume scan fixed (both directory levels).
3. Profiling baseline: tf01a quick mode serial = 1742.5s (backtest stage 98.6%); data-load reuse ruled out by evidence.
4. Quick batch `f365c8a07b33` (2026-07-19 06:32 +08): **106 OK / 5 error** (known missing-factor strategies), wall time **11.1h** with 4 jobs (vs ~51h serial), per-strategy mean 1459s (-16%), **2,013 files / 2.8GB** (~99.9% fewer files, ~89% fewer bytes); `qre report-audit` on compact manifests → ok.
5. Milestone 10 planned (CR-0003): M10.1 strategy-fit clustering, M10.2 parameter overrides, M10.3 continuous refresh, M10.4 optional ML clustering; M9.2/M9.3 merged into M10.1.
6. R-QRE-009 locked (user standing instruction): small-sample validation before any full-scale run.

## Git State

- Current branch: `master`
- Last commit: `b72b9af` Vectorize analytics cross-symbol; backtest stage 25.9s (target met) (6 files)
- Working tree: clean except untracked `.claude/scheduled_tasks.lock` (lock file, intentionally untracked).
- **Run outputs now live outside the repo**: `outputs` → symlink to `/home/van/qre-outputs/` (all 19GB preserved there); `QRE_OUTPUT_DIR` env var overrides the batch runner output root.
- Remote: none configured.

## Latest Validation Evidence

```
uv run pytest tests/ -x -q → 1532 passed, 4 warnings（2026-08-22, QRE-RISK-CORE-001；基线 1471 + 61 净增）
风险包单测 61/61 绿（教材例题/解析解/手算/scipy 对照全覆盖）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1471 passed, 4 warnings (2026-08-20, QRE-GUI-DEEP-VALIDATE-001)
node --check index.html 三段内联 JS → OK
真实 E2E：mr01a 全历史（2015-01-01~2026-08-19）池 2826 信号日/均 3770 只；
四关验证 ~14min → NO-GO（gate1 -0.087% t=-13.12 / gate3 -0.130% t=-10.75 /
gate4 等权 -0.080% t=-18.64）；parse_report_summary 对真实报告逐关解析正确
未重启 qre-gui（用户约束）；未 commit
```

```
uv run pytest tests/ -x -q → 1454 passed, 4 warnings (2026-08-20, QRE-GUI-PROMO-GATE-001)
node --check admin.html 内联 JS → 随 test_gui_admin 通过
未重启 qre-gui（用户约束）；未 commit
```

```
uv run pytest tests/ -x -q → 1437 passed, 4 warnings (2026-08-20, QRE-GUI-CREATE-GAPS-001)
node --check index.html 三段内联 JS → OK
grep .p3c-hidden / TODO-P3c → 全仓零引用（仅剩「断言不存在」测试）
未重启 qre-gui（用户约束）
```

```
uv run pytest tests/ -x -q → 1412 passed, 4 warnings (2026-08-19, QRE-ADMIN-CLUSTER-001)
curl /admin → 200；/api/admin/cluster 四分区全 ok
下载白名单：md/json 200，parquet 404，路径穿越 404
systemctl restart qre-gui.service → active
```

```
uv run pytest -q → 1034 passed, 4 warnings (2026-07-19, M9.1b final)
scripts/check-progress-docs.sh → passed
git diff --check → clean
equality ladder: 61 synthetic + 40 randomized + 106/106 catalog × 50 + full-market artifacts identical
benchmark: backtest stage 1718.9s → 40.2s (42.8×)
```

## Pending Decisions (user)

1. ~~CR-0002/0003 slices~~ — ALL DONE through M10.3 (commits `24699ce`/`c86441b`/`d514c4c`/`a16d6c5`/`24c284d`/`1345471`).
2. **Trigger full-scale full-history batch?** (~3h estimate, `outputs/full_history_pilot/feasibility.md`) — ready when you are.
3. ~~Upstream factor computation~~ — DONE (QRE-UPSTREAM-FACTOR-DELIVERY-001): backfill 5,544 stocks/0 failed; queue 7/7 fulfilled; 5/5 strategies unblocked; daily timer covers new columns from tomorrow. Full 111-strategy re-run (incl. formerly-shelved 5) is now a user decision alongside the full-history trigger.
4. M10.4 ML clustering — needs separate dependency approval (5070 Ti noted).
5. Follow-up micro-slices (optional): groupby-aware signal evaluation; runner-level cross-strategy frame caching (frame load ~17s is now the dominant cost). ~~Preflight UndefinedColumn robustness~~ — DONE. ~~Trailing stop~~ — DONE. ~~Cross-symbol analytics (≤30s)~~ — DONE, target MET at 25.852s.

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
