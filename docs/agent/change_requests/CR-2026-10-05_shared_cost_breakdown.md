# CR-2026-10-05 shared 模式交易费用拆分补齐（交易磨损卡 0 值 bug）

状态：已实施并部署（用户报告 bug，根因已由用户定位确认）

## 问题

多股票回测走 shared（共享资金）模式：「交易磨损」卡佣金/印花税显示 0，
只有「过户费/其他」有值（总磨损被全算进其他）。

## 根因链（用户定位，核实无误）

1. `portfolio/shared.py` 的 `_trade_row` 只写 `cost` 总费用，无拆分列；
2. `portfolio/full_market_report.py` shared_cash 分支压根不读拆分列
   （batch 分支读），round_trips.csv 的 commission/stamp_tax 为 None；
3. `gui/lab_result.py:_fees_summary` 聚合为 0，other_cost 吞掉全部。

## 修法

- shared.py：买入用 `calculate_cost_breakdown(BUY, notional)`（total ==
  calculate_cost 原口径），lot 存 `entry_cost_parts`；`_consume_lots` 按比例
  分摊各组件（缺拆分的 lot 退化归入佣金，总额不变）；卖出用
  `calculate_cost_breakdown(SELL, notional)`；`_trade_row` 补写 6 列
  （entry/exit × commission/stamp_tax/transfer_fee，键名与 vectorized 一致）。
  覆盖普通买入、rebalance 买入、普通卖出、rebalance 卖出四个路径。
- full_market_report.py：shared_cash 分支补读拆分聚合成
  commission/stamp_tax/transfer_fee（与 batch 分支同口径）。
- 存量产物不回填（新跑的结果才有拆分）；既有结果页对旧产物仍显示旧口径
  （wear 聚合兜底路径不受影响）。

## 实测数值证据（真库 shared 小回测，2025-06~12 × 000001.SZ+600519.SH）

7 笔交易：每行 commission=10.0（最低 5 元×双边）、stamp_tax 4.46~5.12、
transfer_fee≈0.19，组件和 == total_cost（逐行 <1e-6）；
_fees_summary 聚合：佣金 70.00 / 印花税 32.88 / 过户费 1.31 / 总磨损 104.19
（修复前佣金与印花税为 0、104.19 全进 other）。

## 测试

- test_portfolio_shared.py：默认列集合断言补 6 列 + 新增拆分正确性测试
  （组件和==cost、买入无印花税、卖出印花税>0）
- test_full_market_report.py：新增 shared→round_trips 链路回归
- 全量：`-k saas` 237 passed；`-k "portfolio or shared or market or worker"` 482 passed
