# 策略目录 Strategy Catalog

自动生成，共 **111** 个策略变体。

## 目录结构

```
strategies/catalog/
├── trend_following/    # 趋势跟踪 Trend Following
├── mean_reversion/    # 均值回归 Mean Reversion
├── breakout/    # 突破 Breakout
├── cross_sectional/    # 截面因子 Cross-Sectional
├── price_volume/    # 量价因子 Price-Volume
├── kline_pattern/    # K线形态 K-Line Pattern
├── composite/    # 组合增强 Composite
```

## 趋势跟踪 Trend Following

### 趋势跟踪 — 移动平均趋势系统

| ID | 名称 | 难度 |
|----|------|------|
| `tf01a_ma_cross_20_120` | 双均线金叉 MA20/MA120 | ★★☆☆☆ |
| `tf01b_triple_ma_alignment` | 三均线多头排列 MA5/MA10/MA20 | ★★☆☆☆ |
| `tf01c_sma200_bull_filter` | 200日均线牛熊过滤 | ★★☆☆☆ |
| `tf01f_ema_channel_breakout` | EMA通道突破 EMA12/EMA26 | ★★★☆☆ |
| `tf01h_wma_cross_5_20` | WMA加权均线交叉 WMA5/WMA20 | ★★☆☆☆ |

### 趋势跟踪 — MACD 动量系统

| ID | 名称 | 难度 |
|----|------|------|
| `tf02a_macd_golden_cross` | MACD 标准金叉 DIF/DEA | ★★☆☆☆ |
| `tf02b_macd_zero_second_cross` | MACD 零轴上二次金叉 | ★★★☆☆ |
| `tf02e_dif_zero_breakthrough` | MACD DIF 零轴突破 | ★★☆☆☆ |

### 趋势跟踪 — ADX 趋势过滤

| ID | 名称 | 难度 |
|----|------|------|
| `tf03_adx_trend_filter` | ADX 趋势过滤器 +DI/-DI | ★★★☆☆ |

### 趋势跟踪 — Supertrend 动态止损

| ID | 名称 | 难度 |
|----|------|------|
| `tf04_supertrend_breakout` | Supertrend 趋势突破 | ★★★☆☆ |

### 趋势跟踪 — 移动平均趋势系统（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `tf01d_dema_tema_cross` | DEMA/TEMA 响应策略 | ★★★☆☆ |
| `tf01e_hma_cross_20` | HMA 赫尔均线变色 | ★★★☆☆ |
| `tf01g_kama_adaptive_cross` | KAMA 自适应均线交叉 | ★★★☆☆ |
| `tf01i_ma20_slope_positive` | 均线斜率转正 MA20 | ★★☆☆☆ |
| `tf01j_pbo_waterfall` | 瀑布线 PBO 均线族 | ★★★☆☆ |

### 趋势跟踪 — MACD 动量系统（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `tf02c_macd_histogram_slope` | MACD 柱状图斜率反转 | ★★★☆☆ |
| `tf02d_macd_divergence_bottom` | MACD 底背离 | ★★★☆☆ |

### 趋势跟踪 — Ichimoku 云图趋势确认

| ID | 名称 | 难度 |
|----|------|------|
| `tf05a_ichimoku_cloud_breakout` | Ichimoku 云图趋势确认 | ★★★★☆ |

### 趋势跟踪 — 绝对动量 / 双动量

| ID | 名称 | 难度 |
|----|------|------|
| `tf06a_dual_momentum` | 绝对动量 + 相对动量筛选 | ★★★★☆ |

### 趋势跟踪 — 另类趋势指标家族

| ID | 名称 | 难度 |
|----|------|------|
| `tf07a_aroon_trend_confirm` | Aroon 趋势确认 | ★★★☆☆ |
| `tf07b_aroon_oscillator` | Aroon Oscillator 转正 | ★★★☆☆ |
| `tf07c_parabolic_sar_flip` | 抛物线 SAR 翻多 | ★★★☆☆ |
| `tf07d_vortex_indicator` | Vortex 涡旋指标 +VI/-VI | ★★★☆☆ |
| `tf07e_ravi_trend_strength` | RAVI 趋势强度 | ★★★☆☆ |

### 趋势跟踪 — 另类动量中轴家族

| ID | 名称 | 难度 |
|----|------|------|
| `tf08a_tsi_zero_cross` | TSI 真实强度指数零轴突破 | ★★★☆☆ |
| `tf08b_dsi_zero_cross` | DSI 动力指标零轴突破 | ★★★☆☆ |

## 均值回归 Mean Reversion

### 均值回归 — RSI 反转家族

| ID | 名称 | 难度 |
|----|------|------|
| `mr01a_rsi14_oversold_reversal` | RSI(14) 超卖回归 | ★☆☆☆☆ |
| `mr01b_rsi2_connors` | RSI(2) Connors 超卖反弹 | ★★☆☆☆ |
| `mr01c_multi_rsi_resonance` | RSI 多周期共振 RSI(7/14/21) | ★★★☆☆ |
| `mr01f_rsi14_midline_break` | RSI(14) 中轴突破 | ★★☆☆☆ |

### 均值回归 — KDJ / Stochastic 极值反转

| ID | 名称 | 难度 |
|----|------|------|
| `mr02d_williams_r_reversal` | Williams %R 超卖反转 | ★★☆☆☆ |

### 均值回归 — 布林带均值回归

| ID | 名称 | 难度 |
|----|------|------|
| `mr03a_bollinger_lower_reversion` | 布林下轨回归 BOLL(20,2) | ★☆☆☆☆ |
| `mr03b_bollinger_lower_volume` | 布林下轨 + 放量确认 | ★★☆☆☆ |
| `mr03c_bollinger_percent_b` | 布林 %b 极值回归 | ★★☆☆☆ |

### 均值回归 — Double 7 双七策略

| ID | 名称 | 难度 |
|----|------|------|
| `mr06_double7` | 双七策略 Double 7 | ★★☆☆☆ |

### 均值回归 — R3 极端超卖系统

| ID | 名称 | 难度 |
|----|------|------|
| `mr07_r3_extreme_oversold` | R3 极端超卖 RSI(2) | ★★★☆☆ |

### 均值回归 — 均线偏离与缩量止跌

| ID | 名称 | 难度 |
|----|------|------|
| `mr09a_bias_oversold` | 均线偏离 BIAS 超卖回归 | ★★☆☆☆ |
| `mr09b_volume_contraction_reversal` | 缩量止跌反弹 | ★★★☆☆ |

### 均值回归 — 其他摆动指标

| ID | 名称 | 难度 |
|----|------|------|
| `mr10a_cmo_reversal` | CMO 极值反转 | ★★☆☆☆ |
| `mr10b_uo_reversal` | Ultimate Oscillator 极值反转 | ★★☆☆☆ |

### 均值回归 — RSI 反转家族（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `mr01d_rsi_divergence_bottom` | RSI 标准底背离 | ★★★☆☆ |
| `mr01e_rsi_hidden_divergence` | RSI 隐性背离 | ★★★☆☆ |

### 均值回归 — KDJ / Stochastic 极值反转（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `mr02a_kdj_j_line_extreme` | KDJ 极限 J 线 | ★★★☆☆ |
| `mr02b_stochastic_cross` | Stochastic %K/%D 超卖金叉 | ★★☆☆☆ |
| `mr02c_stoch_rsi_slow` | 慢速 StochRSI | ★★★☆☆ |

### 均值回归 — IBS 日内位置反弹

| ID | 名称 | 难度 |
|----|------|------|
| `mr04a_ibs_reversal` | IBS 日内收盘位置反弹 | ★★★☆☆ |

### 均值回归 — CCI 回归与趋势系统

| ID | 名称 | 难度 |
|----|------|------|
| `mr05a_cci_oversold_reversal` | CCI 超卖回归 | ★★☆☆☆ |
| `mr05b_cci_trend_following` | CCI 趋势跟随 | ★★☆☆☆ |

### 均值回归 — MFI 量价反转

| ID | 名称 | 难度 |
|----|------|------|
| `mr08a_mfi_oversold_reversal` | MFI 超卖反转 | ★★☆☆☆ |

## 突破 Breakout

### 突破 — Donchian / 海龟通道突破

| ID | 名称 | 难度 |
|----|------|------|
| `bo01a_donchian_20_breakout` | 海龟通道突破 20日 | ★★☆☆☆ |
| `bo01b_donchian_55_breakout` | 海龟通道突破 55日 | ★★☆☆☆ |

### 突破 — Keltner 通道突破

| ID | 名称 | 难度 |
|----|------|------|
| `bo02_keltner_breakout` | Keltner 通道突破 EMA(20)+2*ATR(10) | ★★★☆☆ |

### 突破 — 52 周新高突破

| ID | 名称 | 难度 |
|----|------|------|
| `bo03_52w_high_breakout` | 52周(250日)新高突破 | ★★☆☆☆ |

### 突破 — Bollinger Squeeze 收缩后突破

| ID | 名称 | 难度 |
|----|------|------|
| `bo05_bollinger_squeeze` | 布林带收缩突破 Bollinger Squeeze | ★★★☆☆ |

### 突破 — 波动率压缩与释放

| ID | 名称 | 难度 |
|----|------|------|
| `bo08a_ma_pinch_breakout` | 均线粘合突破 | ★★★☆☆ |
| `bo08d_dual_vol_breakout` | 双重波动率突破 | ★★★☆☆ |

### 突破 — 结构与回测突破

| ID | 名称 | 难度 |
|----|------|------|
| `bo09a_volume_price_breakout` | 价量突破确认 | ★★☆☆☆ |
| `bo09b_n_breakout` | N字突破 | ★★☆☆☆ |
| `bo09d_three_candle_breakout` | 三连阳突破 | ★★☆☆☆ |

### 突破 — 布林趋势突破

| ID | 名称 | 难度 |
|----|------|------|
| `bo10a_bb_upper_trend_breakout` | 布林上轨趋势突破 | ★★☆☆☆ |

### 突破 — Darvas Box 箱体突破

| ID | 名称 | 难度 |
|----|------|------|
| `bo04a_darvas_box_breakout` | Darvas 箱体突破 | ★★★☆☆ |

### 突破 — ATR 异常波动率动量

| ID | 名称 | 难度 |
|----|------|------|
| `bo06a_atr_anomaly_momentum` | ATR 异常波动突破 | ★★★☆☆ |

### 突破 — Larry Williams 波动率突破

| ID | 名称 | 难度 |
|----|------|------|
| `bo07a_larry_williams_breakout` | Larry Williams 波动率突破 | ★★★☆☆ |

### 突破 — 波动率压缩与释放（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `bo08b_hv20_low_breakout` | 历史波动率低位突破 | ★★★☆☆ |
| `bo08c_atr_ratio_filter` | ATR 比率过滤 + MA 金叉 | ★★★☆☆ |
| `bo08e_amplitude_expansion` | 振幅扩张率突破 | ★★★☆☆ |

### 突破 — 结构与回测突破（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `bo09c_sideways_breakout` | 横盘突破 | ★★★☆☆ |
| `bo09e_channel_retest_breakout` | 通道突破回测 | ★★★☆☆ |
| `bo09f_orb_daily_approx` | ORB 开盘区间突破（日线近似） | ★★★☆☆ |

### 突破 — 布林趋势突破（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `bo10b_bb_lower_rsi_volume` | 布林下轨 + RSI 超卖 + 放量 | ★★☆☆☆ |

## 截面因子 Cross-Sectional

### 截面因子 — 小市值扩展家族

| ID | 名称 | 难度 |
|----|------|------|
| `cs01a_pure_small_cap` | 纯小市值筛选 | ★★★☆☆ |
| `cs01b_small_cap_quality` | 小市值+质量过滤 | ★★★★☆ |
| `cs01c_small_cap_macd_timing` | 小市值+MACD择时 | ★★★★☆ |
| `cs01d_small_cap_low_pb` | 小市值+低PB | ★★★★☆ |

### 截面因子 — Size+Value 双因子排序

| ID | 名称 | 难度 |
|----|------|------|
| `cs02_size_value_ranking` | Size+Value排序 | ★★★★☆ |

### 截面因子 — 低波动因子

| ID | 名称 | 难度 |
|----|------|------|
| `cs03_low_volatility` | 低波动因子筛选 | ★★★☆☆ |

### 截面因子 — 截面与统计动量家族

| ID | 名称 | 难度 |
|----|------|------|
| `cs06a_n_day_return_momentum` | N日收益率动量 | ★★☆☆☆ |
| `cs06b_sharpe_factor` | 夏普率因子 | ★★★☆☆ |
| `cs06c_12_1_momentum_diff` | 12-1动量差 | ★★★☆☆ |
| `cs06d_beta_rotation` | Beta轮动 | ★★★★☆ |
| `cs06e_rs_ranking` | RS Ranking 相对强度排名 | ★★★☆☆ |
| `cs06f_return_skewness` | 收益率分布偏度 | ★★★★☆ |
| `cs06g_max_return_ratio` | 累计最高涨幅占比 | ★★★★☆ |
| `cs06h_overnight_vs_intraday` | 隔夜vs日内收益 | ★★★★☆ |

## 量价因子 Price-Volume

### 量价 — OBV 能量潮

| ID | 名称 | 难度 |
|----|------|------|
| `pv01a_obv_divergence` | OBV 底背离 | ★★★☆☆ |

### 量价 — 量价流量扩展

| ID | 名称 | 难度 |
|----|------|------|
| `pv05c_volume_ratio_breakout` | 量比排行启动 | ★★☆☆☆ |

### 量价 — OBV 能量潮（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `pv01b_obv_ma_cross` | OBV 上穿均线 | ★★☆☆☆ |

### 量价 — CMF 资金流量因子

| ID | 名称 | 难度 |
|----|------|------|
| `pv02a_cmf_money_flow` | CMF 资金流量突破 | ★★★☆☆ |

### 量价 — WorldQuant 风格公式因子

| ID | 名称 | 难度 |
|----|------|------|
| `pv03a_alpha41` | Alpha#41 sqrt(high*low) - vwap | ★★★★☆ |
| `pv03b_alpha101` | Alpha#101 (close-open)/(high-low) | ★★★☆☆ |
| `pv03c_alpha12_style` | Alpha#12 风格 rank(ts_delta(vol,1)) | ★★★★☆ |

### 量价 — 量价流量扩展（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `pv05a_ad_accumulation` | A/D 累积派发线上穿均线 | ★★★☆☆ |
| `pv05b_daily_vwap_support` | 日线 VWAP 连续站上 | ★★★☆☆ |
| `pv05d_eom_ease_of_movement` | EOM 轻松移动上穿零轴 | ★★★☆☆ |
| `pv05e_vpt_volume_price_trend` | VPT 量价趋势上穿均线 | ★★★☆☆ |

## K线形态 K-Line Pattern

### K线形态 — 底部反转形态

| ID | 名称 | 难度 |
|----|------|------|
| `pt01a_hammer_reversal` | 锤头线反转 | ★★★☆☆ |
| `pt01b_bullish_engulfing` | 看涨吞没形态 | ★★★☆☆ |

### K线形态 — 底部反转形态（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `pt01c_morning_star` | 早晨之星 | ★★★★☆ |
| `pt01d_three_white_soldiers` | 三白兵 | ★★★☆☆ |

### K线形态 — 持续与风险形态家族

| ID | 名称 | 难度 |
|----|------|------|
| `pt02a_rising_three_methods` | 上升三法 | ★★★★☆ |
| `pt02b_island_reversal` | 岛形反转 | ★★★★☆ |
| `pt02c_tombstone_doji_exit` | 墓碑十字星高位平仓 | ★★★☆☆ |

### K线形态 — 底部结构形态

| ID | 名称 | 难度 |
|----|------|------|
| `pt03a_double_bottom` | 双底/W底突破颈线 | ★★★★☆ |

## 组合增强 Composite

### 组合增强 — 多信号共振模板

| ID | 名称 | 难度 |
|----|------|------|
| `cb01a_ma_cross_rsi` | 均线金叉 + RSI 确认 | ★★☆☆☆ |
| `cb01d_bb_rsi_volume` | 布林下轨 + RSI 超卖 + 放量 | ★★☆☆☆ |
| `cb01g_turtle_ma60_filter` | 海龟突破 + MA60 过滤 | ★★☆☆☆ |

### 组合增强 — 多信号共振模板（扩展变体）

| ID | 名称 | 难度 |
|----|------|------|
| `cb01b_macd_cross_volume` | MACD金叉+放量 | ★★☆☆☆ |
| `cb01c_adx_rsi_momentum` | ADX趋势+RSI动量 | ★★★☆☆ |
| `cb01e_ma_alignment_kdj` | 均线多头排列+KDJ共振 | ★★★☆☆ |
| `cb01f_new_high_obv_macd` | 新高+OBV+MACD | ★★★☆☆ |
| `cb01h_sideways_rsi_volume` | 横盘+RSI+量能 | ★★★☆☆ |
