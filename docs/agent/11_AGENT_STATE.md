# Agent State

This file is the source of truth for single-agent workflow recovery.

## Current Phase

AWAITING_GIT_APPROVAL

## Current Owner

KIMI_CODE (sole development agent; user is final approver)

## Current Task

QRE-DERIV-ADAPTER-013 (DONE — 1795 tests green + 4 skipped；awaiting git approval)

2026-08-23: 衍生品数据适配层落地（CR_2026-08-23_derivatives_market_data
D1.5/D2.2/D3.2，CR §11 追加「适配层落地」）。新 data/derivatives.py
（只读：load_zero_curve 连续复利近似+最近日回填、load_cb_terms/
cb_cashflows/cb_bond_floor 债底示例、load_option_chain 平值隐波断言；
库内无 ETF 日线为已知缺口，标的价缺失时传 underlying_price，示例用
put-call parity 反推披露）+ scripts/derivatives_adapter_smoke.py +
tests/test_data_derivatives.py（纯函数 11 + DB 冒烟 4 无库 skip）。
冒烟 2026-08-21：曲线 8 节点 1.164%–2.110%；5 只转债债底 99.14–101.74
vs bond_value 105.4–111.2（赎回溢价差异可解释）；50ETF 平值 IV 13.67%。
1795 tests green + 4 skipped（基线 1784 + 11 净增）。未 commit、
未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-GUI-DERIV-CARD-012 (DONE — 1784 tests green；见 05/09)

2026-08-23: 风向标 M3 落地（CR 状态改「✅ M1–M3 已完成」）。
deploy/hardened/qre-barometer.{service,timer}（Mon..Fri 18:30、Persistent、
默认最近交易日，未 sudo）；barometer_job latest_trade_date 默认日期 +
`qre barometer` CLI；admin TIMER_UNITS/PIPELINES 登记；/admin 新「大盘
风险」tab（gui/market_risk.py 只读 market_risk.daily + 仪表盘/五序列
SVG/双口径热力表/预警详情，复用现有样式）；阈值首轮校准观察入 06
（red 11/1850=0.59% 全为已知风险事件，初值保留）。真库冒烟 ok。
1778 tests green（+14）。未 commit、未重启 qre-gui、未装 timer。
详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-BAROMETER-M2-009 (DONE — 1764 tests green；commit b0713d7)

2026-08-23: 大盘/板块风险风向标 M2 落地（CR_2026-08-23_market_risk_barometer
§5 M2 阶段；M1 = commit 64addd7）。新 risk/barometer_job.py（risk 包唯一
读写 DB 层：pct_chg/100 收益 + total_mv 市值 + industry 行业 +
daily_tags 当日簇 <5 跳过 → M1 纯函数 → 独立 schema market_risk.daily
表（PK (trade_date,scope)、ON CONFLICT 幂等 upsert）+ JSON 产物
outputs/market_risk/<date>.json；年分块 + 312 交易日 buffer）。真实回填
2019-01-02→2026-08-20：220,034 行 / 1,850 日 × 120 scope，~21min。
方向性验证全过：2020-02-03 red（突破 85.2% P100）、2024-02 微盘连续
red（总分 P99–100）、常态 green；全样本 red 11 天均为已知风险事件。
1764 tests green（+10）。未 commit、未重启 qre-gui。详见
09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-BAROMETER-M1-008 (DONE — 1754 tests green；commit 64addd7)

2026-08-23: 大盘/板块风险风向标 M1 落地（CR_2026-08-23_market_risk_barometer
§5 M1 阶段）。risk 包新增 cross_section.py（纯函数零 DB、向量化：EWMA
方差面板与 volatility 单列口径 atol 1e-15 一致、截面波动率中位/90 分位、
等权/市值加权离散度、滚动 60 日平均两两相关等权 + w_i·w_j 偶权近似、
VaR 突破计数/占比、summary 一把梭 σ shift(1) 防前视）与 barometer.py
（组合法 100% 复用 volatility/tail、252 日滚动分位分数 warmup 降级
None、红/黄/绿双判据预警、build_barometer 全市场+板块统一 dict、分组
映射调用方传入）；constants.py 加 BAROMETER_CORR_WINDOW=60/
SCORE_WINDOW=252/ALERT_CORR_LOOKBACK=20/ALERT_CORR_JUMP=0.10/
ALERT_BREACH_RATIO_MAX=0.03/BREACH_CONFIDENCE=0.99/
CROSS_SECTION_SIGMA_QUANTILE=0.90 全回显（阈值初值待 M3 校准）。
1754 tests green（+30：cross_section 17 + barometer 13）。全量首跑
test_gui_risk_report.py::test_post_conflict_409 flake，复跑全绿。
未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-PORTFOLIO-007 (DONE — 1724 tests green；awaiting git approval)

2026-08-23: FRM 风险模块 R7 落地（CR_2026-08-23_risk_derivatives_extension
R7 阶段，CR 状态改「R5–R7 已完成」；R5=5472832、R6 待审批）。新
risk/portfolio.py（纯函数零 DB，summarize_mixed_portfolio：股票腿沿用
R1–R4 收益序列法、债券/转债腿 DV01 可加 + D/C 市值加权 + 可选 KR01 按
节点加总、期权腿组合 Greeks 加权求和、config 显式给 dgv.spot_shock_sd
才计算 DGV-VaR；仅股票退化为仅 equity 节）；risk/report.py 显式传入
bond_positions/option_positions/bond_kr01 才追加 portfolio 节 +
markdown「组合与衍生品风险」渲染；GUI run_detail 有节才追加「衍生品风险
（组合层）」卡片（_risk_display + risk-card 模式）；constants.py 加
GATE_DV01_MAX/GATE_GREEKS_MAX（默认 None=不启用），evaluate_gate_risk
启用时追加组合 DV01/Greeks 限额判据、默认关闭时返回与 R4 逐键一致。
1724 tests green（+28：portfolio 14 + report 7 + gui 7）。默认 run 产物
零变化，老格式 report 向后兼容专项测试覆盖。未 commit、未重启 qre-gui。
详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-OPTIONS-006 (DONE — 1696 tests green；awaiting git approval)

2026-08-23: FRM 风险模块 R6 落地（CR_2026-08-23_risk_derivatives_extension
R6 阶段；R5=5472832）。risk 包新增 options.py（BSM 式 15.6–15.9 无股息/
q/离散股息 S₀−D、Black's 式 15.12/15.13、隐波 brentq IV_BRACKET、CRR
式 14.4–14.7 欧式+美式含 q + 第一层 delta + 可选全节点网格、美式 Greeks
数值差分（书4 Ch16）、Greeks 解析全组 Table 16.2 含 q 版与期货期权版
rho=−f·T、组合 Greeks 加权）与 derivatives_var.py（DGV 近似 P&L
式 2.3+vega 项、非中心卡方累积量解析矩、正态/Cornish-Fisher 分位 VaR、
VaR 序列对接 backtest_var_summary 复用 HIT/LR）；constants.py 加
IV_BRACKET/DEFAULT_TREE_STEPS=50/GREEK_SHOCK_*（全部 dict 回显）。
教材数值全复现：BSM 例 c=8.3069/p=7.9715+parity、隐波 7.00→25.14%、
美式 put 节点 3.058/0.494/5.699（欧式 2.838，参数 S=29,K=30,r=3%,σ=25%,
T=1 经教材原文 p193 核对）、收敛 3.082/3.067/3.059/3.055、PDE 恒等式
1e-10、纯 gamma 解析二阶矩、CF-VaR 对 MC rel 5%、VaR 序列回测违约率
≈1% 不拒绝。自审修正 Black76 theta 符号（有限差分自检发现）。
纯函数零 DB 零行情，既有 risk 模块零行为改动。1696 tests green（+39）。
未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-RATES-005 (DONE — 1657 tests green；awaiting git approval)

2026-08-23: FRM 风险模块 R5 落地（CR_2026-08-23_risk_derivatives_extension
R5 阶段；R1=96db59d / R2=f52c0f4 / R3=6852eaa，R4 待审批）。risk 包新增
rates.py（式 16.1–16.5 复利换算、PV/FV、spot↔折现因子、书4 Ch9 附息债
bootstrap 零息曲线、线性/对数线性插值、远期利率、par yield 式 16.7/10.4）
与 bonds.py（YTM brentq、actual/actual+30/360 应计利息、式 12.6 久期凸性、
effective duration/convexity、DV01 与 D↔DV01、组合聚合与对冲配比、
式 12.4 二阶近似、书4 Ch13 KR01（ΣKR01=DV01 自检）、书3 Ch16/17 转债
债底+spread duration）；constants.py 加 DEFAULT_DAY_COUNT/
CURVE_INTERPOLATION/KEY_RATE_TENORS/RATE_SHOCK_BP/YTM_BRACKET（全部
结果 dict 回显）；pyproject.toml 补 scipy 显式依赖。教材数值全复现：
bootstrap d=0.991909/0.980944/0.969406/0.956909、par yield 2.2103%、
年金解析解 P/D/C、ΣKR01=DV01、+100bp 二阶近似 rel 偏差 1.9e-5。
纯函数零 DB 零行情，既有 risk 模块零行为改动。1657 tests green（+52）。
未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-GATE-004 (DONE — 1605 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R4 落地（R1=96db59d / R2=f52c0f4 / R3=6852eaa）。
晋升全量回测闸加入风险判据：risk/constants.py 加 GATE_ES99_MAX=0.03 /
GATE_VAR_CONFIDENCE=0.99；gui/risk_report.py 加 evaluate_gate_risk（读
runs/<run_id>/risk_report.json，ES99 超阈或 99% 覆盖率 Kupiec LR 拒绝 →
risk=warning，缺失 → unavailable 不阻断）；finalize_promotion_gate 写
gate json risk 节（主判据照旧）；gate_blocks_daily 扩展 failed 或
risk=warning 非 forced 即阻止日更（force 照评估不阻断）；admin.html
闸列 warning 追加「⚠ 风险警示」徽标（tooltip ES99 + VaR 回测结论）
+ style.css .gate-risk。存量 gate json 无 risk 节行为不变。1605 tests
green（+6）。未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-INTEGRATION-003 (DONE — 1599 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R3 落地（R1=96db59d / R2=f52c0f4）。risk 包集成进
回测报告与 GUI：risk/report.py + render_risk_markdown（汉化风险分析节，
两位小数，分布与尾部/VaR回测/波动率/压力/绩效分区，error 降级）；
新 gui/risk_report.py（组合级 equity_curve.csv daily_return 提取 +
benchmark_close 可选 + finalize 钩子写 runs/<run_id>/risk_report.json +
幂等追加 summary.md 风险节 + daily_jobs 按需 job bootstrap 开）；
engine.py:354-361 收尾钩子（try/except 兜底同 smoke/promotion_gate）；
app.py run_detail risk 视图 + POST/GET risk-report 端点（404/400/409）；
run_detail.html 风险分析六卡片 + 老 run 按需生成按钮。#4 admin badge
未加（refresh_overview 无 risk_report，硬塞超范围）。真实 E2E：mr01a
5 股×2024-2025，n=484，99% VaR 1.50%/1.79%、ES 1.72%/2.19%，JB
p<0.0001，VaR 回测两级均不拒绝，summary.md 风险节落盘。未 commit、
未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-CORE-002 (DONE — 1578 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R2 落地（R1 = commit 96db59d）。risk 包新增
backtest_var（书2 Ch6：HIT、覆盖率 Bernoulli LR + 精确二项、独立性
Christoffersen 转移矩阵 LR——摘要未点名 Kupiec/Christoffersen 如实标注、
多重检验假阳性 1−(1−α)ⁿ）、stress（书4 Ch8：A 股四情景库、回放累计损失/
峰谷/Peak/VaR + 相关性崩溃提示、reverse stress β 穿透反查市场冲击分位/
σ 倍数）、inference（书2 Ch13：arch CBB 块长 √n 给年化收益/夏普/最大
回撤 CI + iid 对照 + MC 标准误 σ/√b）；report.py 升 R2（var_backtest
默认开用 EWMA μ=0 VaR 防前视，stress/bootstrap config 可选开启）。
46 个新测试全为已知答案核对（LR 手算 4.13085、转移计数手算、回放
−0.119179/0.05/2.5、reverse β=2、bootstrap 固定 seed CI 含真值 +
AR(1) 下 iid 低估 CBB）。未 commit、未重启 qre-gui。详见
09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-CORE-001 (DONE — 1532 tests green；commit 96db59d)。

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
- Last commit: `96db59d` feat(risk): FRM 风险模块 R1 核心包（R2+R3 未 commit，工作树含两者改动）
- Working tree: R2/R3 改动 + untracked `.claude/scheduled_tasks.lock` (lock file, intentionally untracked)。
- **Run outputs now live outside the repo**: `outputs` → symlink to `/home/van/qre-outputs/` (all 19GB preserved there); `QRE_OUTPUT_DIR` env var overrides the batch runner output root.
- Remote: none configured.

## Latest Validation Evidence

```
uv run pytest -q → 1795 passed, 4 skipped, 4 warnings（2026-08-23, QRE-DERIV-ADAPTER-013；基线 1784 + 11 净增）
带库：QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data pytest tests/test_data_derivatives.py → 15 passed
真实冒烟：scripts/derivatives_adapter_smoke.py 2026-08-21 → 曲线 8 节点 1.164%–2.110%；
  转债债底 5 只 99.14–101.74 vs bond_value 105.4–111.2（赎回溢价差异可解释）；
  50ETF 平值 K=3.0 call/put IV 13.67%（parity 标的 2.9931）
基线首跑 test_gui_admin_p3b.py::test_daily_job_lock_per_pipeline 失败，单独复跑绿（已知 flake 家族）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1778 passed, 4 warnings（2026-08-23, QRE-RISK-BAROMETER-M3-010；基线 1764 + 14 净增）
真实冒烟：market_risk_overview() 真库 ok（2026-08-20 总分 63.3 green，252 日序列，105 行业，14 簇）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1764 passed, 4 warnings（2026-08-23, QRE-RISK-BAROMETER-M2-009；基线 1754 + 10 净增）
真实回填：2019-01-02→2026-08-20，8 年块，220,034 行 / 1,850 交易日 × 120 scope，~21min
方向性验证：2020-02-03 red（breach 85.2% P100）、2024-02-05 red（score 99.4 P100）、常态 2023-06 green（P10–21）；red 11 天全为已知风险事件
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1754 passed, 4 warnings（2026-08-23, QRE-RISK-BAROMETER-M1-008；基线 1724 + 30 净增）
风险新单测 30/30 绿（cross_section 17：面板对单列一致/相关==np.corrcoef/离散度手算/突破计数；barometer 13：组合法对 tail+volatility 逐键一致/预警三态/warmup 降级/等权 vs 市值加权差异）
scripts/check-progress-docs.sh → passed
git diff --check → clean
注：全量首跑 test_gui_risk_report.py::test_post_conflict_409 失败，单独与全量复跑均绿（环境敏感 flake）
```

```
uv run pytest tests/ -x -q → 1724 passed, 4 warnings（2026-08-23, QRE-RISK-PORTFOLIO-007；基线 1696 + 28 净增）
风险新单测 28/28 绿（组合层退化/混合合并/KR01 加总/DGV 开关 + report 节开关与渲染两态 + GUI 卡片两态 + 闸默认关闭逐键一致与启用判据）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1696 passed, 4 warnings（2026-08-23, QRE-RISK-OPTIONS-006；基线 1657 + 39 净增）
风险新单测 39/39 绿（BSM/隐波/二叉树收敛/PDE/Black76/美式 Greeks/DGV 解析矩/CF/MC/回测集成全教材数值核对）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1657 passed, 4 warnings（2026-08-23, QRE-RISK-RATES-005；基线 1605 + 52 净增）
风险新单测 52/52 绿（bootstrap/par yield/年金解析解/DV01/KR01/情景/债底全教材数值核对）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1599 passed, 4 warnings（2026-08-22, QRE-RISK-INTEGRATION-003；基线 1578 + 21 净增）
scripts/check-progress-docs.sh → passed
git diff --check → clean
真实 E2E：run 20260822T114522831346（mr01a 5股×2024-2025）→ risk_report.json + summary.md 风险节
注：首跑 test_gui_factor_wizard.py::test_job_lock_conflict 失败，全量复跑 1599 全绿（已知 flake）
```

```
uv run pytest tests/ -x -q → 1578 passed, 4 warnings（2026-08-22, QRE-RISK-CORE-002；基线 1532 + 46 净增）
风险包单测 107/107 绿（R2 46 新：LR/转移计数/情景回放/reverse/bootstrap 全手算核对）
scripts/check-progress-docs.sh → passed
git diff --check → clean
注：基线首跑 test_gui_factor_wizard.py::test_job_lock_conflict 失败，单独+全量复跑均绿（环境敏感 flake，非本任务引入）
```

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
