# 21_FACTOR_LIBRARY_PLAN.md — Tushare 202 因子本地复现立项方案

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
