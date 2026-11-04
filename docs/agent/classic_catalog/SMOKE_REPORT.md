# 经典策略公网三入口与 100 股两年冒烟报告

> 本报告验证入口、执行和统计管线；小样本收益不是策略有效性结论或投资建议。

- 总数 **118**（唯一 118）；状态 `{'completed': 118}`；入口 `{'yaml': 42, 'nl': 38, 'wizard': 38}`。
- 入口能力错误 `{'wizard': 24}`；NL 语义不一致回退 **13**；零交易 **7**；数值异常 **0**。

## 失败项

| 策略 | 入口 | Job | 错误 |
|---|---|---:|---|

## 零交易项

- `bo09e_channel_retest_breakout`、`cs01b_small_cap_quality`、`cs01d_small_cap_low_pb`、`mr02c_stoch_rsi_slow`、`mr08a_mfi_oversold_reversal`、`mr10b_uo_reversal`、`pv01a_obv_divergence`

## 全量明细

| 策略 | 入口 | Job | 状态 | 交易数 | 总收益 | 最大回撤 | 入口/语义备注 |
|---|---|---:|---|---:|---:|---:|---|
| `bo04a_darvas_box_breakout` | yaml | 93 | completed | 2690 | -6.6014% | -8.2775% | — |
| `bo01a_donchian_20_breakout` | nl | 94 | completed | 221 | -2.4607% | -4.2618% | — |
| `bo01b_donchian_55_breakout` | nl | 95 | completed | 130 | -1.2204% | -4.0077% | — |
| `bo02_keltner_breakout` | nl | 96 | completed | 535 | -1.7775% | -4.9456% | — |
| `bo03_52w_high_breakout` | wizard | 97 | completed | 333 | -2.2561% | -4.7656% | 入口不支持，回退原 YAML |
| `bo05_bollinger_squeeze` | wizard | 212 | completed | 94 | -3.0012% | -5.3087% | — |
| `bo06a_atr_anomaly_momentum` | yaml | 99 | completed | 4693 | -11.0917% | -12.8438% | — |
| `bo07a_larry_williams_breakout` | yaml | 100 | completed | 561 | -0.7838% | -4.8444% | — |
| `bo08a_ma_pinch_breakout` | yaml | 101 | completed | 286 | -1.8152% | -5.3300% | — |
| `bo08b_hv20_low_breakout` | nl | 102 | completed | 88 | -2.5909% | -4.7434% | — |
| `bo08c_atr_ratio_filter` | yaml | 103 | completed | 456 | -0.5413% | -3.7960% | — |
| `bo08d_dual_vol_breakout` | wizard | 104 | completed | 2803 | -7.7491% | -9.8091% | 入口不支持，回退原 YAML |
| `bo08e_amplitude_expansion` | yaml | 105 | completed | 307 | -1.9739% | -4.9846% | — |
| `bo09a_volume_price_breakout` | nl | 106 | completed | 2641 | -6.9591% | -8.0935% | NL 语义不同，回退原 YAML |
| `bo09b_n_breakout` | wizard | 107 | completed | 368 | -1.3079% | -4.1117% | 入口不支持，回退原 YAML |
| `bo09c_sideways_breakout` | wizard | 108 | completed | 162 | -2.4711% | -4.6561% | 入口不支持，回退原 YAML |
| `bo09d_three_candle_breakout` | nl | 109 | completed | 3707 | -2.9925% | -6.1533% | — |
| `bo09e_channel_retest_breakout` | wizard | 110 | completed | 0 | 0.0000% | -3.0000% | 入口不支持，回退原 YAML |
| `bo09f_orb_daily_approx` | nl | 111 | completed | 526 | -0.8774% | -4.7571% | — |
| `bo10a_bb_upper_trend_breakout` | wizard | 112 | completed | 88 | -2.5909% | -4.7434% | 入口不支持，回退原 YAML |
| `bo10b_bb_lower_rsi_volume` | yaml | 113 | completed | 194 | 8.8590% | -5.2419% | — |
| `cb01a_ma_cross_rsi` | wizard | 213 | completed | 10274 | -13.7854% | -15.9059% | — |
| `cb01b_macd_cross_volume` | nl | 115 | completed | 1799 | 7.1055% | -9.7748% | NL 语义不同，回退原 YAML |
| `cb01c_adx_rsi_momentum` | yaml | 116 | completed | 1142 | 1.5115% | -10.3150% | — |
| `cb01d_bb_rsi_volume` | wizard | 117 | completed | 194 | 8.8590% | -5.2419% | 入口不支持，回退原 YAML |
| `cb01e_ma_alignment_kdj` | wizard | 214 | completed | 7661 | -9.4169% | -10.9603% | — |
| `cb01f_new_high_obv_macd` | yaml | 119 | completed | 228 | -3.0928% | -4.4044% | — |
| `cb01g_turtle_ma60_filter` | nl | 120 | completed | 221 | -2.4607% | -4.2618% | — |
| `cb01h_sideways_rsi_volume` | yaml | 121 | completed | 1772 | -3.7368% | -10.4253% | — |
| `cs01a_pure_small_cap` | nl | 122 | completed | 205 | 1.2649% | -4.5238% | — |
| `cs01b_small_cap_quality` | nl | 123 | completed | 0 | 0.0000% | -3.0000% | — |
| `cs01c_small_cap_macd_timing` | nl | 124 | completed | 294 | -0.1255% | -4.5584% | NL 语义不同，回退原 YAML |
| `cs01d_small_cap_low_pb` | wizard | 215 | completed | 0 | 0.0000% | -3.0000% | — |
| `cs02_size_value_ranking` | nl | 126 | completed | 1 | -0.2076% | -3.2246% | — |
| `cs03_low_volatility` | wizard | 216 | completed | 409 | -1.5001% | -5.2013% | — |
| `cs06a_n_day_return_momentum` | nl | 128 | completed | 432 | -2.4307% | -4.4643% | — |
| `cs06b_sharpe_factor` | wizard | 129 | completed | 432 | -2.3751% | -4.4037% | 入口不支持，回退原 YAML |
| `cs06c_12_1_momentum_diff` | yaml | 130 | completed | 139 | -1.2059% | -3.9786% | — |
| `cs06d_beta_rotation` | wizard | 131 | completed | 171 | -3.2781% | -5.2868% | 入口不支持，回退原 YAML |
| `cs06e_rs_ranking` | nl | 132 | completed | 329 | -1.7943% | -4.3736% | — |
| `cs06f_return_skewness` | wizard | 133 | completed | 266 | -1.7962% | -4.7758% | 入口不支持，回退原 YAML |
| `cs06g_max_return_ratio` | yaml | 134 | completed | 717 | -3.1440% | -5.0486% | — |
| `cs06h_overnight_vs_intraday` | yaml | 135 | completed | 451 | -1.3552% | -4.4640% | — |
| `cs07a_mf001_atrr14_high_hv20_normal_mvp` | yaml | 136 | completed | 252 | 1.9005% | -10.4431% | — |
| `cs07b_mf002_alpha072_low_mvp` | yaml | 137 | completed | 575 | 3.9108% | -13.8886% | — |
| `cs07c_mf003_alpha082_low_mvp` | yaml | 138 | completed | 531 | 6.0050% | -12.5886% | — |
| `gui_accept_rsi14_reversal` | yaml | 139 | completed | 313 | 14.5712% | -6.6290% | — |
| `pt01a_hammer_reversal` | nl | 140 | completed | 192 | -0.6069% | -4.0231% | NL 语义不同，回退原 YAML |
| `pt01b_bullish_engulfing` | nl | 141 | completed | 1376 | -4.9443% | -6.0777% | — |
| `pt01c_morning_star` | yaml | 142 | completed | 303 | -2.4271% | -5.3409% | — |
| `pt01d_three_white_soldiers` | nl | 143 | completed | 216 | -1.0032% | -4.2302% | — |
| `pt02a_rising_three_methods` | wizard | 144 | completed | 399 | -2.2142% | -3.9606% | 入口不支持，回退原 YAML |
| `pt02b_island_reversal` | yaml | 145 | completed | 134 | 1.6264% | -3.2002% | — |
| `pt02c_tombstone_doji_exit` | yaml | 146 | completed | 72 | -0.8141% | -3.9654% | — |
| `pt03a_double_bottom` | wizard | 147 | completed | 211 | -2.1205% | -4.4821% | 入口不支持，回退原 YAML |
| `mr01a_rsi14_oversold_reversal` | nl | 148 | completed | 6598 | 5.5363% | -26.7772% | — |
| `mr01b_rsi2_connors` | nl | 149 | completed | 252 | 1.1889% | -3.3494% | — |
| `mr01c_multi_rsi_resonance` | wizard | 217 | completed | 71 | 3.4748% | -3.1024% | — |
| `mr01d_rsi_divergence_bottom` | nl | 151 | completed | 124 | 0.3623% | -3.7078% | — |
| `mr01e_rsi_hidden_divergence` | yaml | 152 | completed | 22 | 0.6757% | -3.0254% | — |
| `mr01f_rsi14_midline_break` | wizard | 218 | completed | 3202 | 9.4364% | -13.5069% | — |
| `mr02a_kdj_j_line_extreme` | nl | 154 | completed | 566 | -3.8683% | -7.4649% | NL 语义不同，回退原 YAML |
| `mr02b_stochastic_cross` | wizard | 155 | completed | 679 | -2.9614% | -5.8590% | 入口不支持，回退原 YAML |
| `mr02c_stoch_rsi_slow` | yaml | 156 | completed | 0 | 0.0000% | -3.0000% | — |
| `mr02d_williams_r_reversal` | nl | 157 | completed | 868 | -3.4847% | -6.9214% | NL 语义不同，回退原 YAML |
| `mr03a_bollinger_lower_reversion` | yaml | 158 | completed | 912 | 3.9891% | -17.7867% | — |
| `mr03b_bollinger_lower_volume` | nl | 159 | completed | 307 | 13.3109% | -5.8828% | NL 语义不同，回退原 YAML |
| `mr03c_bollinger_percent_b` | yaml | 160 | completed | 2068 | 1.7440% | -30.3153% | — |
| `mr04a_ibs_reversal` | yaml | 161 | completed | 999 | -2.1748% | -5.0331% | — |
| `mr05a_cci_oversold_reversal` | wizard | 219 | completed | 452 | 1.5687% | -4.5929% | — |
| `mr05b_cci_trend_following` | yaml | 163 | completed | 163 | -2.3331% | -5.8346% | — |
| `mr06_double7` | wizard | 164 | completed | 449 | 0.3624% | -5.3909% | 入口不支持，回退原 YAML |
| `mr07_r3_extreme_oversold` | wizard | 220 | completed | 252 | 1.1889% | -3.3494% | — |
| `mr08a_mfi_oversold_reversal` | nl | 166 | completed | 0 | 0.0000% | -3.0000% | — |
| `mr09a_bias_oversold` | wizard | 167 | completed | 1961 | 2.5510% | -28.2110% | 入口不支持，回退原 YAML |
| `mr09b_volume_contraction_reversal` | yaml | 168 | completed | 226 | -2.8706% | -4.7969% | — |
| `mr10a_cmo_reversal` | nl | 169 | completed | 4355 | 6.9796% | -31.1099% | NL 语义不同，回退原 YAML |
| `mr10b_uo_reversal` | yaml | 170 | completed | 0 | 0.0000% | -3.0000% | — |
| `pv01a_obv_divergence` | wizard | 221 | completed | 0 | 0.0000% | -3.0000% | — |
| `pv01b_obv_ma_cross` | nl | 172 | completed | 293 | -1.1180% | -5.2862% | — |
| `pv02a_cmf_money_flow` | wizard | 173 | completed | 229 | -1.7753% | -5.3128% | 入口不支持，回退原 YAML |
| `pv03a_alpha41` | nl | 174 | completed | 568 | -0.8143% | -4.5025% | — |
| `pv03b_alpha101` | yaml | 175 | completed | 356 | 0.3154% | -3.6550% | — |
| `pv03c_alpha12_style` | nl | 176 | completed | 269 | -0.5434% | -4.9362% | — |
| `pv05a_ad_accumulation` | yaml | 177 | completed | 274 | 0.5001% | -4.9668% | — |
| `pv05b_daily_vwap_support` | yaml | 178 | completed | 427 | -1.0822% | -4.6270% | — |
| `pv05c_volume_ratio_breakout` | nl | 179 | completed | 238 | -0.7380% | -3.8497% | — |
| `pv05d_eom_ease_of_movement` | wizard | 180 | completed | 439 | -1.0502% | -4.1969% | 入口不支持，回退原 YAML |
| `pv05e_vpt_volume_price_trend` | wizard | 181 | completed | 568 | -0.8143% | -4.5025% | 入口不支持，回退原 YAML |
| `pv06a_alpha083_high_rank_mvp` | yaml | 182 | completed | 2732 | 7.1922% | -8.1675% | — |
| `pv06b_alpha099_high_rank_mvp` | yaml | 183 | completed | 2926 | 8.5771% | -7.7406% | — |
| `pv06c_alpha042_high_rank_mvp` | wizard | 184 | completed | 1175 | 12.2547% | -9.7155% | 入口不支持，回退原 YAML |
| `tf01a_ma_cross_20_120` | nl | 185 | completed | 1512 | 0.8992% | -19.0794% | NL 语义不同，回退原 YAML |
| `tf01b_triple_ma_alignment` | wizard | 222 | completed | 286 | -1.8064% | -5.3300% | — |
| `tf01c_sma200_bull_filter` | yaml | 187 | completed | 421 | -4.2441% | -6.7616% | — |
| `tf01d_dema_tema_cross` | wizard | 223 | completed | 1550 | -0.7697% | -20.4908% | — |
| `tf01e_hma_cross_20` | wizard | 189 | completed | 322 | -2.3813% | -4.8887% | 入口不支持，回退原 YAML |
| `tf01f_ema_channel_breakout` | nl | 190 | completed | 492 | -1.3418% | -4.3955% | — |
| `tf01g_kama_adaptive_cross` | yaml | 191 | completed | 1764 | 10.5664% | -15.8608% | — |
| `tf01h_wma_cross_5_20` | nl | 192 | completed | 2265 | 15.0368% | -11.5346% | NL 语义不同，回退原 YAML |
| `tf01i_ma20_slope_positive` | nl | 193 | completed | 250 | -1.6287% | -4.4665% | — |
| `tf01j_pbo_waterfall` | nl | 194 | completed | 236 | -1.9866% | -5.4195% | NL 语义不同，回退原 YAML |
| `tf02a_macd_golden_cross` | wizard | 224 | completed | 2209 | 9.6439% | -11.1165% | — |
| `tf02b_macd_zero_second_cross` | nl | 196 | completed | 1417 | -0.9042% | -7.6878% | NL 语义不同，回退原 YAML |
| `tf02c_macd_histogram_slope` | yaml | 197 | completed | 738 | 3.9148% | -6.0115% | — |
| `tf02d_macd_divergence_bottom` | wizard | 198 | completed | 515 | 0.8556% | -3.2975% | 入口不支持，回退原 YAML |
| `tf02e_dif_zero_breakthrough` | yaml | 199 | completed | 1651 | 3.7947% | -15.8599% | — |
| `tf03_adx_trend_filter` | wizard | 225 | completed | 309 | -2.6755% | -6.4995% | — |
| `tf04_supertrend_breakout` | yaml | 201 | completed | 535 | -1.7775% | -4.9456% | — |
| `tf05a_ichimoku_cloud_breakout` | yaml | 202 | completed | 278 | -3.6804% | -6.0795% | — |
| `tf06a_dual_momentum` | wizard | 203 | completed | 6417 | -9.1799% | -10.0716% | 入口不支持，回退原 YAML |
| `tf07a_aroon_trend_confirm` | yaml | 204 | completed | 228 | -3.8662% | -4.7694% | — |
| `tf07b_aroon_oscillator` | nl | 205 | completed | 365 | -2.8932% | -6.8368% | — |
| `tf07c_parabolic_sar_flip` | wizard | 206 | completed | 433 | -2.0876% | -4.0683% | 入口不支持，回退原 YAML |
| `tf07d_vortex_indicator` | yaml | 207 | completed | 1651 | 3.7947% | -15.8599% | — |
| `tf07e_ravi_trend_strength` | wizard | 208 | completed | 456 | -1.8714% | -4.7703% | 入口不支持，回退原 YAML |
| `tf08a_tsi_zero_cross` | nl | 209 | completed | 356 | -0.9051% | -5.7085% | NL 语义不同，回退原 YAML |
| `tf08b_dsi_zero_cross` | yaml | 210 | completed | 1631 | 5.1418% | -14.7312% | — |
