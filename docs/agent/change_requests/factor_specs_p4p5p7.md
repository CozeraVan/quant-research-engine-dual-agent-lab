# factor_specs_p4p5p7.md — P4/P5/P7 因子实施规范（Liquidity 35 + Risk 25 + Alpha101 31 = 91）

> 来源：tushare.pro/document/2?doc_id=486（202 因子官方文档），由 plan 子代理整理，2026-10-18。
> 格式与口径约定同 factor_specs_p1p3.md。本批全部为量价因子，**不涉及** `_pit_financial_panel`。
> **复权口径（全批统一硬规则）**：收益率/滚动窗口/回归一律用 **后复权价 hfq = close × adj_factor**（open/high/low 同理 ×adj_factor）；stock_daily 存的是不复权原始价，计算时现乘，禁止入库前锁死。VWAP 用 stock_daily.vwap 列（已验证 = amount×1000/(vol×100)），不复权。
> **输入面板**（index=trade_date × columns=ts_code，复用 alpha191 面板管线）：
> - public.stock_daily：open/high/low/close/pre_close/vol（手）/amount（千元）/adj_factor/vwap
> - reference.daily_basic：turnover_rate（换手率%，自由流通口径 turnover_rate_f 备用）、total_mv/circ_mv（万元）
> - reference.index_daily：000001.SH（上证）、000300.SH（沪深300）的 close/vol（已确认在同步清单内）
> - 算子库：`indicators_tushare/alpha191/ops.py` 现成（delay/delta/ts_max/ts_min/ts_argmax/ts_rank/ts_sum/stddev/sma/correlation/decay_linear/adv/signedpower/returns/cs_rank/scale）
> **截面 rank**：同 P1-P3 约定——存原值 + `xxx_rank` 双列，当日有效样本 <100 整日 rank 置 NaN。
> **未满窗一律 NaN**（含 1320 日窗口在 2010 年起数据的前段），不降级用不满窗值。
> 落表：P4 → `factors.stock_daily_liquidity`；P5 → `factors.stock_daily_risk`；(ts_code,trade_date) 主键 + hypertable 7 天 chunk。P7 → `factors.stock_daily_alpha101`。
> **两处存疑点已核实（2026-10-18 主代理）**：①alpha191 panel_loader 已乘 adj_factor（hfq，panel_loader.py:91-104），P7 口径直接取齐；②daily_basic.turnover_rate 为百分数口径（000001.SZ 2026-10-16 = 0.573 即 0.573%），P4 均值族存原值并注释单位。

## 一、P4 Liquidity（35 个，目标表 factors.stock_daily_liquidity）

**通用构件**：`DailyTurnoverRate = Volume / AShares`，本地实现**直接用 daily_basic.turnover_rate**（tushare 官方换手率，口径=成交量/流通股本），免去自算 AShares；w_N 表示 N×21 个交易日窗口。

### 换手率均值族（9 个）

| # | 因子名 | 表达式 | 输入 | 窗口 | 注意点 |
|---|---|---|---|---|---|
| 1 | avg_turnover_5d | ts_mean(TurnoverRate, 5) | daily_basic.turnover_rate | 5 | 停牌日 turnover 缺失则该日剔除（pandas rolling 默认行为），官方口径推定为剔 NaN |
| 2 | avg_turnover_10d | ts_mean(·, 10) | 同上 | 10 | |
| 3 | avg_turnover_20d | ts_mean(·, 20) | 同上 | 20 | |
| 8 | avg_turnover_21d | MA(·, 21) | 同上 | 21 | 与 #3 仅窗口差 1，官方两列并存，照算 |
| 15 | avg_turnover_42d | MA(·, 42) | 同上 | 42 | |
| 21 | avg_turnover_63d | MA(·, 63) | 同上 | 63 | |
| 26 | avg_turnover_126d | MA(·, 126) | 同上 | 126 | |
| 33 | avg_turnover_252d | MA(·, 252) | 同上 | 252 | |
| 4 | amount_ma_20d | Mean(TurnoverAmount, 20) | stock_daily.amount（千元） | 20 | 存原值（千元），注意单位注释 |

### 换手率标准差族（6 个）

| # | 因子名 | 表达式 | 窗口 | 注意点 |
|---|---|---|---|---|
| 9 | std_turnover_21d | StdDev(TurnoverRate, 21) | 21 | ddof=1（与 ops.py stddev 一致） |
| 14 | std_turnover_42d | StdDev(·, 42) | 42 | |
| 20 | std_turnover_63d | StdDev(·, 63) | 63 | |
| 27 | std_turnover_126d | StdDev(·, 126) | 126 | |
| 32 | std_turnover_252d | StdDev(·, 252) | 252 | |

### 换手率乖离族（16 个：bias = 短期/长期 − 1）

| # | 因子名 | 表达式 | 窗口 | 注意点 |
|---|---|---|---|---|
| 11 | bias_turn_21d_252d | MA(·,21)/MA(·,252) − 1 | 21/252 | 长期均值为 0 → NaN |
| 10 | bias_std_turn_21d_252d | Std(·,21)/Std(·,252) − 1 | 21/252 | |
| 13 | bias_turn_21d_504d | MA(·,21)/MA(·,504) − 1 | 21/504 | |
| 12 | bias_std_turn_21d_504d | Std(·,21)/Std(·,504) − 1 | 21/504 | |
| 16 | bias_turn_42d_252d | MA(·,42)/MA(·,252) − 1 | 42/252 | |
| 17 | bias_std_turn_42d_252d | Std(·,42)/Std(·,252) − 1 | 42/252 | |
| 19 | bias_turn_42d_504d | MA(·,42)/MA(·,504) − 1 | 42/504 | |
| 18 | bias_std_turn_42d_504d | Std(·,42)/Std(·,504) − 1 | 42/504 | |
| 22 | bias_turn_63d_252d | MA(·,63)/MA(·,252) − 1 | 63/252 | |
| 23 | bias_std_turn_63d_252d | Std(·,63)/Std(·,252) − 1 | 63/252 | |
| 25 | bias_turn_63d_504d | MA(·,63)/MA(·,504) − 1 | 63/504 | |
| 24 | bias_std_turn_63d_504d | Std(·,63)/Std(·,504) − 1 | 63/504 | |
| 28 | bias_turn_126d_252d | MA(·,126)/MA(·,252) − 1 | 126/252 | |
| 29 | bias_std_turn_126d_252d | Std(·,126)/Std(·,252) − 1 | 126/252 | |
| 30 | bias_turn_126d_504d | MA(·,126)/MA(·,504) − 1 | 126/504 | |
| 31 | bias_std_turn_126d_504d | Std(·,126)/Std(·,504) − 1 | 126/504 | |

### 其他流动性因子（5 个）

| # | 因子名 | 表达式 | 输入 | 注意点 |
|---|---|---|---|---|
| 5 | turnover_ma_20d | VolCapRatio = TurnoverVolume/FloatMarketCap；Factor = −MA(VolCapRatio, 20)（short=20，long=0 分支） | stock_daily.vol + daily_basic.circ_mv | 官方注明"结果取负值"，勿漏负号；与 #1 近似但口径为量/流通市值，非换手率，照官方分别实现 |
| 7 | turnover_ma_20d_120d | Factor = −MA(VolCapRatio, 20)/MA(VolCapRatio, 120)（long>0 分支） | 同上 | 长短均值比版 |
| 6 | sum_abs_rtn_amount_20d | Sum(\|Return\|, 20) / Sum(TurnoverAmount, 20) | hfq 日收益 + stock_daily.amount | 收益用 hfq pct_change；amount 单位千元保持原值 |
| 34 | volume_alpha_300d_000001 | VolMomentum = (RollingSum(Volume,5) − Lag(RollingSum(Volume,5),1)) / Lag(·,1)；VolumeAlpha = OLS(StockVolMom ~ IndexVolMom, 300) 截距 | stock_daily.vol + reference.index_daily(000001.SH).vol | 回归族：闭式解 α=ȳ−βx̄ 面板化；指数量序列先与交易日历对齐；不满 300 窗 NaN |
| 35 | volume_alpha_300d_000300 | 同上，基准 000300.SH | 同上(000300.SH) | 同上 |

**P4 复现注意**：①27 个均值/标准差/乖离是同一模板，写一个参数化工件函数批量出列；②全部不 rank（官方未标 CrossSectionalRank）；③turnover_rate 为百分数口径（tushare 给 %），乖离类比值不受影响，均值类存原值即可。

## 二、P5 Risk（25 个，目标表 factors.stock_daily_risk）

**通用构件**：日收益 r = hfq.pct_change()；指数收益 ir = index hfq 等效（指数无 adj_factor，直接 close.pct_change()）。

### 收益波动族（6 个）

| # | 因子名 | 表达式 | 窗口 | 注意点 |
|---|---|---|---|---|
| 2 | return_std_21d | StdDev(r, 21) | 21 | ddof=1 |
| 5 | return_std_42d | StdDev(r, 42) | 42 | |
| 8 | return_std_63d | StdDev(r, 63) | 63 | |
| 13 | return_std_126d | StdDev(r, 126) | 126 | |
| 15 | return_std_252d | StdDev(r, 252) | 252 | |
| 1 | days_beyond_upper_lower_21d | Z=(Close−MA(Close,21))/Std(Close,21)；Factor = #(Z>1) − #(Z<−1) | 21 | Close 用 hfq；计数为整数差 |

### 高低点比族（5 个）

| # | 因子名 | 表达式 | 窗口 | 注意点 |
|---|---|---|---|---|
| 3 | high_low_21d | NetValue=∏(1+r)；Max(NV,21)/Min(NV,21) | 21 | NV 用 hfq 累计净值；窗口内 max/min 同面板 rolling |
| 4 | high_low_42d | 同上 | 42 | |
| 9 | high_low_63d | 同上 | 63 | |
| 12 | high_low_126d | 同上 | 126 | |
| 16 | high_low_252d | 同上 | 252 | |

### 夏普族（3 个）

| # | 因子名 | 表达式 | 窗口 | 注意点 |
|---|---|---|---|---|
| 6 | sharpe_60d | Mean(r,60)/StdDev(r,60) | 60 | 无风险利率取 0（官方未给，照推定）；std=0 NaN |
| 18 | sharpe_750d | Mean(r,750)/StdDev(r,750) | 750 | |
| 19 | adjusted_sharpe_750d | Mean(r,750)/StdDev(r,750)^4 | 750 | 分母为 4 次方，极端小 std → 巨大值，存原值不截尾 |

### Beta 族（8 个）：Beta = Cov(r, ir)/Var(ir) 滚动窗口

| # | 因子名 | 基准 | 窗口 | 注意点 |
|---|---|---|---|---|
| 7 | beta_60d_000300 | 000300.SH | 60 | 面板 rolling.cov/rolling.var，复用 ops.correlation 同款机制 |
| 11 | beta_125d_000300 | 000300.SH | 125 | |
| 14 | beta_250d_000300 | 000300.SH | 250 | |
| 17 | beta_500d_000300 | 000300.SH | 500 | |
| 20 | beta_1000d_000300 | 000300.SH | 1000 | 2010 起前 ~4 年不满窗 NaN 属正常 |
| 22 | beta_1320d_000001 | 000001.SH | 1320 | 前 ~5.5 年 NaN |
| 10 | volume_beta_120d_000300 | 000300.SH | 120 | 量版：VolMomentum 定义同 P4 #34（RollingSum(vol,5) 变化率），Cov/Var 滚动 120 |

### 特质风险族（3 个）：残差 = r − (α+β·ir)，1320 日窗口

| # | 因子名 | 表达式 | 基准 | 注意点 |
|---|---|---|---|---|
| 21 | sigma_1320d_000001 | StdDev(Residual, 1320) | 000001.SH | 同一窗口内先 OLS 出 α/β 再算残差 std；面板闭式解 |
| 24 | sigma_1320d_000300 | 同上 | 000300.SH | |
| 23 | beta_consistency_1320d_000300 | StdDev(Beta × Residual, 1320) | 000300.SH | Beta 为窗口内常数（非时变），注意官方语义=窗口级 β × 逐日残差再求 std |

### 其他（1 个）

| # | 因子名 | 表达式 | 注意点 |
|---|---|---|---|
| 25 | log_price | log(ClosePrice) | Close 用**原始价**（官方未提复权；价格水平因子，复权会破坏"价格"语义），与全批 hfq 规则的例外，注释说明 |

**P5 复现注意**：①回归族 11 个（8 beta + 3 sigma/consistency）+ P4 量回归 2 个 + P6 alpha 7 个共用同一个"滚动 OLS 面板闭式解"工具函数，写一次；②指数与个股交易日对齐用 inner join 交易日历，缺口日该股当日 beta NaN；③全部不 rank。

## 三、P7 Alpha101（31 个，目标表 factors.stock_daily_alpha101）

**通用构件**：Returns = hfq 日收益；VWAP = stock_daily.vwap；ADV20 = adv(Volume, 20)（vol 面板 20 日均量）；截面 Rank = ops.cs_rank（pct，(0,1]）；条件表达式 `cond ? a : b` 用 np.where/pandas mask。逐因子表达式照抄官方（WorldQuant Alpha101 编号即官方选用编号，非连续）：

| # | 因子名 | 官方表达式 | 输入 | 注意点 |
|---|---|---|---|---|
| 1 | alpha101_1 | Rank(Ts_ArgMax(SignedPower(IF(Returns<0, StdDev(Returns,20), Close), 2), 5)) − 0.5 | hfq close, returns | IF 为逐日掩码；StdDev 窗口内遇 NaN→NaN；最外层截面 Rank |
| 2 | alpha101_2 | −1 × Correlation(Rank(Delta(Log(Volume),2)), Rank((Close−Open)/Open), 6) | vol, hfq open/close | 内层两个 Rank 均为截面；Correlation 为时序滚动 6 日 |
| 3 | alpha101_3 | −1 × Correlation(Rank(Open), Rank(Volume), 10) | hfq open, vol | |
| 4 | alpha101_4 | −1 × Ts_Rank(Rank(Low), 9) | hfq low | Ts_Rank 用 ops.ts_rank（pct 末位口径） |
| 5 | alpha101_5 | Rank(Open − Sum(VWAP,10)/10) × (−1 × Abs(Rank(Close − VWAP))) | hfq open/close, vwap | |
| 6 | alpha101_6 | −1 × Correlation(Open, Volume, 10) | hfq open, vol | |
| 7 | alpha101_7 | (ADV20 < Volume) ? (−1 × Ts_Rank(Abs(Delta(Close,7)),60) × Sign(Delta(Close,7))) : −1 | vol, hfq close | 逐日逐股条件，np.where |
| 8 | alpha101_8 | −1 × Rank((Sum(Open,5)×Sum(Returns,5)) − Delay(Sum(Open,5)×Sum(Returns,5),10)) | hfq open, returns | |
| 9 | alpha101_9 | (0<Ts_Min(Delta(Close,1),5)) ? Delta(Close,1) : ((Ts_Max(Delta(Close,1),5)<0) ? Delta(Close,1) : −1×Delta(Close,1)) | hfq close | 嵌套条件；**无截面 rank**，存原值 |
| 10 | alpha101_10 | Rank(#9 的同结构，窗口 4) | hfq close | 先算 #9 逻辑再截面 Rank |
| 11 | alpha101_11 | (Rank(Ts_Max(VWAP−Close,3)) + Rank(Ts_Min(VWAP−Close,3))) × Rank(Delta(Volume,3)) | vwap, hfq close, vol | 三个截面 Rank 组合 |
| 12 | alpha101_12 | Sign(Delta(Volume,1)) × (−1 × Delta(Close,1)) | vol, hfq close | 无 rank |
| 13 | alpha101_13 | −1 × Rank(Covariance(Rank(Close), Rank(Volume), 5)) | hfq close, vol | Covariance=滚动协方差，rolling.cov |
| 14 | alpha101_14 | −1 × Rank(Delta(Returns,3)) × Correlation(Open, Volume, 10) | returns, hfq open, vol | |
| 15 | alpha101_15 | −1 × Sum(Rank(Correlation(Rank(High), Rank(Volume), 3)), 3) | hfq high, vol | Rank 嵌套层级多，逐层验证 |
| 16 | alpha101_16 | −1 × Rank(Covariance(Rank(High), Rank(Volume), 5)) | hfq high, vol | |
| 17 | alpha101_17 | (−1×Rank(Ts_Rank(Close,10))) × Rank(Delta(Delta(Close,1),1)) × Rank(Ts_Rank(Volume/ADV20,5)) | hfq close, vol | |
| 18 | alpha101_18 | −1 × Rank(StdDev(Abs(Close−Open),5) + (Close−Open) + Correlation(Close,Open,10)) | hfq open/close | |
| 19 | alpha101_19 | ((−1×Sign((Close−Delay(Close,7))+Delta(Close,7)))×(1+Rank(1+Sum(Returns,250)))) + ((Rank(Corr(Rank(VWAP−Close),Rank(Volume),12)×Rank(Corr(Rank(Close),Rank(ADV20),12)))×−1)) × Rank(同左乘积) | hfq close, vwap, vol | 全批最长表达式；按官方括号结构拆 4 个中间面板再组合；250 日窗 |
| 20 | alpha101_20 | −1 × Rank(Open−Delay(High,1)) × Rank(Open−Delay(Close,1)) × Rank(Open−Delay(Low,1)) | hfq OHLC | |
| 21 | alpha101_22 | −1 × Delta(Correlation(High,Volume,5),5) × Rank(StdDev(Close,20)) | hfq high/close, vol | |
| 22 | alpha101_23 | (Sum(High,20)/20 < High) ? −1×Delta(High,2) : 0 | hfq high | 条件不满足取 **0**（官方如此，非 NaN） |
| 23 | alpha101_25 | Rank(−1 × Returns × ADV20 × VWAP × (High−Close)) | returns, vol, vwap, hfq high/close | |
| 24 | alpha101_33 | Rank(−1 × (1 − Open/Close)) | hfq open/close | |
| 25 | alpha101_34 | Rank(1 − Rank(StdDev(Returns,2)/StdDev(Returns,5)) + 1 − Rank(Delta(Close,1))) | returns, hfq close | std 分母 0 → NaN |
| 26 | alpha101_41 | (High × Low)^0.5 − VWAP | hfq high/low, vwap | 无 rank，存原值 |
| 27 | alpha101_52 | ((−1×Ts_Min(Low,5)+Delay(Ts_Min(Low,5),5)) × Rank((Sum(Returns,240)−Sum(Returns,20))/220)) × Ts_Rank(Volume,5) | hfq low, returns, vol | 240 日窗，前段 NaN |
| 28 | alpha101_53 | −1 × Delta(((Close−Low)−(High−Close))/(Close−Low), 9) | hfq HLC | C=L 日除零 NaN |
| 29 | alpha101_54 | (−1×(Low−Close)×Open^5) / ((Low−High)×Close^5) | hfq OHLC | 价格 5 次方量级巨大，用 float64 且建议对结果做数值稳定性检查；L=H 除零 NaN |
| 30 | alpha101_57 | −(Close−VWAP) / Decay_Linear(Rank(Ts_ArgMax(Close,30)),2) | hfq close, vwap | decay_linear 用 ops 现成；分母 0 NaN |
| 31 | alpha101_101 | (Close−Open) / ((High−Low)+0.001) | hfq OHLC | 无 rank |

**P7 复现注意**：
1. **全部走 alpha191 面板管线**（index=trade_date × columns=ts_code），截面 Rank 逐日沿 columns 轴；单股流水线不适用。
2. **复权**：官方未说明，推定为复权价（WorldQuant 原文用 adjusted）；统一 hfq 并在表注释声明，与 alpha191 现有口径取齐（已核实 panel_loader 乘 adj_factor）。
3. **VWAP 口径**：stock_daily.vwap 已验证 = amount×1000/(vol×100)，停牌/零量日为 NaN，相关因子当日 NaN。
4. **Rank 并列处理**：ops.cs_rank 为 pct=True 平均法，WorldQuant 原定义未指明，取此口径并注释；这是与官方值无法逐位对账的主要来源之一，验收降为内部自洽+量级检查。
5. **条件表达式**：`cond ? a : b` 逐元素 np.where；条件本身含 NaN 时结果 NaN（不进任一分支）。
6. **窗口 NaN 传播**：rolling 窗口内任一 NaN → 输出 NaN（与 ops.py 现有 ts_argmax/decay_linear 一致），与 alpha191 行为统一。
7. **存储**：31 列入 `factors.stock_daily_alpha101`，与现有 191 列表并列但不同表；日更挂 alpha191_daily 同款 watermark 幂等脚本。

## 通用计算注意点（适用本批 91 因子）

1. **hfq 统一**：除 log_price 外全部收益/窗口/回归基于 hfq=原始价×adj_factor；除权日由 indicators 现有机制触发全历史重算（dispatcher full 模式），本批继承。
2. **指数数据**：000001.SH/000300.SH 均已在 reference.index_daily 同步清单；每日增量依赖 quant-ts 16:30 任务先完成，调度顺序保持在其后。
3. **不 rank**：P4/P5 全部存原值；P7 的 Rank 已内嵌在表达式内（属因子定义一部分），不再额外存 xxx_rank 双列。
4. **NaN 语义**：未满窗/除零/输入 NaN → NaN；仅 alpha101_23 的条件 else 分支按官方取 0。
5. **耗时估算**：P4 模板族秒级/因子；P5+P4 回归族（1320 窗最重）全历史约 0.5–1.5h；P7 参照 alpha191 现有回填耗时量级（同一管线），瓶颈在 ts_argmax/decay_linear 的 rolling.apply，必要时 raw=True + numba 优化。
