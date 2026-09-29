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
