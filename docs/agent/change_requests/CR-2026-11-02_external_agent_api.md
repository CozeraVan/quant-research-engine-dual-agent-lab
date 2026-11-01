# CR-2026-11-02 · 第四入口外部 AI Agent API：边界修订与 V1 设计立项

> 任务：§11.8 E 项「第四入口外部 AI Agent API」的 M0 初始工作。
> 用户 2026-11-02 明确：**现阶段只做设计，不写业务代码、不部署、不上线**。
> 设计定稿文档：`docs/superpowers/specs/2026-11-02-external-agent-api-design.md`（下称「设计文档」）。

---

## 1. 目标

把 2026-10-25 的 brainstorm 升级为可执行设计：定位从「机器可读薄 API」修订为
**「个人量化研究员 agent」**——对话定边界 → 出工作清单 → 批量回测 → 汇总结论提交用户。
本 CR 只登记决策、影响面与验收门；实现待用户批准 M1 后另行立项。

---

## 2. 用户设定边界（不可协商）

1. 个人开发，**不自建/不调任何模型**；智能全部来自用户自带的外部 AI。
2. 可调用库内**全部数据**做回测，但只做回测相关动作（发现/校验/提交/轮询/读结果/聚合）。
3. **不做任何投资建议**，只做数据结果聚合。
4. 其余边界由设计文档 §10 推荐参数确定（默认值 + 9090 可调）。

---

## 3. 与 10-25 brainstorm 的差异（需用户确认的修订）

| # | 10-25 原文 | 本 CR 修订 | 影响 |
|---|---|---|---|
| R1 | 不做 sweep / 参数网格 / parent-child 编排 | 提供**最小 sweep 原语**：笛卡尔积展开为 N 个串行子 job、共享会话预算、聚合排名表；编排逻辑仍在外部 agent | 新增 `sweeps` 端点 + 预算闸；引擎/worker 不变 |
| R2 | 无会话容器 | 新增 `research_runs` 一等公民（边界文本/工作清单/预算/结论） | 新增一张表 + 4 个端点 |
| R3 | 无成本口径 | 新增 `capabilities` 成本信封（实测基线机器可读化） | 依赖 §10 与 11-02 压测数据校准 |
| R4 | 估算 12–15 人日 | **20–25 人日** | 排期预期修正 |
| R5 | MCP 后置 | 维持后置 | 无 |

---

## 4. 影响面（实现时才触碰，本次零代码）

- 新增：`api/agent_v1.py`（或蓝图）、`api_tokens` 表、`research_runs` 表、`schema/strategy` 导出。
- 修改：`jobs` 加 `token_id` / `research_run_id` / `labels` 三列；结果 GET 放行 token 归属（复用 P0-8 `_require_completed_result`）；9090 console 新增「外部 Agent」页（R-ADMIN-001）。
- 复用（不改）：`validate_yaml`、`check_factor_limits`、`normalize_ts_codes`、`classify_job_weight`、
  队列/租约/取消（`17_JOB_PROTOCOL.md`）、`/api/results/*`、因子与 universe 元数据端点、归档机制。
- **明确不改**：回测引擎、worker 协议、结果合同、产物格式、配额既有语义。

---

## 5. 容量与风险门（实现前必须满足）

1. **压测校准**：11-02 全期全量压测结果出来后，必须校准 `capabilities` 数值；偏差 >50% 需记录原因。
2. **产物 TTL 与 compact 与 sweep 同时上线**，不得后补（磁盘头号风险）。
3. **nightly_only 默认开启**，agent 任务不得抢占真人时段。
4. **强制两阶段**：screen（抽样 + 短区间）→ confirm（短名单 + 全量显式确认），写进 API 合同而非靠 agent 自觉。
5. **免责口径**：所有响应带 `disclaimer`；聚合表零解释字段。

---

## 6. 验收门（M1–M6 通用）

- IDOR / 配额 / 限流 / 预算 / 幂等 / 吊销六类测试全绿（设计文档 §12 有逐项清单）。
- 9090 管理台可视化与执行常量同源（R-ADMIN-001）。
- M6 用一个**真实外部 agent** 完成一次 EMA 周期扫描研究会话，全程未经显式确认不得全量。
- 全量回归 `uv run pytest -q -p no:randomly` 不许变红。

---

## 7. 待用户批准的决策

| # | 决策 | 建议值 |
|---|---|---|
| D1 | 编排放外部 agent（方案 A）还是站内（方案 B） | **A**（边界 1 已隐含确认） |
| D2 | 是否提供 sweep 原语 | **是**（V1 串行版） |
| D3 | 是否要 `research_runs` 一等公民 | **是** |
| D4 | 强制两阶段是否写进 API 合同 | **是** |
| D5 | 引擎原生参数网格是否列入后续 | **列入 F 节，V1 不做** |
| D6 | M0 之后是否立即启动 M1 | **待用户决定**（建议等 11-02 压测结果校准成本信封后再动工） |

---

## 8. 状态

- M0 设计：**已完成并 commit/push**（`6f82567`），待用户批准 D1–D6 与 M1 启动。
- M1 令牌与能力信封：**代码已完成并 commit/push**（`fb419b4`），ECS 已部署。
- M2 研究会话容器：**代码已完成并部署 ECS**（2026-11-03，MainPID 604411；
  回滚副本 `/tmp/qre-deploy-20261101T183600Z.bak`）。
  - 新增 `research_runs` 表（`boundary_text`/`todo`/`conclusion_text`/`conclusion_table`
    原样存储，QRE 不解释）；状态机 `planned→running→aggregated→concluded`，`archived` 为 TTL 终态。
  - 端点：`POST /research-runs`、`GET /research-runs`、`GET /research-runs/<id>`、
    `POST .../status`、`POST .../conclusion`；他人/不存在一律 404 同体。
  - 预算：白名单四键，超 `AGENT_DEFAULTS` 会话级上限自动收敛；详情回 `usage` /
    `budget_exceeded` / `budget_remaining`；`research_run_usage()` 汇总 jobs 数、
    `results.artifacts` 体积与墙上时间。
  - R-ADMIN-001：9090「外部 Agent API」卡新增研究会话区（总数/未完结/已结论 + 最近 20 条）。
  - 测试：新 13 例；**全量 3335 passed + 34 skipped**（零回归）。
- M3–M6：**未启动**。
- 长期记录：`14_LAUNCH_ROADMAP.md` §11.8 E 项已更新为「M0 设计定稿待批准」；
  任务已登记 `26_WEEKLY_HANDOFF_2026-11-02.md` §7。
