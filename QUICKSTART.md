# Quick Start Guide

本指南帮助你在 **10 分钟内** 完成从零到第一次回测的全流程。

---

## 1. 前置条件 (Prerequisites)

| 组件 | 版本要求 | 验证命令 |
|------|---------|---------|
| Python | 3.10+ | `python --version` |
| uv | 最新版 | `uv --version` (未安装: `pip install uv`) |
| PostgreSQL | 14+ | `psql --version` |

安装 uv (如未安装):

```bash
pip install uv
```

---

## 2. 数据库准备

QRE 需要 PostgreSQL 数据库，其中包含 A 股行情、因子和元数据表。

> **数据来源说明:** QRE 自身 **不负责** 数据下载和入库。这部分工作由兄弟项目 `quant_ts` (Tushare 数据管道) 和 `indicators_tushare` (技术因子计算) 负责。如果你还没有准备好数据，请先参考这些项目的文档。

### 2.1 创建数据库

```bash
createdb tushare_data
# 或者通过 psql:
# psql -c "CREATE DATABASE tushare_data;"
```

### 2.2 必需的数据库表

数据管道需要填充以下表结构：

| Schema | 表名 | 用途 | 优先级 |
|--------|------|------|--------|
| `public` | `stock_daily` | 日线 OHLCV 数据 (trade_date, ts_code, open, high, low, close, pre_close, vol, amount) | **必需** |
| `factors` | `*` | 技术因子列 (如 `stock_daily_momentum_close.rsi_2`) | **必需** (回测依赖) |
| `reference` | `stock_basic` | 证券基本信息 (ts_code, list_date, board) | 推荐 (元数据) |
| `reference` | `daily_basic` | 每日基础数据 (总市值、流通市值、换手率) | 推荐 (分组分析) |
| `reference` | `stock_suspend` | 停牌记录 | 可选 (停牌过滤) |
| `reference` | `stock_st` | ST 记录 | 可选 (ST 过滤) |
| `reference` | `stock_risk_warning` | 风险警示记录 | 可选 (风险过滤) |

### 2.3 验证数据

```bash
psql -d tushare_data -c "SELECT count(*) FROM public.stock_daily;"
# 应该有数千万行数据

psql -d tushare_data -c "SELECT count(*) FROM reference.stock_basic;"
# 应该有 5000+ 行
```

---

## 3. 环境配置

### 3.1 克隆项目

```bash
git clone <repo-url> quant-research-engine
cd quant-research-engine
```

### 3.2 配置环境变量

```bash
# 复制模板
cp .env.example .env

# 编辑 .env，填入你的数据库连接信息
# 至少修改 QRE_MARKET_DB_URL 中的 user:pass
vim .env

# 加载环境变量
set -a && source .env && set +a
```

### 3.3 验证连接

```bash
uv run qre db-smoke --start 2024-01-01 --end 2024-01-31 --limit 5
```

如果看到 OHLCV 数据输出，说明数据库连接成功。

---

## 4. 安装依赖

```bash
uv sync
```

安装完成后可以快速验证测试套件 (可选):

```bash
uv run pytest -q
# 预期: 947 passed, 2 warnings
```

---

## 5. 第一次冒烟测试

冒烟测试一键运行编译 → 预检查 → 回测全流程，验证整个工具链是否正常:

```bash
uv run qre strategy-smoke
```

查看结果:

```bash
uv run qre smoke-files --details
```

预期输出: `total=3 pass=3 fail=0 skip=0`

---

## 6. 第一次回测

### 6.1 编译高层策略入口

从人类可读的 YAML 编译为引擎可执行的低层规格:

```bash
uv run qre compile strategies/high_level/rsi2_oversold_reversal_entry.yaml
```

输出示例:
```
strategy_id=rsi2_oversold_reversal
compile_status=ok
factor_target_count=1
signal_expression=(rsi_fast < 10)
exit_signal_expression=(rsi_fast > 70)
```

### 6.2 运行单标回测

```bash
uv run qre backtest-single strategies/low_level/rsi2_reversal_research.yaml \
  --symbol 000001.SZ \
  --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 \
  --output-dir outputs/my-first/
```

### 6.3 查看回测结果

```bash
ls outputs/my-first/
# 产物列表: orders.csv  trades.csv  equity_curve.csv  drawdown_curve.csv
#          summary.json  strategy_performance.json  backtest_report.xlsx
#          backtest_report.html  report_manifest.json  ...

# 查看摘要
uv run qre report-files outputs/my-first/report_manifest.json
```

### 6.4 启动 GUI (推荐)

浏览器控制台提供策略编辑器、运行历史和产物查看器:

```bash
uv run qre gui
# 浏览器访问 http://127.0.0.1:8080
```

---

## 7. 进阶用法

### 全市场批量回测

```bash
uv run qre backtest-batch strategies/low_level/rsi2_reversal_research.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 \
  --output-dir outputs/rsi2_full/ \
  --group-by board
```

### 共享资金池回测

```bash
uv run qre backtest-shared strategies/low_level/rsi2_reversal_with_risk.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 10000000 --max-positions 20 \
  --stop-loss-pct 0.08 \
  --output-dir outputs/rsi2_shared/
```

### 完整研究流程 (预检查 → 评估 → 回测)

```bash
uv run qre research-run strategies/low_level/rsi2_reversal_research.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --output-dir outputs/research/rsi2_2024/ \
  --backtest-mode batch --initial-cash 1000000
```

### 报告校验

```bash
uv run qre report-audit outputs/rsi2_full/report_manifest.json --require-match
```

---

## 8. 下一步

| 想做的事 | 参考文档 |
|---------|---------|
| 理解全部 18 个 CLI 命令 | [README.md](README.md) — "入口" 章节 |
| 编写自己的策略 | [docs/strategy_entry/README.md](docs/strategy_entry/README.md) |
| 了解评估引擎细节 | [docs/modules/evaluation_layer.md](docs/modules/evaluation_layer.md) |
| 了解投资组合引擎细节 | [docs/modules/portfolio_layer.md](docs/modules/portfolio_layer.md) |
| 查看项目架构 | [docs/modules/module_boundaries.md](docs/modules/module_boundaries.md) |
| 使用 Makefile 快捷命令 | 运行 `make` 或 `make help` |

---

## 9. 常见问题

### `QRE_MARKET_DB_URL or SR_MARKET_DB_URL is required`

环境变量未设置。检查:
1. `.env` 文件是否已创建: `ls -la .env`
2. 环境变量是否已加载: `echo $QRE_MARKET_DB_URL`
3. 如果未加载: `set -a && source .env && set +a`

### `relation "public.stock_daily" does not exist`

数据库表不存在。检查:
1. 数据库连接是否正确: `psql $QRE_MARKET_DB_URL -c "\dt public.*"`
2. 数据是否已通过 `quant_ts` 管道导入

### `factor ... not found in factors.*`

因子尚未计算。检查:
1. 策略需要哪些因子: 查看 `factor_requirements` 部分
2. 因子是否存在于数据库: `psql -d tushare_data -c "\dt factors.*"`
3. 如需新增因子，使用 `indicators_tushare` 项目计算

### `Connection refused`

PostgreSQL 未运行或连接信息错误。检查:
1. PostgreSQL 是否运行: `pg_isready`
2. `.env` 中的 host/port 是否正确
3. 防火墙是否允许连接
