# 17_JOB_PROTOCOL.md — SaaS 化 job 协议与状态机规范（A1，可直接编码）

> 定稿日期：2026-09-19。本文件是 ECS（调度中心）↔ 家里 worker（执行端）之间
> job 协议的唯一权威定义；编码时以本文为准，偏离需先改本文。
> 上游约束：`15_SAAS_SYSTEMS_DESIGN.md`（架构）、`16_ECS_DEPLOYMENT.md`（ECS 现状）。
> 参考实现：`gui/engine.py`（run 提交/status.json 生命周期/gui_pid 僵尸自愈）、
> `gui/strategy_lab_routes.py`（/api/run 参数结构）、`gui/saas/app.py` + `worker/`
> （M1–M3 已实现的单机过渡版队列——本文是它的目标态超集，差异见 §7）。

---

## 1. 状态机

### 1.1 状态枚举

| 状态 | 含义 | 进入条件 | 负责方 |
|---|---|---|---|
| `queued` | 排队待认领 | 用户提交（或派生 full job）；lease 超时回队 | server |
| `leased` | 已被 worker 认领，未确认开工 | claim 成功返回 | server |
| `running` | worker 执行中（收到首个 heartbeat 起算） | 首个 heartbeat | server（由 worker 心跳触发迁移） |
| `uploading` | 执行完成，产物回传中 | worker 调 result/meta 开始回传 | worker 触发 |
| `completed` | 成功终态 | result 全部回传且校验通过 | server |
| `failed` | 失败终态（attempts 耗尽或不可重试错误） | worker 报 fail 且 attempts 用尽，或错误类别不可重试 | server |
| `expired` | 硬超时终态（见 §5） | 超过 job 级硬超时 | server |
| `canceled` | 用户取消终态 | 用户取消且未进入 completed | server |

### 1.2 合法迁移图

```
queued ──claim──▶ leased ──首个心跳──▶ running ──result 开始──▶ uploading ──校验通过──▶ completed
  ▲                  │                     │                        │
  │                  │租约超时              │租约超时                  │租约超时
  │                  ▼                     ▼                        ▼
  └──回队（attempts+1 未耗尽）◀─────────────┴────────────────────────┘
  │                  │                     │                        │
  │                  └──── worker fail 可重试（attempts 未耗尽）────▶ 回队 queued
  │
  ├── attempts 耗尽 / 不可重试错误 ──▶ failed
  ├── 用户取消（queued/leased/running/uploading 任意时刻）──▶ canceled
  └── 硬超时（见 §5）──▶ expired
```

规则：
- 终态（completed/failed/expired/canceled）不可再迁移；终态不可被 claim。
- 回队时 `status=queued`、`leased_by=NULL`、`lease_expires_at=NULL`，`attempts` 保留累加。
- `leased → running` 是唯一由 heartbeat 驱动的迁移；claim 后 worker 沉默不超 lease 即视为未开工。
- 用户取消不杀进程：worker 在下一次心跳/回传时发现 `cancel_requested`，自行终止并上报（见 §5）。

---

## 2. Job 数据模型

表 `jobs`（PG；列类型以 PG 为准）：

| 字段 | 类型 | 可空 | 默认 | 说明 |
|---|---|---|---|---|
| id | BIGSERIAL PK | 否 | — | |
| kind | TEXT | 否 | — | `smoke` / `full`（仅此两种，同协议不同参数） |
| status | TEXT | 否 | `queued` | §1.1 枚举 |
| idempotency_key | TEXT | 否 | — | 用户侧去重键（§4.5），`(user_id, idempotency_key)` 唯一 |
| strategy_id | BIGINT | 可 | NULL | 引用已保存策略；与 strategy_yaml 二选一 |
| strategy_yaml | TEXT | 可 | NULL | 内联策略 YAML（用户未保存策略时） |
| params_json | JSONB | 否 | `{}` | 回测参数，字段与 /api/run 对齐（§2.1） |
| priority | INT | 否 | 0 | 大者先跑（付费预留） |
| attempts | INT | 否 | 0 | 已认领次数（含失败重试） |
| max_attempts | INT | 否 | 3 | |
| leased_by | TEXT | 可 | NULL | worker_id |
| lease_expires_at | TIMESTAMPTZ | 可 | NULL | 租约到期（§4.1） |
| heartbeat_at | TIMESTAMPTZ | 可 | NULL | 最近一次心跳 |
| progress | SMALLINT | 否 | 0 | 0–100，worker 心跳上报 |
| progress_message | TEXT | 可 | NULL | 人话进度（「正在加载数据」等） |
| cancel_requested | BOOL | 否 | false | 用户取消标记（§5） |
| error_class | TEXT | 可 | NULL | fail 分类（§3.4） |
| error_message | TEXT | 可 | NULL | 用户可读原因 |
| created_at / started_at / finished_at | TIMESTAMPTZ | 可 | now()/-/- | |
| user_id | BIGINT | 可 | NULL | 登录用户；游客可空（会话 Cookie 归属，见 §4.6） |

派生关系：`smoke` job completed 且带 `derive_full` 参数时，server 端自动创建对应
`full` job（同 strategy + params 去掉 smoke 截断），`parent_job_id` 记录来源（可加列）。

### 2.1 params_json 字段（与现有 /api/run 对齐）

| 字段 | 类型 | 说明 |
|---|---|---|
| start / end | "YYYY-MM-DD" | 回测区间（必填） |
| mode | "single"/"batch"/"shared" | 默认 batch |
| codes | [ts_code] | 缺省且 all_market=false 且 random_n 空 → 报错（同 /api/run 校验） |
| all_market | bool | 全 A 股 |
| random_n | int 1–2000 | 服务端随机抽样（沿用 QRE-LAB-RANDOM-UNIVERSE 语义） |
| universe | {group, key} | 板块/概念范围（QRE-SAAS-012 体系，worker 侧解析成 codes） |
| initial_cash / max_positions | number/int | |
| commission_rate, min_commission, stamp_tax_sell, transfer_fee_rate, slippage_buy_rate, slippage_sell_rate | float | 费率覆盖（同 /api/run profile_override_keys） |
| stop_loss_pct / take_profit_pct / trailing_stop_pct | float | 可空 |
| engine_impl | "simulator"/"vectorized" | 默认 simulator |
| precheck | bool | smoke job 恒 true（截断由服务端按 kind 生成，前端不传） |

smoke 参数派生规则（server 侧）：1 只固定标的（600519.SH）× 近 6 个月、precheck 语义，
与既有冒烟口径一致。

---

## 3. Worker 协议（4 端点；全部 HTTPS，头 `X-Worker-Token: <token>`，见 §4.6）

### 3.1 `POST /api/worker/jobs/claim`（长轮询）

请求：
```json
{"worker_id": "home-pc-1", "wait_seconds": 30, "capabilities": {"engine": "streaming", "max_job_kind": "full"}}
```
- server 持有请求最长 `wait_seconds`（默认 30s），有任务立即返回。
- **空响应**：200 + `{"job": null}`（不是 404/204，worker 收到后继续下一轮）。
- 取任务 SQL：`SELECT ... WHERE status='queued' ORDER BY priority DESC, id FOR UPDATE SKIP LOCKED LIMIT 1`，同事务置 `leased` + 租约。

响应（有任务）：
```json
{"job": {
  "id": 123, "kind": "full", "strategy_yaml": "...", "params_json": {...},
  "attempt": 2, "lease_expires_at": "...", "hard_deadline": "...",
  "cancel_requested": false
}}
```

### 3.2 `POST /api/worker/jobs/<id>/heartbeat`

每 **60s** 一次（worker 实现允许 55–65s 抖动）：
```json
{"worker_id": "home-pc-1", "progress": 42, "message": "回测中 2100/5200"}
```
响应：`{"ok": true, "cancel_requested": false, "lease_expires_at": "..."}`。
- server 侧动作：`heartbeat_at=now()`、`lease_expires_at` 顺延、`progress/message` 更新；首个心跳把 `leased → running`。
- `cancel_requested=true` 时 worker 必须尽快终止执行并走 §3.4 fail（error_class=`canceled`）或直接静默退出（server 已置 canceled）。
- 心跳时 job 已非本 worker 持有（409）→ worker 立即停止该 job。

### 3.3 `POST /api/worker/jobs/<id>/result`

分两步（避免大 multipart，便于断点重传）：
1. `POST .../result/meta`：`{"summary": {...}, "chart_data": {...}, "tag_analysis": {...}, "data_until": "...", "files": [{"name": "equity_curve.csv", "size": 12345, "sha256": "..."}, ...]}` → server 校验后返回 `{"upload_token": "..."}`，job 置 `uploading`。
2. `POST .../result/files`（multipart，带 upload_token）：逐个上传产物文件。
全部校验通过 → `completed`；缺文件/校验失败 → server 按可重试处理（回队或 fail）。

**结果合同（QRE-SAAS-RESULT-CONTRACT-001，2026-10-25；协议不变）**：worker 请求体**不新增字段**。服务端在接收 `result/meta`（及旧单包 `/result`）时注入 `results.result_contract`：合同版本、`data_until`、两种收益口径（曲线=日收益累乘交集口径剔注入；总收益=初始资金加权）、验证状态。历史行该列为空，由应用层显式例外表归类（58/66 verified、74 未验证），不按时间推断。worker 与引擎零改动。

### 3.4 `POST /api/worker/jobs/<id>/fail`

```json
{"worker_id": "home-pc-1", "error_class": "engine_error", "error_message": "...", "retryable": true}
```
error_class 枚举：

| error_class | 含义 | retryable |
|---|---|---|
| `strategy_compile_error` | 策略 YAML/表达式不合法 | 否（直接 failed） |
| `data_missing` | 因子/行情缺失 | 否 |
| `engine_error` | 引擎运行异常 | 是 |
| `system_error` | worker 资源/系统错误 | 是 |
| `canceled` | 响应取消 | —（终态） |

retryable=false → 直接 `failed`；retryable=true 且 attempts<max_attempts → 回队。

---

## 4. 租约与故障语义

### 4.1 参数（server 配置，可调）

| 参数 | 值 | 说明 |
|---|---|---|
| 租约时长 | 15 min | claim/每次心跳顺延 |
| 心跳间隔 | 60 s | 远小于租约，容忍 ≥10 次丢包 |
| max_attempts | 3 | 第 3 次失败置 failed |
| claim 长轮询 | 30 s | |

### 4.2 超时回队

server 侧定时扫描（或每次 claim 时顺带）：`status IN (leased,running,uploading)
AND lease_expires_at < now()` → attempts<max_attempts 则回队，否则 failed。
这从协议层根除单机版「执行器死了 status 永远 running」的僵尸问题
（本地 gui_pid 自愈的分布式等价物）。

### 4.3 幂等

- claim：SKIP LOCKED 保证一任务只被一个 worker 拿走。
- result/meta：重复提交按 `upload_token` 幂等（同 token 覆盖写）。
- fail：对已终态 job 返回 200 no-op。

### 4.4 重复提交去重（用户侧）

`(user_id, idempotency_key)` 唯一约束；重复 POST 返回 200 + 既有 job（不新建）。

### 4.5 idempotency key 格式

客户端生成 `uuid4`；浏览器端每个「开始回测」点击生成一次（防双击/重试重复扣配额）。

### 4.6 认证

worker → server：`X-Worker-Token: <预共享密钥>`（env SAAS_WORKER_TOKEN，未配置 server 返回 503）。
用户 → server：登录用户 `Authorization: Bearer <session token>`（15 号文档 §1）。
游客（未登录）归属（QRE-SAAS-ACCESS-HARDENING-001，2026-10-25）：**不按 IP**。
Cookie 缺失时 server 签发随机 `qre_guest_sid`（HttpOnly/SameSite=Lax），
`jobs.guest_key = sha256("gsess:"+sid+salt)[:32]`；旧版 sha256(IP+salt) 行仅在
同一 IP 的新会话首次创建任务时一次性迁移到新键（先迁移后计数），迁移后旧键
不再参与归属。游客 NL 编译限流例外地仍按 IP（成本口径）。协议字段与状态机不变。

---

## 5. 取消与超时

- **用户取消**：`POST /api/jobs/<id>/cancel` 置 `cancel_requested=true`。
  queued → 直接 canceled；leased/running/uploading → worker 下次心跳（≤60s）发现标记后终止并停止回传，server 置 canceled；completed/终态 → 409。
- **硬超时**（server 配置，可调）：smoke **10 分钟**、full **6 小时**，自 `started_at`（首个心跳）起算；
  超时 → `expired`（终态，不回队）。上传阶段硬超时单独 30 分钟（自 uploading 起算）。

---

## 6. 服务端存储选型：内测期纯 PG（SKIP LOCKED），不上 Redis

结论：**内测期用 PG 的 `SELECT ... FOR UPDATE SKIP LOCKED` 当队列，不引入 Redis**。
理由：
1. ECS 只有 2G 内存，少一个常驻组件就是少一份 OOM 与运维面（Redis 持久化/密码/监控都是事）；
2. 队列语义（claim/租约/回队）全部是 PG 行级事务能精确表达的，SKIP LOCKED 是 Postgres 队列的成熟模式；
3. 内测量级（每日几十~几百任务）PG 毫无压力；
4. 单机过渡版（gui/saas + worker/）已用 PG 跑通 lease/heartbeat/result 全链路。
何时再上 Redis：队列深度长期 >1000 或 claim 延迟成为瓶颈时，以同一协议换实现（协议与存储解耦，本文不含任何 PG 专属语义泄漏到 worker 协议层）。

---

## 7. 与现有代码的映射（迁移对照表）

单机版 `status.json`（gui/engine.py run record）→ 本协议 job 字段：

| status.json 字段 | job 字段 | 备注 |
|---|---|---|
| run_id | 外部展示 id（`job-<id>` 或 uuid 列） | 历史 run 导入时保留原 run_id 于 `legacy_run_id` |
| status: running | queued/leased/running（按 gui_pid 活性折算） | 导入时无进程一律 failed |
| status: completed / failed | completed / failed | |
| mode / start / end / codes | params_json.mode / start / end / codes | |
| initial_cash / max_positions | params_json 同名 | |
| executor / engine_impl | params_json.engine_impl（executor 废弃，worker 恒 module） | |
| profile_overrides | params_json 费率平铺字段 | 展开为 §2.1 费率键 |
| stop_loss_pct / take_profit_pct / trailing_stop_pct | params_json 同名 | |
| precheck / full_params | kind=smoke + 派生关系 | full_params 即 full job 的 params_json |
| created_at / finished_at | created_at / finished_at | |
| error | error_message（error_class=engine_error） | |
| gui_pid | —（废弃，由租约替代） | |
| artifacts | results 产物清单（§3.3 files） | 单机版文件路径 → 上传文件清单 |
| sandbox_strategy / promotion_gate | —（lab 流程概念，不进协议） | |

与 M1–M3 已实现过渡版（gui/saas/app.py + worker/）的差异（升级到本协议时要做）：
- 状态枚举扩充：`done → completed`，新增 `uploading/expired/canceled`；
- claim 从短轮询改长轮询（30s）；heartbeat 从「仅续租」升级为携带 progress/message；
- result 从单包 JSON 改为 meta+files 两步（产物文件上云/OSS）；
- 新增 idempotency_key、cancel_requested、hard deadline、error_class 分类；
- jobs 表相应加列（迁移脚本随 A2 实现时提供）。
