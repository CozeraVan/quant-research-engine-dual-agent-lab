# 2026-11-02-external-agent-api-design.md — 第四入口：外部 AI Agent API 设计（V1 / M0）

> 状态：**M0 设计定稿，待用户批准**。本阶段不写业务代码、不部署、不上线。
> 本文修订并取代 `2026-10-25-external-agent-api-brainstorm.md` 的范围定义；该文保留为历史记录，
> 以本文为准（差异对照见 §2）。

---

## 0. 用户设定边界（2026-11-02，不可协商）

1. **不自建模型**：个人开发，QRE 不自建、不微调、不托管任何模型；智能全部来自用户自带的
   外部 AI（Claude / Grok / WorkBuddy / DeepSeek 等）。QRE 不提供站内 AI 循环、不调 LLM、
   不做 prompt 工程、不含任何模型推理代码。
2. **只做回测**：第四入口可调用本数据库内**全部数据**进行回测（全市场、全区间、全因子库，
   能力上不设限），但职责仅限于回测相关动作：发现 → 校验 → 提交 → 轮询 → 读结果 → 聚合。
   不做盯盘、下单、信号推送、资讯、组合管理、外部数据抓取等任何非回测工作。
3. **不做投资建议**：QRE 只做数据结果聚合（每配置标准指标、排名、基准对比、成本估计），
   不判定显著性、不给目标函数评分、不给买卖结论。解释与决策归外部 agent 与用户。
4. 其余边界按 §10 推荐参数默认值执行，均可在 9090 管理台调整。

---

## 1. 定位：个人量化研究员 agent 的四段式工作流

```
① 定边界（用户 ↔ 外部 agent 对话）  ② 出工作清单   ③ 批量回测   ④ 汇总结论提交用户
        │                                │                │              │
   外部 agent 负责                   外部 agent 负责    QRE 执行       QRE 只算数
   意图/范围/预算协商                 拆成可执行配置     串行展开       聚合表 + 存结论文本
```

QRE 的角色是**执行器 + 记账本 + 聚合器**，不是研究员。对话、规划、解释全部在 QRE 之外。

典型用例（用户原话）："测试 EMA 这个指标是否有意义" → 外部 agent 拆成
EMA 周期扫描（5→250）与 EMA×其他指标组合，先抽样粗筛，再对短名单上全市场全期，最后给出结论。

---

## 2. 与 2026-10-25 brainstorm 的边界修订

| 10-25 原文 | 11-02 修订 | 理由 |
|---|---|---|
| 明确不做 sweep / parent-child 编排 / 参数网格 | **提供最小 sweep 原语**（串行展开、共享预算、聚合表）；编排逻辑仍在外部 agent | 用户核心诉求即周期/组合扫描 |
| 不建会话容器 | **新建 `research_runs` 一等公民**（边界/清单/预算/结论的结构化落点） | 「汇总结论提交用户」需要落点与审计单位 |
| 成本口径未提 | **新增 `capabilities` 成本信封** | agent 需要用它跟用户对话定边界 |
| 估算 12–15 人日 | **20–25 人日** | 新增 sweep / 容器 / 预算闸 / 审计 / 9090 |
| MCP 后置 | 维持后置 | — |
| 不改引擎 / worker 协议 / 结果合同 | 维持不变 | 边界 1、2 |

---

## 3. 架构总览

```
用户 ──对话──▶ 外部 Agent（规划 / 解释 / 结论）
                 │ HTTPS + Authorization: Bearer <api_token>
                 ▼
        QRE SaaS（ECS 2C2G）  /api/agent/v1/*
                 │ 现有 job 队列（PG SKIP LOCKED，17_JOB_PROTOCOL 不变）
                 ▼
        家里 worker（执行端，容量硬瓶颈）
```

新增面只在 SaaS 应用层：一个蓝图/路由模块 + 两张表（`api_tokens`、`research_runs`）+ jobs 三列。
引擎、worker、结果合同、产物格式零改动。

---

## 4. API 合同 V1

统一响应 envelope：`{"ok": true, "data": {...}}` / `{"ok": false, "error": {"code": "...", "message": "..."}}`。
错误码表见 §11。所有响应（除 openapi 外）带 `disclaimer` 字段：`"本研究结果仅供研究使用，不构成投资建议"`。

### 4.1 发现（需 token）

| 端点 | 说明 |
|---|---|
| `GET /api/agent/v1/openapi.json` | 版本、端点、限额、错误码、轮询建议、A 股规则 |
| `GET /api/agent/v1/capabilities` | **成本信封**（§5），agent 与用户定边界的依据 |
| `GET /api/agent/v1/factors` | 复用 `/api/saas/factors`（分组 + 中文别名 + 价格口径） |
| `GET /api/agent/v1/universes` | 复用 `/api/saas/universes`（名称 + 成员数 + `all_a_count`） |
| `GET /api/agent/v1/schema/strategy` | `StrategySpec` 的 JSON Schema（**新增导出**，一次成型后随因子目录快照维护） |

### 4.2 校验

`POST /api/agent/v1/validate`，body `{yaml, params}` →

```json
{"ok": true, "data": {
  "valid": true, "issues": [],
  "normalized_params": {"codes": ["600519.SH"], "start": "2021-01-04", "end": "2026-10-30"},
  "factor_usage": {"tables": 2, "fields": 6},
  "cost_estimate": {"profile": "sample300_5y", "est_seconds": 14, "artifact_kb": 900}
}}
```

复用：`gui/engine.py:158 validate_yaml`、`check_factor_limits`、`normalize_ts_codes`、
universe 解析、`classify_job_weight`。**不执行、不建 job、不计配额、不写缓存、不调 LLM。**

### 4.3 研究会话 `research_runs`

| 端点 | 说明 |
|---|---|
| `POST /api/agent/v1/research-runs` | `{title, boundary_text, todo[], budget{}}` → `{run_id, status:"planned"}` |
| `GET /api/agent/v1/research-runs/<id>` | 含 jobs 列表、预算消耗、聚合结果引用 |
| `POST /api/agent/v1/research-runs/<id>/conclusion` | `{conclusion_text, conclusion_table}`——**只存不解释**，QRE 不生成、不改写 |
| `GET /api/agent/v1/research-runs` | 本人列表（分页） |

状态机：`planned → running → aggregated → concluded`（`archived` 为 TTL 终态）。
迁移由 agent 调用驱动，QRE 只校验归属与预算，不替 agent 决定下一步。
`boundary_text` / `todo[]` / `conclusion_text` 均为**用户与 agent 的原始文本**，QRE 原样存储。

### 4.4 sweep（核心原语）

`POST /api/agent/v1/sweeps`

```json
{"research_run_id": 12,
 "base_yaml": "<StrategySpec YAML，含待扫描参数的占位值>",
 "grid": {"data.factor_params.ema_fast": [5,10,20,30,60]},
 "params": {"mode": "batch", "random_n": 300, "start": "2021-01-04", "end": "2026-10-30"},
 "stage": "screen"}
```

- `stage=screen`（默认）：**强制**抽样股票池与较短区间（§10 默认 random_n=300 / 近 5 年），
  拒绝 `all_market` 与超过上限的区间——这是防爆炸的第一道闸。
- `stage=confirm`：短名单全量，需 `budget.allow_full_market=true` 且配置数 ≤ 5。
- 服务端把 grid 笛卡尔积展开为 N 个 `kind=full` 子 job，**串行**入队（V1 不做并发调度），
  全部挂 `research_run_id` 与 `token_id`，**共享会话预算**。
- 响应：`{sweep_id, planned_count, job_ids[], budget_remaining, eligible_at}`。
- `GET /api/agent/v1/sweeps/<id>/aggregate` → 排名表，**只有数字没有解读**：

```json
{"ok": true, "data": {"rows": [
  {"config": {"ema_fast": 5}, "n_symbols": 287, "total_return": 0.183,
   "annualized": 0.041, "sharpe": 0.22, "max_drawdown": -0.31, "trades": 1204,
   "cost_drag": 0.012, "benchmark": {"code": "000300.SH", "excess": -0.06}}
], "sorted_by": "sharpe", "note": "聚合仅为数值计算结果，不含任何投资建议"}}
```

### 4.5 任务与结果

| 端点 | 说明 |
|---|---|
| `POST /api/agent/v1/jobs` | 单配置提交，**强制 `Idempotency-Key`**（缺 key 400） |
| `GET /api/agent/v1/jobs/<id>` | 复用现有响应（`queue_position` / `worker_online` / 进度） |
| `POST /api/agent/v1/jobs/<id>/cancel` | 复用现有取消语义 |
| `GET /api/agent/v1/jobs/<id>/result` | 复用 `/api/results/<id>/{summary,chart-data,symbols,risk-analysis}`，按 token 归属放行（走 P0-8 的 `_require_completed_result`） |
| `GET /api/agent/v1/jobs/<id>/artifacts/<name>` | 受控下载：token 归属 + 文件名白名单 + 限速 + TTL |

---

## 5. 成本信封 `capabilities`（关键设计）

基于 `14_LAUNCH_ROADMAP.md` §10 实测基线与 2026-11-02 全期全量压测结果（**压测出来后必须校准**）：

```json
{"scale_profiles": [
  {"name": "smoke_6m",     "universe": "1 只固定标的", "est_seconds": 5,   "peak_mem_mb": 1500, "artifact_kb": 400},
  {"name": "sample300_5y", "universe": "随机 300 只",   "est_seconds": 14,  "peak_mem_mb": 2000, "artifact_kb": 900},
  {"name": "full_a_2y",    "universe": "全 A 约 5860",  "est_seconds": 111, "peak_mem_mb": 5900, "artifact_kb": 400000},
  {"name": "full_a_full",  "universe": "全 A 全区间",   "est_seconds": 900, "peak_mem_mb": 5900, "artifact_kb": 4000000}
], "measured_at": "2026-10-03", "source": "§10 容量基线 + 27_STRESS_TEST",
 "note": "历史实测估计，不承诺；实际以 job 记录为准"}
```

作用：外部 agent 用它把"跑 1250 个组合要 4.9 小时、2GB 产物"这类事实告诉用户，再定边界。
这是全项目**性价比最高**的一块——不需要新代码路径，只是把已有实测数据机器可读化。

---

## 6. 令牌体系 `api_tokens`

```sql
CREATE TABLE IF NOT EXISTS api_tokens (
    id                BIGSERIAL PRIMARY KEY,
    user_id           BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,
    prefix            TEXT NOT NULL,                 -- 展示用前 8 位
    token_hash        TEXT NOT NULL UNIQUE,          -- sha256("apitok:" + token + salt)
    scopes            TEXT[] NOT NULL DEFAULT ARRAY['jobs:submit','jobs:read','results:read','factors:read'],
    allow_full_market BOOL NOT NULL DEFAULT false,   -- 能力开关，授予后仍受会话预算约束
    daily_submit_limit INT NOT NULL DEFAULT 50,
    in_flight_limit    INT NOT NULL DEFAULT 5,
    rate_per_minute    INT NOT NULL DEFAULT 60,
    nightly_only       BOOL NOT NULL DEFAULT true,
    expires_at        TIMESTAMPTZ,
    revoked_at        TIMESTAMPTZ,
    last_used_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens(user_id);
```

纪律（复用 `share_links` 踩坑）：明文 token **只在创建响应返回一次**；库内只存加盐 hash；
生产须先 `postgres apply` 再发代码；revoked/过期立即 401；token 明文不进日志、不进错误体。

`jobs` 增加三列：`token_id BIGINT`、`research_run_id BIGINT`、`labels JSONB`（QRE 只存不解释）。

---

## 7. 配额、限流与容量保护

| 机制 | 设计 |
|---|---|
| 不抢占真人 | agent job `priority=0`，与人工同队 FIFO；worker claim 协议不变 |
| 夜间窗口 | `nightly_only` 默认 true（00:00–06:00 Asia/Shanghai，可配）。**实现取舍**：提交即返回 `queued` + `eligible_at`，由现有定时扫描到点置可认领，**不改 claim 热路径** |
| 会话预算 | `max_jobs` / `max_artifact_bytes` / `max_wall_clock_hours` / `allow_full_market`；sweep 展开前预检，超限返回 `budget_exhausted` 并不再展开 |
| 每 token 配额 | `daily_submit_limit` / `in_flight_limit`；超限 429 + `Retry-After` 与 `reset_seconds` |
| 限流 | `rate_per_minute`，同 key 咨询锁模式复用 `nl_compile_support` 思路 |
| 产物 TTL | sweep 子 job 产物默认 compact，到期归档（复用 CR-2026-10-29_artifact_archive 机制，保留期 15 天） |

**硬规则**：产物 TTL 与 compact 必须与 sweep **同时上线**，不得后补——sweep 是磁盘风险的头号来源。

---

## 8. 审计与管理台（R-ADMIN-001）

- 9090 console 新增「外部 Agent」页：
  - token 列表：prefix / scopes / 限额 / 最近使用 / 吊销按钮；
  - 研究会话列表：预算消耗、job 数、聚合结果入口、结论文本；
  - 成本信封当前值（与执行常量同源，不建第二套配置）。
- 事件口径最小化：记录 token 提交次数与拒绝原因分类（参考 `nl_compile_events`），
  **不存策略文本、不存 token 明文、不存原始 IP**。
- 权限/配额改动必须在 commit/push 前完成管理台可视化（R-ADMIN-001），本次为文档阶段先行登记。

---

## 9. 明确不做（V1）

- 不自建/不调任何 LLM；不做站内对话 UI；不做 prompt（边界 1）。
- 不做盯盘、下单、信号、资讯、组合管理、外部抓数（边界 2）。
- 不做投资建议、显著性判定、目标函数评分、排行榜（边界 3）。
- 不做 MCP、OSS 直传、机器时配额付费。
- 不改回测引擎、不改 worker 协议、不改结果合同、不改产物格式。
- 不做并发 sweep 调度（V1 串行）、不做父子 job 可视化树。
- 不加仓/金字塔/自定义订单类型（需独立引擎 CR）。

---

## 10. 推荐参数默认值（边界 4 落地）

| 参数 | 默认 | 说明 |
|---|---|---|
| `daily_submit_limit` | 50 | 每 token 每日提交上限 |
| `in_flight_limit` | 5 | 在飞任务上限 |
| `rate_per_minute` | 60 | 请求限流 |
| `nightly_only` / 窗口 | true / 00:00–06:00 | 可配；保护真人时段 |
| sweep screen universe | `random_n=300` | 阶段一强制抽样 |
| sweep screen 区间 | 近 5 年 | 阶段一强制 |
| sweep confirm 配置数 | ≤ 5 | 阶段二短名单上限 |
| `allow_full_market` | false | 需 token scope **且**会话预算双确认 |
| 会话 `max_jobs` | 200 | 会话级 |
| 会话 `max_artifact_bytes` | 20 GB | 会话级 |
| 会话 `max_wall_clock_hours` | 12 | 会话级 |
| 产物 TTL | 15 天 | 与 D-21 保留期一致 |
| 成本信封校准周期 | 每次压测后 | 偏差 >50% 必须更新并记录 |

> 边界 2 说"可调用全部数据"：以上默认值是**运营收紧**而非能力剥夺——
> `allow_full_market` 授予后能力不受限，只是需要显式确认与预算。

---

## 11. 错误码表（V1）

| code | HTTP | 含义 |
|---|---|---|
| `unauthorized` | 401 | 缺/错/过期/已吊销 token |
| `forbidden_scope` | 403 | token 无对应 scope |
| `not_found` | 404 | 他人资源与不存在同体（不泄露存在性） |
| `invalid_yaml` | 400 | YAML/StrategySpec 不合法 |
| `factor_limit_exceeded` | 400 | 超出 max_fields/max_tables |
| `missing_idempotency_key` | 400 | 单提交缺幂等键 |
| `budget_exhausted` | 409 | 会话预算用尽 |
| `stage_not_allowed` | 409 | screen 阶段要全量 / confirm 超配置数 |
| `in_flight_limit` | 429 | 在飞任务超限 |
| `daily_submit_limit` | 429 | 每日提交超限 |
| `rate_limited` | 429 | 每分钟限流（带 `Retry-After`） |
| `nightly_window` | 202 | 已受理，`eligible_at` 后才可认领（**非错误**） |

---

## 12. 测试与验收清单

- **IDOR**：token A 读不到 token B / 他人用户的 job、research_run、result（匿名 401、他人 404、与不存在同体）。
- **配额**：日限 / 在飞 / 限流三项各自复现与恢复；429 必带 `Retry-After`。
- **预算**：sweep 展开到 `max_jobs` 即停；confirm 阶段无 `allow_full_market` 拒绝；screen 阶段要全量拒绝。
- **幂等**：同 `Idempotency-Key` 返回既有 job（`deduped: true`），不重复扣配额。
- **吊销**：revoke 后新请求 401；已生成结果随 owner 权限，不因 token 吊销而放给他人。
- **成本信封**：数值与实测偏差 ≤50% 即通过（明确标注为估计）。
- **聚合口径**：`aggregate` 与 `/api/results/<id>/summary` 同源函数计算，禁第二套实现。
- **免责**：所有响应带 `disclaimer`；聚合表无任何解释性字段。
- **M6 真实 agent 验收**：用一个真实外部 agent 完成一次 EMA 周期扫描会话
  （screen 50 配置随机300×5年 → confirm 3 配置全A×全期 → 提交 conclusion），
  **全程未经显式确认不得全量**。

---

## 13. 里程碑与工期

| 切片 | 内容 | 估时 |
|---|---|---|
| M0 | 设计（本文 + CR） | 本次完成 |
| M1 | `api_tokens` + `capabilities` + `openapi.json` + `schema/strategy` | 3–4 人日 |
| M2 | `research_runs` 容器与状态机 | 2–3 人日 |
| M3 | `validate` + `sweeps`（串行展开 + 预算闸 + 聚合） | 5–6 人日 |
| M4 | 配额/限流/夜间窗口/审计 + 9090 页面 | 4–5 人日 |
| M5 | 结果放行 + 受控下载 + 产物 TTL 归档 | 3–4 人日 |
| M6 | 真实外部 agent 端到端验收 | 2–3 人日 |

合计约 **20–25 人日**。M1 是否启动由用户决定；每片完成后按 R-DEPLOY-001 先部署 ECS 再提交。

---

## 14. 风险与对策

1. **容量**：家里 worker 是硬瓶颈，成本信封可能低估 → 压测结果出来后强制校准；nightly_only 默认开。
2. **磁盘**：sweep 产物是头号风险 → TTL + compact 与 sweep 同时上线，不得后补。
3. **误导**：聚合表易被读成投资建议 → 统一 `disclaimer` + 聚合表零解释字段 + 文档口径。
4. **令牌泄露**：bearer 语义只能整体吊销 → 不做 IP 绑定（个人场景），提供即时吊销与限额收紧。
5. **与 P2-14 混淆**：P2-14 是展示用同族参数列，不是 sweep → 文档明确区分；聚合计算复用 `lab_result` 指标函数，禁第二套实现。
6. **引擎原生网格**：V1 用 N job，每个都重载数据 → 列入 F 节后续（`orchestration/research_run.py` 已有本地研究编排可参考），不在 V1 范围。
