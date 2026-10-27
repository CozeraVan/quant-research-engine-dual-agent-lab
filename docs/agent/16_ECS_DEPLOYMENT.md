**root SSH 直连已禁、deploy+sudo 部署纪律已落地（2026-10-27，QRE-ECS-SSH-HARDENING，待人工验收、未 commit/push）**：
`/etc/ssh/sshd_config.d/99-qre-hardening.conf`（新）设 `PermitRootLogin no`/`PasswordAuthentication no`/
`KbdInteractiveAuthentication no`/`PubkeyAuthentication yes`/`AllowTcpForwarding yes`（TCP 转发显式保留——
9090 管理台隧道依赖它）。因 sshd 同关键字取先出现者且 drop-in 按字典序展开，`99-aguhuice-hardening.conf`
（排在前）的 `PermitRootLogin prohibit-password` 必须改为 `no`，否则新文件被完全遮蔽（已实测证明），
该文件另两行未动。**前置条件**：审计发现 deploy 密码锁定（`L`）且 sudoers 仅放通 systemctl/docker，
`sudo -n` 改动前不可用——直接禁 root 会失去文件安装、PG 备份恢复、证书、防火墙能力；故先新增
`/etc/sudoers.d/90-qre-deploy`（`deploy ALL=(ALL:ALL) NOPASSWD: ALL`，0440，`visudo -c` 全绿）并修掉
`sudoers.d/deploy` 0644 权限隐患，之后才动 sshd。`sshd -t` 通过后 `systemctl reload ssh`（不断会话）。
**验证**：root 新连接 `Permission denied (publickey)`；既有 root 隧道 reload 后仍 200；deploy 新连接 +
`sudo -n` + qre-saas active/qre-worker inactive/nginx/ssh 全过；deploy 隧道 9092 与 `admin-tunnel.sh`
（默认已改 deploy@）起的 9090 均 `/saas/new` 200、`/saas/console` 200；`sudo -n fail2ban-client status
sshd` 正常；陈旧 root 隧道已停，现网无 root 会话。**脚本**：新增 `deploy/saas/deploy-ecs.sh`
（deploy+sudo 唯一部署入口，`--dry-run`，自带 /tmp 回滚副本，只重启 qre-saas）——已用与生产 SHA256
相同的 `deploy/saas/metadata.json` **真实端到端跑通**（MainPID 493988、api 200、生产字节未变），并修掉
两个真 bug（scp 不自建远程嵌套目录；内联 `bash -c` 二次转义 → 改远程脚本文件）；`admin-tunnel.sh` 与
`pull-ecs-backup.sh` 默认 `root@`→`deploy@`；`scripts/sync_saas_metadata.py` 用法注释同步。**测试**：无
`src/` 改动、无测试引用这三脚本；`bash -n` 全过；**全量 2890 passed + 6 skipped**（零回归）。
**备份/回滚/救援**：`/tmp/qre-ssh-hardening-pre-20261027/`；回滚两步（删 99-qre-hardening.conf + 改回
`prohibit-password` → reload ssh；删 90-qre-deploy）均不断业务；阿里云控制台 VNC 救援路径见 §7。
**无 schema 变更、未重启 worker、未跑真实回测。未 commit/push，待用户人工验收。**

**因子中文显示名全覆盖已部署（2026-10-27，QRE-FACTOR-ZH-COVERAGE，待人工验收、未 commit/push）**：
剩余 341 列中文名全部维护完成（alpha191 191 / alpha101 31 / quality 87 / growth 16 /
`_pit_financial_panel` 14 / candle 1 / value 1），**未维护 0 列**，覆盖 554 → **895/895（100%）**，
`deploy/saas/metadata.json` 902/902 项带 zh。命名逐条可溯源（alpha191 formulas.py docstring、
官方 486 文档表达式表 `change_requests/factor_specs_*.md`、quality/growth `compute_all`/results、
Tushare 标准字段语义），无伪造翻译、无英文列名冒充中文名（测试锁定）。只同步
`configs/factor_registry.json` 与 `deploy/saas/metadata.json` 两文件：核对生产两文件 SHA256 与
上一轮基线一致并拉回本地逐字段比对（仅 341 处 zh 差异）→ 备份
`/tmp/qre-factor-zh-pre-20261027/` → scp 两文件并改回 deploy 属主 → **仅重启 qre-saas
（新 MainPID 491196）**，`qre-worker` inactive 未触碰；**无 schema 变更、未 apply、未跑真实回测**。
两文件生产 SHA256 与本地逐一相等（registry `020b0874…`、metadata `29045e24…`）。应用层验证
（域名无 DNS，ECS 上 `curl -H "Host: www.aguhuice.com" http://127.0.0.1:8090/...`，TLS/nginx 未改）：
`/api/saas/factors` 902/902 带 zh；`/saas/new`、`/saas/`、`/saas/help`、`/saas/login` 均 200。
`scripts/gen_factor_registry.py` 为开发工具，**不同步生产**（生产只消费生成产物）。
回滚：恢复 `/tmp/qre-factor-zh-pre-20261027/` 两文件并重启 qre-saas。未 commit/push，待用户人工验收。

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
| SSH | **仅密钥、禁 root 直连**（2026-10-27 QRE-ECS-SSH-HARDENING 起）：`ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40`。`PermitRootLogin no` / `PasswordAuthentication no` / `KbdInteractiveAuthentication no` / `PubkeyAuthentication yes` / `AllowTcpForwarding yes`（TCP 转发为 9090 管理台隧道保留），配置见 `/etc/ssh/sshd_config.d/99-qre-hardening.conf`。`root@` 直连会得到 `Permission denied (publickey)`。 |
| 用户 | deploy（sudo 组，公钥 `SHA256:ghZ0NGRMwpXkAk6CrAnmDILAxRYhJ3lhLCUntkLPooE` 已写入 `/home/deploy/.ssh/authorized_keys`）+ `/etc/sudoers.d/90-qre-deploy` 给 `NOPASSWD: ALL`，故 `sudo -n` 全程非交互可用。root 仍存在但**不可登录**，仅作 sudo 目标；救援走云控制台 VNC（见 §6）。 |

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

**P1 只读分享已发布（2026-10-26，QRE-SAAS-READONLY-SHARE，commit `08b4a27`）**：postgres 幂等 apply `share_links`（owner=postgres）后同步 app.py、四个结果/个人信息模板与 schema，仅重启 qre-saas。公网 job74 创建→匿名只读 200→撤销 401；job58 无参数 showcase=200、无效/撤销 share=401、有效 share=200，显式失效分享不会回退 showcase。临时链接已清理，share_links=0，未重启 worker、未跑真实回测。回滚备份 `/tmp/qre-readonly-share-pre-20261026/` 与 `/tmp/qre-readonly-share-showcase-hotfix-pre-20261026/`。

**结果页 UI 精简已发布（2026-10-26，QRE-SAAS-UI-DECLUTTER-001，commit `8accb66`）**：同步 `_records_scripts.html`、help/job/showcase/symbol 四模板与 lab-theme.css（共六文件），仅重启 qre-saas。公网 job58/symbol58/showcase/profile/help 200，无合同标签、合同版本或 `/saas/help#` 深链；help 侧边栏目与 20px 标题生效，六文件 SHA256 与 HEAD 一致。回滚备份 `/tmp/qre-ui-declutter-pre-20261026/`，未重启 worker、未跑真实回测。

**经典策略与分享热修已验收发布（2026-10-26，commit `e6f4f77`）**：经典策略与结果操作卡精修、分享序列权限热修、分享完整公网 URL 热修均通过用户验收并已 push。最终全量 2703 passed + 5 skipped；生产创建返回完整公网 URL、公开页面与撤销均 200。备份分别为 `/tmp/qre-classic-actions-pre-20261026/`、`/tmp/qre-share-sequence-grant-pre-20261026/`、`/tmp/qre-share-absolute-url-pre-20261026/`。未跑真实回测。以下为实施过程记录。

**分享完整 URL 热修已部署（2026-10-26，QRE-SAAS-SHARE-ABSOLUTE-URL，待人工复验、未 commit/push）**：用户链接经 API 与 Chromium 验证实际有效，但创建响应只有相对路径。新增 `SAAS_PUBLIC_BASE_URL=https://www.aguhuice.com`，创建接口返回完整公网 URL（缺省回退 request.url_root）。生产创建/公开页面/撤销均 200，全量 2703 passed + 5 skipped，app.py 哈希一致。备份 `/tmp/qre-share-absolute-url-pre-20261026/`（app.py + 0600 env），未跑真实回测。

**分享创建权限热修已部署（2026-10-26，QRE-SAAS-SHARE-SEQUENCE-GRANT，待人工复验、未 commit/push）**：生产日志确认 `share_links_id_seq` 缺 USAGE 导致 POST 分享 500；已授予 aguhuice 表 CRUD + 序列 USAGE/SELECT 并写入 `cloud_schema.sql` 幂等 DO 块。另将既有 showcase/showcase_daily 同构定义纳入权威 schema，消除新库懒建表时序依赖。真实创建/撤销 API 均 200，临时链接/session 清理，share_links=0；全量 2702 passed + 5 skipped，schema SHA256 一致。备份 `/tmp/qre-share-sequence-grant-pre-20261026/`，未跑真实回测。

**经典策略与结果操作 UI 已发布（2026-10-26，QRE-SAAS-CLASSIC-ACTIONS-UI，已部署待人工验收、未 commit/push）**：核对 ECS 三文件与本地 HEAD 基线 SHA256 一致后，备份 `/tmp/qre-classic-actions-pre-20261026/`，仅同步 `showcase.html`、`job.html`、`lab-theme.css` 并重启 qre-saas（未重启 worker、未跑真实回测）。showcase：页头灰字备注移入 H1 旁问号提示，`#sc-hint` 与底部灰字长文/弱链接删除，改「复现经典策略」tip +「新建同款策略」主按钮（`/saas/new`），subtitle 保留。job：`#box-actions`/`#box-share` 合并进 `#result-actions-card`「结果操作」卡，保存/确认信号=主按钮、信号/分享=次按钮，状态文本去 `.opt`，信号 T+1 提示移入扫描范围问号；新增空安全 `syncResultActionCard()`（任一组可见才显示外层，游客/showcase/分享只读整体隐藏），原 ID/权限/事件绑定/API 不变。lab-theme.css 仅加局部规则（按钮 ≥44px、≤768px 纵排全宽、375px 不横溢）。测试：TDD RED→GREEN，新 `tests/test_saas_classic_actions_ui.py` 12 例 + 3 处既有断言更新，相关 10 文件 289 passed、全量 2701 passed + 5 skipped（零回归）；真实 Chromium 9/9 零 JS error 零横溢，证据 `.tmp/classic-actions-ui/`。公网：showcase/job58/`/static/lab-theme.css` 200，新标记齐全、删除标记为零、CSS SHA256 与本地一致，`/saas/`、help、login、new、symbols 两页 200。**未 commit/push，待用户人工验收；不通过立即恢复 `/tmp/qre-classic-actions-pre-20261026/` 并重启 qre-saas。**

**公测运营与反馈闭环已验收发布（2026-10-26，QRE-SAAS-PUBLIC-BETA-OPS）**：用户批准提交，ECS 保持已部署版本，本次 commit/push；发布前聚焦 20 passed、全量 2773 passed + 6 skipped，未跑真实回测。以下为实施与部署过程记录。

**公测运营与反馈闭环已部署（2026-10-26，QRE-SAAS-PUBLIC-BETA-OPS，实施过程）**：9090 管理台新增「公测运营」tab（`GET /api/saas/console/ops`，窗口 today/7d/30d/all，admin 门禁不变）与反馈分类/处理状态闭环。核对 ECS 四文件与本地 HEAD 基线 SHA256 一致后，备份 `/tmp/qre-public-beta-ops-pre-20261026/`（app.py + console.html + feedback.html + cloud_schema.sql），postgres 幂等 apply `cloud_schema.sql`（新增 `nl_compile_events` 表——只存 ok/cache_hit/error_class/scope/created_at，不存策略文本/API key/原始 IP；feedback 增 category/status 两列；`feedback_id_seq` 授权 DO 块），scp app.py、`gui/saas/ops_support.py`（新）、console.html、feedback.html、cloud_schema.sql，仅重启 qre-saas（active；worker 在家未动），未跑真实回测。**生产缺陷热修**：`feedback_id_seq` 缺 USAGE 导致登录用户提交反馈 HTTP 500（feedback 特性此前从未部署 ECS，首次上线暴露；同 share_links 序列坑）——已 `GRANT USAGE, SELECT ON SEQUENCE feedback_id_seq TO aguhuice` 并将幂等 DO 块写入 schema。**生产验证**（临时 admin/member 用户 + session + 临时反馈，结束即清理，未输出凭证）：ops 鉴权匿名 401/会员 403/非法 window 400；空口径诚实（编译前 nl.total=0、first_event_at=None、ratio=None）；反馈闭环（提交→筛选→open→doing→本人可见）；游客真实 DeepSeek 编译两次 cache_hit false→true 且 YAML 一致（A2A3 无回归）；编译后 ops all 窗口 nl.total=2、first_event_at=2026-10-26；清理后 temp_users=0/feedback=0、真实 sessions 未动；9090 隧道 `/saas/console` 200 含 ops 标记、ops API 无 token 401；公网 `/saas/`、login、new、feedback、help 200，`/saas/console` 仍 404。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-public-beta-ops-pre-20261026/` 四文件并重启 qre-saas**（或按 `.tmp/public-beta-ops/production-verification.txt` 内回滚 SQL 处理新表/新列）。回测/队列/转化口径与「自功能上线起统计」边界详见 04/05/11。下一项：按灰度反馈继续修正公网体验。

**NL 输入校验与 DeepSeek 裁判已验收发布（2026-10-26，QRE-SAAS-NL-A1）**：用户批准提交，ECS 保持已部署版本，本次 commit/push；最终专项 67 passed、全量 2840 passed + 6 skipped，真实 DeepSeek 分层 12 条评估 0 失败，未跑真实回测。以下为实施与部署过程记录。

**因子呈现属性统一协议已部署（2026-10-27，QRE-FACTOR-DISPLAY-CONTRACT，Step 5 实现，Kimi 复核与部署收尾，待人工验收、未 commit/push）**：备份 `/tmp/qre-factor-display-pre-20261027/` 后，同步 configs/factor_registry.json、deploy/saas/metadata.json、gui/factor_registry.py、factor_wizard.py、lab_result.py、factor-layout.js、replay.js、job.html、symbol.html，**仅重启 qre-saas**（active；worker 在家未动）；无 schema 变更。专项与注册表 59 passed，全量 2890 passed + 6 skipped；真实 Chromium 验证 EMA 主图、MACD 同副图、夜间切换与 375 无横溢，证据 `.tmp/factor-display-contract/`。未跑真实回测。建议提交 `feat(factors): 统一因子呈现属性与图表合同`。

**重播边界核验已部署（2026-10-27，QRE-SAAS-REPLAY-BOUNDARIES，待人工验收、未 commit/push）**：核验证明重播既有路径完整（展开/收起、seek、重播、重入、orders 优先、多因子布局）后修复两处真实缺口——①同日聚合计数口径（`replay.js` `aggHead` 按 sym 去重计「只」、事件数大于标的数时披露「（M 笔）」，修 symbol 页 6 笔同日买单误显示「6 只」；`evChipText` 统一 chip 文案，缺字段不拼装）；②job 事件价量补足（`lab_result._trade_points` 在 round_trips.csv 有 quantity/entry_price/exit_price 列时补足到散点，缺列不加键、仅对新 run 生效、不回填；job/symbol 事件带 sym+价量；旧产物降级纯标的 chip）。核对四文件与本地 HEAD 基线 SHA256 一致后，备份 `/tmp/qre-replay-boundaries-pre-20261026/`（replay.js + job.html + symbol.html + lab_result.py），scp 四文件，仅重启 qre-saas（active；worker 在家未动）；**无 schema 变更、未 apply**。测试：TDD RED=5→GREEN，新 `tests/test_saas_replay_boundaries.py` 7 passed，全量 **2863 passed + 6 skipped**；Chromium 10/10 零 JS error 零横溢（1280/375）。公网验证（匿名 job58，verified 公开只读）：replay.js 新口径标记在位；进入重播→空仓快进到首个事件日→末帧 4069/4069→退出静态重建，全程零 JS error；旧数据（无价量字段）chip 为纯标的、不造值。9090 隧道 job58 200。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-replay-boundaries-pre-20261026/` 四文件并重启 qre-saas。**

**夜间模式已部署（2026-10-27，QRE-SAAS-NIGHT-MODE，待人工验收、未 commit/push）**：SaaS 全部页面（含 9090 console）新增夜间主题，浅色 token/配色/视觉/排版/文案/数据零变化，唯一新增交互是主题切换按钮；8080/8081 未改，红涨绿跌保留，`#guest-note` 深色告警（`#B4761F`/`#3D3118`）刻意保留。夜间 8 token：bg `#17153B`／card `#2E236C`／line `#433D8B`／text `#F1EDF8`／muted `#C8ACD6`／accent `#7E60BF`／accent-deep `#C8ACD6`／accent-soft `#2E236C`。机制：三态（未选择跟随 `prefers-color-scheme`）+ `localStorage('qre-theme')` 持久化 + `<html data-theme>` + 首帧内联防 FOUC（`login_callback.html` 同样内联并补深色 `:root` 兜底）+ meta theme-color 同步 + `QRETheme.themeChart` 让 ECharts 全要素随主题改（不重算数据/布局）。部署前核对：生产 5 文件与记录基线 SHA256 一致（replay.js `d002dbc3…`、base `3f1e5467…`、login_callback `71099a18…`、job `e39901ba…`、symbol `be9723c4…`），night-mode.css/js 不存在；把生产 5 文件 scp 回本地逐一 `diff -u` → **差异只有夜间模式行**（Step 5 `aggHead` 已在生产，本地增量纯净）。备份 `/tmp/qre-night-mode-pre-20261027/`（`static/` + `saas/templates/` 共 5 文件），scp 7 文件（`static/night-mode.css` `46e328c5…`、`static/night-mode.js` `7494cb69…`、`static/replay.js` `b1f1d75e…`、`base.html` `2e2f6f45…`、`login_callback.html` `17f82698…`、`job.html` `a8ffc35e…`、`symbol.html` `1e8ebd44…`，生产 SHA256 与本地逐一相等），**仅重启 qre-saas（active，MainPID 487122）**；`qre-worker` 仍 inactive、未触碰；**无 schema 变更、未 apply、未跑真实回测**。测试：新 `tests/test_saas_night_mode.py` 24 passed，相关 6 文件 148 passed，全量 **2871 passed + 6 skipped**；真实 Chromium 审计 138 ok / 0 FAILURES（exit 0）。**生产验证方式说明**：`www.aghuice.com` 在本机与 ECS 均无 DNS，本地代理 7897 对该域名 `SSL_ERROR_SYSCALL`（同代理 example.com 200），因此改用 ECS 上 `curl -H "Host: www.aghuice.com" http://127.0.0.1:8090/...` 做应用层端到端验证（**TLS 与 nginx 配置未改动**）：`/saas/new` 200/103937B、`/saas/` 200/45033B、`/saas/help` 200/31830B、`/saas/login` 200/27552B、`/static/night-mode.css` 200/15250B、`/static/night-mode.js` 200/8469B、`/saas/console` 200/68285B；主题标记计数齐全（new：css=1/js=1/btn=1/内联=1/theme-color=2；login、console：css=1/js=1/btn=1）。生产路径前缀实为 `/srv/aguhuice/qre/src/quant_research_engine/gui`。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-night-mode-pre-20261027/` 七文件（其中 2 个新增文件直接删除）并重启 qre-saas。** 建议提交 `feat(saas): 新增夜间模式（浅色不变）`。

**NL 裁判路径一致性复核后重新部署（2026-10-26，QRE-SAAS-NL-A1 复核轮，实施过程）**：主 Agent 复核 2 个路径一致性 Required Fixes——①删除 admin 裁判豁免（`if not force`，管理员不限配额但与会员一样经过 DeepSeek 裁判；原绕过是未经要求的新权限差异）；②DB 故障回退路径仅 `not force` 时裁判（force 用户在回退路径跳过裁判，与正常路径一致；规则硬拒仍在最前）。本轮只同步 `app.py`（无 schema 变更）：备份 `/tmp/qre-nl-a1-deepseek-review1-pre-20261026/` → scp → 仅重启 qre-saas（active；worker 在家未动）。测试：TDD RED=2→GREEN，guard 67 passed，全量 **2840 passed + 6 skipped**；Chromium 7/7 零 JS error 零横溢（裁判 prompt 未变，未重复真实评估）。公网最小复核：合法 MACD 缓存命中 200 cache_hit=true（零裁判零配额，guest 配额 5→5）、乱码+force 仍 422、jobs 10→10、cache 4→4；公网 /saas/、new、login 200，9090 隧道 /saas/new 200。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-nl-a1-deepseek-review1-pre-20261026/` 并重启 qre-saas。**

**NL 输入校验 DeepSeek 方向已部署（2026-10-26，QRE-SAAS-NL-A1 方向变更轮，待人工验收、未 commit/push）**：用户明确暂不配置 Jev，第二裁判改用现有 DeepSeek（`QRE_NL_LLM_*`，`/etc/qre-saas.env` 已配置，未读取/输出任何密钥）。删除 Jev/TypeSafe 客户端、环境变量、requests 依赖与评估脚本；裁判复用 `nl_compiler.call_llm` 独立裁判 prompt（严格 JSON 三分类，故障降级规则层）。编排：规则层 → 缓存快路径/锁内复检（命中零裁判）→ 配额计数 → 裁判（仅 cache miss；force 跳过；admin 豁免已于后续复核删除）→ 编译；裁判拒绝也占配额。核对四文件与上一轮部署基线一致后，备份 `/tmp/qre-nl-a1-deepseek-pre-20261026/`（nl_input_guard.py + app.py + new.html + strategy.html），scp 四文件，仅重启 qre-saas（active；worker 在家未动）；无 schema 变更。测试：TDD RED=29→GREEN，guard 67 passed，全量 **2840 passed + 6 skipped**；Chromium 7/7 零 JS error 零横溢。**真实评估**（ECS 生产凭证，分层 ≤12 条）：deepseek-flash、0 失败、延迟 533–1590ms、not_strategy 4/4、strategy 3/4（1 unclear→review）。**公网计数验证**（临时游客会话）：规则拒绝/review 配额 +0；非策略描述 cache miss 裁判拦截（422 review、配额 +1、cache 不写、events 不记）；合法 MACD cache hit 零裁判（200 cache_hit=true）；新合法描述裁判+编译两阶段 200。前后计数 jobs 10→10、cache 3→4、events 5→7、guest 配额 3→5。9090 隧道 new/strategies 200 且 DeepSeek 隐私 tip 在位；公网四页 200。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-nl-a1-deepseek-pre-20261026/` 四文件并重启 qre-saas。**

**NL 输入校验复核修正后重新部署（2026-10-26，QRE-SAAS-NL-A1 复核轮，待人工验收、未 commit/push）**：主 Agent 复核 3 项 Required Fixes——①领域语境门槛（买房/买菜等通用买卖文本在无 Jev 生产被放行）：`nl_input_guard.py` 新增 DOMAIN_WORDS/STRONG_TRADING_WORDS 与 `_has_domain_context`，有入出场词但无领域语境至少 review；②strategy.html 重编译区隐私 tip-trigger + new.html review 模态 role=dialog/aria-modal/aria-labelledby；③`force` 只认 JSON 布尔 true（`data.get("force") is True`）。本轮只同步 `nl_input_guard.py`、`app.py`、`new.html`、`strategy.html`（无 schema 变更）：备份 `/tmp/qre-nl-a1-review1-pre-20261026/` → scp 四文件 → 仅重启 qre-saas（active；worker 在家未动）。测试：TDD RED=8→GREEN，guard 60 passed，全量 **2833 passed + 6 skipped**；Chromium 6/6 零 JS error 零横溢（截图几何稳定后拍摄）。生产复核：两条对抗文本 422 `nl_input_review`（领域语境原因）、`force:"false"` 字符串 422、合法 MACD 编译 cache_hit=true；9090 隧道 new/strategies 200 且新标记齐全。整任务回滚点 `/tmp/qre-nl-a1-pre-20261026/`；本轮回滚点 `/tmp/qre-nl-a1-review1-pre-20261026/`。

**NL 输入前置校验已部署（2026-10-26，QRE-SAAS-NL-A1，待人工验收、未 commit/push）**：`POST /api/saas/nl/compile` 在 empty 检查后、prompt/缓存/配额/LLM 之前增加规则层校验（reject=422 `nl_input_rejected` 不可绕过；review=422 `nl_input_review` 缺入场/缺出场，用户确认后 `force=true` 重发，force 只豁免 review）与可选 Jev 第二裁判（官方 `POST https://api.typesafe.ai/v1/systemone`，`TYPESAFE_API_KEY` 环境读取、模型缺省 jev-latest、阈值 0.7；未配置/超时/非 2xx/结构异常降级规则层；Jev 只升级 review 不硬拒；不记录策略文本与密钥）。核对三文件与本地 HEAD 基线 SHA256 一致后，备份 `/tmp/qre-nl-a1-pre-20261026/`（app.py + new.html + strategy.html），scp app.py、`gui/saas/nl_input_guard.py`（新）、new.html、strategy.html，仅重启 qre-saas（active；worker 在家未动）。**无 schema 变更、未 apply**。生产 `/etc/qre-saas.env` 未配置 `TYPESAFE_API_KEY`（只启用规则层；未索取/输出任何密钥）。公网验证（临时游客会话）：纯数字 reject 422 且 force 仍 422；缺出场 review 422（missing=["exit"]）；合法编译不回归（经典 MACD cache_hit=true；新合法描述 force 200、真实 DeepSeek 编译一次）；jobs 表 10→10；nl_compile_events 2→4。9090 隧道 `/saas/new` 与 `/saas/strategies/1` 200 且 A1 标记齐全（nl-review-modal/隐私 tip/sd-nl-review）；公网 /saas/、new、login、help 200。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-nl-a1-pre-20261026/` 三文件并删除 nl_input_guard.py 重启 qre-saas。** 证据 `.tmp/nl-input-guard/production-verification.txt`。

**公测运营复核修正后重新部署（2026-10-26，QRE-SAAS-PUBLIC-BETA-OPS 复核轮，待人工验收、未 commit/push）**：主 Agent 复核 2 项 Required Fixes——①转化比率误导（new_users/guest_sessions 之比可 >100%，生产实测「注册 / 游客 300.0%」）：API 改 `ratio=null` + `measurement="unlinked"`，console 卡改「转化率 —」，保留两个真实计数，未扩展用户追踪 schema；②today 窗口 UTC 零点改 Asia/Shanghai 自然日（`_now_shanghai()` + zoneinfo，UTC 00:00=上海 08:00 原漏当日凌晨 8 小时）。本轮只同步 `ops_support.py` 与 `console.html`（**无 schema 变更、不 apply**）：备份 `/tmp/qre-public-beta-ops-review1-pre-20261026/` → scp 两文件 → 仅重启 qre-saas（active；worker 在家未动）。测试：TDD RED=4 failed → GREEN；ops 20 passed；相关 3 文件 135 passed；全量 **2772 passed + 6 skipped**（1 例已知 flake 复跑通过）。Chromium 重跑 9/9 零 JS error 零横溢，console-ops-1280/375 确认无伪转化率。生产/9090 复核：ops API conversion.ratio=null、measurement=unlinked；today 窗口按上海日界；公页面 200。整任务回滚点仍为 `/tmp/qre-public-beta-ops-pre-20261026/`（含首轮五文件）；本轮回滚点 `/tmp/qre-public-beta-ops-review1-pre-20261026/`。

**NL A2/A3 已验收发布（2026-10-26，QRE-SAAS-NL-A2A3）**：用户批准通过，持久限频、版本化编译缓存与 9090 管理台同步已 commit/push；ECS 保持已部署版本，发布前全量复跑 2753 passed + 6 skipped，未跑真实回测。以下为部署过程记录。

**NL 持久限频与编译缓存已部署（2026-10-26，QRE-SAAS-NL-A2A3，待人工验收、未 commit/push）**：postgres 幂等 apply `cloud_schema.sql` 新增 `nl_rate_limits`（scope/subject_hash/window_start/hits，PK 三元组；游客 guest_daily=10 保持 403/code=guest_nl_limit，会员 member_minute=6 超限 429/code=nl_rate_limited+reset_seconds 且每日仍不限，admin 不计）与 `nl_compile_cache`（cache_key PK/description/result JSONB/model/prompt_hash/cache_version/created_at/last_hit_at/hit_count + last_hit_at 索引；只存 ok=true 完整结果，无 API key）；两表无序列，aguhuice 表 CRUD 由 schema DO 块授予。同步 app.py、`gui/saas/nl_compile_support.py`（新）、cloud_schema.sql 后仅重启 qre-saas，未重启 worker、未跑真实回测。公网临时游客会话对经典 MACD 描述纯编译两次：第一次 cache_hit=false（真实调用 LLM）、第二次 cache_hit=true 且 YAML 一致，jobs 表 10→10 未创建回测；缓存行 model=deepseek-flash、hit_count=1，guest_daily hits=1（命中不占额度）。全量 2726 passed + 6 skipped。回滚备份 `/tmp/qre-nl-a2a3-pre-20261026/`（app.py + cloud_schema.sql），不通过立即恢复并重启 qre-saas。实现细节见 04/05/09，证据 `.tmp/nl-a2a3/`。

**NL 管理台同步已部署（2026-10-26，QRE-SAAS-NL-A2A3 续，R-ADMIN-001，待人工验收）**：`api_console_overview` 新增 `nl` 对象（guest_daily/member_minute 读执行常量 `GUEST_NL_DAILY_LIMIT`/`MEMBER_NL_MINUTE_LIMIT`、admin=不限、cache_version、`nl_rate_limits`/`nl_compile_cache` 真实行数与 hits）；console.html 总览在 Worker 资源卡前新增「自然语言编译」卡（metric 卡 + tip-trigger，无灰色小字）。仅同步 app.py 与 console.html 并重启 qre-saas，无 schema 变更、未重启 worker、未跑真实回测。9090 隧道临时 admin session 验证 overview nl 字段与常量/表计数一致（匿名/错 token 401），临时账号与会话已清理。全量 2731 passed + 6 skipped。回滚备份 `/tmp/qre-nl-console-pre-20261026/`（app.py + console.html）。

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
- [x] **禁 root 直连（2026-10-27 完成，QRE-ECS-SSH-HARDENING）**：`PermitRootLogin no` + `PasswordAuthentication no` + `KbdInteractiveAuthentication no` + `PubkeyAuthentication yes`，`AllowTcpForwarding yes` 显式保留（9090 管理台隧道依赖）。配置文件 `/etc/ssh/sshd_config.d/99-qre-hardening.conf`（新）+ `99-aguhuice-hardening.conf` 的 `PermitRootLogin` 行 `prohibit-password`→`no`。**为什么必须改第二个文件**：sshd 同关键字取先出现者，drop-in 按字典序展开，`99-aguhuice-hardening.conf` 排在前会遮蔽新文件的 `no`（已实测证明）。配套 `/etc/sudoers.d/90-qre-deploy`（`deploy ALL=(ALL:ALL) NOPASSWD: ALL`，0440）——**禁 root 的前置条件**：改前 `deploy` 密码锁定且 sudoers 仅放通 systemctl/docker，`sudo -n` 不可用。回滚/救援见 §6。
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
# 登录（root 直连已禁，2026-10-27 QRE-ECS-SSH-HARDENING；一律用 deploy）
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40
# root@ 会得到 Permission denied (publickey)——这是预期，不是故障

# 部署业务文件（deploy+sudo 唯一入口；禁止再 scp 到 root@ 或直接写业务路径）
./deploy/saas/deploy-ecs.sh deploy/saas/metadata.json
./deploy/saas/deploy-ecs.sh --dry-run configs/factor_registry.json deploy/saas/metadata.json
#   内部动作：scp 到 /tmp/qre-deploy-<STAMP>/ → sudo -n install -o deploy -g deploy
#   → sudo -n systemctl restart qre-saas（仅此单位，worker 在家不动）→ curl 校验
#   回滚副本在 /tmp/qre-deploy-<STAMP>.bak/（root 属主，清理需 sudo -n rm -rf）

# 手工等效命令（脚本不可用时）
scp -i ~/.ssh/aguhuice_ed25519 <file> deploy@47.119.127.40:/tmp/
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 \
  'sudo -n install -o deploy -g deploy -m 0644 /tmp/<file> /srv/aguhuice/qre/<相对路径> \
   && sudo -n systemctl restart qre-saas'

# 改落地页：改仓库 deploy/landing/index.html 后同步（保持线上与仓库一致）
scp -i ~/.ssh/aguhuice_ed25519 deploy/landing/index.html deploy@47.119.127.40:/tmp/index.html
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 \
  'sudo -n install -o deploy -g deploy -m 0644 /tmp/index.html /var/www/aguhuice/index.html'

# Nginx
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 'sudo -n nginx -t && sudo -n systemctl reload nginx'
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 'sudo -n journalctl -u nginx -f'

# 证书续期（certbot timer 已自动；手动强制续期/检查）
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 'sudo -n certbot renew --dry-run'

# 防火墙
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 'sudo -n ufw status verbose'

# fail2ban（需 sudo，deploy 直连读不了 socket）
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 'sudo -n fail2ban-client status sshd'

# sshd 配置（改动后必须 sshd -t 再 reload；reload 不断会话）
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 'sudo -n sshd -t && sudo -n systemctl reload ssh'
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 'sudo -n sshd -T | grep -iE "^(permitrootlogin|passwordauthentication|kbdinteractive|pubkey|allowtcpforwarding)"'

# SaaS 管理台（QRE-SAAS-ADMIN-TUNNEL，2026-09-27 起公网 404，仅隧道访问）
./deploy/saas/admin-tunnel.sh        # 本地执行后浏览器开 http://localhost:9090/saas/console
curl -s -o /dev/null -w '%{http_code}\n' https://www.aguhuice.com/saas/console   # 应为 404

# PG 备份（ECS cron 03:17 生成，本地 cron 04:23 拉取；均走 deploy）
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 'ls -lht /srv/aguhuice/backups/'   # ECS 端，留 7 天
ls -lht ~/quant-workspace/backups/ecs-aguhuice/                                      # 本地端，留 7 份
./deploy/saas/pull-ecs-backup.sh     # 手动拉取一次
# 恢复：scp dump 上 ECS 后  ssh deploy@... 'sudo -u postgres pg_restore -d aguhuice --clean <file>'

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

# 只读分享（QRE-SAAS-READONLY-SHARE，2026-10-26 RELEASED）：新增 share_links 表
# （token_hash 完整哈希/job_id ON DELETE CASCADE/owner_id/expires_at/revoked_at/created_at）。
# ⚠️ 与 results.result_contract 同款 owner 踩坑：app 账号 CREATE TABLE 会报 must be owner，
# 懒自愈 therefore 只兜底本地/测试库；**生产发布顺序 = 先备份 → postgres apply → 同步代码 →
# 重启 qre-saas**；未 apply 时分享创建返回 503、读取按无效 token（不放权）：
#   sudo -u postgres psql aguhuice -f /srv/aguhuice/qre/deploy/saas/cloud_schema.sql
# 公网验证用专用测试任务走 创建→匿名只读→撤销，不跑真实回测，完成后清理测试链接/任务：
#   sudo -u postgres psql aguhuice -c "SELECT id, job_id, owner_id, expires_at, revoked_at FROM share_links ORDER BY id;"

# NL 持久限频与编译缓存（QRE-SAAS-NL-A2A3，2026-10-26，待人工验收）：
#   nl_rate_limits（原子计数，跨 worker/重启；scope=guest_daily 游客 10/日、
#     member_minute 会员 6/分钟，admin 不计）+ nl_compile_cache（只存 ok=true；
#     key=规范化描述+model+base_url+完整 prompt 哈希+NL_COMPILER_CACHE_VERSION；
#     命中不调 LLM 不占配额；不明文存 API key）。两表无序列，schema DO 块已授
#   aguhuice CRUD。改 gui/saas/nl_compile_support.py 或 app.py 的 NL 路由后：
#   scp 两文件 + cloud_schema.sql（若 schema 变，先 sudo -u postgres psql apply）→ 仅重启 qre-saas。
#   编译缓存版本覆盖 prompt 文案与因子目录（完整 prompt 哈希）；编译后处理变化必须手动
#   bump NL_COMPILER_CACHE_VERSION，否则旧结果会被继续命中。
#   sudo -u postgres psql aguhuice -c "SELECT scope, window_start, hits FROM nl_rate_limits ORDER BY window_start DESC LIMIT 5;"
#   sudo -u postgres psql aguhuice -c "SELECT description, model, cache_version, hit_count FROM nl_compile_cache ORDER BY created_at DESC LIMIT 5;"
#   公网纯编译验证（不创建回测）：
#   curl -s -X POST https://www.aguhuice.com/api/saas/nl/compile -H 'Content-Type: application/json' \
#     -d '{"description":"当 MACD 指标出现金叉时买入，出现死叉时卖出，最多持仓 20 天"}'   # 第一次 cache_hit=false
#   # 同一描述第二次应 cache_hit=true 且 yaml 与第一次一致
#   管理台同步（R-ADMIN-001）：9090 总览「自然语言编译」卡读 overview 的 nl 对象
#   （限额=执行常量、计数=两表真实行）。改 app.py 的 NL 路由/常量或 console.html 后：
#   scp 两文件 → 仅重启 qre-saas；隧道内核验：
#     curl -s http://127.0.0.1:9091/api/saas/console/overview -H "Authorization: Bearer <admin-token>"
#   回滚：恢复 /tmp/qre-nl-a2a3-pre-20261026/（app.py+cloud_schema.sql）或
#   /tmp/qre-nl-console-pre-20261026/（app.py+console.html）后 systemctl restart qre-saas
```

## 6. 纪律

- ECS 不落行情/因子明细（数据不出家门）；
- **先部署后验收再提交（2026-10-26 用户长期指令）**：代码/UI 改动先记录备份路径并直接同步 ECS，无需逐次询问部署批准；用户人工验收通过后再 commit/push，不通过立即恢复备份。文档-only 无需同步 ECS；
- 8080 管理台永远留在本地，不随 SaaS 上线。

## 7. SSH 加固、回滚与云控制台救援（2026-10-27，QRE-ECS-SSH-HARDENING）

**当前生效配置**（`/etc/ssh/sshd_config.d/`，`sshd -T` 可复核）：

| 文件 | 内容 | 说明 |
|---|---|---|
| `99-qre-hardening.conf`（新） | `PermitRootLogin no` / `PasswordAuthentication no` / `KbdInteractiveAuthentication no` / `PubkeyAuthentication yes` / `AllowTcpForwarding yes` | 独立加固 drop-in；`AllowTcpForwarding yes` 是 9090 管理台隧道（`admin-tunnel.sh`）的生命线，**不要关** |
| `99-aguhuice-hardening.conf`（改一行） | `PasswordAuthentication no` / `PermitRootLogin no`（原 `prohibit-password`）/ `PubkeyAuthentication yes` | 因 sshd 同关键字取先出现者且该文件字典序在前，不改这行新文件的 `no` 会被完全遮蔽 |
| `/etc/sudoers.d/90-qre-deploy`（新，0440） | `deploy ALL=(ALL:ALL) NOPASSWD: ALL` | 禁 root 的**前置条件**：改前 deploy 密码锁定 + sudoers 仅放通 systemctl/docker，`sudo -n` 不可用 |

**部署纪律（强制）**：

1. 生产只接受 SSH 公钥；`root@47.119.127.40` 不可用（`Permission denied (publickey)` 是预期）。
2. 禁止 root 直接操作业务文件；一律 `deploy` 登录 + `sudo -n`，入口脚本 `deploy/saas/deploy-ecs.sh`。
3. 业务树 `/srv/aguhuice/qre` 属 root，deploy 只能经 `sudo -n install` 写入，因此**落盘文件属主必须是 deploy**（脚本已用 `-o deploy -g deploy`）。
4. 只重启 `qre-saas`；`qre-worker` 在家（WSL），任何时候都不要在 ECS 上动它。
5. sshd 改配置：先 `sudo -n sshd -t`，通过后 `sudo -n systemctl reload ssh`（**reload 不断会话**，不要用 restart 去踢人）。

**回滚（两步，均不断业务）**：

```bash
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40
# ① 恢复 root 登录能力
sudo -n rm /etc/ssh/sshd_config.d/99-qre-hardening.conf
sudo -n sed -i 's/^PermitRootLogin no$/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config.d/99-aguhuice-hardening.conf
sudo -n sshd -t && sudo -n systemctl reload ssh
# ② 如连 sudo 也要退回原状
sudo -n rm /etc/sudoers.d/90-qre-deploy
```

原配置副本在本地 `/tmp/qre-ssh-hardening-pre-20261027/`（`etc/ssh/sshd_config`、`etc/ssh/sshd_config.d/99-aguhuice-hardening.conf`、`etc/sudoers.d/deploy`）。

**云控制台救援（最后手段，SSH 完全不可用时）**：

1. 阿里云控制台 → ECS 实例 `iZwz9fsp1t4gx1uawjyqgmZ`（47.119.127.40）→ **VNC / 远程连接**（独立于 sshd，sshd 配错也能进）。
2. 用 VNC 里的 root 登录（阿里云 VNC 不经过 sshd 的 `PermitRootLogin` 判定）。
3. 修复：`ls /etc/ssh/sshd_config.d/` → 删除或改错文件 → `sshd -t` → `systemctl reload ssh`。
4. 若 VNC 也要求密码且不知 root 密码：控制台「重置密码」/「更换系统盘快照回滚」（会中断业务，仅在极端情况使用）。
5. 救援后按上文回滚步骤把配置恢复到已知良好状态，再重新走一遍「审计 → `sshd -t` → reload → 验证」流程。

**风险提示**：本机私钥 `~/.ssh/aguhuice_ed25519` 是唯一凭据（密码认证已禁、root 已禁）。丢钥匙 = 只能走云控制台 VNC。请确认该私钥有可靠备份。

## 8. 本地（WSL）数据备份缺口 —— 与 ECS 备份纪律相关，必读

> 2026-10-27 QRE-DATA-CLEANUP-AUDIT 只读盘点发现，记在这里因为它直接决定「出事能不能恢复」。

- **ECS 侧有备份**：`/srv/aguhuice/backups/aguhuice-*.dump`（root cron 03:17 生成、留 7 天），本地 cron 04:23 经
  `deploy/saas/pull-ecs-backup.sh` 拉取到 `~/quant-workspace/backups/ecs-aguhuice/`（留 7 份）。
  **但这只是 aguhuice SaaS 用户小库，不是行情/因子主库。**
- **WSL 侧 `tushare_data`（513 GB，行情+因子主库）没有任何逻辑备份**——`~/quant-workspace/backups/` 下
  只有 ECS 的 dump，没有主库的 pg_dump。目前仅靠磁盘 + TimescaleDB 自身保护。
- **代价已经发生过一次**：`public.stock_daily_qfq_legacy`（2026-10-12 方案A 的回滚表）已被删除且无 dump 可恢复
  ⇒ qfq 回滚能力永久失去。详见 `20_DATA_DICTIONARY_DAILY_MINUTE.md` §2.1/§7.4。
- **待用户决定**：是否建立 `tushare_data` 定期 dump 策略（可仿 `pull-ecs-backup.sh` 做本地版；注意 513GB 全量
  dump 体积与 386G 可用磁盘的矛盾，可能需要按 schema 分批或只 dump 关键表）。
- 另有一项**低风险高收益**的例行运维待用户点头：`stock_minute_1m` 有 213 个早于 T-7 的 chunk 未压缩（140GB），
  重跑 `quant_ts/compress_minute_chunks.sh`（幂等）预计回收 ~139GB。见 20 §3.4。
