# Quant Research Engine

`quant-research-engine` 是一个本地化、只读的量化研究与回测引擎，首个目标市场为中国 A 股（日线级别技术因子研究）。

## 当前状态

- **核心 MVP 已完成，本仓库处于维护模式。**
- QRE 当前 CLI 表面、产物合同和报告管道为稳定形态；新需求通过 `docs/agent/change_requests/` 进入单 agent 开发流程。
- 上游数据生产工作属于 `quant_ts`，不在此仓库范围内。
- 本 README 仅保留当前可用命令、产物文件、参数和验证方式，不含未来规划或愿望清单。
- 本项目自 2026-07-18 起由 Kimi Code 单 agent 开发（规划/实现/自审查/git 执行），开发流程与项目状态长期记忆存放于 `docs/agent/`；早期的双智能体（Codex + Claude Code）工作流记录见 `docs/agent/06_DECISION_LOG.md`。

## Quick Start

新用户请看这里：**[QUICKSTART.md](QUICKSTART.md)** — 从零到第一次回测的 10 分钟指南。

三步快速启动：
1. `cp .env.example .env` — 编辑数据库连接信息
2. `uv sync` — 安装依赖
3. `uv run qre strategy-smoke && uv run qre gui` — 运行冒烟测试并打开控制台

完整 CLI 参考见下方。

---

## 项目原理

### 双引擎架构

项目包含两个独立但协作的引擎：

| 引擎 | 定位 | 特点 |
|------|------|------|
| **Evaluation Engine** (评估引擎) | 快速全市场因子/策略筛选 | 向量化计算，IC/Rank IC，分位数收益，因子衰减，近似摩擦 |
| **Portfolio Engine** (投资组合引擎) | 真实账户级验证 | 订单/成交/失败订单/成本/滑点/持仓/T+1/权益曲线 |

工作流：`数据加载 → 评估筛选 → 组合回测 → 报告输出`

### 核心设计原则

- **只读数据层**：从 PostgreSQL 读取行情和因子数据，不写入上游数据库
- **因子外部计算**：引擎消费 `factors.*` 表中的因子列，不在内部重算技术指标
- **市场规则隔离**：A 股交易规则（手续费、印花税、涨跌停、T+1、最小交易单位）集中在市场配置文件中
- **无未来信息泄露**：信号基于 `t` 日数据，最早执行日为 `t+1`
- **报告可复现**：所有持久化输出均附带 `report_manifest.json`

### 技术栈

- **语言**：Python 3.10+
- **数据库**：PostgreSQL (SQLAlchemy + pandas)
- **打包**：pyproject.toml, uv
- **CLI**：argparse (`qre` 命令)
- **Web GUI**：Flask 本地浏览器控制台
- **配置**：YAML
- **测试**：pytest
- **图表**：matplotlib (Agg 后端)
- **Excel**：openpyxl

---

## 已实现功能

### 数据层 (Data Layer)

| 功能 | 说明 |
|------|------|
| `load_daily_bars` | 从 `public.stock_daily` 读取日线 OHLCV 数据 |
| `load_factor_history` | 从 `factors.*` 读取指定因子列 |
| `load_security_metadata` | 读取证券元数据（板块、ST、风险警示等） |
| `load_benchmark_bars` | 读取基准指数数据 |
| `ResearchFrameAssembler` | 将行情+因子+元数据组装成研究框架 |
| Tushare 安全探测 | 只读源数据形态验证工具 |
| 预检查 (Preflight) | 数据可用性、因子覆盖率、成分股筛选 |

### 评估引擎 (Evaluation Engine)

| 功能 | 说明 |
|------|------|
| 安全表达式信号 | `close > ema_200 and close <= bb_lower` |
| 前向收益计算 | 自定义时间窗口 (1/3/5/10/20 日) |
| IC / Rank IC | 信息系数和秩信息系数 |
| 分位数收益 | 按因子分组的收益汇总 |
| 近似摩擦调整 | 基于市场配置的往返成本率 |
| 元数据分组汇总 | 按板块、行业等维度分组统计 |
| 随机基线对比 | 确定性随机种子，评估信号质量 |
| 因子衰减汇总 | 从 IC 序列推导因子预测力衰减 |

### 投资组合引擎 (Portfolio Engine)

| 回测模式 | 说明 |
|---------|------|
| `backtest-single` | 单标的独立回测 |
| `backtest-batch` | 多标的独立并行回测（每个标的独立资金池） |
| `backtest-shared` | 共享资金池多标的回测 |

| 实盘规则 | 说明 |
|---------|------|
| A 股手续费 | 佣金 (默认万2.5) |
| 印花税 | 卖出 0.05% |
| 过户费 | 双向 |
| 滑点 | 百分比滑点模型 |
| 涨跌停校验 | 超出涨跌停价格自动拒绝订单 |
| 最小交易单位 | 100 股整手 |
| T+1 卖出限制 | 当日买入次日才可卖出 |
| FIFO 批次核算 | 先进先出成本核算 |
| 风险控制 | 止损/止盈/移动止损/最大持仓天数 |
| 再平衡 | 固定交易间隔再平衡 |
| 权重模型 | equal_weight / score_weight / inverse_volatility |

### 报告与复现 (Reporting)

| 输出格式 | 说明 |
|---------|------|
| CSV | 订单/成交/权益/分组汇总 |
| JSON | 策略表现/交易分析/资金使用/汇总指标 |
| Markdown | 可读摘要报告 |
| Excel (.xlsx) | 全市场报告 (多 sheet，含图表) |
| HTML | 自包含 HTML 报告 (base64 内嵌图表) |
| PNG | 权益曲线图/回撤图 |

| 可复现工具 | 说明 |
|-----------|------|
| `report_manifest.json` | 每次运行均生成，记录所有产出物元数据 |
| `run_manifest.json` | 记录运行参数和策略配置 |
| `qre report-files` | 产出物发现 (支持 role/symbol/window/group-by 过滤) |
| `qre report-audit` | 产出物校验 (文件存在性/内容完整性/列校验) |
| `--run-id` | 跨命令关联 preflight/eval/backtest 产物 |

### 策略系统

| 功能 | 说明 |
|------|------|
| 策略编译器 (`qre compile`) | 高层入口 → 低层 StrategySpec 编译 |
| 因子别名解析 | 自动将 `rsi_fast` → `factors.stock_daily_momentum_close.rsi_2` |
| 缺失因子检测 | 自动生成 `missing_factor_requests.json` |
| 策略冒烟测试 (`qre strategy-smoke`) | 一键编译+预检+回测，生成 `smoke_summary.json` |
| 冒烟发现 (`qre smoke-files`) | 22 种状态标志，支持 CI 集成 |
| 跨域运算符 | `crosses_above` / `crosses_below` 编译为滞后量比较 |
| 指标目录 | 13 种技术指标 (rsi/ema/sma/wma/macd/bollinger/atr/adx/cci/mfi/obv/stochastic/williams_r) |
| 3 个已验证策略族 | RSI2 超卖反转 / EMA200+Bollinger / MACD 零轴交叉 |

### GUI 控制台

| 功能 | 说明 |
|------|------|
| YAML 策略编辑器 | 文本编辑 + 文件保存/加载 |
| 策略构建器 (Builder) | 表单式高层策略创建，无需了解数据库表路径 |
| 编译端点 | 表单 → 编译为低层 spec → 即时运行 |
| 运行历史 | 本地文件系统持久化 |
| 产物查看器 | 摘要/订单/成交/权益/Manifest |

### 研究流程编排

| 命令 | 说明 |
|------|------|
| `qre research-run` | 一键编排 preflight → eval → backtest，统一 `--run-id` |
| `research_run_manifest.json` | 记录三阶段运行状态和产物路径 |

---

## 入口 (Entry Points)

### 命令行 (CLI)

所有功能通过 `qre` 命令访问：

```bash
qre <command> [options]
```

#### 数据探测

| 命令 | 用途 | 必填参数 |
|------|------|---------|
| `db-smoke` | 行情数据探测 | `--start`, `--end` |
| `factor-smoke` | 因子数据探测 | `--start`, `--end`, `--logical-name`, `--target` |
| `metadata-smoke` | 元数据探测 | 无 (可选 `--codes`, `--limit`) |
| `benchmark-smoke` | 基准数据探测 | `--table`, `--start`, `--end` |
| `preflight` | 完整数据预检 | `strategy`, `--start`, `--end` |

#### 策略编译

| 命令 | 用途 | 必填参数 |
|------|------|---------|
| `compile` | 编译高层策略入口 | `strategy` |

#### 评估

| 命令 | 用途 | 必填参数 |
|------|------|---------|
| `eval-smoke` | 表达式评估探测 | `--start`, `--end`, `--logical-name`, `--target`, `--signal` |
| `eval-config` | 从 YAML 运行评估 | `strategy`, `--start`, `--end` |

#### 回测

| 命令 | 用途 | 必填参数 |
|------|------|---------|
| `backtest-single` | 单标回测 | `strategy`, `--symbol`, `--start`, `--end` |
| `backtest-batch` | 批量回测 (独立资金) | `strategy`, `--start`, `--end` |
| `backtest-shared` | 共享资金池回测 | `strategy`, `--start`, `--end`, `--max-positions` |

#### 策略验证

| 命令 | 用途 | 必填参数 |
|------|------|---------|
| `strategy-smoke` | 一键冒烟测试 | 无 (可选 `--output-dir`) |
| `smoke-files` | 冒烟结果发现 | 无 (支持 22 个标志) |

#### 报告管理

| 命令 | 用途 | 必填参数 |
|------|------|---------|
| `report-files` | 列出清单产物 | `manifest` |
| `report-audit` | 校验清单产物 | `manifest` |

#### 流程编排与 GUI

| 命令 | 用途 | 必填参数 |
|------|------|---------|
| `research-run` | 编排完整研究流程 | `strategy`, `--start`, `--end`, `--output-dir` |
| `gui` | 启动浏览器控制台 | 无 (可选 `--host`, `--port`) |
| `profile` | 加载市场配置文件 | `path` |

### 策略入口文件

支持两级策略入口格式：

#### 高层入口 (High-Level Entry) — `strategies/high_level/`

标准四段式 YAML，面向策略研究者：

```yaml
strategy:           # 策略身份
  id: bollinger_mean_reversion
  name: Bollinger Band Mean Reversion
  family: mean_reversion
  direction: long_only

rules:              # 交易规则
  entry:
    all:
      - alias: close
        operator: "<="
        alias_b: bb_lower
  exit:
    any:
      - alias: close
        operator: ">="
        alias_b: bb_middle

factor_requirements:  # 因子需求
  - alias: bb_lower
    indicator: bollinger
    source: close
    period: 20
    params: {stddev: 2.0}
    output: lower

experiment:         # 实验配置
  id: bollinger_mean_reversion_full
  frequency: daily
  market: ashare
  start: 2010-01-04
  end: 2026-05-22
  universe:
    include: all_a
    exclude_st: true
```

#### 低层规格 (Low-Level Spec) — `strategies/low_level/`

编译后的可直接执行的 YAML，面向引擎：

```yaml
experiment:
  name: bollinger_mean_reversion
data:
  factor_fields:
    bb_lower: factors.stock_daily_volatility_close.bbl_20_2_0_2_0
    bb_middle: factors.stock_daily_volatility_close.bbm_20_2_0_2_0
  market_fields: [open, high, low, close, pre_close, vol, amount]
signal:
  entry: (close <= bb_lower)
  exit: (close >= bb_middle)
holding:
  max_holding_days: 20
risk:
  stop_loss_pct: 0.08
```

#### 编译流程

```bash
# 高层入口 → 低层规格
uv run qre compile strategies/high_level/bollinger_mean_reversion_entry.yaml

# 编译 + 预检查
uv run qre compile strategies/high_level/bollinger_mean_reversion_entry.yaml \
  --preflight --start 2020-01-01 --end 2020-12-31

# 编译 + 输出低层文件
uv run qre compile strategies/high_level/bollinger_mean_reversion_entry.yaml \
  --output-dir outputs/compiled/
```

### GUI 入口

```bash
uv run qre gui                    # 默认 http://127.0.0.1:8080
uv run qre gui --port 9090        # 自定义端口
uv run qre gui --host 0.0.0.0     # 允许外部访问
```

GUI 提供两个 Tab：
- **Builder**：表单式策略构建（不需要写 YAML 和数据库路径）
- **YAML Editor**：直接编辑 YAML 策略文件

---

## 出口 (Outputs)

### 策略回测出口文件

每次回测运行在 `--output-dir` 下生成完整的报告包：

#### 全市场报告 (Full-Market Report)

```
outputs/<run_name>/
├── backtest_report.xlsx          # Excel 全市场报告 (多 sheet)
├── backtest_report.html          # 自包含 HTML 报告
├── trades_ledger.csv             # 交易台账
├── round_trips.csv               # 往返交易 (买入-卖出配对)
├── symbol_performance.csv        # 按标的绩效
├── strategy_performance.json     # 策略总体绩效
├── equity_curve.csv              # 权益曲线
├── equity_curve_chart.png        # 权益曲线图 (双轴)
├── drawdown_curve.csv            # 回撤曲线
├── drawdown_curve_chart.png      # 回撤曲线图 (填充面积)
├── trade_analysis.json           # 交易分析
├── capital_usage.json            # 资金使用分析
├── run_manifest.json             # 运行参数记录
└── report_manifest.json          # 产物清单
```

#### Excel 报告 Sheet 结构

| Sheet | 内容 |
|-------|------|
| Summary | 策略概要指标 |
| Symbol Performance | 按标的汇总 (收益率/胜率/交易次数/成本) |
| Strategy Performance | 策略级绩效指标 |
| Trades Ledger | 逐笔交易记录 |
| Round Trips | 完整往返交易 |
| Equity Curve | 权益曲线数据 |
| Drawdown Curve | 回撤曲线数据 |
| Trade Analysis | 交易统计分布 |
| Capital Usage | 资金使用历史 |
| Chart: Equity Curve | 权益曲线 PNG 图表 (openpyxl 嵌入) |
| Chart: Drawdown | 回撤 PNG 图表 (openpyxl 嵌入) |

#### 评估出口文件

```
outputs/<eval_run>/
├── events.csv                    # 信号事件
├── summary.csv                   # 评估汇总
├── ic_summary.csv                # IC/Rank IC 汇总
├── quantile_summary.csv          # 分位数收益
├── group_summary.csv             # 分组汇总
├── factor_decay_summary.csv      # 因子衰减
├── regime_summary.csv            # 市场状态汇总
├── random_baseline_summary.csv   # 随机基线对比
├── run_manifest.json             # 运行参数记录
└── report_manifest.json          # 产物清单
```

#### 冒烟测试出口文件

```
outputs/strategy-entry-smoke/<run_id>/
├── smoke_summary.json            # 冒烟汇总
├── smoke_report_manifest.json    # 产物清单
└── <strategy_id>/                # 每策略独立目录
    ├── compiled_strategy_spec.json
    ├── missing_factor_requests.json
    ├── backtest_smoke_summary.csv
    ├── backtest_smoke_metrics.json
    └── ... (更多回测产物)
```

### 报告发现与校验

```bash
# 发现产物
uv run qre report-files outputs/shared/report_manifest.json
uv run qre report-files outputs/shared/report_manifest.json --role orders
uv run qre report-files outputs/shared/report_manifest.json --json

# 校验产物
uv run qre report-audit outputs/shared/report_manifest.json --require-match
uv run qre report-audit outputs/shared/report_manifest.json --json

# 按窗口过滤
uv run qre report-files outputs/shared/report_manifest.json --window M
uv run qre report-files outputs/shared/report_manifest.json --window-size 20

# 按分组列过滤
uv run qre report-audit outputs/shared/report_manifest.json --group-by board
```

---

## 传入参数完整参考

### 通用参数

| 参数 | 适用命令 | 说明 | 默认值 |
|------|---------|------|--------|
| `--db-url` | 大多数命令 | 数据库连接 URL | `QRE_MARKET_DB_URL` 环境变量 |
| `--start` | 数据/评估/回测 | 起始日期 (YYYY-MM-DD) | 必填 |
| `--end` | 数据/评估/回测 | 结束日期 (YYYY-MM-DD) | 必填 |
| `--codes` | 评估/回测/预检 | 指定标的列表 | 空 = 全部 |
| `--run-id` | 大多数命令 | 运行标识符 | 自动生成 |
| `--output-dir` | 大多数命令 | 产物输出目录 | 无 (不产生文件) |
| `--metadata-as-of` | 预检/评估/回测/编排 | 元数据快照日期 | 无 |
| `--market-profile` | 回测 | 市场配置 YAML 路径 | 内置 A 股零滑点配置 |

### 预检查参数 (`qre preflight`)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--min-factor-coverage` | 最小因子覆盖率 | 0.8 |
| `--metadata-as-of` | 元数据快照日期 | 无 |
| `--benchmark-table` | 基准表名 | 无 |
| `--benchmark-code` | 基准标的代码 | 无 |
| `--benchmark-value-column` | 基准值列名 | close |
| `--output-json` | 预检报告 JSON 输出路径 | 无 |

### 评估参数 (`qre eval-config`)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--round-trip-cost-rate` | 往返成本率 (覆盖市场配置) | 无 |
| `--group-by` | 分组列 (如 board, industry) | 无 |
| `--random-baseline-seed` | 随机基线种子 | 无 |
| `--horizons` | 前向收益窗口 (仅 eval-smoke) | 1 3 5 |
| `--metadata-as-of` | 元数据快照日期 | 无 |
| `--benchmark-table` | 基准表名 | 无 |
| `--benchmark-code` | 基准标的代码 | 无 |
| `--benchmark-value-column` | 基准值列名 | close |

### 回测参数 (`qre backtest-batch`)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--initial-cash` | 每标的初始资金 | 100000.0 |
| `--group-by` | 分组汇总列 | 无 |
| `--group-rank-top-n` | 每组排名前N/后N | 1 |
| `--print-summary-md` | 打印 Markdown 摘要到 stdout | false |
| `--metadata-as-of` | 元数据快照日期 | 无 |
| `--benchmark-table` | 基准表名 | 无 |
| `--benchmark-code` | 基准标的 | 无 |
| `--benchmark-value-column` | 基准值列名 | close |

### 共享资金回测参数 (`qre backtest-shared`)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--max-positions` | 最大持仓数 | 必填 |
| `--initial-cash` | 初始总资金 | 100000.0 |
| `--weight-model` | 权重模型 (equal_weight/score_weight/inverse_volatility) | equal_weight |
| `--score-column` | score_weight 需要的评分列 | 无 |
| `--volatility-column` | inverse_volatility 需要的波动率列 | 无 |
| `--stop-loss-pct` | 止损比例 (如 0.08) | 无 |
| `--take-profit-pct` | 止盈比例 (如 0.12) | 无 |
| `--trailing-stop-pct` | 移动止损比例 (如 0.10) | 无 |
| `--rebalance-interval-days` | 再平衡间隔 (交易日) | 无 |
| `--metadata-as-of` | 元数据快照日期 | 无 |
| `--benchmark-table` | 基准表名 | 无 |
| `--benchmark-code` | 基准标的 | 无 |
| `--benchmark-value-column` | 基准值列名 | close |
| `--metadata-columns` | 输出附加元数据列 | 无 |

### 策略编译参数 (`qre compile`)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--output-dir` | 编译后低层 spec 输出目录 | 无 |
| `--preflight` | 编译后运行预检查 | false |
| `--min-factor-coverage` | 预检最小因子覆盖率 | 0.8 |

### 策略冒烟参数 (`qre strategy-smoke`)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--output-dir` | 冒烟产物目录 | outputs/strategy-entry-smoke |
| `--strategies` | 指定策略 YAML 路径 | 三个标准示例 |
| `--no-preflight` | 跳过预检查 | false |
| `--no-backtest` | 跳过回测 | false |
| `--start` | 预检/回测起始日期 | 2024-01-01 |
| `--end` | 预检/回测结束日期 | 2024-02-01 |

### 编排参数 (`qre research-run`)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--backtest-mode` | 回测模式 (batch/shared) | batch |
| `--skip-preflight` | 跳过预检查阶段 | false |
| `--skip-eval` | 跳过评估阶段 | false |
| `--window-size` | 滚动窗口大小 | 无 |
| `--metadata-as-of` | 元数据快照日期 | 无 |
| `--benchmark-table` | 基准表名 | 无 |
| `--benchmark-code` | 基准标的代码 | 无 |
| `--benchmark-value-column` | 基准值列名 | close |

### 报告参数 (`qre report-files` / `qre report-audit`)

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--role` | 按产物角色过滤 (如 orders, trades, equity_curve) | 无 |
| `--symbol` | 按标的代码过滤 | 无 |
| `--window` | 按窗口标签过滤 (M/Q/Y) | 无 |
| `--window-size` | 按窗口大小过滤 | 无 |
| `--group-by` | 按分组列过滤 | 无 |
| `--json` | JSON 输出 | false |
| `--require-match` | 无匹配时退出码 2 | false |
| `--check-exists` | 校验文件是否存在 (仅 report-files) | false |
| `--validate-contents` | 校验文件内容结构 (仅 report-files) | false |
| `--keys` | 打印 manifest 键而非路径 (仅 report-files) | false |

### 冒烟发现参数 (`qre smoke-files`)

22 个状态富化标志，主要如下：

| 参数 | 说明 |
|------|------|
| `--json` | JSON 输出 |
| `--strategy` | 按 strategy_id 过滤 |
| `--role` | 按产物角色过滤 |
| `--latest` | 使用最新冒烟运行目录 |
| `--details` | 每策略详细状态 |
| `--output-file` | 导出到文件 |
| `--check-exists` | 校验产物文件存在 |
| `--require-match` | 严格选择器匹配 |
| `--list-missing` | 列出缺失产物路径 |
| `--quiet` | 安静模式 (仅退出码) |
| `--status-only` | 紧凑状态输出 (CI 友好) |
| `--status-code` | 数字状态码 0/1 |
| `--status-summary` | 策略计数 (total/pass/fail/skip) |
| `--status-file` | 持久化状态到文件 |

---

## 环境变量

| 变量 | 说明 |
|------|------|
| `QRE_MARKET_DB_URL` | 市场数据库连接 URL (必填) |
| `QRE_FACTOR_DB_URL` | 因子数据库连接 URL |
| `QRE_REFERENCE_DB_URL` | 参考数据库连接 URL |
| `QRE_BENCHMARK_DB_URL` | 基准数据库连接 URL |
| `QRE_RESEARCH_DB_URL` | 研究数据库连接 URL |
| `QRE_SECURITY_METADATA_TABLE` | 证券元数据表名 (可选覆盖) |
| `SR_MARKET_DB_URL` | 兼容旧环境变量名 |

---

## 完整使用示例

### 1. 环境准备

```bash
# 安装依赖
uv sync

# 设置数据库连接
export QRE_MARKET_DB_URL='postgresql+psycopg://user:pass@localhost:5432/tushare_data'
```

### 2. 数据探测

```bash
# 验证行情数据
uv run qre db-smoke --start 2024-01-01 --end 2024-01-31 --limit 5

# 验证因子数据
uv run qre factor-smoke --start 2024-01-01 --end 2024-01-31 \
  --logical-name rsi_2 \
  --target factors.stock_daily_momentum_close.rsi_2

# 验证证券元数据
uv run qre metadata-smoke --limit 10
```

### 3. 策略编译

```bash
# 编译高层策略入口
uv run qre compile strategies/high_level/bollinger_mean_reversion_entry.yaml

# 输出：
# strategy_id=bollinger_mean_reversion
# compile_status=ok
# factor_target_count=2
# signal_expression=(close <= bb_lower)
# exit_signal_expression=(close >= bb_middle)

# 编译并输出低层规格文件
uv run qre compile strategies/high_level/bollinger_mean_reversion_entry.yaml \
  --output-dir outputs/compiled/
```

### 4. 预检查

```bash
# 全市场预检查
uv run qre preflight strategies/low_level/bollinger_mean_reversion.yaml \
  --start 2024-01-01 --end 2024-12-31

# 指定标的列表预检
uv run qre preflight strategies/low_level/bollinger_mean_reversion.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --codes 000001.SZ 000002.SZ 600000.SH

# 带缺失因子检测 (preflight 需要低层 StrategySpec)
uv run qre preflight strategies/low_level/bollinger_mean_reversion.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --output-dir outputs/preflight/
# 生成 outputs/preflight/missing_factor_requests.json
```

### 5. 评估

```bash
# 快速评估探测
uv run qre eval-smoke --start 2024-01-01 --end 2024-03-31 \
  --logical-name rsi_2 \
  --target factors.stock_daily_momentum_close.rsi_2 \
  --signal 'rsi_2 < 10' \
  --codes 000001.SZ 000002.SZ

# 从 YAML 运行完整评估
uv run qre eval-config strategies/low_level/bollinger_mean_reversion.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --output-dir outputs/eval/ \
  --group-by board \
  --random-baseline-seed 42

# 产物：
# outputs/eval/events.csv
# outputs/eval/summary.csv
# outputs/eval/ic_summary.csv
# outputs/eval/group_summary.csv
# outputs/eval/group_summary_by_board.csv
# outputs/eval/regime_summary.csv
# outputs/eval/random_baseline_summary.csv
# outputs/eval/factor_decay_summary.csv
# outputs/eval/report_manifest.json
```

### 6. 回测

```bash
# 单标回测
uv run qre backtest-single strategies/low_level/bollinger_mean_reversion.yaml \
  --symbol 000001.SZ --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/single/

# 批量回测 (独立资金池)
uv run qre backtest-batch strategies/low_level/bollinger_mean_reversion.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/batch/ \
  --group-by board --print-summary-md

# 共享资金池回测
uv run qre backtest-shared strategies/low_level/bollinger_mean_reversion.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 10000000 --max-positions 20 \
  --stop-loss-pct 0.08 --output-dir outputs/shared/
```

### 7. 全市场回测 (大运算量)

```bash
# 使用分块回测脚本 (5,525 只股票, 2010-2026)
QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' \
  uv run python -u strategies/run_bollinger_full.py

# 产物：outputs/bollinger_mean_reversion_full/batch/summary.csv
```

### 7b. 策略目录批量回测 (catalog batch runner)

```bash
# 对 strategies/catalog/ 全部策略跑研究流程 (预检+评估+回测)
QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' \
  uv run python scripts/batch_backtest_runner.py --mode smoke --skip-preflight

# 并行 + 精简产物 (推荐用于 quick/full 模式)
# --jobs N    进程池并行 worker (默认 1 串行)
# --compact   仅写策略级聚合产物 (summary.csv 等 ~9 个文件),
#             跳过 per-symbol 目录树与全市场报告包; 指标与标准模式一致
# --engine-impl {simulator,vectorized}  回测引擎实现 (默认 vectorized:
#             交易级向量化引擎, 与 simulator 结果完全一致, 实测约 43 倍提速;
#             simulator 保留为回退选项)
# --position-sizing {full_compound,fixed_cash}  仓位模型
#             (full_compound 全仓复利=现行为; fixed_cash 固定金额,
#              需配合 --engine-impl vectorized)
# --universe-filter   回测前应用策略 universe 规则 (ST/停牌/次新股/低成交额,
#             逐规则剔除计数+不可用如实标注, 产出 universe_report.json)
# --commission-rate/--min-commission/--stamp-tax/--transfer-fee/
#   --slippage-buy/--slippage-sell   成本参数运行时覆盖 (不改 YAML)
# --apply-stops   启用策略 risk: 段的止盈止损 (收盘价评估, 次日开盘执行)
# --stop-loss-pct/--take-profit-pct   覆盖策略声明的止损/止盈比例
# --trailing-stop-pct   移动止损 (锚点跟踪日内最高价, 收盘跌破即次日开盘离场)
uv run python scripts/batch_backtest_runner.py --mode quick --jobs 4 --compact --skip-preflight --resume

# 模式: smoke (2024-01~03) / quick (2024 全年) / full (2015-2025)
# 产物: outputs/backtests/<batch_id>/batch_summary.json (含分阶段耗时 stage_durations_s)
```

### 7b-2. 持续策略刷新 (continuous refresh)

```bash
# 检查数据水印与上次刷新状态 (不执行任何回测)
uv run python scripts/refresh_batch.py --check-only

# 有新数据时幂等重跑目录策略 (滚动 2 年窗口, vectorized, compact)
uv run python scripts/refresh_batch.py --jobs 4

# 强制执行 / 小样本
uv run python scripts/refresh_batch.py --force --codes 000001.SZ 600000.SH
```

产物: `outputs/refresh/state.json` (刷新状态), `outputs/backtests/refresh/<id>/` (批次),
`outputs/refresh/delta/<ts>_<batch_id>/` (与上一批次的逐策略差异报告, manifest 可审计)。

定时调度 (systemd 用户单元, 默认不安装, 需要时手动启用):

```bash
mkdir -p ~/.config/systemd/user
cp deploy/qre-refresh.service deploy/qre-refresh.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now qre-refresh.timer   # 每天 18:30 检查并刷新
```

### 7b-3. 缺因子请求队列 (missing-factor handoff)

```bash
# 缺因子的策略在批跑中自动搁置 (missing_factors), 其请求自动写入队列
# 查看队列 / 检查因子是否已入库
uv run python scripts/factor_request_queue.py list --pending
uv run python scripts/factor_request_queue.py recheck
```

队列文件: `outputs/handoff/missing_factor_requests.json`;
上游消费契约 (indicators_tushare 计算入库 → recheck → 重跑搁置策略): `docs/handoff.md`。

### 7c. 策略适配分析 (strategy fit)

```bash
# 对已完成的批次做显著性赢家分析 (零回测, 只读已有产物 + 元数据快照)
# 每股二项检验置信档 90%/99%/99.9% + 量级门槛(净收益>0 且 超额>0)
# + 策略级元检验(显著股票数 vs 假阳性期望) + 类别富集 + BH-FDR
uv run python scripts/strategy_fit_report.py --batch-dir outputs/backtests/quick_batch_106/f365c8a07b33

# 产物: outputs/strategy_fit/<batch_id>/
#   strategy_fit_stocks.csv   显著股票池 (置信档/p值/策略收益/自然收益/超额)
#   strategy_fit_summary.csv  策略级元检验档/池内与全市场超额/搭便车计数
#   strategy_fit_classes.csv  类别富集 (board/市值/流动性 + q 值)
#   strategy_fit_report.md    排名报告 (筛选证据, 非研究结论)
```

### 8. 报告查看

```bash
# 发现产物
uv run qre report-files outputs/batch/report_manifest.json --role orders

# 校验产物完整性
uv run qre report-audit outputs/batch/report_manifest.json --require-match

# JSON 输出 (脚本友好)
uv run qre report-files outputs/batch/report_manifest.json --json
uv run qre report-audit outputs/batch/report_manifest.json --json
```

### 9. 冒烟测试与 CI

```bash
# 一键冒烟测试（编译+预检+回测）
uv run qre strategy-smoke

# 查看结果
uv run qre smoke-files --details

# CI 紧凑状态
uv run qre smoke-files --status-only --status-code --status-summary

# 输出：
# 0   total=3  pass=3  fail=0  skip=0
```

### 10. 研究流程编排

```bash
# 完整流程 (preflight → eval → backtest)
uv run qre research-run strategies/low_level/bollinger_mean_reversion.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --output-dir outputs/research/bollinger_2024/ \
  --backtest-mode batch --initial-cash 1000000

# 产物：
# outputs/research/bollinger_2024/preflight/preflight_report.json
# outputs/research/bollinger_2024/eval/report_manifest.json
# outputs/research/bollinger_2024/backtest/report_manifest.json
# outputs/research/bollinger_2024/research_run_manifest.json
# outputs/research/bollinger_2024/report_manifest.json    # 顶层报告清单入口

# 顶层清单（汇总审计）
uv run qre report-files outputs/research/bollinger_2024/report_manifest.json --check-exists --validate-contents
uv run qre report-audit outputs/research/bollinger_2024/report_manifest.json --require-match
```

#### 按角色审计

顶层 `report_manifest.json`（kind=`research_run_report_manifest`）包含四个角色，每条从入口文件均为独立校验单元。`report-files --validate-contents` 与 `report-audit` 共享同一选择器语义，`--role` 将校验隔离到所选角色。

```bash
# run_manifest — 校验 research_run_manifest.json 的字段完整性
uv run qre report-audit outputs/research/bollinger_2024/report_manifest.json \
  --role run_manifest --require-match

# preflight_report — 校验 preflight_report.json JSON 内容（status / checks / missing_factor_requests）
uv run qre report-audit outputs/research/bollinger_2024/report_manifest.json \
  --role preflight_report --require-match

# eval_report_manifest — 递归校验嵌套的 eval/report_manifest.json
uv run qre report-audit outputs/research/bollinger_2024/report_manifest.json \
  --role eval_report_manifest --require-match

# backtest_report_manifest — 递归校验嵌套的 backtest/report_manifest.json
uv run qre report-audit outputs/research/bollinger_2024/report_manifest.json \
  --role backtest_report_manifest --require-match

# 角色隔离：--role run_manifest 不会校验 preflight 或嵌套阶段清单
# --role preflight_report 不会校验嵌套阶段清单
# --role eval_report_manifest 不会校验兄弟 backtest_report_manifest
```

#### 严格匹配与批量发现

```bash
# --require-match：匹配的角色退出 0，无匹配角色退出 2
uv run qre report-files outputs/research/bollinger_2024/report_manifest.json \
  --role preflight_report --require-match --json
# → {"matched_files": 1, ...} (exit 0)

uv run qre report-files outputs/research/bollinger_2024/report_manifest.json \
  --role missing_role --require-match --json
# → {"matched_files": 0, ...} (exit 2)

# report-files --validate-contents 产出的问题输出到 stderr
uv run qre report-files outputs/research/bollinger_2024/report_manifest.json \
  --role backtest_report_manifest --validate-contents --json
```

### 11. GUI 控制台

```bash
# 启动
uv run qre gui

# 浏览器访问 http://127.0.0.1:8080
# Builder 标签页: 表单式创建策略, 编译, 运行
# YAML Editor 标签页: 直接编辑策略 YAML, 保存/加载/运行
```

---

## 项目结构

```
quant-research-engine/
├── src/quant_research_engine/       # 引擎源码
│   ├── apps/cli.py                  # qre CLI 入口
│   ├── config/                      # 配置加载
│   ├── core/models.py               # 核心模型
│   ├── data/                        # 数据层
│   │   ├── postgres.py              # PostgreSQL 数据仓库
│   │   ├── assembler.py             # 研究框架组装器
│   │   ├── catalog.py               # 因子目录
│   │   ├── settings.py              # 数据库配置
│   │   └── tushare_security.py      # Tushare 安全探测
│   ├── evaluation/                  # 评估引擎
│   │   ├── engine.py                # 评估引擎
│   │   ├── signals.py               # 安全表达式信号
│   │   └── models.py                # 评估模型
│   ├── markets/                     # 市场配置
│   │   ├── base.py                  # 基础市场接口
│   │   └── ashare.py                # A 股市场配置
│   ├── orchestration/               # 流程编排
│   │   └── research_run.py          # 研究运行编排器
│   ├── portfolio/                   # 投资组合引擎
│   │   ├── single_symbol.py         # 单标回测
│   │   ├── batch.py                 # 批量回测
│   │   ├── shared.py                # 共享资金回测
│   │   ├── analytics.py             # 分析
│   │   ├── benchmark.py             # 基准对比
│   │   ├── risk_controls.py         # 风险控制
│   │   ├── weights.py               # 权重模型
│   │   ├── io.py                    # 报告 IO
│   │   ├── report_manifest.py       # 产物清单
│   │   └── full_market_report.py    # 全市场报告
│   ├── strategies/                  # 策略系统
│   │   ├── spec.py                  # StrategySpec
│   │   ├── compiler.py              # 策略编译器
│   │   ├── missing_factor.py        # 缺失因子检测
│   │   └── smoke_runner.py          # 冒烟测试执行器
│   └── gui/                         # Web GUI
│       ├── app.py                   # Flask 应用
│       ├── engine.py                # GUI 引擎逻辑
│       └── templates/               # HTML 模板
├── strategies/                      # 策略文件
│   ├── high_level/                  # 高层入口 (4 个)
│   ├── low_level/                   # 低层规格 (6 个)
│   ├── catalog/                     # 策略目录 (7 大类 111 个变体, 未提交)
│   └── run_bollinger_full.py        # 全市场运行脚本
├── tests/                           # 测试
├── docs/                            # 文档
│   ├── agent/                       # 单 agent 工作流与项目长期记忆
│   ├── modules/                     # 模块文档
│   └── strategy_entry/              # 策略入口标准
├── outputs/                         # 运行产物 → 符号链接到项目外 ~/qre-outputs (gitignore)
├── pyproject.toml                   # 项目配置
├── AGENTS.md                        # Kimi Code 单 agent 项目指令
├── CLAUDE.md                        # 跳转页（指向 AGENTS.md）
└── README.md                        # 本文件
```

---

## 策略模板示例

项目中已包含 4 个高层策略入口和 6 个低层规格：

### 高层入口 (`strategies/high_level/`)

| 文件 | 策略 | 类型 |
|------|------|------|
| `rsi2_oversold_reversal_entry.yaml` | RSI2 超卖反转 | 均值回归 |
| `ema200_bollinger_reversal_entry.yaml` | EMA200 + Bollinger 反转 | 趋势过滤均值回归 |
| `bollinger_mean_reversion_entry.yaml` | Bollinger 均值回归 | 纯均值回归 |
| `macd_zero_cross_momentum_entry.yaml` | MACD 零轴交叉 | 动量 |

### 低层规格 (`strategies/low_level/`)

| 文件 | 风险控制 |
|------|---------|
| `rsi2_reversal_research.yaml` | 无风险控制 |
| `rsi2_reversal_with_risk.yaml` | 止损+止盈 |
| `rsi2_reversal_with_risk_and_weight.yaml` | 止损+止盈+权重 |
| `rsi2_reversal_with_rebalance.yaml` | 止损+止盈+权重+再平衡 |
| `ema200_bollinger_reversal.yaml` | 原始 EMA200+Bollinger (0 交易) |
| `bollinger_mean_reversion.yaml` | 修正 Bollinger 均值回归 |

---

## 验证

```bash
# 完整测试套件 (947 个测试通过, 2 个警告)
uv run pytest -q

# 进度文档一致性检查
scripts/check-progress-docs.sh

# git diff 空白检查
git diff --check

# 目标冒烟测试
uv run pytest -q tests/test_smoke_runner.py tests/test_cli.py -k 'strategy_smoke or smoke_files'
# → 136 passed

# 目标安全探测测试
uv run pytest tests/test_tushare_security.py tests/test_postgres_store.py -q
```

---

## 设计文档索引

- [Quick Start 指南](QUICKSTART.md)
- [产品愿景](docs/agent/00_PRODUCT_VISION.md)
- [锁定需求](docs/agent/02_LOCKED_REQUIREMENTS.md)
- [路线图](docs/agent/03_ROADMAP.md)
- [模块边界](docs/modules/module_boundaries.md)
- [A 股首个市场配置](docs/modules/ashare_first_market_profile.md)
- [数据层](docs/modules/data_layer.md)
- [评估层](docs/modules/evaluation_layer.md)
- [投资组合层](docs/modules/portfolio_layer.md)
- [投资组合工作流](docs/modules/portfolio_workflow.md)
- [策略入口标准](docs/strategy_entry/README.md)
- [策略示例](docs/strategy_entry/examples.md)
- [单 agent 工作流与项目记忆](docs/agent/)
