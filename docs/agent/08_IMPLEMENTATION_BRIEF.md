# Implementation Brief

## Task ID

QRE-RISK-BAROMETER-M3-010（大盘/板块风险风向标 M3：日更 timer 接入 + GUI 风向标页 + 阈值首轮校准观察）

## Created By

KIMI_CODE（主代理 2026-08-23 指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-23_market_risk_barometer.md` §4/§5 M3 阶段；
M1=64addd7、M2=b0713d7，基线 1764 tests green）

## Intended Implementer

KIMI_CODE（子代理执行 M3）

## Goal

1. 日更接入：`deploy/hardened/qre-barometer.{service,timer}`
   （Mon..Fri 18:30、Persistent=true、oneshot、沿用 hardened 模板护栏；
   安装命令写注释，不 sudo）；barometer_job 无 --date 时默认最近交易日
   （latest_trade_date）；`qre barometer` CLI 子命令；
   admin TIMER_UNITS + daily_jobs PIPELINES 登记（日更中心可见可手触）。
2. GUI：/admin 新增「大盘风险」tab——总分仪表盘（最新日 + 红黄绿灯 +
   四指标当前值）、五序列 SVG 时间序列（近 252 日，客户端 polyline，
   与 run_detail 同方案 inline SVG、零新前端框架）、板块热力表（行业/动态簇
   双视图切换，按总分/突破占比排序着色）、预警详情（双判据当前值 vs 阈值）。
   数据层 `gui/market_risk.py::market_risk_overview`（只读 market_risk.daily，
   _cached TTL 300s，分区降级）；路由 `/api/admin/market-risk`。
3. 阈值首轮校准：回填 1,850 日统计 red/amber 频率与双判据分位数，
   结论记 06_DECISION_LOG（初值不动，记录观察）。
4. 测试：timer/service 静态校验、TIMER_UNITS/install_hint、PIPELINES
   登记、CLI 解析与分发、overview 数据层（fake store：排序/空表/双降级）、
   路由 200、admin 页含新 tab、barometer_job 默认日期。
5. CR 状态改「✅ M1–M3 已完成」；docs/agent 同步。

## 约束

最小侵入；既有 1764 测试全绿；不 git commit、不 sudo、不重启 qre-gui。

## Validation

`uv run pytest tests/ -x -q`（目标 1764 + 新增全绿）；真实库
market_risk_overview 直连冒烟；`scripts/check-progress-docs.sh` → passed。

---

# Implementation Brief (archive: QRE-RISK-BAROMETER-M2-009, 风向标 M2 数据装配与回填)

## Created By

KIMI_CODE（主代理 2026-08-23 指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-23_market_risk_barometer.md` §4/§5 M2 阶段；
M1 = commit 64addd7，基线 1754 tests green）

## Intended Implementer

KIMI_CODE（子代理执行 M2 装配层）

## Goal

1. 新 `risk/barometer_job.py`（本包唯一读 DB 层，只读业务表 + 写自有结果表）：
   - 取数：`public.stock_daily.pct_chg/100` 收益面板（前收盘口径，与
     cluster-ashare tags_daily 一致）、`reference.daily_basic.total_mv`
     市值面板、`reference.stock_basic.industry` 行业分组、
     `cluster.daily_tags` 当日标签簇分组（簇内 <5 只跳过）、
     `reference.trade_calendar`（cal_date/is_open）交易日历；
   - 单日与区间两模式；区间按 chunk（默认年）分块，每块前补
     252+60=312 交易日 buffer（分位窗口 + 相关窗口 warmup），
     块内计算后只写块区间日期，块间幂等；
   - 调用 M1 纯函数（build_barometer / cross_section / 零改动）；
   - 结果写 `outputs/market_risk/<date>.json` + `market_risk.daily`
     表（ON CONFLICT (trade_date, scope) 幂等 upsert）。
2. 结果表 DDL：独立 schema `market_risk`（决策与理由见下）：
   `(trade_date, scope, n_stocks, indicators jsonb, scores jsonb,
   alert jsonb, created_at)`，PK (trade_date, scope)；
   scope ∈ `market` / `industry:<行业>` / `cluster:<tag>`。
3. 回填入口：模块 __main__（`--date` 单日 / `--d0 --d1 --chunk year`
   区间回填，进度日志），回填 2019-01→今（覆盖 CR 验收的 2020-02
   疫情与 2024-02 微盘危机方向性验证时点，且超 CR「近 252+60」下限）。
4. 方向性验证：2020-02-03、2024-01 下旬~02 初的风险分数/突破占比/
   相关系数 vs 常态分位，摘要写进 10_REVIEW。
5. 测试：monkeypatch 取数函数 + fake engine（沿用 test_postgres_store
   模式）——幂等 upsert SQL、簇 <5 跳过、分块边界、端到端小面板。

## schema 决策（记录理由）

独立 schema `market_risk`，理由：①QRE 产出与 cluster-ashare 产物
（cluster schema）分空间，避免跨项目写对方 schema 的所有权混淆；
②用户 van 已验证有 CREATE SCHEMA 权限；③与「引擎与结果分空间存放」
既有原则一致。写库通道沿用 cluster 日更同款 sqlalchemy engine +
事务写入（ upsert 改 ON CONFLICT 行级幂等，因结果行少、非千万级长表）。

## 口径与边界（披露）

- 收益 = pct_chg/100（tushare 前收盘复权一致口径）；市值权重 = total_mv
  当日截面归一化。
- cluster 簇成员逐日变动：簇行输出当日截面指标 + 预警；252 日分数需
  固定成员历史序列，M2 对簇不计算分数（scores=null + note 披露），
  行业（静态映射）与全市场计算完整分数。
- 组合法 ES99/组合汇总为整段统计，入 JSON 产物与 market 行 indicators；
  表按日行存储指标/分数/预警。
- 不修改 M1 内核行为（只 import 调用）。

## Validation

`uv run pytest tests/ -x -q`（目标 1754 + 新增全绿）；
真实库回填一次 + 方向性验证摘要；
`scripts/check-progress-docs.sh` → passed。

---

# Implementation Brief (archive: QRE-RISK-BAROMETER-M1-008, 风向标 M1 纯函数内核)

## Created By

KIMI_CODE（主代理 2026-08-23 指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-23_market_risk_barometer.md` §2/§4/§5 M1 阶段；
前置 R1–R7 已完成，基线 1724 tests green）

## Intended Implementer

KIMI_CODE（子代理执行 M1 内核）

## Goal

1. 新 `risk/cross_section.py`（纯函数零 DB、向量化）：
   - `ewma_variance_panel`：个股收益面板（dates×stocks）→ 逐列 EWMA
     方差面板，口径与 volatility.ewma_variance_series 完全一致
     （σ²_1=r²_1、λ=0.94；NaN 观测跳过、方差顺延，对齐单列 dropna 语义）；
   - `cross_sectional_volatility_stats`：EWMA σ 面板 → 逐日中位数/90 分位/
     覆盖股票数；
   - `cross_sectional_dispersion`：当日收益截面 → 等权标准差与市值加权
     标准差（权重行内归一化，Σw(r−μ_w)² 口径）；
   - `average_pairwise_correlation`：滚动窗口（默认 60）两两相关均值——
     等权 = 相关矩阵上三角均值；市值加权 = 以 w_i·w_j 为偶权的加权均值
     （常规近似，docstring 披露）；窗口内个股按列均值/标准差标准化、
     不足 window 个非 NaN 观测的个股当日剔除；
   - `var_breach_ratio_series`：当日收益 vs 各自 EWMA VaR（损失正号口径
     r < −VaR）→ 逐日突破计数/占比。
2. 新 `risk/barometer.py`（纯函数）：
   - `portfolio_return_series`：面板收益+权重 → 等权/市值加权组合收益；
   - `portfolio_risk_summary`：组合序列 → 复用 volatility + tail 出
     EWMA σ 预测与 VaR95/99、ES95/99（历史模拟 + EWMA 参数法）；
   - `rolling_percentile_score`：指标序列对 252 日滚动窗口的分位数
     （0–100，含当日）；历史不足 → None + warmup 标记，不伪造；
   - `evaluate_alert`：相关系数 20 日升幅与 VaR 突破占比双超阈 → red、
     单超阈 → amber、否则 green；阈值集中 constants 并回显；
   - `build_barometer`：全市场 + 板块（groups 映射由调用方传入，
     不感知行业/簇来源）统一输出 dict（五指标各做滚动分位，
     等权合成总分，任一 warmup 则总分标注、全 warmup 则总分为 None）。
3. `risk/constants.py` 追加：BAROMETER_CORR_WINDOW=60、
   BAROMETER_SCORE_WINDOW=252、BAROMETER_ALERT_CORR_LOOKBACK=20、
   BAROMETER_ALERT_CORR_JUMP=0.10、BAROMETER_ALERT_BREACH_RATIO_MAX=0.03、
   BAROMETER_BREACH_CONFIDENCE=0.99、CROSS_SECTION_SIGMA_QUANTILE=0.90，
   全部在结果 dict 回显。
4. 测试 `tests/test_risk_cross_section.py`、`tests/test_risk_barometer.py`：
   合成面板已知答案核对（EWMA 面板对单列一致性、已知相关系数面板、
   离散度手算、突破计数）、预警三态、warmup 降级、等权 vs 市值加权
   差异、组合序列对接 tail/volatility 集成。

## 约束

纯函数零 DB；既有 1724 测试保持全绿；不 git commit；M2 数据装配
（barometer_job.py）不做。

## Validation

`uv run pytest tests/ -x -q`（目标 1724 + 新增全绿）；
`scripts/check-progress-docs.sh` → passed。

---

# Implementation Brief (archive: QRE-RISK-PORTFOLIO-007, R7 组合层汇总)

## Created By

KIMI_CODE（用户 2026-08-23 直接指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R7 阶段；
R5 = commit 5472832、R6 已完成（1696 绿）待审批）

## Intended Implementer

KIMI_CODE

## Goal

1. 新 `risk/portfolio.py`（纯函数零 DB）：`summarize_mixed_portfolio`——
   股票腿沿用 R1–R4 收益序列法（performance_summary + EWMA 参数 VaR/ES 参照）、
   债券/转债腿用 `bonds.portfolio_aggregate`（DV01 可加、D/C 市值加权）与
   可选 `bonds.key_rate_shifts` 逐头寸 KR01 按节点加总、期权腿用
   `options.portfolio_greeks`（加权求和）、可选 `derivatives_var.dgv_var`
   （config 显式给 spot/vol shock 才计算）；输出合并 dict（JSON 可序列化，
   numpy 数组转 list）。仅股票输入退化为仅 equity 节。
2. `risk/report.py`：config 显式传入 `bond_positions`/`option_positions`/
   `bond_kr01` 之一（非空）才追加 `report["portfolio"]` 节
   （meta.sections["portfolio"] 回显）；`render_risk_markdown` 有该节才渲染
   「### 组合与衍生品风险」。默认 run 产物零变化（收尾钩子不传这些键）。
3. GUI：`_risk_display` 增加 portfolio 视图；`run_detail.html` 在
   `risk_view.portfolio` 存在时追加「衍生品风险」卡片组（沿用 risk-card
   模式），无此节不显示。
4. 晋升闸扩展（可选判据，默认关闭）：`risk/constants.py` 加
   `GATE_DV01_MAX=None` / `GATE_GREEKS_MAX=None`；
   `evaluate_gate_risk` 仅在阈值非 None 且 report 有 portfolio 节时追加
   dv01/greeks 判据（超阈 → reason + warning）；阈值全 None 时返回 dict
   与现状逐键一致（零行为变化）。
5. 测试：组合汇总（纯股票退化/混合合并/空输入报错/KR01 加总）、report
   节开关与渲染两态、risk_report.json 向后兼容（老格式读取不炸）、
   GUI 卡片有无两渲染、闸默认关闭零变化 + 启用判据逻辑。

## 约束

纯函数、零 DB；不改既有 risk 模块行为；既有 1696 测试保持全绿；
不 git commit、不重启 qre-gui。

## Validation

`uv run pytest tests/ -x -q`（目标 1696 + 新增全绿）；
`scripts/check-progress-docs.sh` → passed。

---

# Implementation Brief (archive: QRE-RISK-OPTIONS-006, R6 期权内核 + DGV-VaR)

## Task ID

QRE-RISK-OPTIONS-006（FRM 风险管理模块 R6：期权计算内核 + DGV-VaR）

## Created By

KIMI_CODE（用户 2026-08-23 直接指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R6 阶段；
R5 = commit 5472832 已完成）

## Intended Implementer

KIMI_CODE

## Goal

在 `risk/` 包内新增两个纯函数内核（零 DB、零行情依赖）：

1. `risk/options.py`：
   - BSM 定价（式 15.6–15.9：无股息/连续股息 q；离散股息修正 S₀−D）；
   - Black's model 期货期权定价（式 15.12/15.13）；
   - 隐含波动率 scipy brentq 反解（bracket 集中 constants）；
   - CRR 二叉树（式 14.4–14.7：u/d/p、欧式+美式 backward induction、
     含股息 q；可选输出全节点网格；树第一层节点输出 delta）；
   - 美式 Greeks 数值差分（书4 Ch16 方法：delta 第一层、gamma 第二层、
     theta 隔层中节点、vega/rho 微扰重建树）；
   - Greeks 全组解析（Table 16.2 含 q 版 + 期货期权版 rho=−f·T）；
   - 组合 Greeks = 头寸加权求和。
2. `risk/derivatives_var.py`：Delta-Gamma-Vega 近似组合 P&L
   （ΔV ≈ Δ·δS + ½Γ(δS)² + vega·δσ，式 2.3 + vega 项）；
   二次型 P&L 的解析矩（非中心卡方累积量）→ 正态 / Cornish-Fisher
   分位 VaR；VaR 序列函数对接既有 backtest_var.backtest_var_summary
   复用 HIT/LR（不新造回测引擎）。
3. `risk/constants.py` 追加：IV_BRACKET、DEFAULT_TREE_STEPS、
   数值差分微扰参数，全部在结果 dict 回显。

## 验收（CR §4 R6 行）

- BSM 教材解析例：S=56,K=60,r=5%,σ=30%,T=1.5 → d1=0.2001、
  d2=−0.1674、c=8.3069、p=7.9715（含 put-call parity 自检）。
- 隐波反解教材例：同参数 call 市价 7.00 → σ≈25.14%。
- 二叉树收敛例（书4 Ch14 美式 put：S=29,K=30,r=3%,σ=25%,T=1）：
  2 步=3.058（节点 B=0.494、C=5.699 提前行权，欧式=2.838）、
  4 步=3.097；20/50/100/500 步 → 3.082/3.067/3.059/3.055。
- Greeks 对 BSM PDE 恒等式 θ + rSΔ + ½σ²S²Γ = rf（式 16.2）。
- DGV-VaR：delta 中性纯 gamma 组合对解析二阶矩核对
  （Var = ½Γ²sS⁴，均值 = ½ΓsS²）。

## 约束

纯函数、零 DB；不改既有 risk 模块行为；不做 Heston/波动率曲面/
LSM/奇异期权。既有 1657 测试保持全绿。不 git commit。

## Validation

`uv run pytest tests/ -x -q`（目标 1657 + 新增全绿）

---

# Implementation Brief (archive: QRE-RISK-RATES-005, R5 利率与债券内核)

## Task ID

QRE-RISK-RATES-005（FRM 风险管理模块 R5：利率与债券计算内核）

## Created By

KIMI_CODE（用户 2026-08-23 直接指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R5 阶段；
R1–R4 已完成）

## Intended Implementer

KIMI_CODE

## Goal

在 `risk/` 包内新增两个纯函数内核（零 DB、零行情依赖，输入为 dict/现金流表）：

1. `risk/rates.py`：复利频率换算（式 16.1–16.5）、PV/FV、spot↔折现因子、
   附息债 bootstrap 零息曲线（线性/对数线性插值）、远期利率（连续式与
   半年复利式 10.5）、par yield（式 16.7/10.4）。
2. `risk/bonds.py`：YTM 反解（scipy brentq）、dirty/clean 与应计利息
   （day count 参数化，默认 actual/actual）、Macaulay/Modified duration、
   yield convexity、effective duration/convexity（±Δr 重定价）、DV01 及
   D↔DV01 换算、组合聚合（DV01 可加、D/C 市值加权、DV01 对冲配比）、
   利率情景冲击（平行移动二阶近似；key-rate 扭转 KR01，ΣKR01=DV01 自检）、
   可转债债底折现（无风险+信用利差，spread duration）。
3. `risk/constants.py` 追加集中参数（day count 默认、曲线插值方式、
   key rate 节点、Δr 扰动 bp、YTM bracket），全部在结果 dict 回显。
4. `pyproject.toml` 补 scipy 显式依赖声明。

## 验收（CR §4 R5 行）

- 书4 Ch9 bootstrap 折现因子例：maturities 0.5/1/1.5/2、coupons
  5.75/5.5/5.875/5.5、prices 102.0426/103.5197/105.5852/106.4136 →
  d = 0.991909/0.980944/0.969406/0.956909（1e-6 容差）。
- par yield 算例（式 16.7/10.4）+ 平价债回验。
- 平坦曲线连续年金债久期/凸性解析解核对。
- DV01↔duration 换算自洽（D = 10,000×DV01/Value）。
- KR01 之和 = DV01。
- 平行移动二阶近似 ΔP=−D·P·Δr+½CP(Δr)² 与直接重定价偏差在容差内。

## 约束

纯函数、零 DB；不改既有 risk 模块行为；PCA 冲击/条款引擎/信用违约模型/
互换期货定价不做。既有 1605 测试保持全绿。

## Validation

`uv run pytest tests/ -x -q`（目标 1605 + 新增全绿）

---

# Implementation Brief (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004（FRM 风险管理模块 R4：晋升全量回测闸加入风险判据）

## Created By

KIMI_CODE（用户 2026-08-22 直接指定的任务书；依据已批准 CR
`docs/frm/CR_2026-08-21_frm_risk_module.md` R4 阶段；R1 = commit 96db59d、
R2 = commit f52c0f4、R3 = commit 6852eaa 已完成，risk_report.json 已随
每个 completed run 自动生成）

## Intended Implementer

KIMI_CODE

## Goal

在晋升全量回测闸（QRE-GUI-PROMO-GATE-001，commit cfb860d）的评估中
增加 FRM 风险维度：

1. **风险判据**：`finalize_promotion_gate` 收尾时读取该 run 的
   `runs/<run_id>/risk_report.json`：
   - 不存在/损坏 → `risk.status = "unavailable"`，不判风险项、不阻断。
   - 存在 → 取 99% ES（历史模拟口径，日收益损失取正）与 99% VaR 回测
     覆盖率 Kupiec LR 检验（5% 显著）：
     - ES99 > 阈值（默认 3%）或覆盖率 LR 被拒绝 → `risk.status = "warning"`。
     - 否则 `risk.status = "ok"`。
2. **闸语义**：主判据（交易≥30 且超额>0）照旧；`risk.status == "warning"`
   时与 failed 同效阻止日更拾取（force 晋升可覆盖），gate json 记录
   risk 详情（独立一节，便于 admin 展示）。
3. **admin GUI**：策略状态表「全量回测闸」列在 risk=warning 时追加
   ⚠ 风险警示徽标，tooltip 显示 ES99 与 VaR 回测结论。
4. **测试**：risk ok / warning（ES 超阈）/ warning（LR 拒绝）/
   unavailable（无 risk_report）四情形 + force 覆盖 + admin 徽标渲染。

## Semantics

- 阈值集中在 `risk/constants.py`：`GATE_ES99_MAX = 0.03`（日收益口径
  99% ES 上限）、`GATE_VAR_CONFIDENCE = 0.99`（VaR 回测取 99% 节，
  与 ES99 同置信）。LR 显著性 5% 沿用 backtest_var 既有 `reject_5pct`。
- ES99 取 `report["tail"]["99pct"]["historical_simulation"]["es"]`
  （经验日收益口径，非参数假设）；VaR 回测取
  `report["var_backtest"]["levels"]["99pct"]["coverage"]["reject_5pct"]`
  （Kupiec 覆盖率 LR；独立性检验不进闸判据，仅报告）。
- 关键字段缺失（老格式 report）→ 该子项不触发 warning，如实记 None。
- gate json 新增一节（不改动既有顶层键语义）：

  ```json
  "risk": {
    "status": "ok | warning | unavailable",
    "es99": 0.0219,
    "es99_threshold": 0.03,
    "var_lr_reject": false,
    "var_confidence": 0.99,
    "reasons": ["es99_exceeds_threshold", "var_lr_rejected"],
    "report_run_id": "rid-gate"
  }
  ```

- `gate_blocks_daily` 扩展：`(gate == "failed" 或 risk.status == "warning")`
  且非 forced → 阻止日更。force 通道照旧评估、不阻断。

## Scope

1. `src/quant_research_engine/risk/constants.py`：+ `GATE_ES99_MAX`、
   `GATE_VAR_CONFIDENCE`。
2. `src/quant_research_engine/gui/risk_report.py`：+
   `evaluate_gate_risk(run_id)`（load_risk_report → risk 判据 dict）。
3. `src/quant_research_engine/gui/strategy_create.py`：
   `finalize_promotion_gate` 写入 `payload["risk"]`（复用 record.run_id；
   run 失败时同路径评估，report 不存在自然落 unavailable）。
4. `src/quant_research_engine/gui/refresh_registry.py`：
   `gate_blocks_daily` 加 risk warning 分支（docstring 同步）。
5. `src/quant_research_engine/gui/templates/admin.html`：闸列追加
   risk=warning 徽标 + tooltip（ES99/VaR 结论）；`static/style.css`
   加 `.gate-risk` 样式。
6. 测试：`tests/test_gui_strategy_create.py`（四情形 + force + gate_blocks_daily
   联动）、`tests/test_gui_admin_strat_tab.py`（徽标字符串断言）。
7. docs/agent 08/10/09/05/04/11 同步。

## Non-Goals

- 不 git commit、不重启 qre-gui.service。
- 不改 risk 包核心计算、不改 refresh 管线取数逻辑、不动 DB。
- 不对存量 gate json 回填 risk 节（下次晋升回测评估自然写入；
  缺失时 admin 不显示徽标，语义=未知不阻断）。

## Validation

- `uv run pytest tests/ -x -q` 全绿（基线 1599）。
- 单测覆盖四情形 + force 覆盖 + admin 徽标。
