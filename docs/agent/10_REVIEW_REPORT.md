# Review Report

## Task ID

QRE-GUI-LAB-PORT-017（回测台新端口移植：新增策略 + 回测管理两页面 → 独立 Flask 应用 @8081）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **8080 零行为变化（机械核对）**：新 create_app 的 url_map（rule+methods）
  与 git HEAD 版本逐条相等（59/59）；被搬走路由的函数体逐字不变，仅从
  create_app 闭包迁入 `strategy_lab_routes.register_strategy_lab_routes`，
  create_app 尾部调用同一函数。Flask endpoint 名随函数 __name__ 不变。
- **既有测试锚点兼容**：test_gui_strategy_create.py 把 monkeypatch 打在
  `gui.app.try_acquire_run_slot/release_run_slot/run_backtest`——app.py
  保持三符号 re-export，共享模块经 gui.app 命名空间调用时解析，
  该测试文件零改动通过（重构后首轮全量曾因此 14 errors，已修复复跑全绿）。
- **lab.html 原样性**：两个 tab 的 HTML/JS 由脚本按行号从 index.html /
  admin.html 精确切片组装（非手抄），含 QRE-GUI-SORT-016 排序 JS、
  搜索框、toggle/删除、gate/风险徽标；helpers（esc/fetchWithTimeout/
  cardError/isAbort）随 onboard JS 一并移植；两个 <script> 均为独立
  IIFE，无 DOM id 冲突。
- **范围裁切**：lab 不挂 /admin、/api/admin/overview、factor-create/*、
  builder/* 等 8080 专有路由（测试断言 lab⊂create_app 且专有规律互斥）；
  /runs、/runs/<id> 及 run artifact/risk-report API 一并在共享集内，
  保证新增策略 tab 的冒烟/回测/深度验证链接在 8081 可用。
- **运维**：qre-gui-lab.service enabled/active，与 qre-gui 并存互不干扰；
  base.html 顶栏「管理台 Admin」链接在 8081 上 404（指向 8080 功能，
  已知留白，待用户对齐优化方向时处理）。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1807 passed, 4 skipped, 4 warnings（基线 1795 + 12 净增）
路由集合核对：create_app() vs git HEAD → equal: True（59/59）
冒烟（两个 service 均重启后）：
  curl 8081 / → 含「新增策略」「回测管理」、data-tab strategy/onboard
  curl 8081 /api/admin/refresh → ok True, registered 0/118, stopped 118
  curl 8080 /api/admin/refresh → 同上（一致）
  curl 8081 /admin/strategy/bo01a_donchian_20_breakout → 200（8080 同 200）
  curl 8080 / → 200；curl 8080 /admin → 200
  curl 8081 /api/strategies/sandbox → ok true
systemctl is-enabled qre-gui-lab → enabled；is-active → active
```

## Required Fixes

无。

## Nice-to-Have

- lab 顶栏导航与 8080 的互链口径、页面标题/样式对齐等，留待用户明天
  对齐优化方向后处理（本任务明确只做移植）。

---

# Review Report (archive: QRE-DERIV-ADAPTER-013)

## Task ID

QRE-DERIV-ADAPTER-013（衍生品数据适配层：yc_curve/cb/opt 三个只读 loader + 示例管道）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §6 D1.5/D2.2/D3.2 行一一对应**：三个 loader + 示例管道 +
  单测；内核函数签名零改动，data/derivatives.py 是唯一直接读
  derivatives schema 的新代码（QRE 只读，无任何写库语句）。
- **口径披露齐全**：连续复利转换近似（yield%÷100 视为年复利）、8 节点
  插值近似、最近日回填 + latest_curve_date 披露、转债现金流四近似
  （常数票息/网格取整/面值到期/利差假设）、T=actual/365、parity 反推
  标的价——均写入 docstring、示例输出与 CR §11。
- **已知边界**：①库内无 ETF 日线（510050.SH 不在 stock_daily/
  index_daily），load_option_chain 标的价缺失时明确抛错引导传
  underlying_price，示例用 parity 反推（欧式近似）——缺口补数列后续；
  ②转债债底 vs bond_value 系统性差 −5.6~−9.5，主因到期赎回溢价
  106–115 未含（cb_basic 无赎回价字段），差异可解释，CR 验收本就
  「不求一致」；③平值隐波 call=put 同值（13.67%）是 settle 口径下
  parity 自洽的结果，非 bug。
- **测试纪律**：纯函数 11 个真单测；DB 冒烟 4 个按 QRE_MARKET_DB_URL
  skip（与仓库「单测不依赖真实库」惯例一致）；带库 15/15 绿。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1795 passed, 4 skipped, 4 warnings（基线 1784 + 11 净增）
带库：QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data
  pytest tests/test_data_derivatives.py -q → 15 passed
冒烟：scripts/derivatives_adapter_smoke.py 2026-08-21 → 曲线 8 节点
  1.164%–2.110%；债底 5 只全正、spread_duration 1.00–1.98；
  50ETF 平值 K=3.0 call/put IV 13.67%（断言通过）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

## Nice-to-Have

- fund_daily（ETF 日线）入库后可去掉 parity 反推旁路；
- cb_coupon 精确票息与到期赎回价字段接入可收窄债底差异；均不阻塞本 CR。

---

# Review Report (archive: QRE-RISK-BAROMETER-M3-010)

## Task ID

QRE-RISK-BAROMETER-M3-010（大盘/板块风险风向标 M3：日更 timer + GUI 风向标页 + 阈值校准观察）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §5 M3 行一一对应**：deploy/hardened/qre-barometer.{service,
  timer}（Mon..Fri 18:30、Persistent、oneshot、沿用 qre-refresh hardened
  模板护栏；安装说明在头部注释，未 sudo）、barometer_job 默认最近交易日、
  `qre barometer` CLI、admin TIMER_UNITS + install_hint + daily_jobs
  PIPELINES 登记、/admin「大盘风险」tab（仪表盘/五序列 SVG/双口径
  热力表/预警详情）、阈值首轮校准观察入 06、CR 状态改 M1–M3 已完成。
- **纪律一致**：GUI 只读 market_risk.daily（cluster tab 同款 _store +
  _cached TTL 300s + 分区降级）；图表沿用项目 inline SVG 方案（客户端
  polyline，与 run_detail equity_svg 同思路），零新前端框架；
  timer/service 与现有 hardened 模板逐字段对齐（User/WorkingDirectory/
  Environment/Restart/MemoryMax/Nice/IOScheduling*/SyslogIdentifier）。
- **真实冒烟**：market_risk_overview 直连真库 ok——latest 2026-08-20、
  market 总分 63.3/green/5541 只、序列 252 日、行业 105（top 黄金 86.1）、
  簇 14（top 跳空:低开 breach 10.8%）。
- **阈值校准观察（06 已记录）**：1,850 日 red 11（0.59%，全为已知风险
  事件）、amber 219（11.8%）；corr 阈值 0.10≈P95、breach 阈值 3%≈P93；
  初值保留，若 amber 嫌多 breach 可上调 4–5%。
- **披露**：GUI 页面未经浏览器人工核对（qre-gui 未重启，用户约束）；
  timer 未安装（sudo 由主代理/用户执行）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1778 passed, 4 warnings（基线 1764 + 14 净增，全绿）
真实冒烟：market_risk_overview() 真库 ok（2026-08-20，63.3 green）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-BAROMETER-M2-009, 风向标 M2 数据装配与回填)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §5 M2 行一一对应**：barometer_job.py（唯一读写 DB 层：
  业务表只读，只写自有 market_risk schema）+ 单日/区间两模式 + 年分块
  312 交易日 buffer + 幂等 upsert + JSON 产物 + 真实回填 + 方向性验证。
  M1 内核零行为改动（仅 build_barometer indicators 增列 n_stocks 序列，
  纯增量）。
- **schema 决策**：独立 schema `market_risk`（QRE 产出与 cluster-ashare
  的 cluster schema 分空间；van 已验证 CREATE SCHEMA 权限；写库通道沿用
  cluster 日更同款 sqlalchemy engine + 事务，行级 ON CONFLICT 幂等）。
  表 `market_risk.daily(trade_date, scope, n_stocks, indicators/scores/alert
  jsonb, created_at)`，PK (trade_date, scope)，120 个 scope
  （1 market + 105 industry + 14 cluster tag）。
- **口径**：收益 = pct_chg/100（tushare 前收盘口径，与 cluster-ashare
  tags_daily 一致）；市值 = daily_basic.total_mv 行内归一化；行业静态
  映射（stock_basic.industry）；簇 = cluster.daily_tags 当日 tag→成员，
  <5 只跳过。簇行只出当日截面指标（scores=None + note 披露：成员逐日
  变动，252 日分数需固定成员历史，M2 不算）。
- **真实回填**：2019-01-02 → 2026-08-20，8 个年块（每块 312 交易日
  buffer），约 21 分钟单进程，220,034 行 / 1,850 交易日 × 120 scope；
  每日 JSON 产物 outputs/market_risk/<date>.json（共 1,850 个）。
- **方向性验证（CR §5 M2 硬要求，全过）**：market 行全样本分位对照——
  - 2020-02-03 疫情暴跌：突破占比 85.2%（P100）、总分 87.7（P99）、
    alert=red；次日 02-04 red。
  - 2024-01-29~02-05 微盘危机：总分 93.9–99.4（P99–100）、
    02-05 突破占比 58.6%（P100）、连续 red。
  - 常态对照 2023-06：总分 28–36（P10–21）、alert=green。
  - 全样本 red 共 11 天，全部为已知风险事件：2020-02-03/04/28（疫情）、
    2024-01-29~02-05、2024-02-28（微盘）、2024-10-09（国庆后回撤）、
    2025-04-07（关税暴跌）——方向性与选择性俱佳。
- **披露/已知边界**：2020-02-04 离散度 12.0（P100）为新股首日 ±44%
  无涨跌幅限制的极端收益所致（数据特征非 bug，等权标准差对离群敏感，
  如实披露）；回填期间单日冒烟发现 daily_basic 缺个别 BJ 股
  （920395.BJ 等）市值列，已修为 reindex 缺列补 NaN（加权时剔除）。
- **测试**：+10（分块边界/DDL/幂等 upsert SQL 与 NaN→None/簇 <5 跳过/
  端到端 monkeypatch 管线 + JSON 产物），全量 1764 绿。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1764 passed, 4 warnings（基线 1754 + 10 净增，全绿）
真实回填：2019-01-02→2026-08-20，8 chunks，220,034 行 / 1,850 日 × 120 scope，~21min
方向性验证：2020-02-03 red（breach 85.2% P100）、2024-02-05 red（score 99.4 P100）、
  常态 2023-06 green（score P10–21）；全样本 red 11 天全部为已知风险事件
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-BAROMETER-M1-008, 风向标 M1 纯函数内核)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §5 M1 行一一对应**：cross_section.py（EWMA 方差面板、
  截面波动率中位/90 分位、等权/市值加权离散度、滚动 60 日平均两两
  相关等权 + w_i·w_j 偶权近似、VaR 突破计数/占比）+ barometer.py
  （组合法封装复用 volatility/tail、252 日滚动分位分数、红/黄/绿
  预警、全市场+板块组装）+ constants 集中参数全回显 + 合成面板单测，
  全覆盖；M2 数据装配（barometer_job.py）按 CR 分期不做。
- **纪律一致**：两新模块纯函数零 DB；参数集中 constants.py
  （BAROMETER_CORR_WINDOW/SCORE_WINDOW/ALERT_*/BREACH_CONFIDENCE/
  CROSS_SECTION_SIGMA_QUANTILE）并全部在结果 dict 回显；既有 risk
  模块零行为改动（仅 __init__ 增列）。
- **数值自检**：EWMA 面板逐列 == volatility.ewma_variance_series
  （atol 1e-15，含 NaN 顺延对 dropna 语义）；两股面板平均相关 ==
  np.corrcoef（1e-12）；完全相关/反相面板均值 −1/3 手算；离散度
  等权 ddof=1 与加权 Σw(r−μ_w)² 手算核对；VaR 突破严格 r<−VaR 与
  backtest_var HIT 同口径；组合法 VaR/ES 与 tail 直接调用逐键一致；
  预警三态（green/amber×2/red）与阈值回显断言；warmup 降级 None
  不伪造分数；权重倾斜下等权 vs 市值加权组合序列差异用例。
- **披露**：加权平均相关为 w_i·w_j 偶权常规近似（非严格加权相关
  系数）；相关窗口内个股需完整 window 观测否则当日剔除；加权离散度
  未做 1−Σw² 集中度校正；预警阈值 +0.10/3% 为 CR 注明待校准初值；
  相关历史不足 20 日时 corr 判据不触发（None 披露）。

## Validation Evidence

```
uv run pytest tests/test_risk_cross_section.py tests/test_risk_barometer.py → 30 passed
uv run pytest tests/ -x -q → 1754 passed, 4 warnings（基线 1724 + 30 净增，全绿）
scripts/check-progress-docs.sh → passed
git diff --check → clean
注：全量首跑 test_gui_risk_report.py::TestRiskReportEndpoints::test_post_conflict_409
失败，单独 24/24 绿、全量复跑全绿（环境敏感 flake，同既往 test_job_lock_conflict 类）
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-PORTFOLIO-007, R7 组合层汇总)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §2 R7 一一对应**：组合层汇总（risk/portfolio.py：股票腿
  R1–R4 收益序列法、债券/转债腿 DV01/KR01、期权腿组合 Greeks、可选
  DGV-VaR）、risk_report 扩展（可选 portfolio 节 + markdown 渲染）、
  GUI 卡片组（沿用 risk-card 模式，有节才显示）、晋升闸可选判据
  （默认关闭）全覆盖。
- **纪律一致**：portfolio.py 纯函数零 DB；参数集中 constants.py 并回显；
  既有 risk 模块零行为改动（仅 report.py 增加可选节 + __init__ 增列）。
- **向后兼容（专项测试覆盖）**：默认 run 产物零变化（收尾钩子不传衍生品
  键，top-level keys 测试未改动仍绿）；老格式 report（无 portfolio 节、
  老 meta 无 sections）markdown/GUI/闸三处均不炸；闸阈值默认 None 时
  evaluate_gate_risk 返回与 R4 逐键一致（set(risk) 断言）。
- **数值自检**：KR01 按节点加总 = 合并现金流单独跑 key_rate_shifts
  （rel 1e-12），kr01_sum ≈ 曲线口径 DV01（一阶恒等式 rel 1e-4）；
  债券聚合/期权 Greeks 加对手算；DGV-VaR 复用 R6 已验证内核。
- **披露**：DGV 需调用方显式给 spot/vol shock（组合层无标的价格水平）；
  kr01_sum 与 portfolio DV01 口径可不同不强制相等（并列披露）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1724 passed, 4 warnings（基线 1696 + 28 净增，全绿）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-OPTIONS-006, R6 期权内核 + DGV-VaR)

## Task ID

QRE-RISK-OPTIONS-006（FRM 风险管理模块 R6：期权计算内核 + DGV-VaR）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §2 R6 表一一对应**：options.py（BSM 无股息/q/离散股息、
  Black's、隐波 brentq、CRR 欧式+美式含 q、树第一层 delta、美式 Greeks
  数值差分、Greeks 全组含 q 版与期货期权版、组合 Greeks 加权）与
  derivatives_var.py（DGV 近似 P&L、正态/CF 分位、VaR 序列对接
  backtest_var_summary 复用 HIT/LR，未新造回测引擎）全覆盖；不做项
  （Heston/波动率曲面/LSM/奇异期权）未触碰。
- **纪律一致**：纯函数零 DB；参数集中 constants.py（IV_BRACKET/
  DEFAULT_TREE_STEPS/GREEK_SHOCK_SIGMA/GREEK_SHOCK_RATE）并全部在
  结果 dict 回显；既有 risk 模块零行为改动（仅 __init__ 增列）。
- **数值验收（CR §4 R6 行全部通过）**：BSM 教材例 d1=0.2001/
  d2=−0.1674/c=8.3069/p=7.9715 + parity 1e-10 自洽；隐波 7.00→25.14%；
  美式 put 教材节点值（A=3.058/B=0.494/C=5.699 行权/欧式 2.838）+
  收敛 20/50/100/500 → 3.082/3.067/3.059/3.055；PDE 恒等式
  （q=0 与 q 版 (r−q)SΔ 形式）1e-10；纯 gamma 组合解析二阶矩
  Var=½Γ²sS⁴ 核对；CF-VaR 对 MC 分位 rel 5%（偏度<0.5 适用域）；
  VaR 序列→backtest_var_summary 集成回测违约率 ≈1% 不拒绝。
- **教材参数溯源**：二叉树收敛例参数（S=29,K=30,r=3%,σ=25%,T=1）
  摘要未载明，已从教材原文 PDF p193 抽取确认（Figure 14.5/14.6
  及收敛段），注释写入测试文件头。
- **自审修正**：Black76 theta 首版符号错误（−r·c 应为 +r·f 结构），
  由有限差分自检测试发现后修正为 θ = r·f − F₀e^{−rT}N′(d1)σ/(2√T)，
  修正后五值全对有限差分（rel 1e-5）。
- **遗留/披露**：CF 在高偏度（纯 gamma χ² 型）下分位失真为已知限制
  （docstring+测试注明，矩核对不受影响）；DGV 的 δS/δσ 独立假设披露；
  CRR 树↔BSM 收敛测试容差 abs 3e-3（O(1/n) 振荡收敛性质）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1696 passed, 4 warnings（基线 1657 + 39 净增，全绿）
tests/test_risk_options.py + tests/test_risk_derivatives_var.py 单独 39/39 绿
scripts/check-progress-docs.sh → 待 docs 同步后运行
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-RATES-005, R5 利率与债券内核)

## Task ID

QRE-RISK-RATES-005（FRM 风险管理模块 R5：利率与债券计算内核）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §2 R5 表一一对应**：rates.py（式 16.1–16.5 复利换算、
  PV/FV、spot↔折现因子、书4 Ch9 bootstrap、线性/对数线性插值、
  远期利率连续式与式 10.5、par yield 式 16.7/10.4）与 bonds.py
  （YTM brentq、式 9.2/30-360 应计利息、式 12.6 久期凸性、式 12.1/12.3
  effective、DV01 与 D↔DV01、组合聚合与对冲配比、式 12.4 二阶近似、
  书4 Ch13 KR01、书3 Ch16/17 转债债底与 spread duration）全覆盖；
  不做项（PCA/条款引擎/信用违约/互换期货）未触碰。
- **纪律一致**：纯函数、零 DB、零行情依赖；参数集中 constants.py
  （DEFAULT_DAY_COUNT/CURVE_INTERPOLATION/KEY_RATE_TENORS/
  RATE_SHOCK_BP/YTM_BRACKET）并全部在结果 dict 回显；day count 默认
  actual/actual 符合中国惯例约束；曲线统一连续复利零息利率口径并在
  docstring 披露。既有 risk 模块零行为改动（仅 __init__ 增列）。
- **数值验收（CR §4 R5 行全部通过）**：
  - 书4 Ch9 bootstrap：d = 0.991909/0.980944/0.969406/0.956909
    （实测 1e-6 内精确复现，另加折现回验自洽）；
  - par yield：2.2103%（式 16.7 手算一致）+ 平价债回验 100.0；
  - 平坦曲线连续年金解析解 P/D/C = 8.6394/4.7504/30.862（周网格
    离散逼近 rel<1e-2）；
  - DV01↔D 换算自洽（duration_from_dv01 = effective duration，1e-12）；
  - ΣKR01 = DV01（一阶，rel 3.5e-6 内，rtol 1e-4 自检通过）；
  - +100bp 平行移动二阶近似 vs 直接重定价 rel 偏差 1.9e-5 < 1e-3。
- **顺手修复**：pyproject.toml 补 scipy>=1.11.0 显式依赖（constants.py
  自 R1 起 import scipy 但未声明，CR §3 已点名）。
- **遗留/披露**：KR01 的 Σ=DV01 为一阶恒等式（二阶残差已写进 note 与
  测试容差）；插值域外平坦外推已披露；测试 3 处首版手算/口径错误
  （0.928597→0.928599、年金网格 int、spread duration 对比基准应为
  r+s 水平）已在实现内修正，非源码缺陷。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1657 passed, 4 warnings（基线 1605 + 52 净增，全绿）
tests/test_risk_rates.py + tests/test_risk_bonds.py 单独 52/52 绿
scripts/check-progress-docs.sh → 待 docs 同步后运行
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004（FRM 风险管理模块 R4：晋升全量回测闸加入风险判据）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **改动最小、复用到位**：闸判据挂在唯一收口点
  `refresh_registry.gate_blocks_daily`（refresh_batch.py /
  list_catalog_strategies / refresh_overview 三处调用方零改动自动生效）；
  风险数据复用 R3 既有 `risk_report.load_risk_report` 与
  `runs/<run_id>/risk_report.json`，无新增存储、无 DB 访问。
- **判据语义符合任务书**：ES99 取历史模拟口径（经验日收益，非参数
  假设）阈值 3%（`risk/constants.py::GATE_ES99_MAX`，可调整）；VaR 回测
  取 99% 节覆盖率 Kupiec LR `reject_5pct`（与 ES99 同置信，
  `GATE_VAR_CONFIDENCE`）；主判据（交易≥30 且超额>0）逻辑零改动，
  warning 只影响 `gate_blocks_daily` 与 admin 徽标。unavailable（无
  report/损坏/run 失败）不阻断——专项测试覆盖。
- **force 通道**：warning + forced → 评估照跑、`forced` 透传、
  gate_blocks_daily=False（专项测试）；admin tooltip 注明「force 晋升，
  不阻止日更」。
- **存量兼容**：旧 gate json 无 risk 节 → `gate.get("risk")` 为 None，
  gate_blocks_daily 行为与 R4 前完全一致（test_gui_admin_p3b 既有用例
  未改动、全绿佐证）；admin 仅在 risk.status==='warning' 时追加徽标。
- **字段缺失健壮性**：老格式 report 缺 tail/var_backtest 键时子项记
  None、不触发 warning（evaluate_gate_risk 逐层 `or {}` 取值）。
- **偏差**：无 Required Fix。已知边界：①风险判据取 99% 单置信节
  （95% 节拒绝不触发 warning），与任务书「ES99 + VaR 回测」口径一致；
  ②独立性 LR 不进闸判据（仅报告层展示），因任务书只点名 Kupiec
  覆盖率；③run 失败时 risk=unavailable（此时 gate 已 failed 阻断，
  risk 维度无增量信息）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1605 passed, 4 warnings（2026-08-22，
  QRE-RISK-GATE-004；基线 1599 + 6 净增：test_gui_strategy_create.py
  R4 节 5 新 + test_gui_admin_strat_tab.py 徽标 1 新）
定向：tests/test_gui_strategy_create.py test_gui_admin_strat_tab.py
  test_refresh.py test_gui_admin_p3b.py → 103 passed（2.86s）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

## Nice-to-Have

- 后续可考虑把 95% 节 VaR 回测也纳入判据、或对存量 gate 回填 risk 节；
  均不影响本次正确性，留待用户决策。
