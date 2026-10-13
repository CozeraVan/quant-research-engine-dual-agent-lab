# factor_specs_p1p3.md — P1-P3 因子实施规范（Value 11 + Size 3 + Growth 15 + Quality 59 = 88）

> 来源：tushare.pro/document/2?doc_id=486（202 因子官方文档），由 plan 子代理（agent-119）整理，2026-10-12。
> **实施必读**：P0 已完成——所有财务字段统一从 `factors._pit_financial_panel`（90 列，(ts_code,trade_date) 主键，2009 起日频 PIT + TTM）读取，**不要**再直接 join fundamentals 四表。列名以 `\d factors._pit_financial_panel` 实际为准（如 inventories / total_share 已在面板内，无需用 daily_basic 反推股本）。
> 本地数据源映射约定（备查）：income / balancesheet / cashflow / fina_indicator 均在 `fundamentals` schema，PIT 对齐 = ann_date <= trade_date 取最新；TTM = 最近 4 个单季之和（流量字段）；时点字段（资产负债表）直接用最新值；单季 Qn = 累计 Qn − 累计 Q(n-1)；官方 {t-4} = 上一同季报告期；{t-63}/{t-252} = 交易日平移（PIT 日频序列上 shift）。
> 截面 rank 因子：主表存原值 + 并列存 `xxx_rank` 列（pct=True, (0,1]），当日有效样本 <100 时整日 rank 置 NaN。
> 分母为 0 或 NULL → 因子值 NaN，禁止填 0。
> 市值：MarketCap = daily_basic.total_mv（万元）；价格用 public.stock_daily.close（原始价）。

## 一、Value（11 个，目标表 factors.stock_daily_value）

### 1. dividend_yield_3y_avg
- 表达式：(SUM(ActualCashDiviRMB, 735) / 3) / ClosePrice
- 输入：fundamentals.dividend（每股实派现金 cash_div_tax，已入库 25 万行至 2026-10-23） + stock_daily.close
- 注意：735 交易日滚动窗口求和 / 3。

### 2. pegh5
- 表达式：EPS_Growth_5Y = (BasicEPS_Y_t / BasicEPS_Y_{t-1260})^(1/5) − 1；PEGH5 = Close / (EPS_Growth_5Y × BasicEPS_TTM)；Factor = −CrossSectionalRank(PEGH5)
- 输入：income.basic_eps（年报口径 Y 与 TTM） + stock_daily.close
- 注意：需 5 年前年报数据，2010–2015 大量 NaN 属正常；增长率 ≤0 时 PEG 无意义置 NaN；存 −rank（官方已取负）。

### 3. etp5
- 表达式：RollingMean(NetProfit_Y, 1260) / RollingMean(MarketCap, 1260)；截面 rank
- 输入：income.n_income（年度口径） + daily_basic.total_mv
- 注意：1260 交易日 ≈ 5 年滚动窗口，在日频 PIT 序列上 rolling(1260).mean()；不满窗 NaN。

### 4. ncf_to_market
- 表达式：(FCF_TTM + ICF_TTM + OCF_TTM) / MarketCap = (n_cashflow_fin_act + n_cashflow_inv_act + n_cashflow_act)_TTM / (close × total_share)
- 输入：cashflow 三分支现金流 TTM + daily_basic.total_mv
- 注意：不做截面 rank（官方未标注 rank，存原值）。

### 5. fcf_to_market
- 表达式：(NOCF_TTM − SICO_TTM) / MarketCap，SICO = 投资现金流出
- 输入：cashflow.n_cashflow_act（TTM） − cashflow.c_paid_invest（TTM） + daily_basic.total_mv
- 注意：投资现金流出用 c_paid_invest + c_paid_acq_const_fiolta 等明细加总，以面板实际列定稿。

### 6. ebitda_to_market
- 表达式：EBITDA / MarketCap
- 输入：income.ebitda（面板已含直连列）+ daily_basic.total_mv

### 7. earnings_to_price
- 表达式：NPParentCompanyOwners_TTM / MarketCap = BasicEPS_TTM / Close
- 输入：income.n_income_attr_p（TTM）或 basic_eps（TTM） + total_mv / close
- 注意：与 1/pe_ttm 交叉验证（相关性应 >0.95）。

### 8. book_to_market
- 表达式：(SE_without_MI + DeferredTaxAssets) / MarketCap
- 输入：balancesheet.total_hldr_eqy_exc_min_int + defer_tax_assets + daily_basic.total_mv
- 注意：递延所得税资产早年 NULL 多，NULL 按 0 处理；与 1/pb 比对时容差放宽。

### 9. earnings_cut_to_market
- 表达式：NetProfitCut_TTM / MarketCap
- 输入：fina_indicator.profit_dedt（扣非净利润 TTM） + daily_basic.total_mv
- 注意：profit_dedt 缺失时降级为归母净利润，报告中标注降级股数。

### 10. ocf_to_market
- 表达式：NetOperateCashFlow_TTM / MarketCap
- 输入：cashflow.n_cashflow_act（TTM） + daily_basic.total_mv

### 11. sales_to_market
- 表达式：OperatingRevenue_Q / MarketCap（官方为单季 Q 口径，非 TTM）
- 输入：income.revenue（单季） + daily_basic.total_mv
- 注意：单季口径季节性波动大，属官方设计，勿改 TTM。

## 二、Size（3 个，目标表 factors.stock_daily_size）

### 1. float_size
- 表达式：−log(FloatShares × ClosePrice / 1e6)
- 输入：daily_basic.circ_mv（万元） → −log(circ_mv×1e4/1e6) 化简
- 注意：值越小市值越大（负对数）。

### 2. nl_size
- 表达式：nlSize = Residual(Size³ ~ Size)，逐日截面回归残差
- 输入：size（见下）
- 注意：**截面因子**，逐日全市场截面 OLS；当日样本 <100 置 NaN；走截面面板层。

### 3. size
- 表达式：−log(TotalShares × ClosePrice / 1e6)
- 输入：daily_basic.total_mv → −log(total_mv×1e4/1e6)

## 三、Growth（15 个，目标表 factors.stock_daily_growth）

| # | 因子名 | 表达式 | 输入字段 | 注意点 |
|---|---|---|---|---|
| 1 | peg_252d | PE = Close/EPS_TTM；EPS_Growth = ts_returns(EPS,252)；PEG = PE/(Growth×100) | basic_eps(TTM) + close | EPS_TTM ≤0 或增长率 ≤0 置 NaN；不 rank |
| 2 | np_ttm_qoq | NetProfit_TTM_t / NetProfit_TTM_{t-1} − 1；截面 rank | n_income_attr_p（TTM） | {t-1}=前一报告期 TTM；基期 ≤0 置 NaN |
| 3 | yoy_net_profit | Value_t/Value_{t-252} − 1 | n_income_attr_p（TTM，PIT 日频 shift 252） | 不 rank；基期 ≤0 NaN |
| 4 | yoy_ocf | OCF_TTM YoY；截面 rank | n_cashflow_act（TTM） | 基期 ≤0 NaN（现金流常跨零，NaN 比例高属预期） |
| 5 | sa | SPS = Revenue_Q/TotalShares；SG = SPS YoY(252)；SA = SG − SG_{t-63}；截面 rank | revenue（单季） + total_share | 加速度=差分的差分，噪声大 |
| 6 | gross_margin_qoq | GrossMargin = (Rev_TTM−Cost_TTM)/Rev_TTM；GPR = GM_t/GM_{t-63} − 1；截面 rank | revenue + oper_cost（TTM） | 与 Quality #31 同源，算一次多表复用 |
| 7 | pa | PG = ROA_t − ROA_{t-252}；PA = PG − PG_{t-63}；截面 rank | fina_indicator.roa | 直通现成 roa |
| 8 | yoy_roa | ROA_TTM YoY；截面 rank | fina_indicator.roa | 同上 |
| 9 | yoy_net_asset | NetAsset YoY；截面 rank | total_hldr_eqy_exc_min_int（时点） | 基期 ≤0 NaN |
| 10 | yoy_revenue | Revenue YoY | revenue（TTM） | 不 rank |
| 11 | yoy_roe | ROE_TTM YoY；截面 rank | fina_indicator.roe | 直通 |
| 12 | yoy_total_asset | TotalAsset YoY；截面 rank | total_assets | |
| 13 | eaa | EGA = EPS_Q_t/EPS_Q_{t-252} − 1；EAA = EGA − EGA_{t-63}；截面 rank | basic_eps（单季） | 单季 EPS 同比再加速度 |
| 14 | eap | EGP = (EPS_Q_t − EPS_Q_{t-252})/Close；EAP = EGP − EGP_{t-63}；截面 rank | basic_eps（单季） + close | close 用当日价（官方如此） |
| 15 | asset_growth_qoq | TotalAssets_t/TotalAssets_{t-1} − 1；截面 rank | total_assets | {t-1}=前一报告期 |

## 四、Quality（59 个，目标表 factors.stock_daily_quality）

**直通 fina_indicator 现成字段（7 个，存原值不 rank）**：roe_ttm_lag63d（=roe，与 #54 同值）、debt_asset_ratio（=debt_to_assets）、quick_ratio、roe_y（=roe_yearly）、current_ratio（=currentratio）、roe_ttm（=roe）。

**需计算的比率/变化因子（52 个，全部截面 rank，除注明外）**：

| # | 因子名 | 表达式 | 输入字段 | 注意点 |
|---|---|---|---|---|
| 3 | eps_ttm | rank(BasicEPS_TTM) | basic_eps（TTM） | |
| 4 | financial_leverage | rank(TotalAssets/TotalShareholderEquity) | total_assets / total_hldr_eqy_inc_min_int | 权益 ≤0 NaN |
| 5 | gpm_ttm | rank((Rev_TTM−Cost_TTM)/Rev_TTM) | revenue, oper_cost | |
| 6 | icr | rank(EBIT_TTM/InterestExpense_TTM) | total_profit + int_exp / int_exp | int_exp 为 0/NULL → NaN，勿填 inf |
| 7 | income_tax_yoy | rank(IncomeTax_TTM_t/IncomeTax_TTM_{t-4} − 1) | income_tax（TTM） | {t-4}=上一同季 |
| 8 | np_to_inventory_yoy | rank((NetProfit_Q/Inventories) 同比 {t-4}) | n_income（单季） + inventories | 存货=0 NaN |
| 9 | npm_q | rank(NetProfit_Q/OperatingRevenue_Q) | n_income, revenue（单季） | |
| 10 | quality_composite | Σ 6 项比率（不 rank）：TotalProfit/TotalAssets；NetProfit/Equity；NetProfit/TotalAssets；(OpCashInflow+InvCashInflow)/TotalAssets；TotalProfit/Revenue；NetProfit/(OpCashInflow+InvCashInflow) | total_profit/n_income + total_assets/equity + cashflow 经营/投资现金流入 | 不 rank；NaN 项剔除后求和 |
| 11 | ar_ap_to_revenue | rank((AdvanceReceipts − AdvancePayment)/Revenue) | adv_receipts − pre_receiv / revenue | ⚠ 新准则后 adv_receipts 大面积 NULL，需加 contract_liab 兜底 |
| 12 | asset_turnover | rank(Revenue_TTM/TotalAssets) | revenue(TTM) / total_assets | |
| 13 | delta_current_ratio | rank(CurrentRatio_t − CurrentRatio_{t-252}) | fina_indicator.currentratio | |
| 14 | delta_de | rank(DE_t − DE_{t-252})，DE=TotalLiab/Equity | total_liab / equity | |
| 15 | gpm_q | rank((Rev−Cost)/Rev)（官方标 TTM 口径） | revenue, oper_cost | 官方描述与 gpm_ttm 相同，按官方表达式实现并注释 |
| 16 | cash_profit_ratio | rank((NOCF_TTM − NetProfit_TTM)/NetProfit_TTM) | n_cashflow_act + n_income（TTM） | 净利润 ≤0 NaN |
| 17 | delta_opm | rank(OPM_t − OPM_{t-252})，OPM=OperateProfit/Revenue | operate_profit / revenue | |
| 18 | eps_q | rank(BasicEPS_Q) | basic_eps（单季） | |
| 19 | eps_y | rank(BasicEPS_Y) | basic_eps（年度） | |
| 20 | delta_npm | rank(NPM_t − NPM_{t-252}) | n_income/revenue | |
| 21 | market_value_leverage | rank((MarketCap − NonCurrentLiability)/MarketCap) | total_mv − total_ncl | |
| 22 | npm_y | rank(NetProfit_Y/Revenue_Y) | 年度 | |
| 23 | opm_y | rank(OperateProfit_Y/Revenue_Y) | 年度 | |
| 25 | delta_gpm | rank(GPM_t − GPM_{t-252}) | revenue, oper_cost | |
| 26 | gpm_y | rank(GPM 年度) | 年度 | |
| 27 | np_to_total_expenses_yoy | rank((NetProfit_Q/(SellExp+AdminExp+FinExp)) 同比 {t-4}) | n_income + sell_exp + admin_exp + fin_exp | 三费和 ≤0 NaN |
| 28 | np_to_deferred_tax_yoy | rank((NetProfit_Q/DeferredTaxAssets) 同比 {t-4}) | n_income + defer_tax_assets | 覆盖率低属预期 |
| 30 | roa_q | rank(NetProfit_Q/TotalAssets) | n_income（单季） + total_assets | |
| 31 | gpm_qoq | rank(GPM_TTM_t/GPM_TTM_{t-63} − 1) | 同 Growth #6，算一次复用 | |
| 32 | delta_inventory_turnover | rank(IT_t − IT_{t-252})，IT=Cost_TTM/Inventories | oper_cost(TTM) + inventories | |
| 33 | delta_roa | rank(ROA_t − ROA_{t-252}) | fina_indicator.roa | |
| 34 | fixed_asset_turnover | rank(Revenue_TTM/FixedAssets) | revenue(TTM) + fix_assets | fix_assets 近 0 → 极端值，存原值 |
| 35 | npm_ttm | rank(NetProfit_TTM/Revenue_TTM) | TTM | |
| 36 | opm_ttm | rank(OperateProfit_TTM/Revenue_TTM) | TTM | |
| 37 | receivable_turnover | rank(Revenue_TTM/AccountsReceivable) | revenue(TTM) + accounts_receiv | 应收=0 NaN |
| 38 | cfcr | rank(NOCF_TTM/InterestExpense_TTM) | n_cashflow_act + int_exp | 同 icr 分母问题 |
| 39 | delta_cash_ratio | rank(CashRatio_t − CashRatio_{t-252})，CashRatio=(Cash+TradingAssets)/CurrentLiab | money_cap + trad_asset / total_cur_liab | |
| 40 | lra_yoy | rank(LTReceivable_t/LTReceivable_{t-4} − 1) | lt_rec | 低覆盖预期 |
| 41 | np_to_fixed_assets_yoy | rank((NetProfit_Q/FixedAssets) 同比 {t-4}) | n_income + fix_assets | |
| 42 | np_to_salary_yoy | rank((NetProfit_TTM/StaffPaid_TTM) 同比 {t-4}) | n_income(TTM) + c_paid_to_for_empl(TTM) | |
| 43 | npm_q_qoq | rank(NPM_Q_t/NPM_Q_{t-1} − 1) | n_income/revenue（单季，{t-1}=上一季） | |
| 44 | npm_tsh | rank(NPParent_TTM / AvgShares)，AvgShares=(总股本 t 与 t-63 均值) ⚠官方表达式疑笔误（写成 Equity 均值） | n_income_attr_p(TTM) + total_share 均值 | 按官方语义（平均总股本）实现并注释笔误 |
| 45 | npm_ttm_qoq | rank(NPM_TTM_t/NPM_TTM_{t-63} − 1) | TTM | |
| 46 | cash_ratio | rank((MoneyCap + TradAsset)/TotalCurLiab) | money_cap + trad_asset / total_cur_liab | |
| 48 | de | TotalLiab/Equity（不 rank） | total_liab / equity | 官方未标 rank |
| 49 | delta_asset_turnover | rank(AT_t − AT_{t-252}) | 同 #12 | |
| 50 | delta_quick_ratio | rank(QuickRatio_t − QuickRatio_{t-252}) | fina_indicator.quick_ratio | |
| 51 | delta_roe | rank(ROE_t − ROE_{t-252}) | fina_indicator.roe | |
| 52 | inventory_turnover | rank(Cost_TTM/Inventories) | oper_cost(TTM) + inventories | |
| 53 | roa_ttm | rank(NetProfit_TTM/TotalAssets) | n_income(TTM) + total_assets | |
| 55 | tax_surcharge_yoy | rank(OperTax_TTM_t/OperTax_TTM_{t-4} − 1) | oper_tax（TTM） | |
| 56 | equity_turnover | rank(Revenue_TTM/Equity) | revenue(TTM) + equity | |
| 57 | expenses_to_equity_yoy | rank((三费_Q/SEWithoutMI) 同比 {t-4}) | sell_exp+admin_exp+fin_exp（单季） + total_hldr_eqy_exc_min_int | |
| 58 | roa_y | rank(NetProfit_Y/TotalAssets) | 年度 | |
| 59 | opt_tpro | rank(OperateProfit_Q/TotalProfit_Q) | operate_profit / total_profit（单季） | 利润总额 ≤0 NaN |

## 通用计算注意点（适用全部 88 因子）

1. **PIT 已由面板保证**：读 `_pit_financial_panel` 即可，面板语义 = ann_date<=trade_date 取最新可见报告期，ffill 日频，流量带 _ttm 后缀。
2. **同比 {t-252}/{t-63}** 在日频面板序列上按交易日 shift；**{t-4}/{t-1}** 在报告期序列上 shift（注意面板是日频 ffill，报告期 shift 需先去重或按 end_date 分组处理）。
3. **rank 列**：`xxx`（原值）与 `xxx_rank`（截面 pct rank, (0,1]）双列并存；当日有效样本 <100 整日 rank 置 NaN。
4. **分母 0/NULL/负值**：除官方明确语义外一律 NaN；基期 ≤0 的增速类一律 NaN，不做符号翻转美化。
5. **单位**：daily_basic 市值万元；fundamentals 金额元；跨表计算先换算。
6. **北交所股**：财务覆盖差，大面积 NaN 属预期，不剔除（rank 自然下沉）。
7. 表结构沿用 factors schema 规范：(ts_code, trade_date) 主键 + hypertable(trade_date, 7天chunk) + trade_date DESC 索引（TimescaleDB 自动建的那个即可，勿重复建），double precision。
