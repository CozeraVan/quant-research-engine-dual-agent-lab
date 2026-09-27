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
  （2026-09-27 实际落地：factors JSONB + strategy_name + formula/purpose + note/reviewed_at；审核经 /saas/console）
- `feedback(id, user_id, content, page, contact, created_at)`（2026-09-27 QRE-SAAS-FEEDBACK-FACTOR-REQ：内测意见反馈，仅登录用户可提交，日 20 条上限；管理台只读）
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

---

## 7. 实施 TODO（2026-09-18 与用户确认的顺序：全链路优先，登录/管理最后）

> 原则：先打通"Web 提交策略 → worker 回测 → Web 看结果"全链路（风险最高），
> 登录/后台管理最后；公网暴露前用 Nginx 层 IP 限流兜底（不做用户系统的过渡方案）。

### 阶段 A：Job 系统 + worker 协议（本地双进程验证，不上云）
- [ ] A1 定义 job 协议与状态机（queued→leased→running→uploading→completed/failed/canceled；租约+心跳）
- [ ] A2 Flask 侧实现 job API：claim / heartbeat / result / fail（先用 PG 小库或 SQLite，Redis 可选）
- [ ] A3 worker 端实现：轮询拉取 → 调 QRE 引擎（流式）→ 回传产物；幂等覆盖写
- [ ] A4 本地端到端验证：Flask 起服务，worker 同机拉任务跑一条真实策略，结果回传可查询
- [ ] A5 故障演练：杀 worker 进程 → 任务租约超时自动回队重跑（分布式僵尸防护实测）

### 阶段 B：结果系统（Web 经 API 读结果）
- [ ] B1 结果存储：results 表 + 产物目录结构（复用现 outputs 产物格式）
- [ ] B2 结果 API：summary / chart-data / tag-analysis / risk / symbols / symbol 明细（路径对齐 8081）
- [ ] B3 8081 结果页数据源切换到 API（前端展示层基本不动）

### 阶段 C：ECS 部署打通（上线内测版）
- [ ] C1 ECS 装 Python/Flask/PG 小库（2G 参数）+ systemd 服务
- [ ] C2 Nginx 反代 /api 到 Flask + IP 限流（如 10 req/min/IP）
- [ ] C3 家里 worker 服务化（systemd）+ worker token 认证，指向 https://aguhuice.com
- [ ] C4 端到端公网验证：浏览器提交策略 → 家里 worker 跑 → 线上看结果
- [ ] C5 8081 页面平移上 ECS（替换落地页为正式 app 入口，落地页保留为 / 首页）

### 阶段 D：用户系统（配额精细化）
- [x] D1 注册/登录（2026-09-20 落地：内测邮箱+密码 pbkdf2 哈希；正式版对接外购身份服务，见三级权限小节）+ users 表加 tier/password_hash
- [x] D2 三阶层配额（2026-09-20 落地：游客单 IP 日 1 次单股近 2 年次日清空；会员日 3 次全量 smoke 不占；付费占位同会员）
- [x] D3 我的策略库（2026-09-26 落地：strategies 按 (user_id,name) upsert 复用、工作台策略库面板[重命名/删除/去回测]、新建页 ?strategy=<id> 回填；有回测引用的策略禁删保可溯；回测历史= /api/results 已有）

#### 内测三级权限（已定稿，2026-09-19 用户拍板）

| 层级 | 登录 | 范围 | 配额 | 记录保存 |
|---|---|---|---|---|
| 游客 | 无需 | 单支股票、近 2 年 | 单 IP 每日 1 次 | 不保留，次日清空 |
| 登录会员 | 需要 | 当前系统全部功能（全历史、全市场） | 每日 3 次 | 永久保存 |
| 付费会员 | — | 暂不设特权（占位） | — | 未来权限从登录会员上调 |

实现触点：users 表加 tier 列；/api/jobs 配额按 tier 取档；游客匿名会话按 IP 限流
（Nginx C2 限流矩阵兜底 + 应用层日计数）；游客记录清理走每日定时任务。

**登录/验证通道外购（2026-09-20 用户拍板）**：用户登录、验证码、短信、微信验证等
**不自建**，正式上线时直接购买成熟服务体系（如阿里云/腾讯云短信、微信开放平台
扫码登录、或 Authing/Clerk 类身份服务）。内测阶段只做流程性测试，沿用 C4 的
临时测试账号通道（env 短路，上线前必须移除或改为外购服务对接）。

### 阶段 E：后台管理（最后）
- [x] E1 总览（job 数/成功率/队列深度/worker 心跳）（2026-09-27 QRE-SAAS-ADMIN-E1E3 落地）
- [x] E2 用户管理 + 因子需求审核队列（2026-09-27 落地：用户列表/tier 调整/禁用恢复 + 申请 approve/reject）
- [x] E3 worker 运维（2026-09-27 落地：worker 在线状态 + 失败任务查看/重试/取消；指令下发与家里 PG 状态卡为最小可行裁剪，见 06 决策日志）

> E 阶段落地要点（2026-09-27）：路由前缀 /saas/console + /api/saas/console/*（不用 /admin
> 字样——SaaS 禁链纪律含 HTML/JS 注释，见 12 号文档 §7）；users 表加 role/status 两列
> （幂等迁移，应用层校验取值）；workers 表落账心跳（claim/heartbeat upsert，3 分钟阈值
> 判在线）；管理员提升方式：SQL `UPDATE users SET role='admin' WHERE email='<邮箱>'`
> （先正常注册再提升；测试管理员账号见 04_TASK_HANDOFF.md）。

> 2026-09-27 方案 A（用户拍板，见 06 决策日志）：管理台已从公网撤下——nginx 对
> /saas/console 与 /api/saas/console/* 直接 404，仅经 SSH 隧道访问
> （deploy/saas/admin-tunnel.sh → http://localhost:9090/saas/console）；顶栏不再注入
> 入口。上文本节「后台管理系统（ECS）」中关于公网访问的描述以此为准。

### 待拍板开放问题（对齐颗粒度时逐条过）
见第 5 节 8 条（游客计数方式/产物大小上限/worker token 轮换/邮箱验证/配额口径/冒烟强制/通知方式/磁盘水位）。
+ 2026-09-20 新增：worker 全 A 任务内存峰值贴近 MemoryMax=4G（job#7 attempt1 OOM、attempt2 通过）——需评估全市场任务内存策略（升上限/分批/引擎流式化），登录会员开放全市场前必须解决。

### 回测资源调度优化（2026-09-20 用户拍板，D/E 阶段前的高优事项）

硬件底牌：主力机 14600KF（14C20T）+ 32G RAM + 5070ti，可分配 50%–80% 资源给回测台
（此前 systemd MemoryMax=4G 明显偏低）。已定方向：

1. **资源配额上调**：worker MemoryMax 从 4G 提升至 16–24G 档（同步评估 CPU 配额
   CPUQuota/AllowedCPUs），消除全 A 全期单策略 OOM 贴边问题。
2. **多租户资源调度**：并发场景（多用户/多策略同测）→ 每任务少核心、拉长时间，
   保证多用户同时可测；空闲场景（单用户单策略）→ 调动多核心加速。即"忙时均摊、
   闲时独占"的弹性调度，而非所有资源砸给单个任务。实现候选：任务级 cpuset/线程池
   配额 + 队列并发度自适应（按在跑 job 数动态分配核心数）。
3. **资源可视化（E 阶段后台管理）**：管理系统中展示 CPU/内存/队列占用，支持高峰/
   低谷时段手动或自动调节分配给回测台的资源比例。
