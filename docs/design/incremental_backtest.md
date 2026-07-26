# 增量回测与日更设计（Incremental Backtest Persistence）

状态：设计稿 v1（2026-07-25，待用户审定后实施）

## 1. 问题与目标

现状：每次全期回测（2010→今）都要重读 ~2,100 万行 K 线并重放全部历史——2 个策略 × 全市场 ≈ 1 小时，且每次结果 99% 与上次重复。用户目标：**历史结果持久化，每日只对新数据做增量计算并叠加**，与 quant_ts（日线下载 16:30）、indicators_tushare（因子计算 16:40）一样纳入日常定时计划。

核心约束：回测是**状态机**（持仓、成本、挂单、移动止损锚点），不能只存"结果"——必须存**可续算的状态**。

## 2. 数据层事实核查（已定）

- `public.stock_daily` 为 **前复权（qfq）价格**（quant_ts `pro_bar(adj='qfq')`，600519 除息日实测平滑过渡）。
- 推论：**持仓跨除权除息日无需任何调整**——前复权价格天然连续，这正是用户提到的"注意除权除息"的答案：数据层已解决。
- 但必须处理**上游重算**：调整因子更新时 quant_ts 会重灌历史 qfq 价格（其 2026-04 commit "Fix configured recompute to refresh full history"）→ 历史检查点可能失效，需要版本检测（见 §6）。

## 3. 存储设计（文件制，遵守 R-QRE-005 只读 DB）

每个策略一个目录 `outputs/state/<strategy_id>/`：

```
outputs/state/<strategy_id>/
├── state.json            # 检查点（见下）
├── orders.csv            # 追加式逐笔委托（含成本分项）
├── trades.csv            # 追加式逐笔往返
├── failed_orders.csv     # 追加式拒单
├── equity_curve.csv      # 追加式逐日权益 (symbol, trade_date, cash, quantity, market_value, total_equity)
├── summary.csv           # 每次更新后由累计账本重算（小成本）
└── report/               # 报告包按需重生成（xlsx/html，非每日必需）
```

`state.json`（检查点 v1）：

```json
{
  "schema_version": 1,
  "strategy_id": "mr04a_ibs_reversal",
  "config_hash": "<sha1(spec YAML + engine 版本 + profile 参数)>",
  "last_processed_date": "2026-07-24",
  "data_watermark": "2026-07-24",
  "symbols": {
    "000001.SZ": {
      "cash": 999690.15,
      "quantity": 106900,
      "entry_bar_date": "2024-02-26",
      "entry_price": 9.35,
      "entry_cost": 309.85,
      "entry_cost_parts": {"commission": 299.85, "transfer_fee": 9.995, "stamp_tax": 0.0},
      "trailing_anchor": 9.80,
      "pending_sell": null,
      "pending_buy": null,
      "flat_since": null
    }
  }
}
```

- 只记录**当前仍有效的状态**：持仓中的标的（含入场信息与锚点）、有未决挂单（含拒单重试）的标的、以及每个标的的当前现金（batch 模式每标的独立资金）。
- 空仓且无挂单的标的无需记录（下次出现信号时自然重新进入）。
- `config_hash`：spec 内容 + 引擎实现 + 市场参数（成本/滑点/止损/universe）的哈希——任一变化则检查点作废，全量重建（防止新旧语义混接）。

## 4. 每日增量算法

定时：新增 `qre-incremental.timer`（建议 18:30，在 quant_ts 16:30 与 indicators 16:40 之后）。

对订阅的每个策略（默认目录策略全集，可配置子集）：

1. 读检查点 → `last_processed_date = D`；查数据水印 `W = MAX(trade_date)`。若 `W <= D`，无操作。
2. 加载暖机窗口数据 `[D − WARMUP, W]`（WARMUP = 该策略信号表达式中最大 shift/rolling 窗口 + 余量，目录最大 sma_120 → 150 个交易日）。暖机数据只用于**正确计算新日期的信号**（指标本身在 factors.* 已是预算好的，只有表达式内 `.shift()/.rolling()` 需要历史）。
3. 符号集合 = 检查点中的持仓/挂单标的 ∪ 新窗口内出现的全部标的（含新上市；universe 过滤按当前规则重算——只影响**新入场**，不追溯历史）。
4. 对每个标的：从检查点恢复状态机（无记录则初始全现金空仓），只在 `[D+1, W]` 上跑事件循环（信号在暖机序列上预计算，取 >= D+1 的部分），产出新增的 orders/trades/failed/equity 行。
5. 追加写入各账本（按 (symbol, trade_date, side) 去重，保证幂等——重复运行同一天不重复记账），重算 `summary.csv`，写新检查点（`last_processed_date = W`）。
6. 可选（每周/每日）：从累计账本重生成报告包（xlsx/html）——报告重生成的输入是**累计账本**，不是重跑。

预期成本：每策略每日 ≈ 秒级（~5,400 标的 × ~150 暖机日 ≈ 80 万行 + 少量新交易），相对全量重放 ~30 分钟，提速 2-3 个数量级。

## 5. 正确性门槛（等值验收，不可妥协）

**增量续算必须与不增量全量重放产出逐字节一致的账本**：

- 测试：合成数据上 全量 [T0,T2] ≡ 全量 [T0,T1] + 增量 [T1+1,T2]（含持仓跨界、挂单重试、移动止损锚点跨界、除权日穿越）。
- 真实库验收：选一个策略，全量 2024-01→2024-06 vs 全量 2024-01→2024-03 + 增量 2024-03→2024-06，orders/trades/equity 逐字节对比。
- 通过后才允许纳入日更。

## 6. 失效与重建

- **config_hash 变化**（策略 YAML、引擎版本、成本参数）→ 检查点作废，全量重建。
- **上游重算历史**（quant_ts 重灌 qfq 价格 / indicators 重算因子）→ 通过 `data_watermark` 与可选的`max(trade_date)`+行数抽检发现；提供 `--rebuild` 手动全量重建与按标的重建。
- **检查点损坏/缺失** → 自动回退为首次全量运行。

## 7. 与现有件的关系

- 复用：`SingleSymbolBacktestEngine`/`SingleSymbolVectorizedEngine`（事件循环不变）、`write_batch_result` 产物写入、symbol chunking、universe filter、factor queue、refresh 定时器模式（deploy/*.timer 交付不安装）。
- 分期：**P1 = batch 模式（单标独立资金，本次范围）**；P2 = shared-cash 模式（组合级状态含 lot FIFO，状态结构更复杂，后续）。
- 初始种子：每个订阅策略先做一次全量运行生成检查点（一次性成本，之后纯增量）。

## 8. 不做的事

- 不写任何数据库表（文件制；若未来需要 DB 镜像，需用户另行批准）。
- 不改引擎语义；不处理分钟级数据；shared-cash 留待 P2。
- 日报表的 xlsx/html 不强制每日重生成（可选策略）。

---

请审定：① 文件制存储是否接受（vs 入 DB）② 定时 18:30 是否合适 ③ 等值门槛（增量 ≡ 全量）作为验收标准 ④ P1 只做 batch 模式。
