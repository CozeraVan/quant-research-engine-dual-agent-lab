# 15 — 内测 SaaS 四系统初步设计（用户 / Job / 结果 / 后台管理）

> 状态：**待用户核验**，核验后进入颗粒度对齐 → 再拆 TODO。今天只做设计，不写代码。
> 前置已定稿（勿推翻，见 14_LAUNCH_ROADMAP.md）：
> - ECS（2C2G）= Web + API + Redis 队列 + PG 用户小库；家里 WSL = 数据中心 + 回测算力；worker 纯出站拉任务。
> - 策略校验在 ECS（compiler 纯函数 + 因子目录表同步）；冒烟与全量都走 worker（路线 A，smoke/full 是同一种 job 的不同参数）。
> - 8081 lab 现有流水线（校验→冒烟→全量）即未来线上流水线的单机原型。

---

## 0. 全局视图

```
用户浏览器
   │  HTTPS (aguhuice.com)
   ▼
┌──────────────── ECS (2C2G) ────────────────┐
│ Nginx → Flask Web/API                       │
│ PG 用户小库: users / strategies / jobs /    │
│              results_meta / factor_catalog  │
│ Redis: job 队列 + 租约/心跳                  │
└───────▲──────────────────────▲─────────────┘
        │ 拉任务(出站)          │ 回传结果(出站)
┌───────┴──────────────────────┴─────────────┐
│ 家里 WSL: worker × N（主 PC，8700 经内网读库）│
│ PG 行情库 123GB + 因子库 + QRE 引擎          │
└─────────────────────────────────────────────┘
```

设计总则：
- **ECS 不存行情、不跑回测**；worker 无状态（挂了换一个即可）。
- 所有 job 幂等：同一 job 被重复执行，结果一致、产物覆盖写。
- 一切状态机显式化，拒绝"假 running"（本地僵尸 run 的教训）。

---

## 1. 用户系统（ECS）

### 功能
- 注册/登录：手机号+验证码 或 邮箱+密码（内测期建议邮箱，免短信费用；微信小程序阶段再换 unionid）。
- 三阶层配额（与已定策略一致）：
  - 游客：每日 3 次、仅单股/小范围、近 2 年、结果不保存（session 级）。
  - 登录用户：每日 3 次全市场/板块回测、结果保存、可看历史。
  - 付费用户：每日 ≥10 次、优先队列、可申请新因子（进因子需求队列，人工审核）。
- 配额计数与限流：按日计数（Redis INCR + 过期），接口级 rate limit。
- 用户策略库：保存自己创建的策略（YAML），可复制/再编辑。

### 数据模型（PG 用户小库）
- `users(id, email/phone, password_hash, tier, created_at, status)`
- `user_quota_usage(user_id, date, used_count)`（或直接 Redis 为主、PG 落账）
- `strategies(id, user_id, name, yaml_text, created_at, updated_at, deleted_at)`

### 关键接口
- `POST /api/auth/register|login|logout`，`GET /api/me`（含当日剩余额度）
- `GET/POST/PUT/DELETE /api/strategies[/id]`

### MVP 裁剪
内测第一版可只做"邮箱+密码 + 单层登录用户"，游客层用 IP 限流顶替，付费层先挂占位。

---

## 2. Job 系统（ECS 队列 + worker 协议）

### 功能
- Job 类型：`smoke`（1 股短窗）与 `full`（完整回测），同一协议不同参数；冒烟通过后自动派生 full job（用户可选跳过）。
- 状态机：`queued → leased → running → uploading → completed | failed | canceled`；另有 `expired`（租约超时回收）。
- **租约+心跳**：worker 拉任务时获得租约（默认 10 分钟），运行中每 60s 心跳续约；超时未心跳 → 任务回队列（attempts+1，上限 3 次后 failed）。— 解决"家里断电任务卡死"。
- 优先级：付费 > 登录 > 游客；同优先级 FIFO（Redis 可用多个 list 或 zset 实现）。
- 幂等：job 携带 `job_id`，worker 产物以 job_id 为键覆盖写。

### 数据模型
- PG：`jobs(id, user_id, strategy_id, kind, params_json, status, priority, attempts, worker_id, created_at, leased_at, finished_at, error)`
- Redis：`queue:{priority}`（list）、`lease:{job_id}`（心跳 TTL）、`job:cancel:{id}`

### worker 协议（HTTPS 出站，携带 worker token）
1. `POST /api/worker/jobs/claim {worker_id, capacity}` → 返回 job 或空（长轮询 30s 降负载）
2. `POST /api/worker/jobs/{id}/heartbeat {progress}`（每 60s）
3. `POST /api/worker/jobs/{id}/result`（结果 JSON + 产物文件 multipart，或先 PUT 到 OSS 再回传 URL）
4. `POST /api/worker/jobs/{id}/fail {error}`

### 关键接口（用户侧）
- `POST /api/jobs`（提交：校验 → 配额扣减 → 入队）
- `GET /api/jobs/{id}`（状态+进度）、`POST /api/jobs/{id}/cancel`
- `GET /api/jobs?mine=1`（我的任务列表）

### MVP 裁剪
优先级可先不分层（单 FIFO + 每日配额天然限流）；心跳必须有（这是分布式僵尸防护，不可裁）。

---

## 3. 结果系统（ECS）

### 功能
- 回测结果落库：元数据进 PG，产物文件内测期直接传 ECS 磁盘（单 run 聚合产物几 MB；明细 CSV 几十 MB 上限，超限截断或只传聚合），未来迁 OSS。
- 结果页数据 API：把 8081 现有结果页的数据源从"读本地 run 目录"换成"读 ECS 结果库"——**前端展示层基本不动**（lab_result 的 chart/tag/risk/symbols 数据结构直接复用）。
- 我的回测列表：按时间/超额收益排序（8081 记录页已有此交互，直接沿用）。
- 游客结果：只回传当次会话展示，不落库。
- 结果保留策略：登录用户保留全部；磁盘水位控制（如总量 >20GB 时清理最旧的非收藏结果）。

### 数据模型
- `results(job_id PK, user_id, strategy_name, params_json, metrics_json,      ← summary_metrics/strategy_performance 聚合
          excess_return, max_drawdown, win_rate, trades_count, symbols_count,
          artifact_path, created_at)`
- 产物目录：`/data/results/{job_id}/...`（结构与现 outputs/gui-run 产物一致）

### 关键接口
- `GET /api/results`（我的列表，排序/分页）
- `GET /api/results/{job_id}/summary|chart-data|tag-analysis|risk|symbols|symbol/{ts_code}`
  —— 与 8081 现行 API 路径逐一对应，前端迁移成本最低。
- `DELETE /api/results/{job_id}`（删记录+产物）

---

## 4. 后台管理系统（ECS）

### 功能（第一期）
- 总览：今日 job 数/成功率、队列深度、worker 在线数与心跳时间、ECS 资源（CPU/内存/磁盘）。
- 用户管理：用户列表、手动调 tier、禁用账号。
- 因子需求队列：用户提交的缺失因子申请 → 人工审核（批准 → 本地因子库计算入库 → 因子目录同步 ECS）。
- Job 管理：查看/重试/取消任意 job；失败 job 的 error 摘要。
- 运维：worker 启停指令下发（worker 拉任务时顺带拉指令）；家里 PG 状态卡片平移（通过 worker 上报而非直连）。

### 数据模型
- `factor_requests(id, user_id, description, status[pending/approved/rejected/done], created_at, handled_at)`
- `workers(id, name, last_heartbeat, status, capacity)`（PG 落账 + Redis 实时心跳）

### 关键接口
- `/api/admin/*`（鉴权：admin 标记的用户）；页面复用 8080 管理台风格。

---

## 5. 待对齐的开放问题（给用户核验时逐条拍板）

1. 游客额度按 IP 还是按浏览器指纹？（IP 简单但公司/校园网会串号）
2. 结果产物单 run 大小上限定多少？（建议 50MB，超出只存聚合 JSON）
3. worker token 的轮换策略？（内测期静态 token 够吗，还是要可吊销）
4. 用户密码算法与是否要邮箱验证？（内测可否跳过验证邮件）
5. 配额"每日"按自然日（0 点刷新）还是滚动 24h？
6. 冒烟是否对所有用户强制？（引擎侧已是默认流程，建议保留强制，省算力）
7. 后台管理是否需要给用户发通知（如因子申请通过）？内测期可用站内标记代替邮件。
8.  ECS 磁盘只有 40G，结果清理水位阈值定多少（建议 20GB）？

## 6. 建议实施顺序（与 14 号文档 Phase 0-4 衔接）

1. **Job 系统 + worker 协议**（Phase 0 核心，本地双进程即可验证：Flask 起队列，worker 在 WSL 拉自己）
2. **结果系统**（把 8081 结果页数据源抽象出来，先本地跑通"经 ECS 读结果"）
3. **用户系统**（加配额闸门）
4. **后台管理**（最后，内测前几天能手动 SQL 顶着）
