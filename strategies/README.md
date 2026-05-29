# 策略文件导航

## 目录结构

```
strategies/
├── README.md                         # 本文件 — 策略导航
├── high_level/                       # 高层策略入口 (人类编写)
│   ├── rsi2_oversold_reversal_entry.yaml        # RSI2 超卖反转 ★☆☆☆☆
│   ├── bollinger_mean_reversion_entry.yaml      # 布林带均值回归 ★★☆☆☆
│   ├── macd_zero_cross_momentum_entry.yaml      # MACD 零轴动量 ★★★☆☆
│   └── ema200_bollinger_reversal_entry.yaml     # EMA200+布林带 ★★★☆☆
├── low_level/                        # 低层规格 (编译后/可直接执行)
│   ├── rsi2_reversal_research.yaml              # RSI2 基础版
│   ├── rsi2_reversal_with_risk.yaml             # RSI2 + 风控
│   ├── rsi2_reversal_with_risk_and_weight.yaml  # RSI2 + 风控 + 权重
│   ├── rsi2_reversal_with_rebalance.yaml        # RSI2 + 风控 + 再平衡
│   ├── ema200_bollinger_reversal.yaml           # EMA200+Bollinger
│   └── bollinger_mean_reversion.yaml            # 布林带均值回归
└── run_bollinger_full.py             # 全市场分块回测脚本 (5525 只标的)
```

## 策略概览

| 策略 | 族 | 信号逻辑 | 推荐场景 |
|------|-----|---------|---------|
| **RSI2 超卖反转** | 均值回归 | RSI(2) < 10 买入, > 70 卖出 | 入门学习、冒烟测试 |
| **布林带均值回归** | 均值回归 | 触及下轨买入，回到中轨卖出 | 实盘验证、全市场筛选 |
| **MACD 零轴动量** | 动量 | 零轴下方金叉买入，死叉卖出 | 交叉运算符学习 |
| **EMA200+布林带** | 均值回归 | 趋势+超卖双确认 | 多条件组合参考 |

## 快速开始

**你的第一个策略:**

```bash
# 1. 编译高层入口
uv run qre compile strategies/high_level/rsi2_oversold_reversal_entry.yaml

# 2. 单标回测
uv run qre backtest-single strategies/low_level/rsi2_reversal_research.yaml \
  --symbol 000001.SZ --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/my-first/

# 3. 全市场冒烟
uv run qre strategy-smoke
uv run qre smoke-files --details
```

**编写自定义策略:** 参考 [docs/strategy_entry/](../docs/strategy_entry/) — 包含完整的格式规范、字段说明和三个详细示例。

## 文件类型说明

### 高层入口 (high_level/)

- **用途:** 人类编写，使用指标别名描述策略逻辑
- **格式:** `strategy` + `rules` + `factor_requirements` + `experiment` 四段式 YAML
- **使用方式:** 先 `compile` 再 `backtest-*`
- **标准:** [strategy_entry 文档](../docs/strategy_entry/README.md)

### 低层规格 (low_level/)

- **用途:** 编译后的可执行规格，或手写的直接策略
- **格式:** `data` (表路径) + `signal` (表达式) + `risk` (风控) YAML
- **使用方式:** 直接 `backtest-*` 或 `research-run`
- **注意:** 因子字段使用完整的 `factors.table.column` 路径

**因子列名速查:**

| 策略 | 因子别名 | 完整路径 |
|------|---------|---------|
| RSI2 系列 | `rsi_2` | `factors.stock_daily_momentum_close.rsi_2` |
| 布林带 | `bb_lower` | `factors.stock_daily_volatility_close.bbl_20_2_0_2_0` |
| 布林带 | `bb_middle` | `factors.stock_daily_volatility_close.bbm_20_2_0_2_0` |
| EMA200+Bollinger | `ema200` | `factors.stock_daily_overlap_typical_price.ema_200` |
| EMA200+Bollinger | `bb_upper` | `factors.stock_daily_volatility_close.bbu_20_2_0_2_0` |
| EMA200+Bollinger | `bb_lower` | `factors.stock_daily_volatility_close.bbl_20_2_0_2_0` |

> **列名解码示例:** `bbl_20_2_0_2_0` = Bollinger Band Lower, period=20, stddev=2.0
> 格式: `<指标缩写>_<周期>_<参数...>` (具体编码取决于上游 `indicators_tushare` 生成规则)

**编译后的低层文件可以直接使用:**

```bash
# 直接回测低层规格（跳过编译步骤）
uv run qre backtest-single strategies/low_level/rsi2_reversal_research.yaml \
  --symbol 000001.SZ --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/rsi2-basic/

# 全市场批量回测
uv run qre backtest-batch strategies/low_level/bollinger_mean_reversion.yaml \
  --start 2024-01-01 --end 2024-12-31 --output-dir outputs/bollinger-batch/
```

### Python 脚本

- **`run_bollinger_full.py`:** 示范如何使用 Python API 直接调用引擎，适合大数据量全市场运行（分块处理、断点续跑、增量统计）

## RSI2 系列速查

RSI2 提供了 4 个由简到繁的低层规格，适合循序渐进学习:

| 文件 | 新增功能 | 新增字段 |
|------|---------|---------|
| `rsi2_reversal_research.yaml` | 基础: entry/exit 信号, 基准对比, 评估配置 | — (基线) |
| `rsi2_reversal_with_risk.yaml` | + 止损 8%, 止盈 12%, 移动止损 10% | `risk.stop_loss_pct`, `risk.take_profit_pct`, `risk.trailing_stop_pct` |
| `rsi2_reversal_with_risk_and_weight.yaml` | + score_weight (RSI 值作为评分) | `portfolio.weight_model`, `portfolio.score_column` |
| `rsi2_reversal_with_rebalance.yaml` | + 每 5 日再平衡 | `portfolio.rebalance_interval_days` |

**学习路径建议:**

```bash
# 1. 先跑基础版，理解信号生成和执行
uv run qre backtest-single strategies/low_level/rsi2_reversal_research.yaml \
  --symbol 000001.SZ --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/rsi2-1-basic/

# 2. 加上风控，观察止损/止盈对结果的影响
uv run qre backtest-single strategies/low_level/rsi2_reversal_with_risk.yaml \
  --symbol 000001.SZ --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/rsi2-2-risk/

# 3. 在风控基础上加上权重评分
uv run qre backtest-single strategies/low_level/rsi2_reversal_with_risk_and_weight.yaml \
  --symbol 000001.SZ --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/rsi2-3-weight/

# 4. 最后加上再平衡，体验完整组合管理
uv run qre backtest-single strategies/low_level/rsi2_reversal_with_risk_and_weight.yaml \
  --symbol 000001.SZ --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/rsi2-4-rebalance/
```
