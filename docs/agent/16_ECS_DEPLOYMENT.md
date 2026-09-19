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

代码侧（家里 WSL，部署备用）：SaaS app（gui/saas/：验证码登录/任务队列/worker 协议/四页前端）、
worker 包（client/runner/daemon）、Docker 沙箱、流式批量回测均已实现并测试（见 05 逐条）。

## 4. 后续步骤

主线顺序见 `15_SAAS_SYSTEMS_DESIGN.md` 第 7 节 TODO（阶段 A–E；全链路优先，登录/管理最后）。
ECS 侧专属待办（隶属阶段 C）：

- [x] 装 Python/Flask + PG 用户小库（C1 完成；PG 2G 参数调优暂未做，内测量级先观察）
- [ ] Nginx IP 限流（如 10 req/min/IP；C2 待办，反代本身已完成）
- [ ] 禁 root 直连（PasswordAuthentication/PermitRootLogin 关闭，仅用 deploy 用户）
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
```

## 6. 纪律

- ECS 不落行情/因子明细（数据不出家门）；
- 一切线上文件改动先在仓库 `deploy/` 下留版本再同步；
- 8080 管理台永远留在本地，不随 SaaS 上线。
