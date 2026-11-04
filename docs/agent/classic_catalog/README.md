# 经典策略目录说明（当前 YAML 口径）

> 共 118 个策略。文字说明来自 YAML 注释；实际执行以 YAML 表达式为准。
> 本文只解释规则，不构成收益结论或投资建议。

## 突破（21 个）

### 海龟通道突破 20日 `bo01a_donchian_20_breakout`

- **说明**：价格突破过去 20 日最高价入场，跌破过去 10 日最低价出场。
- **声明的数据依赖**：SMA(60)
- **实际使用指标**：
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(20).max()) & (close > sma_60) / close < close.shift(1).rolling(10).min()
- **实际 YAML 入场**：`(close > close.shift(1).rolling(20).max()) & (close > sma_60)`
- **实际 YAML 出场**：`close < close.shift(1).rolling(10).min()`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 海龟通道突破 55日 `bo01b_donchian_55_breakout`

- **说明**：价格突破过去 55 日最高价入场，跌破过去 20 日最低价出场。更长周期系统。
- **声明的数据依赖**：SMA(60)
- **实际使用指标**：
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(55).max()) & (close > sma_60) / close < close.shift(1).rolling(20).min()
- **实际 YAML 入场**：`(close > close.shift(1).rolling(55).max()) & (close > sma_60)`
- **实际 YAML 出场**：`close < close.shift(1).rolling(20).min()`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### Keltner 通道突破 EMA(20)+2*ATR(10) `bo02_keltner_breakout`

- **说明**：close > EMA(20) + 2*ATR(10) 入场，跌回通道内出场。ATR 通道过滤毛刺。
- **声明的数据依赖**：EMA(20) + ATR(10)
- **实际使用指标**：
  - `atr_10` = 真实波幅(10) （`factors.stock_daily_volatility_close.atr_10`）：真实波幅指标，用于衡量价格波动水平。
  - `ema_20` = 指数移动均线(20) （`factors.stock_daily_overlap_close.ema_20`）：指数移动平均线，对近期价格赋予更高权重。
- **文字入场 / 出场**：(close > ema_20) & (close > ema_20.shift(1)) / close < ema_20
- **实际 YAML 入场**：`(close > ema_20) & (close > ema_20.shift(1))`
- **实际 YAML 出场**：`close < ema_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 52周(250日)新高突破 `bo03_52w_high_breakout`

- **说明**：收盘价创 250 日新高入场，跌破 MA(20) 出场。长期高点突破暗示重新定价。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：close > close.shift(1).rolling(250).max() / close < sma_20
- **实际 YAML 入场**：`close > close.shift(1).rolling(250).max()`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### Darvas 箱体突破 `bo04a_darvas_box_breakout`

- **说明**：价格突破前 20 日整理箱体顶部且放量入场，跌回箱体内出场。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(20).max()) & (vol > vol.shift(1).rolling(20).mean()) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(1).rolling(20).max()) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 布林带收缩突破 Bollinger Squeeze `bo05_bollinger_squeeze`

- **说明**：布林带宽度压缩后价格放量向上突破上轨入场，跌回中轨出场。波动率循环策略。
- **声明的数据依赖**：BOLL(20/2.0) + SMA(20)
- **实际使用指标**：
  - `bbl_20_2_0_2_0` = 布林带下轨(20) （`factors.stock_daily_volatility_close.bbl_20_2_0_2_0`）：布林带下轨，用于观察价格下侧波动边界。
  - `bbm_20_2_0_2_0` = 布林带中轨(20) （`factors.stock_daily_volatility_close.bbm_20_2_0_2_0`）：布林带中轨，用于观察价格中枢。
  - `bbu_20_2_0_2_0` = 布林带上轨(20) （`factors.stock_daily_volatility_close.bbu_20_2_0_2_0`）：布林带上轨，用于观察价格上侧波动边界。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > bbu_20_2_0_2_0) & (close > sma_20) / close < bbm_20_2_0_2_0
- **实际 YAML 入场**：`(close > bbu_20_2_0_2_0) & (close > sma_20)`
- **实际 YAML 出场**：`close < bbm_20_2_0_2_0`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### ATR 异常波动突破 `bo06a_atr_anomaly_momentum`

- **说明**：当日为强势阳线且波动率扩张入场。用当日涨 > 2% 且波动放大近似。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：((close - open) / open > 0.02) & ((high - low) / low > (high.shift(1).rolling(20).mean() - low.shift(1).rolling(20).mean()) / low.shift(1).rolling(20).mean()) / close < sma_20
- **实际 YAML 入场**：`((close - open) / open > 0.02) & ((high - low) / low > (high.shift(1).rolling(20).mean() - low.shift(1).rolling(20).mean()) / low.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### Larry Williams 波动率突破 `bo07a_larry_williams_breakout`

- **说明**：价格突破前收 + 0.25 * 前日波幅入场。极早期捕捉爆发动量。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > open.shift(1) + 0.25 * (high.shift(1) - low.shift(1))) & (close > sma_10) / close < sma_10
- **实际 YAML 入场**：`(close > open.shift(1) + 0.25 * (high.shift(1) - low.shift(1))) & (close > sma_10)`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 均线粘合突破 `bo08a_ma_pinch_breakout`

- **说明**：MA(5)/MA(10)/MA(20) 粘合后向上放量突破入场。
- **声明的数据依赖**：SMA(5,10,20)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_5 > sma_10) & (sma_10 > sma_20) & (close > sma_5) & (close > sma_5.shift(1)) / close < sma_10
- **实际 YAML 入场**：`(sma_5 > sma_10) & (sma_10 > sma_20) & (close > sma_5) & (close > sma_5.shift(1))`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 历史波动率低位突破 `bo08b_hv20_low_breakout`

- **说明**：HV(20) 处于低位并突破布林上轨入场。
- **声明的数据依赖**：BOLL(20/2.0)
- **实际使用指标**：
  - `bbl_20_2_0_2_0` = 布林带下轨(20) （`factors.stock_daily_volatility_close.bbl_20_2_0_2_0`）：布林带下轨，用于观察价格下侧波动边界。
  - `bbm_20_2_0_2_0` = 布林带中轨(20) （`factors.stock_daily_volatility_close.bbm_20_2_0_2_0`）：布林带中轨，用于观察价格中枢。
  - `bbu_20_2_0_2_0` = 布林带上轨(20) （`factors.stock_daily_volatility_close.bbu_20_2_0_2_0`）：布林带上轨，用于观察价格上侧波动边界。
- **文字入场 / 出场**：(close > bbu_20_2_0_2_0) & (vol > vol.shift(1).rolling(20).mean()) / close < bbm_20_2_0_2_0
- **实际 YAML 入场**：`(close > bbu_20_2_0_2_0) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`close < bbm_20_2_0_2_0`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### ATR 比率过滤 + MA 金叉 `bo08c_atr_ratio_filter`

- **说明**：ATR(14) / SMA(20) 极低后配合均线金叉入场。
- **声明的数据依赖**：SMA(5,20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_5 > sma_20) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(sma_5 > sma_20) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### 双重波动率突破 `bo08d_dual_vol_breakout`

- **说明**：创 10 日新高且 SMA(60) 斜率转正入场。趋势与波动共振。
- **声明的数据依赖**：SMA(20,60)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(10).max()) & (sma_60 > sma_60.shift(5)) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(1).rolling(10).max()) & (sma_60 > sma_60.shift(5))`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 振幅扩张率突破 `bo08e_amplitude_expansion`

- **说明**：今日振幅 / 5 日均振幅显著放大并收阳入场。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：((high - low) / low > 1.5 * (high.shift(1).rolling(5).mean() - low.shift(1).rolling(5).mean()) / low.shift(1).rolling(5).mean()) & (close > open) & (close > sma_10) / close < sma_10
- **实际 YAML 入场**：`((high - low) / low > 1.5 * (high.shift(1).rolling(5).mean() - low.shift(1).rolling(5).mean()) / low.shift(1).rolling(5).mean()) & (close > open) & (close > sma_10)`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 价量突破确认 `bo09a_volume_price_breakout`

- **说明**：创 20 日新高且放量收阳入场，跌破 MA(10) 出场。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(20).max()) & (close > open) & (vol > vol.shift(1).rolling(20).mean()) / close < sma_10
- **实际 YAML 入场**：`(close > close.shift(1).rolling(20).max()) & (close > open) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### N字突破 `bo09b_n_breakout`

- **说明**：突破前 10 日高点且仍在 MA(20) 上方入场。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(10).max()) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(1).rolling(10).max()) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 横盘突破 `bo09c_sideways_breakout`

- **说明**：20 日低振幅后放量扩张突破入场。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(20).max()) & (vol > 2 * vol.shift(1).rolling(20).mean()) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(1).rolling(20).max()) & (vol > 2 * vol.shift(1).rolling(20).mean()) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 三连阳突破 `bo09d_three_candle_breakout`

- **说明**：第三根阳线创 10 日新高且量能递增入场。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > open) & (close > close.shift(1).rolling(10).max()) & (vol > vol.shift(1)) / close < sma_10
- **实际 YAML 入场**：`(close > open) & (close > close.shift(1).rolling(10).max()) & (vol > vol.shift(1))`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### 通道突破回测 `bo09e_channel_retest_breakout`

- **说明**：突破 20 日高点后回测不破再上行入场。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_20) & (close.shift(1) > close.shift(1).rolling(20).max()) & (close > close.shift(1)) / close < sma_20
- **实际 YAML 入场**：`(close > sma_20) & (close.shift(1) > close.shift(1).rolling(20).max()) & (close > close.shift(1))`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### ORB 开盘区间突破（日线近似） `bo09f_orb_daily_approx`

- **说明**：以前日 ATR 推导触发带，向上突破入场。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > open.shift(1) + 0.5 * (high.shift(1) - low.shift(1))) & (close > sma_10) / close < sma_10
- **实际 YAML 入场**：`(close > open.shift(1) + 0.5 * (high.shift(1) - low.shift(1))) & (close > sma_10)`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### 布林上轨趋势突破 `bo10a_bb_upper_trend_breakout`

- **说明**：收盘站上上轨且放量入场，跌回中轨出场。沿轨趋势走强。
- **声明的数据依赖**：BOLL(20/2.0)
- **实际使用指标**：
  - `bbl_20_2_0_2_0` = 布林带下轨(20) （`factors.stock_daily_volatility_close.bbl_20_2_0_2_0`）：布林带下轨，用于观察价格下侧波动边界。
  - `bbm_20_2_0_2_0` = 布林带中轨(20) （`factors.stock_daily_volatility_close.bbm_20_2_0_2_0`）：布林带中轨，用于观察价格中枢。
  - `bbu_20_2_0_2_0` = 布林带上轨(20) （`factors.stock_daily_volatility_close.bbu_20_2_0_2_0`）：布林带上轨，用于观察价格上侧波动边界。
- **文字入场 / 出场**：(close > bbu_20_2_0_2_0) & (vol > vol.shift(1).rolling(20).mean()) / close < bbm_20_2_0_2_0
- **实际 YAML 入场**：`(close > bbu_20_2_0_2_0) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`close < bbm_20_2_0_2_0`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 布林下轨 + RSI 超卖 + 放量 `bo10b_bb_lower_rsi_volume`

- **说明**：布林下轨 + RSI(14) < 30 + 放量入场。下轨过度杀跌后的修复，也可视为反转增强。
- **声明的数据依赖**：BOLL(20/2.0) + RSI(14)
- **实际使用指标**：
  - `bbl_20_2_0_2_0` = 布林带下轨(20) （`factors.stock_daily_volatility_close.bbl_20_2_0_2_0`）：布林带下轨，用于观察价格下侧波动边界。
  - `bbm_20_2_0_2_0` = 布林带中轨(20) （`factors.stock_daily_volatility_close.bbm_20_2_0_2_0`）：布林带中轨，用于观察价格中枢。
  - `bbu_20_2_0_2_0` = 布林带上轨(20) （`factors.stock_daily_volatility_close.bbu_20_2_0_2_0`）：布林带上轨，用于观察价格上侧波动边界。
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：(close < bbl_20_2_0_2_0) & (rsi_14 < 30) & (vol > vol.shift(1).rolling(20).mean()) / close > bbm_20_2_0_2_0
- **实际 YAML 入场**：`(close < bbl_20_2_0_2_0) & (rsi_14 < 30) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`close > bbm_20_2_0_2_0`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

## 其他（1 个）

### gui_accept_rsi14_reversal `gui_accept_rsi14_reversal`

- **说明**：原策略文件未提供文字说明；以实际 YAML 规则为准。
- **声明的数据依赖**：
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**： / 
- **实际 YAML 入场**：`(rsi_14 < 30.0)`
- **实际 YAML 出场**：`(rsi_14 > 70.0)`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

## 复合（8 个）

### 均线金叉 + RSI 确认 `cb01a_ma_cross_rsi`

- **说明**：MA(5) 上穿 MA(20) 且 RSI(14) > 50 入场，RSI < 50 或跌破 MA(10) 出场。
- **声明的数据依赖**：SMA(5,10,20) + RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_5 > sma_20) & (rsi_14 > 50) / (rsi_14 < 50) | (close < sma_10)
- **实际 YAML 入场**：`(sma_5 > sma_20) & (rsi_14 > 50)`
- **实际 YAML 出场**：`(rsi_14 < 50) | (close < sma_10)`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### MACD金叉+放量 `cb01b_macd_cross_volume`

- **说明**：MACD金叉且放量确认入场。双条件减少假突破噪音。
- **声明的数据依赖**：MACD(12/26/9)
- **实际使用指标**：
  - `macd_12_26_9` = MACD(12,26,9) （`factors.stock_daily_momentum_close.macd_12_26_9`）：MACD 的 DIF 快线，反映快慢指数均线之差。
  - `macds_12_26_9` = MACD 信号线(12,26,9) （`factors.stock_daily_momentum_close.macds_12_26_9`）：MACD 的 DEA 慢线，即 DIF 的信号线。
- **文字入场 / 出场**：(macd_12_26_9 > macds_12_26_9) & (vol > vol.shift(1).rolling(20).mean()) / macd_12_26_9 < macds_12_26_9
- **实际 YAML 入场**：`(macd_12_26_9 > macds_12_26_9) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`macd_12_26_9 < macds_12_26_9`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### ADX趋势+RSI动量 `cb01c_adx_rsi_momentum`

- **说明**：ADX>25 + RSI(14)>50 入场。趋势明确且动量确认。
- **声明的数据依赖**：ADX(14) + RSI(14)
- **实际使用指标**：
  - `adx_14` = 平均趋向指数(14) （`factors.stock_daily_trend_close.adx_14`）：平均趋向指标，用于衡量趋势强度而非方向。
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：(adx_14 > 25) & (rsi_14 > 50) / (adx_14 < 20) | (rsi_14 < 45)
- **实际 YAML 入场**：`(adx_14 > 25) & (rsi_14 > 50)`
- **实际 YAML 出场**：`(adx_14 < 20) | (rsi_14 < 45)`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 布林下轨 + RSI 超卖 + 放量 `cb01d_bb_rsi_volume`

- **说明**：布林下轨 + RSI(14) < 30 + 放量入场。三重确认均值回归。
- **声明的数据依赖**：BOLL(20/2.0) + RSI(14)
- **实际使用指标**：
  - `bbl_20_2_0_2_0` = 布林带下轨(20) （`factors.stock_daily_volatility_close.bbl_20_2_0_2_0`）：布林带下轨，用于观察价格下侧波动边界。
  - `bbm_20_2_0_2_0` = 布林带中轨(20) （`factors.stock_daily_volatility_close.bbm_20_2_0_2_0`）：布林带中轨，用于观察价格中枢。
  - `bbu_20_2_0_2_0` = 布林带上轨(20) （`factors.stock_daily_volatility_close.bbu_20_2_0_2_0`）：布林带上轨，用于观察价格上侧波动边界。
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：(close < bbl_20_2_0_2_0) & (rsi_14 < 30) & (vol > vol.shift(1).rolling(20).mean()) / close > bbm_20_2_0_2_0
- **实际 YAML 入场**：`(close < bbl_20_2_0_2_0) & (rsi_14 < 30) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`close > bbm_20_2_0_2_0`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 均线多头排列+KDJ共振 `cb01e_ma_alignment_kdj`

- **说明**：MA(5/10/20)多头排列且RSI超卖回归入场。
- **声明的数据依赖**：SMA(5,10,20) + RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_5 > sma_10) & (sma_10 > sma_20) & (rsi_14 > 50) / (rsi_14 < 50) | (close < sma_10)
- **实际 YAML 入场**：`(sma_5 > sma_10) & (sma_10 > sma_20) & (rsi_14 > 50)`
- **实际 YAML 出场**：`(rsi_14 < 50) | (close < sma_10)`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 新高+OBV+MACD `cb01f_new_high_obv_macd`

- **说明**：创20日新高+RSI>50+MACD金叉且价格>MA(60)入场。三重趋势确认。
- **声明的数据依赖**：MACD(12/26/9) + RSI(14) + SMA(60)
- **实际使用指标**：
  - `macd_12_26_9` = MACD(12,26,9) （`factors.stock_daily_momentum_close.macd_12_26_9`）：MACD 的 DIF 快线，反映快慢指数均线之差。
  - `macds_12_26_9` = MACD 信号线(12,26,9) （`factors.stock_daily_momentum_close.macds_12_26_9`）：MACD 的 DEA 慢线，即 DIF 的信号线。
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(20).max()) & (rsi_14 > 50) & (macd_12_26_9 > macds_12_26_9) & (close > sma_60) / macd_12_26_9 < macds_12_26_9
- **实际 YAML 入场**：`(close > close.shift(1).rolling(20).max()) & (rsi_14 > 50) & (macd_12_26_9 > macds_12_26_9) & (close > sma_60)`
- **实际 YAML 出场**：`macd_12_26_9 < macds_12_26_9`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 海龟突破 + MA60 过滤 `cb01g_turtle_ma60_filter`

- **说明**：突破 20 日高点且价格 > MA(60) 入场，跌破 10 日低点出场。
- **声明的数据依赖**：SMA(60)
- **实际使用指标**：
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(20).max()) & (close > sma_60) / close < close.shift(1).rolling(10).min()
- **实际 YAML 入场**：`(close > close.shift(1).rolling(20).max()) & (close > sma_60)`
- **实际 YAML 出场**：`close < close.shift(1).rolling(10).min()`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 横盘+RSI+量能 `cb01h_sideways_rsi_volume`

- **说明**：20日振幅<15%且RSI上穿50且放量入场。整理后方向突破。
- **声明的数据依赖**：SMA(20) + RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：((close.shift(1).rolling(20).max() - close.shift(1).rolling(20).min()) / close.shift(1).rolling(20).mean() < 0.15) & (rsi_14 > 50) & (vol > vol.shift(1).rolling(20).mean()) / rsi_14 < 50
- **实际 YAML 入场**：`((close.shift(1).rolling(20).max() - close.shift(1).rolling(20).min()) / close.shift(1).rolling(20).mean() < 0.15) & (rsi_14 > 50) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`rsi_14 < 50`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

## 截面因子（17 个）

### 纯小市值筛选 `cs01a_pure_small_cap`

- **说明**：做多最小市值分组。用RSI低位+长期均线上方近似。
- **声明的数据依赖**：RSI(14) + SMA(200)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 < 50) & (close > sma_200) / rsi_14 > 70
- **实际 YAML 入场**：`(rsi_14 < 50) & (close > sma_200)`
- **实际 YAML 出场**：`rsi_14 > 70`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### 小市值+质量过滤 `cs01b_small_cap_quality`

- **说明**：小市值叠加ROE>0、资产负债率<60%。用均线上方+低RSI近似。
- **声明的数据依赖**：RSI(14) + SMA(20,200)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 < 40) & (close > sma_200) & (close > sma_20) / rsi_14 > 65
- **实际 YAML 入场**：`(rsi_14 < 40) & (close > sma_200) & (close > sma_20)`
- **实际 YAML 出场**：`rsi_14 > 65`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### 小市值+MACD择时 `cs01c_small_cap_macd_timing`

- **说明**：MACD多头区间持有小市值。
- **声明的数据依赖**：MACD(12/26/9) + SMA(20,60)
- **实际使用指标**：
  - `macd_12_26_9` = MACD(12,26,9) （`factors.stock_daily_momentum_close.macd_12_26_9`）：MACD 的 DIF 快线，反映快慢指数均线之差。
  - `macds_12_26_9` = MACD 信号线(12,26,9) （`factors.stock_daily_momentum_close.macds_12_26_9`）：MACD 的 DEA 慢线，即 DIF 的信号线。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(macd_12_26_9 > macds_12_26_9) & (close > sma_20) / macd_12_26_9 < macds_12_26_9
- **实际 YAML 入场**：`(macd_12_26_9 > macds_12_26_9) & (close > sma_20)`
- **实际 YAML 出场**：`macd_12_26_9 < macds_12_26_9`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### 小市值+低PB `cs01d_small_cap_low_pb`

- **说明**：小市值池内再找PB低分位。用RSI低位+均线过滤近似。
- **声明的数据依赖**：RSI(14) + SMA(60,200)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 < 35) & (close > sma_200) & (close > sma_60) / rsi_14 > 60
- **实际 YAML 入场**：`(rsi_14 < 35) & (close > sma_200) & (close > sma_60)`
- **实际 YAML 出场**：`rsi_14 > 60`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### Size+Value排序 `cs02_size_value_ranking`

- **说明**：size+value双因子打分选综合排名靠前组。用均线+RSI低吸近似。
- **声明的数据依赖**：RSI(14) + SMA(60,200)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 < 40) & (close > sma_200) & (close > sma_60) / rsi_14 > 65
- **实际 YAML 入场**：`(rsi_14 < 40) & (close > sma_200) & (close > sma_60)`
- **实际 YAML 出场**：`rsi_14 > 65`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### 低波动因子筛选 `cs03_low_volatility`

- **说明**：做多过去20/60/120日波动率较低的一组。用波动率收缩+均线过滤近似。
- **声明的数据依赖**：SMA(20,200)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_200) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(close > sma_200) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### N日收益率动量 `cs06a_n_day_return_momentum`

- **说明**：短期累计收益超过阈值后顺势跟进。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(20)) & (close > sma_20) & (close > close.shift(1)) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(20)) & (close > sma_20) & (close > close.shift(1))`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 夏普率因子 `cs06b_sharpe_factor`

- **说明**：20日均收益/20日标准差大于阈值入场。
- **声明的数据依赖**：SMA(20) + RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_20) & (rsi_14 > 50) & (close > close.shift(20)) / close < sma_20
- **实际 YAML 入场**：`(close > sma_20) & (rsi_14 > 50) & (close > close.shift(20))`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 12-1动量差 `cs06c_12_1_momentum_diff`

- **说明**：250日收益减去20日收益仍为正，去除短期反转效应的长趋势股。
- **声明的数据依赖**：SMA(20,200)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(250)) & (close > sma_200) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(250)) & (close > sma_200) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### Beta轮动 `cs06d_beta_rotation`

- **说明**：大盘上行环境中做多高Beta股票。用指数均线方向+价格强势近似。
- **声明的数据依赖**：SMA(20,60)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_20 > sma_60) & (close > sma_20) & (close > close.shift(20)) / sma_20 < sma_60
- **实际 YAML 入场**：`(sma_20 > sma_60) & (close > sma_20) & (close > close.shift(20))`
- **实际 YAML 出场**：`sma_20 < sma_60`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### RS Ranking 相对强度排名 `cs06e_rs_ranking`

- **说明**：近60日涨幅排名前20%买入。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(60)) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(60)) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 收益率分布偏度 `cs06f_return_skewness`

- **说明**：偏度显著为正且平均收益为正入场。用上升趋势+均线过滤近似。
- **声明的数据依赖**：SMA(20,60)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_20) & (sma_20 > sma_60) & (close > close.shift(60)) / close < sma_20
- **实际 YAML 入场**：`(close > sma_20) & (sma_20 > sma_60) & (close > close.shift(60))`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 累计最高涨幅占比 `cs06g_max_return_ratio`

- **说明**：短期涨幅占全年涨幅比例极高。用动量加速近似。
- **声明的数据依赖**：SMA(10,20)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_10 > sma_20) & (close > close.shift(20)) & (close > sma_20) / close < sma_10
- **实际 YAML 入场**：`(sma_10 > sma_20) & (close > close.shift(20)) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 隔夜vs日内收益 `cs06h_overnight_vs_intraday`

- **说明**：连续数日收盘强于开盘且伴随向上跳空入场。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > open) & (close.shift(1) > open.shift(1)) & (close > close.shift(1)) & (close > sma_10) / close < sma_10
- **实际 YAML 入场**：`(close > open) & (close.shift(1) > open.shift(1)) & (close > close.shift(1)) & (close > sma_10)`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### cs07a_mf001_atrr14_high_hv20_normal_mvp `cs07a_mf001_atrr14_high_hv20_normal_mvp`

- **说明**：原策略文件未提供文字说明；以实际 YAML 规则为准。
- **声明的数据依赖**：
- **实际使用指标**：
  - `mf_001` = mf_001 （`cluster.mined_factor_flags.mf_001`）：聚类研究挖掘的因子标记，具体含义以研究产物为准。
- **文字入场 / 出场**：mf_001 == 1（T 日信号，T+1 开盘成交） / 持有满 5 日（对齐 M3b +5 窗口）或止损触发
- **实际 YAML 入场**：`mf_001 == 1`
- **实际 YAML 出场**：``
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### cs07b_mf002_alpha072_low_mvp `cs07b_mf002_alpha072_low_mvp`

- **说明**：原策略文件未提供文字说明；以实际 YAML 规则为准。
- **声明的数据依赖**：
- **实际使用指标**：
  - `mf_002` = mf_002 （`cluster.mined_factor_flags.mf_002`）：聚类研究挖掘的因子标记，具体含义以研究产物为准。
- **文字入场 / 出场**：mf_002 == 1（T 日信号，T+1 开盘成交） / 持有满 5 日（对齐 M3b +5 窗口）或止损触发
- **实际 YAML 入场**：`mf_002 == 1`
- **实际 YAML 出场**：``
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### cs07c_mf003_alpha082_low_mvp `cs07c_mf003_alpha082_low_mvp`

- **说明**：原策略文件未提供文字说明；以实际 YAML 规则为准。
- **声明的数据依赖**：
- **实际使用指标**：
  - `mf_003` = mf_003 （`cluster.mined_factor_flags.mf_003`）：聚类研究挖掘的因子标记，具体含义以研究产物为准。
- **文字入场 / 出场**：mf_003 == 1（T 日信号，T+1 开盘成交） / 持有满 5 日（对齐 M3b +5 窗口）或止损触发
- **实际 YAML 入场**：`mf_003 == 1`
- **实际 YAML 出场**：``
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

## K 线形态（8 个）

### 锤头线反转 `pt01a_hammer_reversal`

- **说明**：连续下跌后出现锤头线（下影线 > 2*实体）且量能放大入场。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：((close - low) > 2 * (close - open).abs()) & (vol > vol.shift(1)) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`((close - low) > 2 * (close - open).abs()) & (vol > vol.shift(1)) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### 看涨吞没形态 `pt01b_bullish_engulfing`

- **说明**：阳线实体完全覆盖前一日阴线实体，且成交量放大入场。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > open) & (open.shift(1) > close.shift(1)) & (close > open.shift(1)) & (open < close.shift(1)) & (vol > vol.shift(1)) / close < sma_10
- **实际 YAML 入场**：`(close > open) & (open.shift(1) > close.shift(1)) & (close > open.shift(1)) & (open < close.shift(1)) & (vol > vol.shift(1))`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### 早晨之星 `pt01c_morning_star`

- **说明**：三 K 线结构：阴线+小实体+阳线收复首根 50% 以上。用三日反转近似。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > open) & (close.shift(1) < open.shift(1)) & (close > close.shift(2)) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(close > open) & (close.shift(1) < open.shift(1)) & (close > close.shift(2)) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### 三白兵 `pt01d_three_white_soldiers`

- **说明**：连续三根温和放量小阳线入场。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > open) & (close.shift(1) > open.shift(1)) & (close.shift(2) > open.shift(2)) & (close > close.shift(1)) & (close.shift(1) > close.shift(2)) & (vol > vol.shift(1)) & (close > sma_10) / close < sma_10
- **实际 YAML 入场**：`(close > open) & (close.shift(1) > open.shift(1)) & (close.shift(2) > open.shift(2)) & (close > close.shift(1)) & (close.shift(1) > close.shift(2)) & (vol > vol.shift(1)) & (close > sma_10)`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 上升三法 `pt02a_rising_three_methods`

- **说明**：强趋势中的空中加油。用趋势突破+缩量回调+再突破近似。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_20) & (close > close.shift(1).rolling(5).max()) & (vol > vol.shift(1)) / close < sma_20
- **实际 YAML 入场**：`(close > sma_20) & (close > close.shift(1).rolling(5).max()) & (vol > vol.shift(1))`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 岛形反转 `pt02b_island_reversal`

- **说明**：双跳空封闭前缺口。用量价背离+趋势反转近似。
- **声明的数据依赖**：SMA(20,60)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close < sma_60) & (close > open) & (close > sma_20) & (vol > vol.shift(1).rolling(10).mean()) / close < sma_20
- **实际 YAML 入场**：`(close < sma_60) & (close > open) & (close > sma_20) & (vol > vol.shift(1).rolling(10).mean())`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 墓碑十字星高位平仓 `pt02c_tombstone_doji_exit`

- **说明**：高位长上影放天量。做空头出场/短线反转信号。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：((high - close) / (high - low + 0.001) > 0.7) & (vol > 2 * vol.shift(1).rolling(20).mean()) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`((high - close) / (high - low + 0.001) > 0.7) & (vol > 2 * vol.shift(1).rolling(20).mean()) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### 双底/W底突破颈线 `pt03a_double_bottom`

- **说明**：两低点接近，突破颈线入场。用突破30日高点+均线过滤近似。
- **声明的数据依赖**：SMA(20,60)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(30).max()) & (close > sma_20) & (close > sma_60) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(1).rolling(30).max()) & (close > sma_20) & (close > sma_60)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

## 均值回归（23 个）

### RSI(14) 超卖回归 `mr01a_rsi14_oversold_reversal`

- **说明**：RSI(14) 下破 30 后重新站回 30 入场，RSI > 60 出场。
- **声明的数据依赖**：RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：rsi_14 > 30 / rsi_14 > 60
- **实际 YAML 入场**：`rsi_14 > 30`
- **实际 YAML 出场**：`rsi_14 > 60`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### RSI(2) Connors 超卖反弹 `mr01b_rsi2_connors`

- **说明**：close > SMA(200) 且 RSI(2) < 10 入场，RSI(2) > 70 出场。
- **声明的数据依赖**：RSI(2) + SMA(200)
- **实际使用指标**：
  - `rsi_2` = 相对强弱指标(2) （`factors.stock_daily_momentum_close.rsi_2`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_200) & (rsi_2 < 10) / rsi_2 > 70
- **实际 YAML 入场**：`(close > sma_200) & (rsi_2 < 10)`
- **实际 YAML 出场**：`rsi_2 > 70`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### RSI 多周期共振 RSI(7/14/21) `mr01c_multi_rsi_resonance`

- **说明**：RSI(7)、RSI(14)、RSI(21) 同时低于 30 入场，任一高于 60 出场。
- **声明的数据依赖**：RSI(7,14,21)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `rsi_21` = 相对强弱指标(21) （`factors.stock_daily_momentum_close.rsi_21`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `rsi_7` = 相对强弱指标(7) （`factors.stock_daily_momentum_close.rsi_7`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：(rsi_7 < 30) & (rsi_14 < 30) & (rsi_21 < 30) / (rsi_7 > 60) | (rsi_14 > 60) | (rsi_21 > 60)
- **实际 YAML 入场**：`(rsi_7 < 30) & (rsi_14 < 30) & (rsi_21 < 30)`
- **实际 YAML 出场**：`(rsi_7 > 60) | (rsi_14 > 60) | (rsi_21 > 60)`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### RSI 标准底背离 `mr01d_rsi_divergence_bottom`

- **说明**：价格创 20 日新低但 RSI(14) 不创新低入场。价格与动量背离的经典信号。
- **声明的数据依赖**：RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：(close < close.shift(1).rolling(20).min()) & (rsi_14 > rsi_14.shift(20)) / rsi_14 > 60
- **实际 YAML 入场**：`(close < close.shift(1).rolling(20).min()) & (rsi_14 > rsi_14.shift(20))`
- **实际 YAML 出场**：`rsi_14 > 60`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### RSI 隐性背离 `mr01e_rsi_hidden_divergence`

- **说明**：价格更高低点、RSI 更低低点，趋势延续型入场。
- **声明的数据依赖**：RSI(14) + SMA(20)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 < 50) & (close > sma_20) & (rsi_14 < rsi_14.shift(5)) / rsi_14 > 60
- **实际 YAML 入场**：`(rsi_14 < 50) & (close > sma_20) & (rsi_14 < rsi_14.shift(5))`
- **实际 YAML 出场**：`rsi_14 > 60`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### RSI(14) 中轴突破 `mr01f_rsi14_midline_break`

- **说明**：RSI(14) 上穿 50 入场，下穿 50 出场。动量中轴切换。
- **声明的数据依赖**：RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：rsi_14 > 50 / rsi_14 < 50
- **实际 YAML 入场**：`rsi_14 > 50`
- **实际 YAML 出场**：`rsi_14 < 50`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### KDJ 极限 J 线 `mr02a_kdj_j_line_extreme`

- **说明**：J < 0 后拐头上行配合低位金叉入场，J > 100 出场。用 Williams %R 近似。
- **声明的数据依赖**：WILLIAMS_R(14) + SMA(60)
- **实际使用指标**：
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `willr_14` = 威廉指标(14) （`factors.stock_daily_momentum_close.willr_14`）：威廉指标，用于观察短期超买与超卖区域。
- **文字入场 / 出场**：(willr_14 > -95) & (close > sma_60) / willr_14 > -10
- **实际 YAML 入场**：`(willr_14 > -95) & (close > sma_60)`
- **实际 YAML 出场**：`willr_14 > -10`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### Stochastic %K/%D 超卖金叉 `mr02b_stochastic_cross`

- **说明**：%K 在 20 以下上穿 %D 入场，80 以上死叉出场。用 Williams %R 近似。
- **声明的数据依赖**：WILLIAMS_R(14) + SMA(50)
- **实际使用指标**：
  - `sma_50` = 简单移动均线(50) （`factors.stock_daily_overlap_close.sma_50`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `willr_14` = 威廉指标(14) （`factors.stock_daily_momentum_close.willr_14`）：威廉指标，用于观察短期超买与超卖区域。
- **文字入场 / 出场**：(willr_14 > -80) & (willr_14 > willr_14.shift(1)) & (close > sma_50) / willr_14 > -20
- **实际 YAML 入场**：`(willr_14 > -80) & (willr_14 > willr_14.shift(1)) & (close > sma_50)`
- **实际 YAML 出场**：`willr_14 > -20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 慢速 StochRSI `mr02c_stoch_rsi_slow`

- **说明**：StochRSI K 线在 0.2 以下上穿 D 线入场。用 RSI(14) 极值近似。
- **声明的数据依赖**：RSI(14) + SMA(200)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 < 25) & (close > sma_200) & (rsi_14 > rsi_14.shift(1)) / rsi_14 > 50
- **实际 YAML 入场**：`(rsi_14 < 25) & (close > sma_200) & (rsi_14 > rsi_14.shift(1))`
- **实际 YAML 出场**：`rsi_14 > 50`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### Williams %R 超卖反转 `mr02d_williams_r_reversal`

- **说明**：%R 上穿 -80 入场，下穿 -20 出场。利用短期极端位置进行反转交易。
- **声明的数据依赖**：WILLIAMS_R(14) + SMA(60)
- **实际使用指标**：
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `willr_14` = 威廉指标(14) （`factors.stock_daily_momentum_close.willr_14`）：威廉指标，用于观察短期超买与超卖区域。
- **文字入场 / 出场**：(willr_14 > -80) & (close > sma_60) / willr_14 > -20
- **实际 YAML 入场**：`(willr_14 > -80) & (close > sma_60)`
- **实际 YAML 出场**：`willr_14 > -20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### 布林下轨回归 BOLL(20,2) `mr03a_bollinger_lower_reversion`

- **说明**：close < 布林下轨入场，回到中轨出场。价格偏离统计均值后回归中心。
- **声明的数据依赖**：BOLL(20/2.0) + RSI(14)
- **实际使用指标**：
  - `bbl_20_2_0_2_0` = 布林带下轨(20) （`factors.stock_daily_volatility_close.bbl_20_2_0_2_0`）：布林带下轨，用于观察价格下侧波动边界。
  - `bbm_20_2_0_2_0` = 布林带中轨(20) （`factors.stock_daily_volatility_close.bbm_20_2_0_2_0`）：布林带中轨，用于观察价格中枢。
  - `bbu_20_2_0_2_0` = 布林带上轨(20) （`factors.stock_daily_volatility_close.bbu_20_2_0_2_0`）：布林带上轨，用于观察价格上侧波动边界。
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：(close < bbl_20_2_0_2_0) & (rsi_14 < 40) / close > bbm_20_2_0_2_0
- **实际 YAML 入场**：`(close < bbl_20_2_0_2_0) & (rsi_14 < 40)`
- **实际 YAML 出场**：`close > bbm_20_2_0_2_0`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 布林下轨 + 放量确认 `mr03b_bollinger_lower_volume`

- **说明**：close < 布林下轨 + RSI(14) < 30 + 成交量放大，回到中轨出场。
- **声明的数据依赖**：BOLL(20/2.0) + RSI(14)
- **实际使用指标**：
  - `bbl_20_2_0_2_0` = 布林带下轨(20) （`factors.stock_daily_volatility_close.bbl_20_2_0_2_0`）：布林带下轨，用于观察价格下侧波动边界。
  - `bbm_20_2_0_2_0` = 布林带中轨(20) （`factors.stock_daily_volatility_close.bbm_20_2_0_2_0`）：布林带中轨，用于观察价格中枢。
  - `bbu_20_2_0_2_0` = 布林带上轨(20) （`factors.stock_daily_volatility_close.bbu_20_2_0_2_0`）：布林带上轨，用于观察价格上侧波动边界。
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：(close < bbl_20_2_0_2_0) & (rsi_14 < 30) / close > bbm_20_2_0_2_0
- **实际 YAML 入场**：`(close < bbl_20_2_0_2_0) & (rsi_14 < 30)`
- **实际 YAML 出场**：`close > bbm_20_2_0_2_0`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 布林 %b 极值回归 `mr03c_bollinger_percent_b`

- **说明**：%b < 0 (价格完全在下轨以下) 入场，%b > 0.5 (回到中轴上方) 出场。
- **声明的数据依赖**：BOLL(20/2.0)
- **实际使用指标**：
  - `bbl_20_2_0_2_0` = 布林带下轨(20) （`factors.stock_daily_volatility_close.bbl_20_2_0_2_0`）：布林带下轨，用于观察价格下侧波动边界。
  - `bbm_20_2_0_2_0` = 布林带中轨(20) （`factors.stock_daily_volatility_close.bbm_20_2_0_2_0`）：布林带中轨，用于观察价格中枢。
  - `bbu_20_2_0_2_0` = 布林带上轨(20) （`factors.stock_daily_volatility_close.bbu_20_2_0_2_0`）：布林带上轨，用于观察价格上侧波动边界。
- **文字入场 / 出场**：close < bbl_20_2_0_2_0 / close > bbm_20_2_0_2_0
- **实际 YAML 入场**：`close < bbl_20_2_0_2_0`
- **实际 YAML 出场**：`close > bbm_20_2_0_2_0`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### IBS 日内收盘位置反弹 `mr04a_ibs_reversal`

- **说明**：IBS = (close - low) / (high - low) < 0.2 且 close > SMA(200) 入场。收盘接近日内低点。
- **声明的数据依赖**：SMA(200)
- **实际使用指标**：
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：((close - low) / (high - low + 0.001) < 0.2) & (close > sma_200) / (close - low) / (high - low + 0.001) > 0.5
- **实际 YAML 入场**：`((close - low) / (high - low + 0.001) < 0.2) & (close > sma_200)`
- **实际 YAML 出场**：`(close - low) / (high - low + 0.001) > 0.5`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### CCI 超卖回归 `mr05a_cci_oversold_reversal`

- **说明**：CCI 从 -100 下方回归向上入场，CCI > 100 出场。用 RSI 近似。
- **声明的数据依赖**：RSI(14) + SMA(20)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 > 25) & (close > sma_20) / rsi_14 > 70
- **实际 YAML 入场**：`(rsi_14 > 25) & (close > sma_20)`
- **实际 YAML 出场**：`rsi_14 > 70`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### CCI 趋势跟随 `mr05b_cci_trend_following`

- **说明**：CCI > +100 连续 2 日入场，跌回 +100 以下出场。用 RSI 强势区近似。
- **声明的数据依赖**：RSI(14) + SMA(10)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 > 65) & (close > sma_10) / rsi_14 < 55
- **实际 YAML 入场**：`(rsi_14 > 65) & (close > sma_10)`
- **实际 YAML 出场**：`rsi_14 < 55`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 双七策略 Double 7 `mr06_double7`

- **说明**：close > SMA(200) 且收盘创 7 日新低入场，创 7 日新高出场。大趋势向上时的短期超跌反弹。
- **声明的数据依赖**：SMA(200)
- **实际使用指标**：
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_200) & (close < close.shift(7)) / close > close.shift(1).rolling(7).max()
- **实际 YAML 入场**：`(close > sma_200) & (close < close.shift(7))`
- **实际 YAML 出场**：`close > close.shift(1).rolling(7).max()`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### R3 极端超卖 RSI(2) `mr07_r3_extreme_oversold`

- **说明**：close > SMA(200)、RSI(2) 连续 3 日下跌、当日 RSI(2) < 10 入场。只抓最极端回归点。
- **声明的数据依赖**：RSI(2) + SMA(200)
- **实际使用指标**：
  - `rsi_2` = 相对强弱指标(2) （`factors.stock_daily_momentum_close.rsi_2`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_200) & (rsi_2 < 10) / rsi_2 > 70
- **实际 YAML 入场**：`(close > sma_200) & (rsi_2 < 10)`
- **实际 YAML 出场**：`rsi_2 > 70`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### MFI 超卖反转 `mr08a_mfi_oversold_reversal`

- **说明**：MFI < 20 后重新站回 20 入场（需确认 MFI 因子列）。用 RSI + 量比近似。
- **声明的数据依赖**：RSI(14) + SMA(60)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 < 30) & (close > sma_60) & (rsi_14 > rsi_14.shift(1)) / rsi_14 > 60
- **实际 YAML 入场**：`(rsi_14 < 30) & (close > sma_60) & (rsi_14 > rsi_14.shift(1))`
- **实际 YAML 出场**：`rsi_14 > 60`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 均线偏离 BIAS 超卖回归 `mr09a_bias_oversold`

- **说明**：偏离 MA(20) 超过 -5% 且当日收阳入场，回归到 -1% 上方出场。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：((close - sma_20) / sma_20 < -0.05) & (close > open) / (close - sma_20) / sma_20 > -0.01
- **实际 YAML 入场**：`((close - sma_20) / sma_20 < -0.05) & (close > open)`
- **实际 YAML 出场**：`(close - sma_20) / sma_20 > -0.01`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 缩量止跌反弹 `mr09b_volume_contraction_reversal`

- **说明**：股价在 MA(60) 上方，连续 3 日缩量后收阳确认入场。
- **声明的数据依赖**：SMA(60)
- **实际使用指标**：
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_60) & (close > open) & (vol < vol.shift(1)) & (vol.shift(1) < vol.shift(2)) / close < sma_60
- **实际 YAML 入场**：`(close > sma_60) & (close > open) & (vol < vol.shift(1)) & (vol.shift(1) < vol.shift(2))`
- **实际 YAML 出场**：`close < sma_60`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### CMO 极值反转 `mr10a_cmo_reversal`

- **说明**：CMO(14) 上穿 -50 入场，下穿 +50 出场。钱德动量摆动指标。
- **声明的数据依赖**：RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：rsi_14 > 35 / rsi_14 > 65
- **实际 YAML 入场**：`rsi_14 > 35`
- **实际 YAML 出场**：`rsi_14 > 65`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### Ultimate Oscillator 极值反转 `mr10b_uo_reversal`

- **说明**：UO 上穿 30 入场，下穿 70 出场。多周期加权摆动指标。
- **声明的数据依赖**：RSI(14) + SMA(20)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 < 35) & (close > sma_20) / rsi_14 > 65
- **实际 YAML 入场**：`(rsi_14 < 35) & (close > sma_20)`
- **实际 YAML 出场**：`rsi_14 > 65`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

## 量价（14 个）

### OBV 底背离 `pv01a_obv_divergence`

- **说明**：OBV 均线上穿入场，价格下跌时资金吸筹的确认信号。
- **声明的数据依赖**：SMA(20) + RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 < 40) & (close > sma_20) / rsi_14 > 60
- **实际 YAML 入场**：`(rsi_14 < 40) & (close > sma_20)`
- **实际 YAML 出场**：`rsi_14 > 60`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### OBV 上穿均线 `pv01b_obv_ma_cross`

- **说明**：OBV 上穿自身均线入场（需确认 OBV 因子列）。用 RSI 金叉 + 放量近似。
- **声明的数据依赖**：RSI(14) + SMA(20)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 > 50) & (close > sma_20) & (vol > vol.shift(1).rolling(20).mean()) / rsi_14 < 50
- **实际 YAML 入场**：`(rsi_14 > 50) & (close > sma_20) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`rsi_14 < 50`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### CMF 资金流量突破 `pv02a_cmf_money_flow`

- **说明**：CMF(21) > +0.2 入场（需确认 CMF 因子列）。用 RSI 强势 + 放量近似。
- **声明的数据依赖**：RSI(14) + SMA(20)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 > 55) & (close > sma_20) & (vol > vol.shift(1).rolling(20).mean()) / rsi_14 < 45
- **实际 YAML 入场**：`(rsi_14 > 55) & (close > sma_20) & (vol > vol.shift(1).rolling(20).mean())`
- **实际 YAML 出场**：`rsi_14 < 45`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### Alpha#41 sqrt(high*low) - vwap `pv03a_alpha41`

- **说明**：sqrt(high * low) - VWAP > 0 入场。用价格站上均线近似。
- **声明的数据依赖**：SMA(5)
- **实际使用指标**：
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_5) & (close > open) & (vol > vol.shift(1).rolling(5).mean()) / close < sma_5
- **实际 YAML 入场**：`(close > sma_5) & (close > open) & (vol > vol.shift(1).rolling(5).mean())`
- **实际 YAML 出场**：`close < sma_5`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### Alpha#101 (close-open)/(high-low) `pv03b_alpha101`

- **说明**：(close - open) / (high - low + 0.001) > 0.7 入场。实体占比高的强势阳线。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：((close - open) / (high - low + 0.001) > 0.7) & (close > open) & (close > sma_10) / (close - open) / (high - low + 0.001) < 0.3
- **实际 YAML 入场**：`((close - open) / (high - low + 0.001) > 0.7) & (close > open) & (close > sma_10)`
- **实际 YAML 出场**：`(close - open) / (high - low + 0.001) < 0.3`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### Alpha#12 风格 rank(ts_delta(vol,1)) `pv03c_alpha12_style`

- **说明**：成交量变化率排名因子。用放量涨 > 1.5 倍均量近似。
- **声明的数据依赖**：SMA(10)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(vol > 1.5 * vol.shift(1).rolling(20).mean()) & (close > open) & (close > sma_10) / close < sma_10
- **实际 YAML 入场**：`(vol > 1.5 * vol.shift(1).rolling(20).mean()) & (close > open) & (close > sma_10)`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### A/D 累积派发线上穿均线 `pv05a_ad_accumulation`

- **说明**：A/D 线上穿自身均线入场（需确认 A/D 因子列）。用 OBV 近似。
- **声明的数据依赖**：RSI(14) + SMA(20)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 > 50) & (close > sma_20) & (vol > vol.shift(1)) / rsi_14 < 45
- **实际 YAML 入场**：`(rsi_14 > 50) & (close > sma_20) & (vol > vol.shift(1))`
- **实际 YAML 出场**：`rsi_14 < 45`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### 日线 VWAP 连续站上 `pv05b_daily_vwap_support`

- **说明**：连续两日收盘高于日线 VWAP（需确认 VWAP 因子列）。用两日连阳量增近似。
- **声明的数据依赖**：SMA(5)
- **实际使用指标**：
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > open) & (close.shift(1) > open.shift(1)) & (vol > vol.shift(1)) & (close > sma_5) / close < sma_5
- **实际 YAML 入场**：`(close > open) & (close.shift(1) > open.shift(1)) & (vol > vol.shift(1)) & (close > sma_5)`
- **实际 YAML 出场**：`close < sma_5`
- **持仓 / 风控**：最长 3 天；止损 0.08；止盈 —；移动止损 —。

### 量比排行启动 `pv05c_volume_ratio_breakout`

- **说明**：当日放量（量比 > 1.5 倍 20 日均量）且价格站上均线入场。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(vol > 1.5 * vol.shift(1).rolling(20).mean()) & (close > sma_20) & (close > open) / close < sma_20
- **实际 YAML 入场**：`(vol > 1.5 * vol.shift(1).rolling(20).mean()) & (close > sma_20) & (close > open)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### EOM 轻松移动上穿零轴 `pv05d_eom_ease_of_movement`

- **说明**：EOM 上穿 0 入场（需确认 EOM 因子列）。用价格 + 量比方向近似。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > open) & (vol > vol.shift(1)) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(close > open) & (vol > vol.shift(1)) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### VPT 量价趋势上穿均线 `pv05e_vpt_volume_price_trend`

- **说明**：VPT 上穿 5 日均线入场（需确认 VPT 因子列）。用量增价涨近似。
- **声明的数据依赖**：SMA(5)
- **实际使用指标**：
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_5) & (vol > vol.shift(1).rolling(5).mean()) & (close > open) / close < sma_5
- **实际 YAML 入场**：`(close > sma_5) & (vol > vol.shift(1).rolling(5).mean()) & (close > open)`
- **实际 YAML 出场**：`close < sma_5`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### Alpha083 高秩量价背离（高位 rank 做多） `pv06a_alpha083_high_rank_mvp`

- **说明**：alpha083=-RANK(COV(RANK(HIGH),RANK(VOL),5))，量高价背离度截面 rank 取负；值越接近 0 排名越前。entry>-0.2=截面前 20%%，exit<-0.5=跌出前一半。
- **声明的数据依赖**：factors.stock_daily_alpha191.alpha083
- **实际使用指标**：
  - `alpha083` = 高价排名与量排名5日协方差（反向） （`factors.stock_daily_alpha191.alpha083`）：Alpha191 横截面量价信号，具体含义以该编号公式为准。
- **文字入场 / 出场**：alpha083 > -0.2 / alpha083 < -0.5
- **实际 YAML 入场**：`alpha083 > -0.2`
- **实际 YAML 出场**：`alpha083 < -0.5`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### Alpha099 高秩收盘价量背离（高位 rank 做多） `pv06b_alpha099_high_rank_mvp`

- **说明**：alpha099=-RANK(COV(RANK(CLOSE),RANK(VOL),5))，与 alpha083 同族（HIGH→CLOSE）。entry>-0.2=截面前 20%%，exit<-0.5=跌出前一半。
- **声明的数据依赖**：factors.stock_daily_alpha191.alpha099
- **实际使用指标**：
  - `alpha099` = 收盘排名与量排名5日协方差（反向） （`factors.stock_daily_alpha191.alpha099`）：Alpha191 横截面量价信号，具体含义以该编号公式为准。
- **文字入场 / 出场**：alpha099 > -0.2 / alpha099 < -0.5
- **实际 YAML 入场**：`alpha099 > -0.2`
- **实际 YAML 出场**：`alpha099 < -0.5`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### Alpha042 低波高价量正相关（高值做多） `pv06c_alpha042_high_rank_mvp`

- **说明**：alpha042=(-RANK(STD(HIGH,10)))*CORR(HIGH,VOL,10)，低波动且价量正相关者值高。entry>0.0≈截面前 12%%（p90=0.015），exit<-0.25≈跌破中位数(-0.24)。
- **声明的数据依赖**：factors.stock_daily_alpha191.alpha042
- **实际使用指标**：
  - `alpha042` = 高价10日波动排名乘高价量相关（反向） （`factors.stock_daily_alpha191.alpha042`）：Alpha191 横截面量价信号，具体含义以该编号公式为准。
- **文字入场 / 出场**：alpha042 > 0.0 / alpha042 < -0.25
- **实际 YAML 入场**：`alpha042 > 0.0`
- **实际 YAML 出场**：`alpha042 < -0.25`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

## 趋势跟踪（26 个）

### 双均线金叉 MA20/MA120 `tf01a_ma_cross_20_120`

- **说明**：MA(20) 上穿 MA(120) 入场，下穿出场。经典中长期趋势跟踪。
- **声明的数据依赖**：SMA(20,120)
- **实际使用指标**：
  - `sma_120` = 简单移动均线(120) （`factors.stock_daily_overlap_close.sma_120`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：sma_20 > sma_120 / sma_20 < sma_120
- **实际 YAML 入场**：`sma_20 > sma_120`
- **实际 YAML 出场**：`sma_20 < sma_120`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### 三均线多头排列 MA5/MA10/MA20 `tf01b_triple_ma_alignment`

- **说明**：MA(5) > MA(10) > MA(20) 且收盘站上 MA(5)，跌破 MA(10) 出场。
- **声明的数据依赖**：SMA(5,10,20)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_5 > sma_10) & (sma_10 > sma_20) & (close > sma_5) / close < sma_10
- **实际 YAML 入场**：`(sma_5 > sma_10) & (sma_10 > sma_20) & (close > sma_5)`
- **实际 YAML 出场**：`close < sma_10`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 200日均线牛熊过滤 `tf01c_sma200_bull_filter`

- **说明**：close > SMA(200) 且 SMA(20) 向上拐头入场，跌破 SMA(200) 出场。
- **声明的数据依赖**：SMA(20,200)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_200` = 简单移动均线(200) （`factors.stock_daily_overlap_close.sma_200`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > sma_200) & (sma_20 > sma_20.shift(1)) / close < sma_200
- **实际 YAML 入场**：`(close > sma_200) & (sma_20 > sma_20.shift(1))`
- **实际 YAML 出场**：`close < sma_200`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### DEMA/TEMA 响应策略 `tf01d_dema_tema_cross`

- **说明**：DEMA(20) 上穿 DEMA(60) 入场，下穿出场。双指数平滑，减少滞后。
- **声明的数据依赖**：EMA(20,60)
- **实际使用指标**：
  - `ema_20` = 指数移动均线(20) （`factors.stock_daily_overlap_close.ema_20`）：指数移动平均线，对近期价格赋予更高权重。
  - `ema_60` = 指数移动均线(60) （`factors.stock_daily_overlap_close.ema_60`）：指数移动平均线，对近期价格赋予更高权重。
- **文字入场 / 出场**：ema_20 > ema_60 / ema_20 < ema_60
- **实际 YAML 入场**：`ema_20 > ema_60`
- **实际 YAML 出场**：`ema_20 < ema_60`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### HMA 赫尔均线变色 `tf01e_hma_cross_20`

- **说明**：HMA(20) 由下转上入场，向下拐头出场。赫尔均线低延迟。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_20 > sma_20.shift(1)) & (close > sma_20) / sma_20 < sma_20.shift(1)
- **实际 YAML 入场**：`(sma_20 > sma_20.shift(1)) & (close > sma_20)`
- **实际 YAML 出场**：`sma_20 < sma_20.shift(1)`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### EMA通道突破 EMA12/EMA26 `tf01f_ema_channel_breakout`

- **说明**：close 突破 EMA(12) + 1.5*(EMA12 - EMA26)，跌破 EMA(26) 出场。
- **声明的数据依赖**：EMA(12,26)
- **实际使用指标**：
  - `ema_12` = 指数移动均线(12) （`factors.stock_daily_overlap_close.ema_12`）：指数移动平均线，对近期价格赋予更高权重。
  - `ema_26` = 指数移动均线(26) （`factors.stock_daily_overlap_close.ema_26`）：指数移动平均线，对近期价格赋予更高权重。
- **文字入场 / 出场**：(ema_12 > ema_12.shift(1)) & (close > ema_12) / close < ema_26
- **实际 YAML 入场**：`(ema_12 > ema_12.shift(1)) & (close > ema_12)`
- **实际 YAML 出场**：`close < ema_26`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### KAMA 自适应均线交叉 `tf01g_kama_adaptive_cross`

- **说明**：KAMA(10,2,30) 上穿 KAMA(20,2,30) 入场，下穿出场。自适应调整平滑系数。
- **声明的数据依赖**：EMA(10,20)
- **实际使用指标**：
  - `ema_10` = 指数移动均线(10) （`factors.stock_daily_overlap_close.ema_10`）：指数移动平均线，对近期价格赋予更高权重。
  - `ema_20` = 指数移动均线(20) （`factors.stock_daily_overlap_close.ema_20`）：指数移动平均线，对近期价格赋予更高权重。
- **文字入场 / 出场**：ema_10 > ema_20 / ema_10 < ema_20
- **实际 YAML 入场**：`ema_10 > ema_20`
- **实际 YAML 出场**：`ema_10 < ema_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### WMA加权均线交叉 WMA5/WMA20 `tf01h_wma_cross_5_20`

- **说明**：WMA(5) 上穿 WMA(20) 入场，下穿出场。
- **声明的数据依赖**：WMA(5,20)
- **实际使用指标**：
  - `wma_20` = 加权移动均线(20) （`factors.stock_daily_overlap_close.wma_20`）：加权移动平均线，用于平滑价格与判断趋势。
  - `wma_5` = 加权移动均线(5) （`factors.stock_daily_overlap_close.wma_5`）：加权移动平均线，用于平滑价格与判断趋势。
- **文字入场 / 出场**：wma_5 > wma_20 / wma_5 < wma_20
- **实际 YAML 入场**：`wma_5 > wma_20`
- **实际 YAML 出场**：`wma_5 < wma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### 均线斜率转正 MA20 `tf01i_ma20_slope_positive`

- **说明**：MA(20) 5 日斜率由负转正且价格站上 MA(20) 入场。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_20 > sma_20.shift(5)) & (close > sma_20) / sma_20 < sma_20.shift(5)
- **实际 YAML 入场**：`(sma_20 > sma_20.shift(5)) & (close > sma_20)`
- **实际 YAML 出场**：`sma_20 < sma_20.shift(5)`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 瀑布线 PBO 均线族 `tf01j_pbo_waterfall`

- **说明**：PB1-PB6 发散向上，回踩 PB3 支撑入场。
- **声明的数据依赖**：SMA(5,10,20,30,60)
- **实际使用指标**：
  - `sma_10` = 简单移动均线(10) （`factors.stock_daily_overlap_close.sma_10`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_30` = 简单移动均线(30) （`factors.stock_daily_overlap_close.sma_30`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_5 > sma_10) & (sma_10 > sma_20) & (sma_20 > sma_30) & (close > sma_20) / close < sma_30
- **实际 YAML 入场**：`(sma_5 > sma_10) & (sma_10 > sma_20) & (sma_20 > sma_30) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_30`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### MACD 标准金叉 DIF/DEA `tf02a_macd_golden_cross`

- **说明**：DIF 上穿 DEA 入场，下穿出场。最经典的 MACD 用法。
- **声明的数据依赖**：MACD(12/26/9)
- **实际使用指标**：
  - `macd_12_26_9` = MACD(12,26,9) （`factors.stock_daily_momentum_close.macd_12_26_9`）：MACD 的 DIF 快线，反映快慢指数均线之差。
  - `macds_12_26_9` = MACD 信号线(12,26,9) （`factors.stock_daily_momentum_close.macds_12_26_9`）：MACD 的 DEA 慢线，即 DIF 的信号线。
- **文字入场 / 出场**：macd_12_26_9 > macds_12_26_9 / macd_12_26_9 < macds_12_26_9
- **实际 YAML 入场**：`macd_12_26_9 > macds_12_26_9`
- **实际 YAML 出场**：`macd_12_26_9 < macds_12_26_9`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### MACD 零轴上二次金叉 `tf02b_macd_zero_second_cross`

- **说明**：DIF、DEA 均 > 0，回抽零轴后再次金叉入场。
- **声明的数据依赖**：MACD(12/26/9)
- **实际使用指标**：
  - `macd_12_26_9` = MACD(12,26,9) （`factors.stock_daily_momentum_close.macd_12_26_9`）：MACD 的 DIF 快线，反映快慢指数均线之差。
  - `macds_12_26_9` = MACD 信号线(12,26,9) （`factors.stock_daily_momentum_close.macds_12_26_9`）：MACD 的 DEA 慢线，即 DIF 的信号线。
- **文字入场 / 出场**：(macd_12_26_9 > 0) & (macds_12_26_9 > 0) & (macd_12_26_9 > macds_12_26_9) / macd_12_26_9 < macds_12_26_9
- **实际 YAML 入场**：`(macd_12_26_9 > 0) & (macds_12_26_9 > 0) & (macd_12_26_9 > macds_12_26_9)`
- **实际 YAML 出场**：`macd_12_26_9 < macds_12_26_9`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### MACD 柱状图斜率反转 `tf02c_macd_histogram_slope`

- **说明**：MACD 柱状图在负值区连续 3 天缩短，配合 RSI(14) 超卖入场。
- **声明的数据依赖**：MACD(12/26/9) + RSI(14)
- **实际使用指标**：
  - `macd_12_26_9` = MACD(12,26,9) （`factors.stock_daily_momentum_close.macd_12_26_9`）：MACD 的 DIF 快线，反映快慢指数均线之差。
  - `macds_12_26_9` = MACD 信号线(12,26,9) （`factors.stock_daily_momentum_close.macds_12_26_9`）：MACD 的 DEA 慢线，即 DIF 的信号线。
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：(macd_12_26_9 > macd_12_26_9.shift(1)) & (rsi_14 < 40) / macd_12_26_9 < macds_12_26_9
- **实际 YAML 入场**：`(macd_12_26_9 > macd_12_26_9.shift(1)) & (rsi_14 < 40)`
- **实际 YAML 出场**：`macd_12_26_9 < macds_12_26_9`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### MACD 底背离 `tf02d_macd_divergence_bottom`

- **说明**：价格创 20 日新低但 DIF 未创新低入场。
- **声明的数据依赖**：MACD(12/26/9)
- **实际使用指标**：
  - `macd_12_26_9` = MACD(12,26,9) （`factors.stock_daily_momentum_close.macd_12_26_9`）：MACD 的 DIF 快线，反映快慢指数均线之差。
  - `macds_12_26_9` = MACD 信号线(12,26,9) （`factors.stock_daily_momentum_close.macds_12_26_9`）：MACD 的 DEA 慢线，即 DIF 的信号线。
- **文字入场 / 出场**：(close < close.shift(1).rolling(20).min()) & (macd_12_26_9 > macd_12_26_9.shift(20)) / macd_12_26_9 < macds_12_26_9
- **实际 YAML 入场**：`(close < close.shift(1).rolling(20).min()) & (macd_12_26_9 > macd_12_26_9.shift(20))`
- **实际 YAML 出场**：`macd_12_26_9 < macds_12_26_9`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。

### MACD DIF 零轴突破 `tf02e_dif_zero_breakthrough`

- **说明**：DIF (= EMA12 - EMA26) 上穿 0 入场，下穿 0 出场。
- **声明的数据依赖**：EMA(12,26)
- **实际使用指标**：
  - `ema_12` = 指数移动均线(12) （`factors.stock_daily_overlap_close.ema_12`）：指数移动平均线，对近期价格赋予更高权重。
  - `ema_26` = 指数移动均线(26) （`factors.stock_daily_overlap_close.ema_26`）：指数移动平均线，对近期价格赋予更高权重。
- **文字入场 / 出场**：(ema_12 - ema_26) > 0 / (ema_12 - ema_26) < 0
- **实际 YAML 入场**：`(ema_12 - ema_26) > 0`
- **实际 YAML 出场**：`(ema_12 - ema_26) < 0`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### ADX 趋势过滤器 +DI/-DI `tf03_adx_trend_filter`

- **说明**：+DI > -DI 且 ADX > 25 且 ADX 上升入场，+DI < -DI 出场。只在趋势明确时持有。
- **声明的数据依赖**：ADX(14) + SMA(20)
- **实际使用指标**：
  - `adx_14` = 平均趋向指数(14) （`factors.stock_daily_trend_close.adx_14`）：平均趋向指标，用于衡量趋势强度而非方向。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(adx_14 > 25) & (close > sma_20) / (adx_14 < 20) | (close < sma_20)
- **实际 YAML 入场**：`(adx_14 > 25) & (close > sma_20)`
- **实际 YAML 出场**：`(adx_14 < 20) | (close < sma_20)`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### Supertrend 趋势突破 `tf04_supertrend_breakout`

- **说明**：价格向上突破 Supertrend 轨道入场，跌回轨道下方出场。基于 ATR 的自适应趋势通道。
- **声明的数据依赖**：ATR(10) + EMA(20)
- **实际使用指标**：
  - `atr_10` = 真实波幅(10) （`factors.stock_daily_volatility_close.atr_10`）：真实波幅指标，用于衡量价格波动水平。
  - `ema_20` = 指数移动均线(20) （`factors.stock_daily_overlap_close.ema_20`）：指数移动平均线，对近期价格赋予更高权重。
- **文字入场 / 出场**：(close > ema_20) & (close > ema_20.shift(1)) / close < ema_20
- **实际 YAML 入场**：`(close > ema_20) & (close > ema_20.shift(1))`
- **实际 YAML 出场**：`close < ema_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### Ichimoku 云图趋势确认 `tf05a_ichimoku_cloud_breakout`

- **说明**：Tenkan > Kijun，价格在 Senkou A/B 云层之上入场，Tenkan < Kijun 出场。
- **声明的数据依赖**：SMA(9,26,52)
- **实际使用指标**：
  - `sma_26` = 简单移动均线(26) （`factors.stock_daily_overlap_close.sma_26`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_52` = 简单移动均线(52) （`factors.stock_daily_overlap_close.sma_52`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_9` = 简单移动均线(9) （`factors.stock_daily_overlap_close.sma_9`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_9 > sma_26) & (close > sma_52) & (sma_9 > sma_9.shift(1)) / sma_9 < sma_26
- **实际 YAML 入场**：`(sma_9 > sma_26) & (close > sma_52) & (sma_9 > sma_9.shift(1))`
- **实际 YAML 出场**：`sma_9 < sma_26`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### 绝对动量 + 相对动量筛选 `tf06a_dual_momentum`

- **说明**：过去 60 日收益为正，且 MA(5) > MA(20) 确认趋势入场。
- **声明的数据依赖**：SMA(5,20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_5` = 简单移动均线(5) （`factors.stock_daily_overlap_close.sma_5`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(60)) & (sma_5 > sma_20) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(60)) & (sma_5 > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 20 天；止损 0.08；止盈 —；移动止损 —。

### Aroon 趋势确认 `tf07a_aroon_trend_confirm`

- **说明**：AroonUp > 70 且 AroonDown < 30 入场（需确认 Aroon 因子列）。用通道突破近似。
- **声明的数据依赖**：SMA(60)
- **实际使用指标**：
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(25).max()) & (close > sma_60) / close < sma_60
- **实际 YAML 入场**：`(close > close.shift(1).rolling(25).max()) & (close > sma_60)`
- **实际 YAML 出场**：`close < sma_60`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### Aroon Oscillator 转正 `tf07b_aroon_oscillator`

- **说明**：Aroon Oscillator 由负转正入场。用价格动量方向近似。
- **声明的数据依赖**：SMA(20,60)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_60` = 简单移动均线(60) （`factors.stock_daily_overlap_close.sma_60`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(sma_20 > sma_60) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(sma_20 > sma_60) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### 抛物线 SAR 翻多 `tf07c_parabolic_sar_flip`

- **说明**：SAR 翻转到价格下方入场。用突破短期高点近似。
- **声明的数据依赖**：SMA(20)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(close > close.shift(1).rolling(5).max()) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`(close > close.shift(1).rolling(5).max()) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### Vortex 涡旋指标 +VI/-VI `tf07d_vortex_indicator`

- **说明**：+VI 上穿 -VI 入场（需确认 Vortex 因子列）。用均线金叉近似。
- **声明的数据依赖**：EMA(12,26)
- **实际使用指标**：
  - `ema_12` = 指数移动均线(12) （`factors.stock_daily_overlap_close.ema_12`）：指数移动平均线，对近期价格赋予更高权重。
  - `ema_26` = 指数移动均线(26) （`factors.stock_daily_overlap_close.ema_26`）：指数移动平均线，对近期价格赋予更高权重。
- **文字入场 / 出场**：ema_12 > ema_26 / ema_12 < ema_26
- **实际 YAML 入场**：`ema_12 > ema_26`
- **实际 YAML 出场**：`ema_12 < ema_26`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### RAVI 趋势强度 `tf07e_ravi_trend_strength`

- **说明**：RAVI > 3% 且价格在 MA(20) 之上入场。用 SMA(7) / SMA(65) 偏离近似。
- **声明的数据依赖**：SMA(7,20,65)
- **实际使用指标**：
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_65` = 简单移动均线(65) （`factors.stock_daily_overlap_close.sma_65`）：简单移动平均线，用于衡量趋势与价格相对位置。
  - `sma_7` = 简单移动均线(7) （`factors.stock_daily_overlap_close.sma_7`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：((sma_7 / sma_65 - 1).abs() > 0.03) & (close > sma_20) / close < sma_20
- **实际 YAML 入场**：`((sma_7 / sma_65 - 1).abs() > 0.03) & (close > sma_20)`
- **实际 YAML 出场**：`close < sma_20`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。

### TSI 真实强度指数零轴突破 `tf08a_tsi_zero_cross`

- **说明**：TSI 与信号线同步上穿 0 入场（需确认 TSI 因子列）。用 RSI 中轴近似。
- **声明的数据依赖**：RSI(14) + SMA(20)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
  - `sma_20` = 简单移动均线(20) （`factors.stock_daily_overlap_close.sma_20`）：简单移动平均线，用于衡量趋势与价格相对位置。
- **文字入场 / 出场**：(rsi_14 > 50) & (close > sma_20) / rsi_14 < 50
- **实际 YAML 入场**：`(rsi_14 > 50) & (close > sma_20)`
- **实际 YAML 出场**：`rsi_14 < 50`
- **持仓 / 风控**：最长 10 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。

### DSI 动力指标零轴突破 `tf08b_dsi_zero_cross`

- **说明**：DSI 上穿 0 入场（需确认 DSI 因子列）。用 RSI 方向近似。
- **声明的数据依赖**：RSI(14)
- **实际使用指标**：
  - `rsi_14` = 相对强弱指标(14) （`factors.stock_daily_momentum_close.rsi_14`）：相对强弱指标，用于观察超买、超卖与动量状态。
- **文字入场 / 出场**：rsi_14 > 55 / rsi_14 < 45
- **实际 YAML 入场**：`rsi_14 > 55`
- **实际 YAML 出场**：`rsi_14 < 45`
- **持仓 / 风控**：最长 5 天；止损 0.08；止盈 —；移动止损 —。
- **语义差异**：文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。
