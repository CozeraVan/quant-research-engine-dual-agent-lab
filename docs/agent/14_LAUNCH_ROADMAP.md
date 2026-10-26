# 14_LAUNCH_ROADMAP.md — 上线路线图与工作手册（2026-09 定稿）

> 面向：未来的人类开发者或 AI。读完本文 + `12_UI_STYLE_GUIDE.md` 即可无缝接续。
> 本文件只沉淀计划与约定；逐任务流水账看 `05_PROGRESS.md`，单任务交接看 `04_TASK_HANDOFF.md`。

---

## 1. 项目现状总览

**QRE 引擎能力**（截至 2026-09-15）：

- 日线下载（tushare → 本地 PostgreSQL）、因子计算（Alpha191 全量 + 技术指标族）、回测（单标的 / 批量 / 共享资金三模式，simulator 与 vectorized 双实现）、FRM 风险报告（VaR/ES/回测/压力测试）。
- 日更定时链：qre-refresh.timer 驱动增量更新与策略刷新。
- 流式批量回测（2026-09-14 落地）：股票数 >250 或全市场时按块加载/跑/落盘，内存峰值有界。

**三个端口分工**：

| 端口 | 服务 | 角色 |
|---|---|---|
| 8080 | qre-gui | 管理台（因子库/刷新/策略管理），**冻结，不许动** |
| 8081 | qre-gui-lab | 策略实验台（面向普通用户的正式 UI） |
| 18080 | 静态预览 | UI 设计稿 `synthesis.html`（已冻结，UI 唯一基准） |

**近期成果**（commit c714820 / 7e3f94a / 807928e 等）：

- 流式批量回测：内存峰值 941MB→299MB（500只×2年实测）；5 年全市场实测峰值 ~513MB（14 分钟采样 383–534MB 有界往复）。
- precheck bug 修复：流水线第③步曾硬编码 `precheck: true`，导致「完整回测」实际只跑 180 天截断小样本（full_params 无消费方）；已改 false，小样本验证由冒烟步骤承担。
- 僵尸 run 自愈：提交时 status.json 写 `gui_pid`，列表读取时 `_reap_zombie_run` 判死（无 PID/PID 不一致/探活失败）自动标 failed 并注明检测原因与时间。
- 空 CSV 修复：流式路径无交易个股的空 DataFrame 落盘为无表头空文件，读回抛 EmptyDataError → 读侧容忍（`_DiskBackedSingleResult._read` 捕获返回空 DataFrame，字节兼容）。
- 记录页时区本地化（`LabUI.fmtLocalTime`，后端 UTC 存储不变）、超额收益列+排序、整行可点、胶囊按钮、36px 等高控件。
- 内存限额：qre-gui-lab 与 qre-gui 的 MemoryMax 2G→8G（/etc 线上 unit；仓库 deploy/ 模板保持 2G 基线不动）。

## 2. UI 设计规范（要点；完整版见 12_UI_STYLE_GUIDE.md）

- **唯一基准**：8081 正式 UI 以 18080 设计稿 `/home/van/qre-outputs/ui-drafts/synthesis.html` 为准（已冻结，一个字节不许再动）。淡紫主题（主紫 #6750A4 系）+ A股红涨绿跌（红 #C93A3A / 绿 #1E8E5A 只给涨跌）+ 黑白灰。
- **工作纪律（铁律）**：UI 改动先在 18080 设计稿上做、用户验收后才移植 8081；8080 管理台一行不动；lab 侧改动**原位改模板，不重写页面**；冲突一律以 18080 为准。
- **已验证交互规范**（归纳自 lab-theme.css 定稿）：表格整行可点（行内按钮/链接自身拦截）；「查看结果」类入口用淡紫胶囊 view-link；行内混排控件统一 36px 等高（form-grid）/30px（栏头部）；排序表头 ▲▼ 且空值恒排最后；折叠区容器透明化（防双背景套娃）；运行状态徽章用紫点呼吸（不占红绿）；时间戳 UTC 存、前端转本地显示。

## 3. ECS 上线架构（已定稿，勿再推翻）

**目标环境**：阿里云 ECS 2C2G（47.119.127.40，Ubuntu 24.04），域名 aguhuice.com，ICP 备案已通过。

**分工原则（2G 内存约束驱动）**：

- **ECS 只跑**：Flask Web + Redis 队列 + PG 用户小库（仅存用户/策略/结果元数据；shared_buffers ≤256MB；总内存预算 ~1.2G）。
- **123GB 行情库/因子库与回测计算留在家用 PC（WSL）**。
- 家用宽带无公网 IP → 家里 worker **主动向云端 Redis 队列拉任务**（纯出站连接，不做内网穿透），算完结果回传云端小库。
- LLM 编译走 DeepSeek/Kimi API（密钥只在服务端 env）。
- 大文件（Excel 明细等）未来走 OSS 而非 ECS 直吐（3M 带宽约束）。
- **安全基线**：安全组只开 80/443/22；Redis/PG 绑 localhost；密钥走环境变量，禁止入库入仓。

## 4. ECS 迁移路线图（分阶段）

### Phase 0 — 本地前置（部分已完成）
- 回测执行器与 Web 解耦：队列协议定义（job schema：strategy_yaml/params/run_id/回调），本地验证。
- 现状：流式回测已落地，执行器拆独立服务列为挂起项（见 §7）。
- 验收：本地起「web + worker」两进程经 Redis 跑通一条 NL→编译→回测→结果链路。

### Phase 1 — ECS 环境安装（照做清单）
- 系统：`apt install python3.12 python3.12-venv redis-server postgresql nginx git`；创建 `qre` 用户。
- PG（2G 适配）：`shared_buffers=256MB`、`work_mem=8MB`、`max_connections=30`、`effective_cache_size=1G`；建小库 `qre_cloud`（仅元数据表）。
- Redis：`bind 127.0.0.1`、`maxmemory 256mb`、`maxmemory-policy allkeys-lru`。
- Python 栈：与仓库 `.venv` 同版本（`pyproject.toml` 为准）；**不装** tushare 数据同步依赖。
- systemd：模板用 `deploy/hardened/`（注意其中 MemoryMax=2G 为仓库基线，ECS Web 用 1G 即可；worker 在家里）。
- 验收：redis-cli ping 通、PG 可建表、venv 可 import 引擎、nginx 返回静态占位页。

### Phase 2 — Web 层部署
- 代码拉取 + venv + env 文件（0600，gitignore 已覆盖）；systemd unit（hardened 模板改造）+ Nginx 反代 8081→80；HTTPS 走 Let's Encrypt（certbot --nginx）。
- 验收：http→https 跳转、证书自动续期定时器在、8081 端口对外不可见、页面 200。

### Phase 3 — 家里 worker 服务化 + 端到端联调
- 家里 PC：worker systemd 服务（轮询云端 Redis，纯出站）；断线重连与任务租约（lease）语义。
- 验收：ECS 提交 → 家里 worker 拾取 → 算完 → 结果在 ECS 页面可见；worker 重启不丢任务。

### Phase 4 — 域名切换 + 灰度
- 域名解析切 ECS IP；先白名单内测再公开。
- 验收：aguhuice.com 全链路可用；一周无 P0。

## 5. 已知的坑与运维手册（两周实测踩坑）

1. **WSL 镜像网络端口抢占**：Windows 的 iphlpsvc 动态端口排除 + portproxy 会抢占/黑洞 WSL 端口。案例：8081 被一条 `::1→127.0.0.1` portproxy 堵死，服务活着但 curl 不通。排查命令：Windows 侧 `netsh interface portproxy show all`、`netsh int ipv4 show excludedportrange protocol=tcp`；WSL 侧 `ss -tlnp`。修法：删 portproxy 或换端口。
2. **WSL localhost 转发 IPv4/IPv6 黑洞**：监听 `::` 时 Windows 转发只命中一侧协议族；服务显式绑 0.0.0.0 与 :: 双栈最稳（qre-gui-lab 已双栈）。
3. **OOM 与 MemoryMax 的教训**：先靠提限额（2G→8G）止血是治标——**引擎流式化才是正解**（峰值 941MB→299MB）。限额只能兜底，且限额会掩盖内存 bug 的暴露。
4. **precheck 语义**：`/api/run` 的 `precheck: true` 只跑截断小样本并记录 full_params（无自动续跑）。流水线里小样本验证由冒烟步骤承担，正式提交必须 `precheck: false`。
5. **curl 本地服务加 `--noproxy '*'`**：本机装了 Clash，否则本地请求走代理失败。
6. **UI 验证用真 Chromium，不信 jsdom**：jsdom 无排版/字体/真实事件时序，曾漏报；Playwright headless-shell 在 `~/.cache/ms-playwright/`，脚本放 `~/.kimi-code/skills/smart-web-scraper/`（有 node_modules），node 在 `/home/van/codex-local/node-v22/bin/node`。
7. **共享输出目录**：lab /api/run 的 output_dir 多 run 共用会互相覆盖，审计以 run 目录 artifacts 为准（worker 已有持久化）；output_dir 隔离列为后续改进。

## 6. 工作流约定（vibe coding 主战场在 WSL）

- **commit 需用户逐次批准**；未批准前一律不 commit、不 push。
- 改代码同步更新 `docs/agent/05_PROGRESS.md`（pre-commit hook 会检查）；任务级状态写 `11_AGENT_STATE.md`。
- 测试基线命令：`cd <repo> && .venv/bin/pytest tests/ -q`；当前基线 **2072 passed + 4 skipped**（不许变红）。
- 子代理分工惯例：agent-97 后端/worker，agent-105 UI/lab。
- **铁律**：全量回测前先小样本冒烟（流水线已固化）；18080 设计稿冻结不动；8080 管理台不动；配色纪律不破（淡紫+红绿+黑白灰）。

## 7. 挂起 / 远期任务清单

| 任务 | 状态一句话 |
|---|---|
| 聚类动量因子研究 | 8080 已有 demo 页（v7 前端性能已优化），策略化未启动 |
| Alpha191 因子本地化 | 计算入库已完成（191 个全量在库），策略层应用待挖 |
| cluster-ashare 聚类 | 数据库已建（company_tags 三层），消费场景待扩 |
| 回测执行器拆独立服务 | R6 证明必要性（GUI OOM 杀回测），ECS Phase 0 前置项 |
| 回测 output_dir 隔离 | 共享目录多 run 覆盖问题，待改 |
| 缺因子申请闭环 | 8081 已能提交申请（JSONL），自动补因子入库未做 |
| 策略 NL 生成增强 | DeepSeek 编译可用（有因子名纠错层），macds 类缺列仍需人工修正 |
| 分时级别数据源调研 | 未启动 |
| SaaS 多用户层 | saas app 代码保留（鉴权/队列/工作流），模板被否后按 lab 观感重做挂起 |
| ECS 部署 | 备案已过，Phase 0–4 见 §4 |

## 8. 下阶段任务清单（2026-09-29 用户拍板，TOKEN 恢复后启动，brainstorm 后执行）

| # | 任务 | 要点 |
|---|---|---|
| N1 | 管理台集中优化 | a) 游客测试统计口径（次数/成功率/热门策略）；b) 会员权限管理：管理台可配游客/注册/付费会员的回测时间范围、每日次数、标的范围等参数（参数化入库，不写死）；c) 会员阶梯留空占位：权限分配系统先建好框架（角色→权限映射表），付费等级与权益一一对应待未来用户增长后填 |
| N2 | SEO 优化 | 让百度/Google/Bing 可收录：sitemap.xml、robots.txt、meta description/keywords、OG 标签、结构化数据、服务端可渲染的首页文案；百度搜索资源平台+Google Search Console 提交 |
| N3 | 引擎压力/性能测试 | 测当前配置（ECS 2C2G + 本机 worker 32G）下：每小时可处理多少个全期全量回测任务；并发多少任务不 OOM/不超时；产出容量报告，作为 R2 弹性调度的输入 |
| N4 | 安全防护初步 | 防 DDoS（nginx 限流/阿里云基础防护）、SQL 注入复查（全链路参数化查询审计）、XSS/CSRF、接口限流、敏感端点（console/feedback）访问控制复核 |

> 执行顺序建议：N1（管理台，内测运营刚需）→ N4（安全，公网暴露面）→ N3（压测，出容量基线）→ N2（SEO，持续见效慢，早提交收录）。启动前逐项 brainstorm 对齐颗粒度。

## 9. 数据源评估记录（2026-10-03）

- **HiThink-Tech/Financial-API**（同花顺官方 hithink-finance，fuyao.aicubes.cn）：官方维护、统一 API Key，REST/MCP/CLI/Python SDK/DuckDB 多接入。日线/财务/估值/交易日历/指数板块/涨跌停与 Tushare 高度重叠，**可作 Tushare 稳定互备**（断更事故的保险）；公开 API 不含分钟 K/tick/L2，**解决不了分时数据需求**。结论：值得注册看额度，作为互备源候选，暂未接入。
- **simonlin1212/a-stock-data**（2026-09-29 评估）：爬虫型 34 源聚合，腾讯分钟 K（1~60min）是分时数据候选，但稳定性/合规性弱，只配当备胎。暂不接入。

## 10. 容量基线（2026-10-03 N3 压测，本机 worker）

| 指标 | 数值 |
|---|---|
| 单任务全量（全A×2年） | 110.8s / 峰值 5.79G |
| 2 并发 | 各 118.5s（-7%）/ 各 5.79G |
| 安全并发上限 | 4（内存闸门：6G × N ≤ 25.6G） |
| 吞吐 | 串行 ≈32 次/时；4 并发 ≈120+ 次/时 |

> R2 弹性调度以"内存余量 ≥ 6G"为全量任务准入条件；多任务排队时多开少核，单任务时集中核心。

### R2 已落地（2026-10-03，commit d5da0dd / 965362d 起）

- **任务分级**：`jobs.weight_class`——light（smoke / ≤5 显式标的）走 2 个轻量槽（预算 1.5G/个），heavy（板块/全市场）走 3 个重量槽（预算 6G/个）；合计 21G ≤ 25.6G。分类器 `classify_job_weight()`（saas/app.py）。
- **分类认领**：`POST /api/worker/jobs/claim` 支持 `classes=light|any`；轻槽只领轻任务，游客单股测试永不被全市场任务堵死。
- **内存闸门**：槽位领取前查 /proc/meminfo MemAvailable（轻 2000MB / 重 6500MB，env 可配），本机有其他负载时 worker 自动降速。
- **子进程隔离**：每个 job 在 fork 子进程执行（GIL/内存隔离，OOM 只死子进程报 exitcode，取消可 terminate）。
- **cgroup 兜底**：user systemd `MemoryMax=26G`（实测委派生效）；超限杀 worker，任务租约过期自动重排。
- **ECS 配套**：gunicorn 改 gthread 2×8（sync 2 workers 被长轮询饿死的坑）；qre-saas.service / qre-worker.service 均收编 deploy/saas/。
- **排队可视化**：job 详情 `queue_position`；console overview 队列深度拆轻/重。

---

## 11. 公测阶段最高优先级（2026-10-25 用户拍板）

未来一段时间以**公网优化和用户体验为最高优先级**。第四入口（外部 AI Agent API）排在最后，设计仅记录于 `docs/superpowers/specs/2026-10-25-external-agent-api-brainstorm.md`，不在本轮启动。

**当前范围修订（2026-10-25 用户再次拍板，优先于本节其他顺序表述）**：现阶段不做任何压力测试、深度性能测试、硬件扩容或其他硬件相关推进，只聚焦公网中用户直观可见、可感知的产品体验。P0-3 的容量实测、磁盘/备份演练和 §11.4 扩容工作全部暂停；§11.7 整体上云仅保留长期方案，不启动。worker 离线时的明确排队/维护提示归入首次使用体验，不做容量或硬件调参。**移动端、App 端与可访问性深化按用户最新要求暂时跳过并挂起。** 当前顺序为：P0-2 权限加固验收发布 → 首次成功路径（NL 编译反馈、排队/等待/错误/重试、worker 离线提示）→ 结果理解与集中帮助 → 默认私有的可撤销只读分享 → 经典策略及结果操作 UI → NL A2/A3 → 公测运营反馈与关键浏览器自动化。NL A2/A3 仅作为减少等待、失败和重复编译的体验支撑，不扩展为性能工程。下文保留容量、云迁移、移动/App 和性能条目仅为完整 backlog，均不得在当前阶段主动启动。

**NL A2/A3 已验收发布（2026-10-26，QRE-SAAS-NL-A2A3，已 commit/push + ECS）**：`nl_rate_limits`（PG 原子计数：游客 guest_daily=10 保持 403/code=guest_nl_limit；会员 member_minute=6 超限 429/code=nl_rate_limited+reset_seconds，每日仍不限；admin 不计）+ `nl_compile_cache`（规范化描述+model/base_url+完整 prompt 哈希+缓存版本生成 key；同 key 咨询锁防并发重复 LLM；只缓存 ok=true，命中不调 LLM 不占配额）。**R-ADMIN-001 管理台同步**：9090 总览「自然语言编译」卡直接读执行常量展示游客/会员/admin 限额与缓存条目/累计命中/限流计数（同源，无第二套配置）。发布前全量 2753 passed + 6 skipped；公网纯编译两次 cache_hit false→true、YAML 一致、未建回测；隧道临时 admin 验证 overview nl 字段与常量/表计数一致。详见 04/05/09/11。下一主线为公测运营反馈与关键浏览器自动化。

### 11.1 对 Step 5 全项目审查的复核意见

主 Agent 认同其核心判断：日线引擎与数据底座已较成熟，当前主要风险是**数字可信度、公网权限与运维容量**，不是继续堆引擎功能。优先级作以下修正：

1. `price_basis` 先核查再定性，不能未经实测宣布线上结果错误；历史产物先隔离/标注未验证，不为了公测大面积回填。经典策略只展示已验证结果。
2. 默认私有 + 端点 IDOR 是 P0；主动分享链接属于 P1 的传播能力，不阻塞首批内测。
3. NL A2（持久限频）与 A3（编译缓存）应提到 P1，直接关系公网成本和编译速度；A1/Jev 输入裁判可后放。Step 5 所述“内存计数”已过时，当前游客 NL 限流是文件计数，仍需覆盖注册账号与成本侧。
4. 禁 root、文档漂移和测试 flake 是运维 P1，不与数字可信度混为同一级别。
5. 扩容先实测再采购：家里 worker 是算力瓶颈，ECS 2C2G 是 API 小层，不能一概升级。GPU 对当前 CPU 回测无直接收益。

### 11.2 P0：邀请用户前的可信与安全底线

| 顺序 | 工作包 | 可验收结果 |
|---|---|---|
| P0-1 | 结果口径与历史产物治理 | 核查 worker `price_basis` 与因子复权口径；页面区分日复利曲线和资金加权总收益；未验证旧结果隐藏或明显打标；经典策略只保留已验证项 |
| P0-2 | 权限与账号安全 | 核查并移除内置测试账号（若存在）；所有结果 GET 补归属/IDOR 自动化；游客归属改 IP+会话 Cookie 或明确迁移；默认私有保持不变 |
| P0-3 | 容量与单点韧性 | 先小样本效率测试，再做受控容量实测；输出当前吞吐/并发/P95/内存曲线；worker 离线时网页明确维护/排队而非无限等待；ECS 磁盘水位、结果保留清理、备份恢复演练落地 |

**公测放行规则**：P0 不全完成则不扩大邀请。发现数字口径不确定时宁可下线相关展示，不用“看起来很好”的结果做推广。

**P0-1A 核查结论（2026-10-25）**：worker 环境与实际进程均 `QRE_PRICE_BASIS=raw`；stock_daily 为原始价并含 adj_factor，job74 订单为原始价尺度。Step 5 的 price_basis 疑点排除，不重跑经典策略。后续 P0-1B 只做结果合同版本、口径标签和历史未验证结果隔离。

**P0-1B 实施结论（2026-10-25，Kimi，未 commit/push/部署）**：结果合同已落地——`gui/saas/result_contract.py` 为唯一权威（版本 `2026-10-25.1`；曲线口径=日收益累乘交集口径剔注入，总收益口径=初始资金加权 Σfinal/Σinitial−1；显式例外表 58/66=verified、74=unverified、其余历史默认未验证；分类不依赖时间）。新结果在 worker 回传接收层带合同，worker/引擎/历史数值零改动；`/api/saas/showcase` 与 showcase 公开只读通道只放行 verified（74 不再公开可见，白名单行/job/产物保留，属主照旧可见）；页面用可见徽标 + data-tip 区分两种收益口径。全量 2559 passed + 5 skipped，真实 Chromium 1280/375 通过，证据 `.tmp/result-contract/`。**上线前置**：ECS 需 DBA apply `deploy/saas/cloud_schema.sql` 的 `results.result_contract` 列（app 账号非 owner）。
**P0-2 发布结论（2026-10-25，commit `0799890` 已 push + ECS）**：①ECS 内置测试账号已移除，正式 Authing 链路保持正常。②全部用户侧 job/result/symbol GET 的 IDOR 矩阵落地（`tests/test_saas_access_hardening.py` 31 例）：匿名 401、其他用户 404、不存在与他人错误体逐字节一致、showcase verified 公开只读 200、未验证白名单项同样 401/404。③游客归属已从纯 IP 改为随机 Secure/HttpOnly/SameSite=Lax 会话 Cookie（`qre_guest_sid`；归属键同形同列，**无 schema 变更**），旧 IP 归属结果在新会话首次创建任务时一次性迁移。发布前全量复跑 2590 passed + 5 skipped；真实 Chromium 同 IP 双游客隔离 + 移动 375 通过。ECS 仅同步 app.py 与 cloud_schema.sql 注释并重启 qre-saas；公网双独立游客 Cookie 值不同、私有 74 匿名 401、58 verified 200、showcase 仅 58/66。备份 `/tmp/qre-access-hardening-pre-20261025-release/`；证据 `.tmp/access-hardening/` 与 `.tmp/access-hardening-production/`。

### 11.3 P1：公测首周用户体验与转化

1. **首次成功路径**：自然语言输入→编译→小样本验证→结果。重点做 NL A2 持久配额、A3 编译缓存和明确错误/重试；展示队列位置、预计等待和可取消操作，避免重复提交。
   **首切片已发布（2026-10-25，QRE-SAAS-FIRST-SUCCESS-UX-001，commit `a84a9a3`）**：队列位置、worker 在线/离线提示、已等待时间进入 new/job 两页；取消（含游客会话归属）与失败恢复（真实 error_message + 按原策略重跑）可用；单次轮询超时不误判失败、80 轮前台超时分流任务页、不自动提交全量。全量 2629 passed + 5 skipped，真实 Chromium 12/12，ECS 公网文件与权限回归通过。
   **NL A2/A3 已部署待人工验收（2026-10-26，QRE-SAAS-NL-A2A3，未 commit/push）**：游客每日 10 次改 PG 原子计数（跨 worker/重启可靠，403/code 不变），会员 6 次/分钟防突发（429/nl_rate_limited/reset_seconds，每日仍不限），admin 不限；相同输入命中版本化编译缓存（key=规范化描述+model/base_url+完整 prompt 哈希+缓存版本），命中不调用 LLM 也不占配额，失败不缓存。管理台同步（R-ADMIN-001）：9090 总览「自然语言编译」卡展示真实生效限额与缓存/限流计数。全量 2731 passed + 6 skipped；公网纯编译两次 cache_hit false→true、YAML 一致、未创建回测。备份 `/tmp/qre-nl-a2a3-pre-20261026/` 与 `/tmp/qre-nl-console-pre-20261026/`；验收通过后才 commit/push。
2. **结果理解与分享**：补集中帮助中心/指标口径、数据截止与费用说明；默认私有前提下增加可撤销、可设有效期的只读分享链接。经典策略只展示验证过且可复现的内容。
   **首切片已发布（2026-10-25，QRE-SAAS-RESULT-UNDERSTANDING，commit `9fd3b3d`）**：公开 `/saas/help` 使用说明页（七锚点），合同文案同源；job/symbol 模块精准深链；五类磨损卡/费率/基准/重播提示补全；symbol 两路径注入 data_until，VaR/ES 统一损失正数；个股过户费重复显示已修。全量 2653 passed + 5 skipped，真实 Chromium 10/10，ECS 帮助页与个股 data_until 验证通过。剩余：默认私有的可撤销只读分享链接（P1 条目 6）。
   **只读分享已发布（2026-10-26，QRE-SAAS-READONLY-SHARE，commit `08b4a27`）**：`share_links` 只存完整 token 哈希（明文仅创建响应一次）；创建/列表/撤销三个 owner API；单 job 绑定公开只读通道（无效/过期/撤销/错 job 不降级，也不回退 showcase）；未验证结果可分享且徽标保留、showcase verified 门不变、游客不开放；job/profile 分享 UI 与「只读分享」chip。最终全量 2688 passed + 5 skipped，真实 Chromium 12/12；ECS schema 与公网创建→匿名只读→撤销验证通过，临时链接已清理。剩余：经典策略及结果操作 UI 精修。
   **结果页精简已发布（2026-10-26，QRE-SAAS-UI-DECLUTTER-001，commit `8accb66`）**：job/showcase/个人记录不再展示结果合同与新旧口径，系统内部合同与 verified 权限不变；job/symbol 模块帮助深链删除，保留悬停提示；help 改桌面侧边栏目与 20px 标题，窄屏双列导航。全量 2689 passed + 5 skipped，真实 Chromium 6/6；公网五个页面与六文件哈希验证通过。小游戏/Steam 仅保留想法并挂起。
   **经典策略与结果操作 UI 已发布（2026-10-26，QRE-SAAS-CLASSIC-ACTIONS-UI，已部署待人工验收、未 commit/push）**：showcase 底部灰字长文改「复现经典策略」问号提示 +「新建同款策略」主按钮，页头备注与 `#sc-hint` 删除；job「下一步」与「分享结果」合并为「结果操作」卡（保存/确认信号=主按钮、信号/分享=次按钮，状态文本去灰字，信号 T+1 提示移入问号），新增 `syncResultActionCard()` 按组可见性控制外层（游客/只读整体隐藏）；按钮 ≥44px、375px 不横溢。TDD RED→GREEN（新 12 例 + 既有断言更新），全量 2701 passed + 5 skipped，真实 Chromium 9/9；ECS 备份 `/tmp/qre-classic-actions-pre-20261026/` 后同步三文件仅重启 qre-saas，公网验证通过。验收通过后才 commit/push。
3. **[挂起] 移动端、App 端与可访问性深化**：用户 2026-10-25 明确暂时跳过；既有移动适配和 Chromium 测试资产保留，未来由用户明确重启。
4. **运营反馈闭环**：管理台优先看编译失败率、回测成功率、排队时长、游客到注册转化、热门失败原因；意见反馈按类型分派，不先堆会员等级和付费功能。
   **已部署待人工验收（2026-10-26，QRE-SAAS-PUBLIC-BETA-OPS，未 commit/push）**：9090 管理台新增「公测运营」tab（`GET /api/saas/console/ops`，窗口 today/7d/30d/all，admin 门禁不变）——NL 编译次数/成功率/缓存命中率/失败原因 Top5/统计起点（新表 `nl_compile_events`，只存 ok/cache_hit/error_class/scope/created_at，不存策略文本/API key/原始 IP，**自功能上线起统计、上线前显示「—」**，超限拒绝不计入分母）；回测（kind='full'，smoke 与用户主动取消不计入）成功率/平均排队/平均执行/失败原因 Top5；游客到注册转化（游客独立会话=guest_key 去重——仅覆盖提交过任务的游客；新增注册=users.created_at；**二者无关联，不计算转化率**——ratio=null + measurement=unlinked，未扩展用户追踪 schema）；反馈按类型/状态计数；分母为 0 一律 null→「—」。**时间窗口 today 按 Asia/Shanghai 自然日**（`_now_shanghai()` + zoneinfo；原 UTC 零点漏当日凌晨 8 小时）。**反馈分类闭环（最小可用，不建工单系统）**：feedback 增 category（bug/experience/factor/other）/status（open/doing/done/closed），提交 allowlist、console 筛选与状态流转端点，用户隔离/每日 20 条/admin 鉴权全保留。**关键浏览器自动化**：可重复执行资产落 `deploy/saas/public-beta-audit/`（seed/browser_audit/run_audit；复用 `.tmp/browser-venv` Playwright + `.tmp/ms-playwright` Chromium，未进生产依赖；stub LLM + worker 协议模拟，不跑真实回测），覆盖游客/登录、新建页、NL 编译 stub、任务等待/失败恢复、结果只读与权限、反馈分类、管理台运营指标；真实 Chromium 9/9 零 JS error 零横溢（1280 与 375）。**主 Agent 复核 2 项 Required Fixes 已解决并重新部署**（2026-10-26）：①转化比率误导——不计算 new_users/guest_sessions 之比（生产实测 300.0%），API ratio=null + measurement=unlinked，console 卡改「转化率 —」；②today 窗口改上海自然日。新回归 3 例，TDD RED=4→GREEN，ops 测试 20 passed，全量 **2772 passed + 6 skipped**（1 例已知 flake 复跑通过）；Chromium 重跑 9/9，console-ops-1280/375 确认无伪转化率；备份 `/tmp/qre-public-beta-ops-review1-pre-20261026/` 后仅同步 ops_support.py + console.html 并重启 qre-saas（无 schema 变更）。生产热修 `feedback_id_seq` 缺 USAGE（提交反馈 500；该特性此前未部署过 ECS）。全量 2770 passed + 6 skipped；生产临时会话验证后彻底清理，9090 隧道与公网页面核验通过。**未 commit/push，待用户人工验收。** 详见 04/05/09/11。

### 11.4 扩容方案（测量驱动，先韧性后硬件）

- **先做**：保留轻/重槽与内存闸，按新实测调参；为人工任务保留响应能力；设置磁盘/结果保留策略、告警、备份和回滚包。
- **再考虑**：若持续队列过长且 CPU 有余量，优先调整并发；若内存持续成为瓶颈，再评估家里主机升 64GB。若长期容量不足，再增加第二 worker，但独立电源/网络/机器才算真正降低单点风险。
- **不先做**：不直接升级 ECS 算力、不买 GPU、不增加未经验证的第二套常驻 worker。ECS 仅在 API CPU/内存/带宽实测超阈时升级。

建议容量指标：每小时完成 full jobs、P50/P95 排队与执行时间、失败率/OOM 率、轻任务被重任务阻塞时间、结果目录日增量、备份恢复时间。扩容验收以这些指标改善为准，不以硬件型号为准。

### 11.5 灰度公测节奏与度量

先邀请 20–50 名用户，维持现有“游客/注册用户”两层，不急于收费。每日观察首次编译成功率、首次回测成功率、P95 出结果时间、重复提交率、移动占比、注册转化和反馈分类；P0 事故立即停止扩量并回滚。公测稳定后再逐步放宽配额。

### 11.6 后续顺序（第四入口最后）

1. P0 数字可信、安全、容量底线。
2. P1 首次成功路径、NL 成本与速度、结果分享/帮助、移动体验、运营指标。
3. 灰度反馈驱动的 UI/稳定性修正与按需扩容。
4. 付费分层、分时回测、ML 聚类等远景项另行立项。
5. **最后：第四入口外部 AI Agent API**（仅提供规则、校验、任务与结果；目标和优化循环由外部 Agent 负责），预估 12–15 人日，未启动。

### 11.7 未来整体上云与数据迁移（用户确认的重点方向）

**当前定界**：home PC 继续作为数据中心与主测 worker；ECS 只承担公网 Web/API 和用户小库。当前邀请朋友测试负载不大，不为早期流量做过度迁移。用户推广放量后，将行情库、因子库、回测引擎和 worker 整体上云，届时重点工作是**数据迁移以及 worker 与数据库之间的数据传输**，不是重写产品。

**现在应保留的云就绪边界**：

- 数据库连接、worker 地址、输出目录和对象存储均通过环境配置，不把 home 路径写死在业务代码中；保持 data store、worker client、result manifest 的接口边界。
- 回测产物保持自描述：run_id、策略/参数、数据快照、引擎与口径版本、artifact 清单和校验信息齐全，未来可从对象存储直接服务结果。
- 任务协议保持云端 authoritative，worker 可替换；避免 Web 直接依赖 home 文件系统或本地数据库。

**未来迁移路线（独立项目，先设计后执行）**：

1. 盘点表体量、日增量、TimescaleDB hypertable/compression/GRANT 和结果产物，确定目标云 region、数据库、计算与对象存储。
2. 建立云 schema/权限/网络，先快照全量迁移，再按 trade_date/watermark 增量追数；原始价、复权因子和因子口径必须逐项对账。
3. 记录表级行数、主键、最大交易日、抽样值和校验和；分钟线大表分块校验，不能只看“导入成功”。
4. 云 worker 小样本→全量性能验证，重点测跨 worker/DB 的查询量、延迟、带宽、内存与结果回传；禁止未经验证直接全量切换。
5. 双读/影子运行对比，随后灰度切流；home 保留只读回滚窗口，验收后再停写入和退役，不做不可逆切换。

**数据与传输原则**：尽量让 worker 与数据库同 region/同可用区，减少跨公网明细传输；云端只回传结果产物，大文件走对象存储，元数据入小库。迁移以 RPO/RTO、校验一致性和回滚能力验收，不以复制速度作为唯一目标。

**顺序**：当前 P0/P1 与灰度优先 → 云迁移方案与容量/成本评估 → 云上小样本与影子验证 → 灰度迁移 → 第四入口最后。

### 11.8 统一待办总表（防丢项，2026-10-25 恢复）

> TodoList 只允许增删完成项或调整优先级，不得用当前阶段短清单覆盖全量 backlog。已完成且经核实的旧项不再重复列入；长期挂起项必须保留并标明。

#### P0（公测底线）
1. ~~P0-1B：结果合同版本、收益口径标签、旧结果隔离。~~ ✅ 已发布（2026-10-25，`37bcffa` + `a87a831`）。
2. ~~P0-2：测试账号核查、结果端点 IDOR、游客归属加固。~~ ✅ 已发布（2026-10-25，`0799890`，公网权限与 Cookie 验证通过）。
3. [挂起] P0-3：容量实测、磁盘水位、结果保留与备份恢复；worker 离线提示转入 P1 首次成功路径，不做压测或硬件推进。

#### P1（公测首周）
4. NL A2 持久限频与 A3 编译缓存。
5. 首次成功路径与帮助中心。（等待状态/离线提示/取消/失败恢复已发布：`a84a9a3`；结果理解与集中帮助已发布：`9fd3b3d`；移动端/App 与可访问性深化挂起）
6. ~~默认私有的可撤销只读分享~~ ✅ 已发布（2026-10-26，`08b4a27`，schema 与公网撤销链路验证通过）。
7. ~~经典策略按钮与结果操作卡 UI 精修~~ ✅ 已验收发布（2026-10-26，`e6f4f77`；含分享序列权限与完整 URL 热修）。
8. ~~公测运营指标与关键浏览器自动化~~ ✅ 已验收发布（2026-10-26，QRE-SAAS-PUBLIC-BETA-OPS）。
   9090「公测运营」tab（NL 编译成功率/缓存命中/失败原因、回测成功率/排队/执行/失败原因、游客独立会话与新增注册两个独立计数——**不计算转化率**、反馈分类计数；today 窗口按 Asia/Shanghai 自然日；事件表自上线起统计，空口径「—」）+ 反馈分类/状态最小闭环 + `deploy/saas/public-beta-audit/` 可重复浏览器验收资产（真实 Chromium 9/9）。下一项：QRE-SAAS-NL-A1（DeepSeek 方向）已部署待人工验收（见 P2 条目 10）。

#### P2（随后按优先级立项）
9. 未来整体上云与数据迁移方案（§11.7）。
10. ~~NL A1 输入校验与裁判评估~~ ✅ 已验收发布（2026-10-26，QRE-SAAS-NL-A1，DeepSeek 方向）。
   NL 编译入口规则层前置校验 + DeepSeek 第二裁判；缓存命中零裁判，裁判只在 cache miss + 配额计数后运行，拒绝也占配额；admin 同样裁判，force 与 DB 回退路径一致。54 条人工标注样本规则层 54/54；DeepSeek 分层 12 条评估 0 失败；全量 2840 passed + 6 skipped；Chromium 7/7。下一项：重播边界；挂起任务放最后。
11. 重播边界：同日聚合、orders 事件源、多因子副图页。
12. 剩余 341 列中文显示名维护。
13. root SSH 与部署发布纪律加固。
14. mindata CSV 与遗留数据清理确认（先核查，禁止直接删除）。
15. 全量策略库批次是否再跑（必须由用户决策，先小样本）。
16. 深度性能与压力测试。
17. M10.4 ML 聚类（需 scikit-learn 依赖批准）。
18. 会员分层、付费权益与微信信号推送。

#### 挂起（保留，不删除）
19. 分时因子与引擎分时适配，等可靠数据源与独立立项重启。
20. 视频数据包 #78 三方案复盘，等视频产出后评估。

#### 最后
21. 第四入口外部 AI Agent API，见 `docs/superpowers/specs/2026-10-25-external-agent-api-brainstorm.md`。

**已核实完成，不再误列旧待办**：买卖价格选项、NL holding 默认 0、全站说明与参数提示、因子三级弹窗、因子中文注册表、Tushare P0–P8、ECS 上线与基础 SEO、信号板块选择、price_basis 核查（P0-1A）、结果合同与旧结果隔离（P0-1B，待用户验收 + ECS apply 新列）。
