# 16_ECS_DEPLOYMENT.md — ECS 部署单一权威文档（aguhuice.com）

> 面向：任意 AI agent / 人类接手者。读完本文即可接续 ECS 相关工作。
> 目标架构与系统设计的权威定义见 `14_LAUNCH_ROADMAP.md` 与 `15_SAAS_SYSTEMS_DESIGN.md`；
> 本文只管 ECS 这台机器的事实、现状与运维操作。逐任务流水账看 `05_PROGRESS.md`。

## 1. 实例与访问

| 项 | 值 |
|---|---|
| 实例 | 阿里云 ECS 2C2G / Ubuntu 24.04 / 40GB ESSD / 3Mbps |
| 公网 IP | 47.119.127.40 |
| 域名 | aguhuice.com（备案号：湘ICP备2026040383号-1） |
| DNS | A 记录 aguhuice.com 与 www 均已指向 ECS |
| SSH | **仅密钥**（root 密码登录不可用）：`ssh -i ~/.ssh/aguhuice_ed25519 root@47.119.127.40` |
| 用户 | root + deploy（sudo 组，同一把公钥已写入 /home/deploy/.ssh/authorized_keys）；禁 root 直连列为后续 |

## 2. 目标架构（已定稿，勿推翻；细节见 15 号文档）

- ECS 只跑：Web/API（Flask）、队列（PG 小库或 Redis）、PG 用户小库——**不落任何行情/因子明细**。
- 行情大库 + 回测算力在家里 WSL（本地 PG，只读账号 qre_worker_ro）。
- Worker 在家里 PC，**纯出站**轮询云端拉任务（HTTPS + worker token），无需公网入站。
- 冒烟与全量回测都走 worker（路线 A，无同步执行路径）。

## 3. 当前实现状态（截至 2026-09-18）

已就绪（ECS 侧）：

- nginx / ufw（仅放行 22/80/443，默认 deny incoming）/ fail2ban（sshd 默认防护）已装已启用；
- HTTPS 已签发（Let's Encrypt，2026-12-17 到期，certbot 自动续期）；
- 落地页已上线：`/var/www/aguhuice/index.html`（纯静态单页，风格遵守 `12_UI_STYLE_GUIDE.md`）；
  **版本管理在仓库** `deploy/landing/`（index.html + nginx-aguhuice.conf，与线上 diff 校验一致）；
  Nginx 站点：`/etc/nginx/sites-available/aguhuice`。

**D1D2 已上线（2026-09-20）**：users+tier/password_hash、jobs+guest_key（幂等迁移已执行）；
POST /api/saas/auth/register（邮箱+密码）；游客匿名提交（单 IP 日 1 次/单股/近 2 年，
jobs.user_id NULL + guest_key=sha256(IP+salt)，每日 04:00
qre-saas-guest-cleanup.timer 清空）；会员日 3 次全量（smoke 不占）403；
登录页改邮箱+密码 UI。注意：D1D2 文件（app.py/cleanup.py/templates/cloud_schema.sql/
timer 两单元）为 scp 同步（未走 git push），与仓库 HEAD 一致待正式提交。
**游客归属已于 2026-10-25 改为会话 Cookie 并发布（QRE-SAAS-ACCESS-HARDENING-001，commit `0799890`）**：
jobs.guest_key 由随机会话 Cookie（`qre_guest_sid`，Secure/HttpOnly/SameSite=Lax）
派生而非 sha256(IP+salt)——同 Wi-Fi 游客结果互不可见；旧 IP 归属行在新会话首次创建
任务时一次性迁移；游客 NL 编译限流仍按 IP。ECS 仅同步 app.py 与 cloud_schema.sql 注释并
重启 qre-saas；公网双独立游客 Cookie、私有结果隔离、verified showcase 与 Authing 均验证通过。
回滚备份 `/tmp/qre-access-hardening-pre-20261025-release/`。

**P1 首次成功路径首切片已发布（2026-10-25，QRE-SAAS-FIRST-SUCCESS-UX-001，commit `a84a9a3`）**：new/job 展示队列位置、worker 离线、已等待与真实失败原因；游客/会员取消与失败恢复上线。仅同步 app.py、new.html、job.html、wait-mask.js、lab-theme.css 并重启 qre-saas，无 schema 变更、未重启 worker。公网五文件 SHA256 与仓库一致，58 verified 200、74 匿名 401、Authing 302。回滚备份 `/tmp/qre-first-success-ux-pre-20261025/`，生产证据 `.tmp/first-success-ux-production/`。

**P1 结果理解切片已发布（2026-10-25，QRE-SAAS-RESULT-UNDERSTANDING，commit `9fd3b3d`）**：公开 `/saas/help` 与主导航「使用说明」上线；结果页/个股页模块深链和 `/api/results/<id>/symbols/<code>` 的 `data_until` 已生效。已同步 app.py、base.html、job.html、symbol.html、help.html、replay.js、lab-theme.css 并重启 qre-saas，无 schema 变更、未重启 worker、未跑真实回测。公网 help 200、58 个股详情 data_until=2026-10-09、74 匿名 401，文件 SHA256 与仓库一致。回滚备份 `/tmp/qre-result-understanding-pre-20261025/`，生产证据 `.tmp/result-understanding-production/`。

**NL DeepSeek V4.1 Flash 配置（2026-10-25）**：生产 `QRE_NL_LLM_BASE_URL=https://api.deepseek.com`，正确模型 ID 为 `QRE_NL_LLM_MODEL=deepseek-flash`（最新 V4.1 Flash；`deepseek-v4.1-flash` 不是可用 ID，真实编译 400）。已用 MACD 金叉死叉纯编译验证成功，未创建回测。改前 env 备份 `/etc/qre-saas.env.bak-deepseek-v41-20261025`（0600）。

**元数据上云（2026-09-26）**：因子目录与板块/概念名单经
`scripts/sync_saas_metadata.py` 导出为 deploy/saas/metadata.json（仅名称+数量，
无行情/成分明细），scp 到 ECS 后由 /api/saas/factors 与 /api/saas/universes 直出
（SAAS_METADATA_PATH 已在 /etc/qre-saas.env）。**因子库/聚类更新后再同步**：
本地跑 `scripts/sync_saas_metadata.py` 然后 scp deploy/saas/metadata.json 到
ECS 同路径即可（saas app 按文件 mtime 自动重载，无需重启）。

**C4 已验证（2026-09-19/20）**：临时测试账号方案——saas app 支持 env
`SAAS_TEST_ACCOUNT_EMAIL`/`SAAS_TEST_ACCOUNT_PASSWORD` 内置账号（login 校验前短路，
配置即凭证，存 /etc/qre-saas.env[0600]，不入仓库；内测开放前须移除）。公网端到端实测：
测试账号登录 → POST /api/jobs（smoke job#2 58s completed；full job#3 20 只×6 月 115s
completed）→ /api/results 列表与详情（summary/chart-data/tag-analysis）数据完整；
权限语义：未登录 401、删他人结果 404。
**⚠️ 该测试账号已于 2026-10-25 移除（QRE-SAAS-ACCESS-HARDENING-001）**：备份
`/etc/qre-saas.env.bak-access-hardening-20261025-173458`[0600] 后两键注释、
`systemctl restart qre-saas`（active）。移除后验证：登录页 200、Authing 302、
callback 假 code 400、me 401、**测试账号正确密码 401（bypass 失效）**、worker
错 token 401、游客越权提交 400（无任务产生）、showcase 200。users 表遗留 1 行
该邮箱用户（无 password_hash，密码登录不可用）保留未动。同批 env 增补
`SAAS_GUEST_COOKIE_SECURE=1`（游客会话 Cookie Secure 标志，下次重启/部署生效）。
app 代码里的 `SAAS_TEST_ACCOUNT_*` 短路逻辑保留（env 不配即完全不生效，
`test_test_account_disabled_by_default` 锁死该语义）。

**C5+游客 UX 已上线（2026-09-20）**：游客免登录测试（单股/近2年/日1次/结果次日清空）全链路打通——游客条+确认弹层+403 回填+结果页次日清空提示；公网新建页与 8081 参数区/顶栏完全对齐（全期按钮+费率滑点字段）；统一顶栏无管理台链接。

**C5 已上线（2026-09-20）**：8081 lab 页面体系完整平移到 SaaS 端。
- 页面：new.html 重写为冻结版三入口（自然语言/快速向导三级级联+两级条件组/高级 YAML）
  + PCB 排线 + 日历选区间 + 标的范围（全 A/随机 N 只/指定代码；板块概念因 ECS 无行情库
  降级为说明+替代选项）+ 预览栏（行号高亮、参数自动合并、持仓天数注入 YAML）+ 唯一
  流水线按钮（校验→冒烟→全量，提交时 401 引导登录，未登录可浏览）；dashboard.html
  记录页加超额收益列+排序+分页+删除弹层；job.html 加交易磨损与 FRM 风险模块
  （risk-analysis 无报告整块隐藏）+ 个股明细大入口；新增 symbols.html/symbol.html
  两页与路由（/saas/jobs/<id>/symbols[/<code>]）。
- 主题：saas base.html 引入 lab-theme.css/lab-ui.js，--accent 换淡紫 #6750A4。
- 联调修复（各带测试）：worker `_job_params` 只读 params 导致 17 协议 params_json 被丢弃
  （按默认参数跑）→ 兼容读取；worker runner 透传 random_n；上传端点
  /api/worker/jobs/<id>/result/files 清单键含子目录时 Path(name).name 拍平导致全部 400
  → 按完整相对路径匹配+保留子目录（.. 穿越仍 400）。
- nginx 修复：`location ~* \.(css|js...)$` 扩展名规则抢在 /static/ 前缀前导致 SaaS
  静态资源 404 → 加 `^/static/` 优先段反代 gunicorn（仓库 deploy/landing/nginx-aguhuice.conf
  已同步线上）。
- 验证：本地 staging（18099，bypass+真行情库+本机 worker）Playwright 全链路——向导出
  因子目录、提交→冒烟→全量 job completed、详情页（磨损可见/无风险报告正确隐藏）、
  个股列表→点行进个股详情（平安银行：7 指标卡/收益曲线+区间卡/磨损/K线买卖点/交易明细
  /下单记录全渲染）。ECS 公网验证（未登录态）：新建页 200 不跳登录、三卡+PCB+日历正常、
  静态资源 200；登录后链路未在 ECS 实测——/etc/qre-saas.env 含测试账号凭证但纪律上不动
  不读，留待用户验收时自验。
- 部署：gui/ 全目录 rsync 至 /srv/aguhuice/qre（含模板+静态），runner.py 同步，qre-saas
  restart 后 /saas/ 与 /saas/jobs/1/symbols 均 200。

**C1 已上线（2026-09-19）**：
- SaaS Web/API：`qre-saas.service`（gunicorn 2 workers，127.0.0.1:8090，MemoryMax=1G，
  User=www-data，EnvironmentFile=/etc/qre-saas.env[0600]，repo /srv/aguhuice/qre + venv
  最小依赖 flask/sqlalchemy/psycopg[binary]/gunicorn/pyyaml——**无 pandas/numpy**）；
- PG 小库：本机 postgresql，库 `aguhuice`，角色 `aguhuice`（密码在 /etc/qre-saas.env），
  cloud_schema.sql 已 apply（7 表）；
- Nginx：443 server 块反代 `/api/`、`/saas/`、`/static/` → 127.0.0.1:8090，
  落地页静态 `/` 不变（仓库 nginx-aguhuice.conf 已同步线上版）；
- 验证：公网 https://aguhuice.com/ 200（落地页）、/saas/login 200、/api/saas/me 401、
  /api/worker/jobs/claim 错 token 401、真 token 200 {job:null}。

**QRE-SAAS-ADMIN-TUNNEL（2026-09-27，方案 A 已上线）**：
- 管理台撤公网：nginx 对 `= /saas/console`、`= /api/saas/console`、`/api/saas/console/`
  直接 `return 404`（仓库 deploy/landing/nginx-aguhuice.conf 已同步线上）；公网
  /saas/console 与 /api/saas/console/overview 实测 404，其余页面回归正常。
- 管理台访问改 SSH 隧道（gunicorn 127.0.0.1:8090 不动，隧道内仍走 _require_admin）。
- PG 每日备份：ECS root cron 03:17 `/srv/aguhuice/backups/pg-backup.sh`
  （pg_dump custom 格式，保留 7 天）；本地 WSL cron 04:23
  `deploy/saas/pull-ecs-backup.sh` scp 拉取最新 dump 至
  `~/quant-workspace/backups/ecs-aguhuice/`（本地留 7 份，拉取模式 ECS 无反向访问）。

代码侧（家里 WSL，部署备用）：SaaS app（gui/saas/：验证码登录/任务队列/worker 协议/四页前端）、
worker 包（client/runner/daemon）、Docker 沙箱、流式批量回测均已实现并测试（见 05 逐条）。

## 4. 后续步骤

主线顺序见 `15_SAAS_SYSTEMS_DESIGN.md` 第 7 节 TODO（阶段 A–E；全链路优先，登录/管理最后）。
ECS 侧专属待办（隶属阶段 C）：

- [x] 装 Python/Flask + PG 用户小库（C1 完成；PG 2G 参数调优暂未做，内测量级先观察）
- [x] Nginx IP 限流（C2 完成，2026-09-19。矩阵：写端点 POST /api/jobs 等 10r/m
  burst 3（仅写方法，$qre_write_key 空键跳过 GET）；读 /api/* 60r/m burst 20；
  /api/saas/auth/* 5r/m burst 2 防爆破；/api/worker/* 120r/m burst 30（另靠
  X-Worker-Token）；limit_conn 20/IP；超限 429，命中记 error_log 含 zone 名）
- [ ] 禁 root 直连（PasswordAuthentication/PermitRootLogin 关闭，仅用 deploy 用户）
- [x] 家里 worker 生产化（C3 完成，2026-09-19）：本机 systemd `qre-saas-worker.service`
  （User=van，EnvironmentFile=/etc/qre-saas-worker.env[0600]，MemoryMax=26G（R2，2026-10-03
  由 16G 上调），Restart=always），指向 https://aguhuice.com，env 无任何代理变量；
  公网端到端实测：smoke job#1 claimed→completed 84s，23 个产物文件 sha256 校验落盘
  /srv/aguhuice/uploads/job_1/。仓库模板 deploy/saas/qre-saas-worker.service 已更新为生产版
- [x] **worker 单例收敛（2026-10-03 晚）**：R2 调试期引入的用户级 `systemctl --user
  qre-worker`（worker_id=home-pc）与系统级 `qre-saas-worker`（wsl-home-pc）双跑，
  绕过全局资源语义。已收敛为唯一系统级 `qre-saas-worker`：env 并入槽位/闸门/
  代理置空/QRE_MARKET_DB_URL 新密码；用户级 unit+env 退役为 ~/.config/*.retired；
  ECS workers 表 home-pc 僵尸行已清。收敛后端到端冒烟 job#35 completed(attempts=1)。
  **不要再并存第二套 worker。**
- [x] **apply `deploy/saas/cloud_schema.sql` 新列（P0-1B 已完成）**：`results.result_contract JSONB` 已由 postgres 执行，2026-10-25 发布时 information_schema 核查列存在。worker 无需改动、无需重启。
- [ ] 结果产物磁盘水位监控（40GB ESSD，结果只留元数据+图表 JSON，大文件走 OSS）
- [ ] 落地页页脚备案号占位替换为正式号：湘ICP备2026040383号-1（改 `deploy/landing/index.html` 后 scp 同步，见第 5 节）

## 5. 运维速查

```bash
# 登录
ssh -i ~/.ssh/aguhuice_ed25519 root@47.119.127.40
# 或 deploy：ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40

# 改落地页：改仓库 deploy/landing/index.html 后同步（保持线上与仓库一致）
scp -i ~/.ssh/aguhuice_ed25519 deploy/landing/index.html root@47.119.127.40:/var/www/aguhuice/index.html

# Nginx
nginx -t && systemctl reload nginx        # 配置改动后
journalctl -u nginx -f

# 证书续期（certbot timer 已自动；手动强制续期/检查）
certbot renew --dry-run

# 防火墙
ufw status verbose
ufw allow 8080/tcp   # 例：临时放行（默认不要开别的端口）

# fail2ban
fail2ban-client status sshd

# SaaS 管理台（QRE-SAAS-ADMIN-TUNNEL，2026-09-27 起公网 404，仅隧道访问）
./deploy/saas/admin-tunnel.sh        # 本地执行后浏览器开 http://localhost:9090/saas/console
curl -s -o /dev/null -w '%{http_code}\n' https://www.aguhuice.com/saas/console   # 应为 404

# PG 备份（ECS cron 03:17 生成，本地 cron 04:23 拉取）
ssh -i ~/.ssh/aguhuice_ed25519 root@47.119.127.40 'ls -lht /srv/aguhuice/backups/'   # ECS 端，留 7 天
ls -lht ~/quant-workspace/backups/ecs-aguhuice/                                      # 本地端，留 7 份
./deploy/saas/pull-ecs-backup.sh     # 手动拉取一次
# 恢复：scp dump 上 ECS 后  sudo -u postgres pg_restore -d aguhuice --clean <file>

# Worker 实时状态（R3 切片1，2026-10-03）：worker 每 15s 上报槽位/内存到
# POST /api/worker/status（间隔 env QRE_WORKER_STATUS_SECONDS，默认 15，两端 env 文件无需改，
# 有默认值）；管理台总览「Worker 资源」卡只读展示（在线=心跳<60s）。
# ⚠️ 踩坑：ECS 上 workers 表 owner 是 postgres（schema apply 所建），app 账号非 owner，
# 懒自愈 ALTER 即使 IF NOT EXISTS 也会报 must be owner（上线首报 500 实测）——
# ① 应用层 ensure 改为先查 information_schema，列在则完全不发 ALTER；
# ② 新列首次仍须手工 apply（已于 2026-10-03 执行）：
#   sudo -u postgres psql aguhuice -c "ALTER TABLE workers ADD COLUMN IF NOT EXISTS status JSONB; ALTER TABLE workers ADD COLUMN IF NOT EXISTS status_at TIMESTAMPTZ;"

# 信号扫描（CR-2026-10-04 模块二）：deploy/saas/signal_scan.py 挂在本机
# qre-refresh.service 的 ExecStartPost（refresh 成功后自动触发；`-` 前缀失败不影响 refresh）。
# 手动跑：本机执行
#   set -a; . /etc/qre-saas-worker.env; set +a
#   /home/van/quant-workspace/quant-research-engine-dual-agent-lab/.venv/bin/python \
#     deploy/saas/signal_scan.py
# env 需要 QRE_SAAS_BASE_URL / QRE_WORKER_TOKEN / QRE_MARKET_DB_URL；
# QRE_SIGNAL_SCAN_LOOKBACK_DAYS 默认 40。幂等可重跑（云端唯一约束去重）。
# ECS 新表首次手工 apply（strategy_watches/signal_events；users/tier_policies 的
# ALTER 由应用懒自愈，这两张表 owner 是 aguhuice）：
#   sudo -u postgres psql aguhuice -f /srv/aguhuice/qre/deploy/saas/cloud_schema.sql

# Worker 资源调配（R3 切片2，2026-10-04）：管理台「Worker 资源」卡设期望槽位/闸门# （POST /api/saas/console/worker-config → worker_configs 表 version+1）；
# worker 下轮 status 上报响应回带期望，不一致记日志「期望配置 vN 待应用」。
# 应用方式=在本机执行（console 卡片给出可复制命令，数值取期望配置）：
bash deploy/saas/worker-tune.sh --light-slots 2 --heavy-slots 3 \
    --light-min-avail-mb 2000 --heavy-min-avail-mb 6500
# 脚本：sed 更新 /etc/qre-saas-worker.env（缺键追加，改前 .bak-<ts> 备份）+
# sudo 自提权 + systemctl restart qre-saas-worker；worker 重启后上报自动回一致态。
# ⚠️ worker_configs 表 ECS 首次须手工建（owner 同 workers 踩坑）：
#   sudo -u postgres psql aguhuice -c "CREATE TABLE IF NOT EXISTS worker_configs (worker_id TEXT PRIMARY KEY, desired_light_slots INT, desired_heavy_slots INT, desired_light_min_avail_mb INT, desired_heavy_min_avail_mb INT, version INT NOT NULL DEFAULT 1, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_by TEXT);"
# DB 直查：
ssh -i ~/.ssh/aguhuice_ed25519 root@47.119.127.40 \
  "sudo -u postgres psql aguhuice -c \"SELECT name, last_heartbeat_at, status_at, status FROM workers;\""
sudo -n systemctl restart qre-saas-worker && sudo -n journalctl -u qre-saas-worker -n 30 --no-pager  # 本机 worker 重启/查日志（唯一 worker：系统级 qre-saas-worker，2026-10-03 收敛）

# 只读分享（QRE-SAAS-READONLY-SHARE，2026-10-26 IMPLEMENTED 待发布）：新增 share_links 表
# （token_hash 完整哈希/job_id ON DELETE CASCADE/owner_id/expires_at/revoked_at/created_at）。
# ⚠️ 与 results.result_contract 同款 owner 踩坑：app 账号 CREATE TABLE 会报 must be owner，
# 懒自愈 therefore 只兜底本地/测试库；**生产发布顺序 = 先备份 → postgres apply → 同步代码 →
# 重启 qre-saas**；未 apply 时分享创建返回 503、读取按无效 token（不放权）：
#   sudo -u postgres psql aguhuice -f /srv/aguhuice/qre/deploy/saas/cloud_schema.sql
# 公网验证用专用测试任务走 创建→匿名只读→撤销，不跑真实回测，完成后清理测试链接/任务：
#   sudo -u postgres psql aguhuice -c "SELECT id, job_id, owner_id, expires_at, revoked_at FROM share_links ORDER BY id;"
```

## 6. 纪律

- ECS 不落行情/因子明细（数据不出家门）；
- 一切线上文件改动先在仓库 `deploy/` 下留版本再同步；
- 8080 管理台永远留在本地，不随 SaaS 上线。
