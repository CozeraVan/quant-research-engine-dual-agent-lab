# 42_CF_FULLSCALE_ACCEPTANCE_2026-11-11.md — 经典策略全期全量回测验收报告

## 1. 范围与统一口径

- **策略**：`docs/agent/classic_catalog/inventory.json` 中 118 个经典策略（编号 CF-001～CF-118）
- **区间**：2009-01-05 → 2026-10-30（全期）
- **标的**：全 A 股（全市场）
- **统一参数**：初始资金 100,000 元、最大持仓 **0 = 不限**、最大持仓天数 20、
  入场/出场成交价均为 `open`；佣金 0.03%（最低 5 元）、印花税卖出 0.05%、滑点 0
- **归属**：全部 `jobs` / `results` / `strategies` 均归 **user 6 = 17157845743**（实测 121 条 job、120 条结果）
- **提交方式**：全部经 `scripts/classic_catalog/fullscale.py` 串行/并行提交，幂等键 `CF-<编号>-<strategy_id>-v<版本>`

## 2. 完成情况

| 项 | 结果 |
|---|---|
| 完成度 | **118 / 118 = 100%** |
| 生产 jobs | 119 completed（CF-005 曾重试多 1 条）+ 2 failed 历史行 + 0 active |
| 交易数合计 | 约 **3,100 万笔**（索引口径 31,061,138，按每个 CF 最新一条 job 计） |
| 交易数中位数 | 104,904 |
| 最大 | CF-022 `cb01a_ma_cross_rsi` 2,693,401 笔；CF-026 1,985,424；CF-111 1,873,483 |
| 零交易 | **CF-018、CF-074**（见 §4） |

时间线：11-03 起跑 → 11-07 改 2 路并行（实测约 **2.1× 加速**）→ 11-11 00:19 全部落账。

## 3. 本轮基础设施事故与修复（索引）

完整登记见 `41_CF_RUN_ANOMALY_LOG_2026-11-09.md`（A-01～A-12，待修项 F-01～F-11）。

- WebBridge 瞬断/标签丢失 → 监管自愈（重建标签 + 幂等 resume）
- 监管 `flock` fd 泄漏自锁 → 子进程 `9>&-` 修复
- 重启竞态 57P03 → `db-ready.conf` 等 `pg_isready`，**11-10 崩溃重启中实测验证通过**
- 回传 429 被判终态 → worker 有限重试 + nginx worker 通道放宽到 `300r/m burst 120`
- 在途预算闸压回单路 → `QRE_WORKER_HEAVY_ADMISSION_GB=6.5`（依据实测 6.05 GiB 峰值）
- SSH rc=255 打断轮询 → 监管 2 分钟自愈（根治在 F-11）
- **11-11 ECS OOM**：118 条进 showcase 后 `/api/saas/showcase` 整列读 `chart_data`，
  2GB 实例 OOM 杀 worker → 改为只取 `chart_data->'metrics'`，公网恢复（200 / 1.34s / 119 条）

## 4. 两个零交易策略的处置建议（待用户批准）

| CF | 根因 | 建议 |
|---|---|---|
| CF-018 `bo09e_channel_retest_breakout` | `close.shift(1) > close.shift(1).rolling(20).max()` 自引用恒假 | 改为 `(close.shift(1) > close.shift(2).rolling(20).max()) & (close > sma_20) & (close > close.shift(1))`，重跑该 CF |
| CF-074 `mr08a_mfi_oversold_reversal` | `rsi<30 & close>sma_60` 全市场 14.88M 行仅 4 次同时成立，条件近乎互斥 | 趋势过滤改为「sma_60 向上」或删去 `close>sma_60`，重跑该 CF |

**重要口径**：引擎 `QRE_PRICE_BASIS=raw` 会把价格列 ×`adj_factor`（后复权），与因子库同尺度，
**不存在系统性价格口径偏差**。排查时请统一用后复权价，否则会得到错误结论。

## 5. 公开访问与取材料入口

- **公开列表（免登录）**：`https://aguhuice.com/saas/showcase`，API `https://aguhuice.com/api/saas/showcase`
- **逐策略结果页**：`https://aguhuice.com/saas/jobs/<job_id>`
- **参数快照（可复现）**：`https://aguhuice.com/saas/jobs/<job_id>` → 「回测参数」折叠卡，
  支持复制参数 JSON / 复制策略 YAML / 用同样参数重跑（新幂等键）
- **给 AI agent 的索引**：`docs/agent/classic_catalog/CF_RESULT_INDEX.json`
  （118 条：CF 编号、策略 ID、job_id、交易数、结果页/参数/图表/个股明细 URL）

## 6. 资源与性能（实测）

- 2 路并行吞吐 ≈ 串行的 **2.1×**（切换后 9h36m 完成 10 个，串行基线需 20h）
- 单任务耗时中位数约 120 分钟，最长 208 分钟（CF-054）
- worker cgroup 峰值：串行 6.05 GiB、双路最高 16.09 GiB（上限 18 GiB）
- 单任务 CPU 约 0.25 核，PG 侧约 0.17 核——**算力不是瓶颈，串行度才是**
- 119 条 showcase 的 API 现在 1.34s / 194KB，ECS 内存 727MB/1612MB

## 7. 待办（下一阶段）

1. 修两个零交易 YAML 并重跑（§4，待批准）
2. `41` 号文档 F-01～F-11：HALT 告警、回传重试大产物实测、并发动态降档、SSH 重试等
3. 上云扩容方案落地（用户端 2C4G + 计算 8C16G + RDS 4C16G/1TB + OSS，VPC 内网互联）
4. 持续跟踪模块：数据库/因子日更后自动增量回测（未做）

---

**验收方式**：在 `https://aguhuice.com/saas/showcase` 逐条打开任一策略，检查收益曲线、
指标、参数快照、个股明细；如需复现，用「回测参数」卡的「用同样参数重跑」。
