# 21_FACTOR_LIBRARY_PLAN.md — Tushare 202 因子本地复现立项方案

## 0. 进度台账（2026-10-19 更新：177/202 已入库验收，P8 日更接线完成，全部批次收口）

| 批次 | 内容 | 状态 |
|---|---|---|
| P6 通道A | Momentum/Reversal 量价 10 新列（pctret_21/42/63/126/252、price_position_ir_60、days_down_up、price_dist、rsrs_18_200、macd_cn_12_26_9） | ✅ 已入库+日更接管（在 config/factors.yaml 体系内） |
| P6 通道B | 7 个回归 Alpha（alpha_125/250/500/1000d_000300、alpha_528/792/1320d_000001）+ small_cap_reversal_21d | ✅ 已全历史入库（panel_factors/ 面板管线，18 chunks/1624 万行，金标准误差 2.8e-17）；✅ 2026-10-19 P8 接入日更（panel-factors-daily.timer channel_b 步骤） |
| P0 | `_pit_financial_panel` 物化面板 + 字段核实 | ✅ 已落地（14.12M 行 × 90 列，2009-01-05 起；四项验收全过）。2026-10-18 修复：ebitda_ttm 改 ebit_ttm+最近年报折旧摊销（tushare ebitda 仅半年/年报披露），7 行→1113 万行；✅ P8 接入日更（感知新财报公告：增量从 watermark+1 起按 eff_ann<=trade_date 重选报告期） |
| P1 | Value 11 + Size 3 → factors.stock_daily_value / stock_daily_size | ✅ 2026-10-18 验收通过（抽查 abs_diff=0；bm vs 1/pb 相关 0.98；ebitda 修复后 1080 万行）；✅ P8 接入日更 |
| P2 | Quality 59 → factors.stock_daily_quality | ✅ 2026-10-18 验收通过（51 rank 列值域、手工核对、毛利率同源比对 99.39%≤1e-4）；✅ P8 接入日更 |
| P3 | Growth 15 → factors.stock_daily_growth | ✅ 2026-10-18 验收通过（RESULT: PASS）；✅ P8 接入日更 |
| P4 | Liquidity 35 → factors.stock_daily_liquidity | ✅ 2026-10-18 全量落库验收（1613 万行，手工重算最大误差 2.9e-14，commit c2a0fd8）；✅ P8 接入日更 |
| P5 | Risk 25（回归族 beta/sigma，复用通道B框架）→ factors.stock_daily_risk | ✅ 2026-10-18 全量落库验收（1622 万行，最大误差 8.5e-15，commit 3ce37de）；✅ P8 接入日更（接入时发现并修复回归族 warmup 按市场交易日数供给的缺口——窗口期停牌 >20 日的股票会凑不足 1320 有效样本对被误产 NaN，约 290 只；改为 pair-aware warmup（个股第 1326 行历史日期取 max），增量与全量口径逐值一致） |
| P7 | Alpha101 31（复用 alpha191 面板管线）→ factors.stock_daily_alpha101 | ✅ 2026-10-19 全量落库验收（1607 万行/5853 只/921 chunks，慢实现比对 max_abs_diff=0、rank 值域与 NaN 语义全过；VWAP 与 OHLC 同乘 adj_factor 同尺度，commit e35227b）；✅ P8 接入日更 |
| P8 | 每日增量调度（panel_factors 接入 timer）+ 8080 纳管 | ✅ 2026-10-19 完成：`panel-factors-daily.timer`（每工作日 17:45，排在 minute-csv-ingest 17:20 后）驱动 indicators 侧 `scripts/panel_factors_daily.py`（watermark 幂等 + 串行子进程内存隔离 + pit→value/quality/growth 依赖门控 + 失败可重跑）；8080 纳管（PANEL_FACTOR_TABLES 登记为日更中、参与滞后判定与健康灯，TIMER_UNITS + daily_jobs「panel-factors」手动触发管线，列级对账由 EXPECTED_COLUMNS_SCRIPT 注入各模块权威列清单）；验证：2026-10-09 全市场单日复算 vs 存量全量值 20 股抽样逐值一致 + 连跑两次幂等（scripts/verify_p8_incremental.py）；首次追数（10-13~10-16，4 交易日）各步耗时 pit 1.3 / value_size 3.9 / quality 1.5 / growth 1.2 / liquidity 0.5 / risk 0.9 / alpha101 1.1 / channel_b 1.0 min，合计 ~11.4 min |

**完成度：177/202（88%）已入库验收** = Momentum 20 + Reversal 3 + Value 11 + Size 3 + Quality 59 + Growth 15 + Liquidity 35 + Risk 25 + Alpha101 31。剩余 25 个为原方案口径裁剪项（含 dividend_yield_3y_avg 等 2 个待 dividend 回填），明细见 §口径裁剪与原清单。P0-P7 全部面板表与通道B 均已接日更（P8 收口）；NL 目录快照（configs/factor_catalog_llm.*）已于 2026-10-19 同步纳入 P4/P5/P7 新表。

## 0.2 因子语义注册表维护纪律（2026-10-25 新增，QRE-GUI-FACTOR-REGISTRY-001）

`configs/factor_registry.json`（v1.0）是自选因子界面与 NL 解析的**单一因子语义来源**：
中文名、价格口径、中英文别名、族与参数。canonical `schema.table.column` 仍是数据库、YAML、
回测和因子申请的唯一字段标识，注册表**不改名、不迁移数据库**。

**新增/变更因子列后的固定动作（缺一不可，漏项会被校验告警）**：

1. 在 `scripts/gen_factor_registry.py` 的 `FAMILY_RULES` 补族规则（列名正则 + 命名组 +
   `zh_base` + `param_order` + 常用别名）；无法用规律表达的特殊项进 `MANUAL_ENTRIES`。
   **不要伪造中文翻译**——暂时维护不了的条目留空，`zh` 会记 null 并进覆盖报告。
2. 重新生成快照与注册表：
   ```bash
   QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data .venv/bin/python scripts/gen_factor_catalog_llm.py
   QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data .venv/bin/python scripts/gen_factor_registry.py
   ```
   前者会同时打印「因子语义注册表校验」与「注册表覆盖：N/M 列（x%）」——出现
   `注册条目指向因子库不存在的字段` 或 `别名指向…不存在的字段` 必须修完再入库。
3. 重新导出 SaaS metadata（弹窗与 `/api/saas/factors` 的数据源）：
   ```bash
   QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data .venv/bin/python scripts/sync_saas_metadata.py --out deploy/saas/metadata.json
   ```
4. 测试门禁：`uv run python -m pytest tests/test_factor_registry.py -q`（40 项，含
   「注册表覆盖每个快照列」「当前快照无失效 canonical」）。新增列若未注册，会被
   `coverage_report` 列出来但不会静默通过——要么补规则，要么在文档里说明为何不维护。

**口径与消歧规则（改动前必读）**：

- 价格口径：同列多口径未说明时默认 **close** 并输出 notice；典型价/均价必须由用户明确
  指定。新增带价格后缀的表时保持 close → typical_price → average_price 优先级。
- MACD 三输出不可混淆：DIF=`macd_*`、DEA/信号线=`macds_*`、柱=`macdh_*`；未给参数时
  默认 (12,26,9) 并提示。
- 其他歧义（同一别名指向多个不同字段）必须返回 candidates，**不得静默覆盖**；这类别名放
  `EXTRA_ALIASES`（如「布林带」→ 上/中/下轨，「kdj」→ K/D/J）。
- LLM Prompt **不注入全量别名**：只保留 canonical 目录 + `CORE_TARGETS`（25 条核心示例）。
  要给 Prompt 加例子时改 `CORE_TARGETS`，不要把 `aliases` 全量塞进去。
- 族别名只挂在「常用 + 默认参数」条目上（`_is_common` / `_is_default_params`），控制 JSON
  体积与 Prompt 成本。

**当前覆盖**：554/895 列有中文名（61.9%）。未维护 341 列 = Alpha191 191 + Alpha101 31
（面板因子，展示用既有「Alpha191 · alphaNNN」label）+ quality/growth 的 `_rank` 族 +
少量财务报告期/现金流明细字段。这些列在前端回退 canonical 展示，不影响任何 canonical、
YAML 与回测口径。


## 0.1 下周恢复指引（2026-10-13 记录，已于 2026-10-18 执行完毕：P1-P3 验收通过、两仓库已提交、NL 目录已同步、P4 完成、P5 启动）

1. **先检查 P1-P3 收尾**：三表续跑进程是否结束（`pgrep -af panel_factors`），各表最新交易日是否到 2026-10-12+；跑各表的 `*_verify.py` 验收（P1: earnings_to_price vs 1/pe_ttm 相关性>0.95 等，见因子规范）。
2. **commit 待批准**：indicators_tushare（panel_factors/ 全部 + P0/P1/P2/P3 实现）、QRE（factor_specs_p1p3.md、NL 目录快照、05/21 号文档）——本周所有改动均未 commit。
3. **NL 目录快照同步**：P1-P3 入库后跑 `scripts/gen_factor_catalog_llm.py`（FACTOR_AUTHORING §3-⑦）。
4. **随后启动 P4/P5/P7**（互不依赖可并行）：先让 agent-119 导出 P4/P5/P7 因子规范（仿 factor_specs_p1p3.md），再派实施。
5. **P8 最后**：统一接日更（消除通道B/基本面表的手动补数缺口）。
6. 因子层口径提醒：hfq 尺度（原始价 × adj_factor），金标准比对必须按 hfq，勿对原始价裸算（05 号文档 2026-10-12 条）。

完成度：23/202 因子已覆盖（Momentum 20 + Reversal 3 全量）。权限与数据已核实达标（2026-10-13：income/balancesheet/cashflow/fina_indicator/daily_basic/dividend 接口实测可用，DB 四表 5573 只 2001 年起、daily_basic 1433 万行、dividend 25 万行齐备；仅 stk_factor/factor_list 官方接口无权限=自研复现动因）。

> 立项日期：2026-10-11。来源：plan 子代理方案（agent-119），主代理核实背景后收录。
> 决策背景：Tushare 因子库（doc_id=486，202 因子 9 大类，公式全公开）为单独付费接口（个人 2000 元/年），本机 token 无权限（factor_list/stk_factor_pro/stk_factor 实测拒绝）。决定自研复现——公式公开可审计、可自调参数、零费用。约 200/202 可复现，仅 dividend_yield_3y_avg 等 2 个待 dividend 回填完成。
> 与现有因子库重叠仅 5~7%（MACD/RSI/收益率等 10~15 个）；现有 490 列全是纯量价，本方案补齐基本面/估值/流动性空白，直接解锁巴菲特策略因子化。

## 1. 表设计（沿用 factors schema 规范）

新表 7 张，全部 `(ts_code, trade_date)` 主键 + hypertable(trade_date, 7天chunk) + trade_date DESC 索引，double precision：

| 表 | 类别 | 因子数 |
|---|---|---|
| factors.stock_daily_value | Value | 11 |
| factors.stock_daily_quality | Quality | 59 |
| factors.stock_daily_growth | Growth | 15 |
| factors.stock_daily_liquidity | Liquidity | 35 |
| factors.stock_daily_risk | Risk | 25 |
| factors.stock_daily_size | Size | 3 |
| factors.stock_daily_alpha101 | Alpha101 | 31 |

Momentum(20)+Reversal(3)：已有等价列的（rsi/macd/return_*/ma_20d）登记别名映射不重复建；17 个新列并入现有 `stock_daily_momentum_close`。

**存原值还是存截面排名**：约 90 个官方因子定义为 CrossSectionalRank。决定：**主表存原值，排名衍生列并存（列名 `xxx_rank`）**——排名对历史截面样本漂移敏感且不可用于阈值策略，原值必须保留；排名当日全截面算，成本可接受。当日有效样本 <100 时整日 rank 输出 NaN。

## 2. 计算架构

- **PIT 财务面板**（基石，P0）：物化中间表 `factors._pit_financial_panel`——ann_date<=trade_date 取每报告期最新公告、ffill 到日频、TTM 构造（单季=累计差分，TTM=近4单季和）、常用 ~40 字段宽表。所有基本面因子从它读，不重复做 PIT join。
- **滚动回归族**（Beta/Alpha/Sigma vs 000001.SH/000300.SH、RSRS 等 ~15 个）：面板向量化（rolling.cov/var + 滚动OLS闭式解），1320 日窗口 2010-2015 前段 NaN 属正常。
- **Alpha101**：复用 alpha191 面板管线（`indicators_tushare/alpha191/ops.py` 的 cs_rank/correlation/ts_* 算子），VWAP=amount×1000/(vol×100)。
- **NaN 策略**：停牌/未满窗输出 NaN 不降级；截面 rank 剔 NaN。

## 3. 分批实施（P0→P8，合计 15~17 个工作日）

- P0（1.5-2天）：`_pit_financial_panel` + 财务四表实际列名核实 + 扩 daily_basic 四列（total_share/float_share/pe_ttm/dv_ratio）并重刷
- P1（1.5天）：Value 11 + Size 3 → 解锁巴菲特价值侧
- P2（3-4天）：Quality 59（最大批，模板化比率）
- P3（1天）：Growth 15
- P4（1.5天）：Liquidity 35（换手率族模板）
- P5（2天）：Risk 25（回归族）
- P6（1天）：Momentum 17 新列 + Reversal 3
- P7（3-4天）：Alpha101 31（表达式翻译+单测）
- P8（2天）：每日增量接入调度（新 systemd timer 17:15，watermark 幂等，仿 alpha191_daily.py）+ 全历史回填 + 验收

**P0-P3 完成即覆盖巴菲特策略全部要素（ROE/毛利率/负债率/FCF/估值/成长）。**

## 4. 增量更新

每日全刷当日截面（不做公告日驱动）；财报修正公告触发受影响股票的 recompute_window。回填与增量共用同一因子函数，重叠日逐位一致（写比对测试锁定）。

## 5. 验收（三层）

1. 自洽：面板实现 vs 单股慢实现抽样逐位一致；回填/增量重叠日一致。
2. 常识值域：rank∈(0,1]、beta截面均值≈1、roe_ttm中位数∈[0,15%] 等，违例阻断入库。
3. 交叉验证：roe_ttm/gross_margin/current_ratio 等与 fina_indicator 现成字段比对（容差1e-6）；earnings_to_price vs 1/pe 相关性>0.95 等。

## 6. 风险清单（摘要，详见 agent-119 方案）

- daily_basic 无 total_share/float_share/pe_ttm → P0 扩列解决
- 扣非净利润=fina_indicator.profit_dedt（待 `\d` 确证）；EBITDA 需拼装；利息费用/递延所得税/长期应收款覆盖率低 → 如实 NaN
- 预收科目 2019 后迁合同负债 → 需 contract_liab 兜底
- 2010 年初截面样本小 → rank 样本<100 时整日 NaN
- 全历史回填规模 ~45 亿单元，估 3-8 小时（4 worker 2-4 小时）；磁盘 40-60GB
- ann_date 缺失行用 end_date 兜底的比例需统计（潜在前视）
- Alpha101 与官方口径细节（min_periods/并列处理）未公开 → 验收降为内部自洽，不追求与官方逐位一致

## 7. 字段核实结果（2026-10-11 已确证）

P0 字段核实**已通过**，关键字段全部存在：
- income：`ebit`/`ebitda`（直连列，无需拼装）✓ `int_exp` ✓ `n_income_attr_p` ✓ `rd_exp` ✓
- balancesheet：`defer_tax_assets`（递延所得税资产）✓ `lt_rec`（长期应收款）✓ `prepayment`（预付）✓ `contract_liab`（合同负债，预收兜底）✓ **`total_share`（总股本）✓ → PIT 面板直接取股本，daily_basic 扩列取消**
- cashflow：`n_cashflow_act` ✓ `n_cashflow_inv_act` ✓ `free_cashflow` ✓ `depr_fa_coga_dpba`/`amort_intang_assets` ✓
- fina_indicator：`roe`/`roe_yearly`/`grossprofit_margin`/`debt_to_assets`/`current_ratio`/`quick_ratio`/`profit_dedt`（扣非净利润）✓

遗留低风险：defer_tax_assets / lt_rec 早年覆盖率可能低（如实 NaN）；daily_basic 的 pe_ttm/dv_ratio 扩列降为可选项。

## 8. 与现有因子入库流程的适配性结论（2026-10-12 核实）

对照 `indicators_tushare/docs/FACTOR_AUTHORING.md`（validate→plan→小样本→backfill→日更接管）：

| 因子类别 | 数量级 | 适用通道 |
|---|---|---|
| 纯量价、pandas_ta 可复现（Momentum 17 新列 + Reversal 3 等） | ~30-40 | ✅ 现有 FACTOR_AUTHORING §3 流程直接适用，只改 yaml 或新增 FactorBase 子类 |
| 基本面/估值/流动性/成长/质量（ROE/毛利率/PE 分位等） | ~130 | ❌ 现有流程 §6 规则 4 明确拒绝非 OHLCV 输入；必须走本方案 P0-P8 的 `_pit_financial_panel` 面板管线 |
| Alpha101（截面排名） | 31 | ❌ 走仿 alpha191 独立面板通道（本方案 §2），不进 validate/backfill 流程 |

结论：现有入库流程**无需改动**即可承接量价类；基本面类与 Alpha101 是本立项新管线覆盖的范围，两通道互补不冲突。
所有通道（含 GUI factor-create 晋升）完成后统一执行 FACTOR_AUTHORING §3-⑦ 的 NL 因子目录快照同步。

## 9. P6 别名映射登记（2026-10-12，通道A已完成入库）

tushare 官方因子名 → 库内等价列（不重复建列）：

| tushare 名 | 库内列 |
|---|---|
| ma_20d | factors.stock_daily_overlap_close.sma_20 |
| dif | factors.stock_daily_momentum_close.macd_12_26_9 |
| dea | factors.stock_daily_momentum_close.macds_12_26_9 |
| rsi | factors.stock_daily_momentum_close.rsi_14 |
| return_5d | factors.stock_daily_performance_close.pctret_5 |

P6 通道A新建列（11）：pctret_21/42/63/126/252（performance_close）；price_position_ir_60、days_down_up、price_dist、rsrs_18_200、macd_cn_12_26_9（momentum_close）。
口径提醒：因子层为 hfq 尺度（CR-2026-10-11 方案A 设计），金标准比对必须按 hfq 口径（原始价 × adj_factor），不能直接对原始价。
通道B（待做）：alpha_125/250/500/1000d_000300、alpha_528/792/1320d_000001 七个回归 Alpha + small_cap_reversal_21d（截面），走 alpha191 式面板管线。
