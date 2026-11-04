# 36 · 自建登录与会员系统（Casdoor 私有化）设计文档

- 日期：2026-11-04
- 状态：设计中 → 本地实施（§5 步骤 1–3 已完成，见 §7；**Authing 已于 2026-11-04 完全移除**，见 §7.9；**未触生产**，上线需用户单独批准）
- 决策人：用户（2026-11-03 确认路线：手机号+密码为主、Casdoor 私有化、QQ 登录）
- 取代历史决策：18 号文档「登录/验证码/短信/微信正式版外购，不自建」（Authing 100+ 元/月不值）

## 1. 背景与目标

Authing 付费套餐 >100 元/月。转为自建：

1. 手机号/邮箱 + **密码**为主登录，短信/邮件验证码仅用于注册验证与找回密码（压低按量开销）。
2. 私有化部署 **Casdoor**（MIT，Go）作为独立认证服务，承载 OIDC 与第三方登录。
3. **会员/配额体系留在业务库**（QRE 已有 `users`/`tier_policies`/`sessions`），不搬进 Casdoor。
4. 接入 **QQ 登录**（个人开发者免费），微信暂缓（需组织主体 + 300 元/年）。
5. **可复用**：认证适配层做成与业务无关的独立模块，未来项目只改配置即可接入。

## 2. 现有资产盘点（审计结论）

| 资产 | 现状 | 复用方式 |
|---|---|---|
| `users` 表 | `phone/email/password_hash/tier/role/status` 齐全 | 直接沿用，不动结构 |
| 密码哈希 | PBKDF2-HMAC-SHA256 已实现（`_password_hash`/`_verify_password`） | 沿用 |
| 邮箱注册/登录 | `/api/saas/auth/register`、`/auth/login` 已支持密码 | 沿用 |
| 验证码 | `sms_codes` 表 + EmailSender 可用；**SmsSender 为占位未开通** | 邮箱通道先用，短信待签名资质 |
| sessions | PG Bearer token，30 天 | 沿用（前端零改动） |
| tier_policies | 每日全量限额/代码数/天数/因子数/watch 上限/扫描开关 | 沿用，会员逻辑不进 Casdoor |
| Authing | 已于 2026-11-04 完全移除（`authing.py`、`users.authing_id`、Authing 登录/回调/bind 路由、登录页入口） | 无，由 Casdoor OIDC + 自建手机号体系承接 |

**结论**：QRE 的用户/会员/会话体系本来就是自建的，Authing 只是可拔插的 OIDC 入口。本次改造 = 把入口从 Authing 换到 Casdoor + 补齐密码登录 UI + QQ 登录。

## 3. 目标架构

```
浏览器
  ├─ 密码登录/注册 ────────────────► QRE /api/saas/auth/*（自建，现有）
  └─ QQ 登录 ─► Casdoor(8000) ─OIDC─► QRE /saas/login/callback（通用 OIDC 适配器 oidc_client.py）
                                        │
                                        ▼
                              业务库 users（sub→本地 user 映射）
                              tier_policies（会员/配额，业务侧权威）
Casdoor 只做：身份、凭证、第三方绑定、OIDC 签发。
QRE 只做：会员、配额、用量、业务数据。
```

### 可复用边界（未来项目）

- 新增 `src/quant_research_engine/gui/saas/oidc_client.py`：**通用 OIDC 适配器**（authorize URL / state / code 换 token / JWKS 验签），provider 由配置决定（`OIDC_ISSUER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI`）。
- `oidc_client.py` 由配置驱动，`CASDOOR_*` 是当前唯一一组 provider 配置（原 Authing 适配分支已于 2026-11-04 删除）。
- 未来任何 Flask 项目复用 = 拷 `oidc_client.py` + 一组 `*_ISSUER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI` 环境变量 + 一张 `users` 映射（本仓库用 `auth_identities(provider, sub)`）。
- 会员/配额接口单独归一为 `membership.py`（读 tier_policies 的纯函数），业务无关部分与 QRE 解耦。

## 4. 关键约束与对策

| 约束 | 影响 | 对策 |
|---|---|---|
| **个人开发者难申请短信签名**（代码既有注释） | 手机号真实性验证可能办不下来 | 一期用**邮箱验证码**做注册验证与找回；手机号密码可登录但不强制验机。短信签名待个体工商户资质后再开 |
| 微信登录需组织主体 + 300 元/年 | 暂缓 | QQ 先行，微信留 provider 插槽 |
| Authing 密码哈希不可导出 | 老用户无本地密码 | 切换时引导老用户走一次「验证码→设密码」；不设双系统长期并行 |
| QQ 登录可能撞出孤儿账号 | 同一真人两个账号 | QQ 首登后强制引导绑定已有手机号/邮箱；命中即合并 |
| 手机号可枚举 → 撞库/扫号 | 密码登录面风险 | 登录失败锁定 + 限频（Casdoor 内置 + QRE 端点既有 guard） |
| Casdoor 运维 | 升级/备份 | 数据存现有 PG 独立库 `casdoor`，纳入每日 pg_dump；版本锁定 |

## 5. 实施步骤（本地 → staging → 生产需批准）

1. 本地 docker 起 Casdoor，PG 建 `casdoor` 库，跑通管理员登录。
2. 抽 `oidc_client.py` 通用适配器（provider 配置化；Authing 适配分支已于 2026-11-04 删除，仅保留 Casdoor）。
3. QRE 增加 Casdoor 登录入口（Authing 已于 2026-11-04 完全移除，Casdoor 为唯一 OIDC 入口；自建手机号登录为默认主入口）。
4. 密码登录 UI 补齐（注册/登录/找回）——后端已完成（2026-11-04，见 §7.7），UI 未做。
5. QQ provider 配置与绑定合并逻辑。
6. staging 验证 + 老用户迁移脚本（草稿）。
7. **上线评审**：用户批准后才切生产、才改 ECS。

## 6. 验收标准

- 本地 Casdoor 可登录、可签发 OIDC。
- QRE 经 Casdoor OIDC 完成一次完整登录（staging），`users` 正确建档/映射。
- 密码注册→登录→退出→再登录全通过；找回密码走邮箱验证码。
- Authing 移除后，Casdoor 与自建手机号/密码/短信登录全部回归通过。
- 新增适配层有测试；不改 `stock_daily`/行情库；不干扰在跑的 CF 全量队列。

## 7. 实施状态（2026-11-04，本地）

对应 §5 步骤：**1（本地）、2、3（登录入口）已完成**；4 的**后端已就绪（密码注册/登录/找回接口，见 §7.7）、UI 未做**；5（QQ 绑定合并）、6（staging + 迁移脚本）、7（上线评审）**未开始**。

### 7.1 本地 Casdoor 部署

| 项 | 值 |
|---|---|
| 容器 | `casdoor`，镜像 `casbin/casdoor:latest`，状态 `Up (healthy)`，端口 `8000`（仅本地） |
| 数据 | SQLite `/data/casdoor.db`，挂卷 `casdoor-data`；**生产规划改用现有 PG 独立库 `casdoor`，未做** |
| 配置 | `deploy/casdoor/app.conf`（`initAdminPassword="123"`、`defaultLanguage=zh`） |
| 管理员 | `admin` / `123`（**仅本地**，上线必须改） |
| 应用 | `app-qre`，client_id `qre-local`，org `built-in`，cert `cert-built-in`，redirectUris 含 `http://127.0.0.1:8099/saas/login/callback`、`http://localhost:8099/saas/login/callback` |

`client_secret` 目前以明文存在 Casdoor 与本地环境变量 `CASDOOR_CLIENT_SECRET` 中（一次性本地值），**上线前必须轮换并通过受管配置注入**。本地 dockerd 曾拉镜像失败，已加系统级 `/etc/systemd/system/docker.service.d/http-proxy.conf`（系统改动，不属于仓库内容）。

### 7.2 关键发现：authorize 是 SPA，不会 302 出 code

`GET /login/oauth/authorize` 是 Casdoor 前端的 React 路由，服务端对任何请求都返回 `index.html`，**不产生 Location 头、URL 里也没有 code**，`curl` 直连无法完成授权码流程。真实取 code 的方式是模拟前端提交：

```
POST /api/login?clientId=qre-local&redirectUri=<callback>&scope=openid profile phone email&state=<state>&responseType=code
Content-Type: application/json
{"application":"app-qre","organization":"built-in","username":"admin","password":"123","type":"code"}
→ {"status":"ok","data":"<code>"}
```

body 必须是 JSON；form-encoded 时 Casdoor 取不到用户、返回的 code 为空。自动化测试与 E2E 均按此路径取 code，不依赖浏览器。

### 7.3 数据模型：`auth_identities`

```sql
CREATE TABLE IF NOT EXISTS auth_identities (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    sub TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, sub)
);
```

- 映射键 `(provider, sub)`，`provider` 如 `casdoor`，`sub` 取自 id_token 的 `sub`。
- `users.authing_id` 与 `idx_users_authing` 已于 2026-11-04 从 `cloud_schema.sql` 移除（`DROP INDEX IF EXISTS` + `ALTER TABLE users DROP COLUMN IF EXISTS`）；生产存量列待运维 apply 后清理。
- **provider 隔离语义**：同一自然人经不同 provider（如未来 QQ）会得到两行 `users`，需人工关联（合并/绑定流程属 §5 步骤 5，未做）。
- 首次 Casdoor 登录：有 `phone` claim 且未与现有 `users.phone` 冲突则写入，冲突置 NULL（不夺占用）；`nickname`/`avatar_url` 走 COALESCE 增量更新；**不写 email**；新建 user 默认 `tier='member'`。
- 已存在身份但 `users.status != 'active'` → 抛 `OidcError("账号已被禁用，请联系运营方")`，回落 403。

### 7.4 路由与适配层

- `src/quant_research_engine/gui/saas/oidc_client.py`：通用 OIDC 适配器 —— discovery 缓存、JWKS 取键、id_token RS256 验签（iss/aud/exp/nonce）、state 签名 + 一次性消费（`new_state`/`pop_state`）、`build_authorize_url`、`get_config`。`get_config` 只接受 `casdoor`（Authing 分支已于 2026-11-04 删除）。
- `GET /saas/login/casdoor`：写 `session["casdoor_next"]` 后 302 到 authorize；未配置时返回 `503 {"ok":false,"error":…}`。
- `GET /saas/login/callback`（仅 Casdoor）：`pop_state(app, "casdoor", state)`，据 `casdoor_next` 回跳；换票与建档固定 `provider="casdoor"`，异常映射 502/403。Authing 状态键与分支已删除。
- `GET /saas/login`：`casdoor_ready` 由 `oidc_client.get_config("casdoor")` 判定，仅就绪时渲染「使用 Casdoor 账号登录（自建认证）」ghost 按钮（`templates/login.html`）；生产未配 `CASDOOR_*` 时零变化，无灰色说明小字。
- 未新增 `/api/saas/auth/casdoor` JSON 端点（当前计划不需要）。

### 7.5 测试与真实端到端

- `tests/test_saas_oidc_client.py`：**7 passed**（验签/iss/aud/nonce/state 重放/discovery 等，假 RSA 密钥 + monkeypatch HTTP；Authing 配置用例已随分支删除）。
- `tests/test_saas_casdoor.py`（新，18 例）：临时 PG 库 `qre_casdoor_test_<hex>` 跑 `cloud_schema.sql`、结束 DROP；覆盖授权跳转、首登建档、幂等、`/api/saas/me`、state 重放/伪造 400、未配置 503、坏签名/错 aud/错 iss 502、禁用 403、手机号冲突置空、provider 隔离、登录页入口显隐与「不含 Authing 路由」—— **18 passed**。
- Authing 回归测试随模块删除（`tests/test_saas_authing.py` 于 2026-11-04 移除）；Casdoor + OIDC 两文件合计 **25 例**，与同类登录/会员套件批量回归全绿。
- 真实 E2E（无 mock，本地 Casdoor + 临时 PG + `create_saas_app().test_client()`）：`/saas/login` 200 且含入口 → `/saas/login/casdoor?next=/saas/` 302 到 `127.0.0.1:8000` → 真实 `POST /api/login` 取 code → `callback` 200「登录成功」并内嵌 `saas_token` → `/api/saas/me` 200（`tier=member`、`role=user`、phone 来自 Casdoor admin 资料）。二次登录幂等，DB `users=1, identities=1`，`sub=31ee6f17-8731-4157-a20d-67843806c72f`。

### 7.6 已知缺口与风险

| 项 | 状态 |
|---|---|
| QQ 登录 | 仅配置位 + mock，**未真实端到端**（无 appid/secret，需 QQ 互联个人开发者审核） |
| 短信验证码 | 已接阿里云个人开发者短信通道并实测发码成功（`SmsSender`，见 `05_PROGRESS.md` 2026-11-04 条目）；生产 AK/SK 仅存 `/etc/qre-saas.env` |
| 密码注册/登录/找回 UI（§5 步骤 4） | **后端已完成，UI 未做**（接口契约见 §7.7） |
| 老用户迁移脚本、staging 验证（§5 步骤 6） | 未做 |
| 生产 Casdoor（PG 独立库、TLS、备份纳入 pg_dump） | 未做 |
| redirect URI | 默认按 `8099`（本地 SaaS 端口），生产端口/域名待定 |
| `client_secret` | 明文，上线前轮换 |
| dockerd 代理 | 系统级 `/etc/systemd/system/docker.service.d/http-proxy.conf`，非仓库内容，需在部署文档声明 |

### 7.7 密码通道与会员视图后端（2026-11-04，本地，UI 未做）

代码：`gui/saas/membership.py`（纯函数）、`gui/saas/app.py`、`deploy/saas/cloud_schema.sql`（`login_attempts`）。测试：`tests/test_saas_membership_auth.py` **19 passed**；按 §7.6 之外的相关回归 **338 passed**（`test_gui_saas` / `test_saas_casdoor` / `test_saas_agent_api` / `test_saas_access_hardening` / `test_no_silent_failure_patterns` / `test_saas_authing` / `test_gui_saas_console`）。

**UI 接口契约（字段名以本表为准）**

- `POST /api/saas/auth/reset`：请求 `{"phone": "<11 位中国大陆手机号>", "code": "<短信验证码>", "new_password": "<≥8 位含字母+数字>"}`；成功 `200 {"ok": true}`，**不返回 token，不自动登录**，该用户全部旧 token 立即 401。错误：400「请输入正确的手机号」/「缺少验证码」/「密码至少 8 位且需同时包含字母和数字」；404「该手机号未注册，请先注册」；401「验证码错误或已过期」（错码不消费）。
- `POST /api/saas/auth/login`：密码路径 `phone` 为主字段（`target`/`email` 仅为老 UI 别名，可省略），`code` 可省略（省略时取 `password`），即 UI 可直接提交 `{"phone": "...", "password": "..."}`。锁定：同 target 连续 5 次密码失败 → 之后 15 分钟内一律 `429 {"ok": false, "error": "密码错误次数过多，请 N 分钟后再试"}`；成功登录清零。验证码登录路径不受锁定影响。错误文案：格式错 400「请输入正确的手机号」、缺凭证 400「缺少验证码或密码」、密码错 401「手机号或密码错误」、验证码错 401「验证码错误或已过期」、禁用账号 403「账号已被禁用，请联系运营方」。
- `GET /api/saas/membership`（需登录）：`200 {"ok": true, "membership": {...}, "tiers": [...]}`；未登录 `401 {"ok": false, "error": "未登录"}`。
  - `membership`：`tier`、`tier_label`（`游客`/`内测会员`/`付费会员`）、`is_admin`、`daily_full{limit,used,remaining,unlimited}`、`watches{limit,used,remaining,unlimited}`、`scan_enabled`、`member_since`、`member_expire_at`。不限时 `limit="不限"`、`remaining=null`、`unlimited=true`（与 `/api/saas/me` 的 `quota_limit` 同口径）。
  - `tiers[]`：每项 `tier`、`label`、`daily_full_limit`、`max_codes`、`max_days`、`max_factor_fields`、`max_factor_tables`、`max_watches`、`scan_enabled`；顺序固定 `guest` → `member` → `paid`，数值实时读 `tier_policies`（不硬编码）。

**风险**：ECS 老库未 apply `login_attempts` DDL 时应用侧会幂等自愈，但若角色权限不足则降级为「不计数不锁定」；`_get_policy` 有 60s 缓存，管理台改权益后最多 1 分钟才在 membership 视图生效；锁定按 target 不按 IP，可被换账号绕过；`sms_codes.phone` 列名沿用，去邮箱化后存的就是手机号。

**边界**：本轮未部署 ECS、未改生产库、未重启任何 qre 服务（本机 CF 经典策略全量队列在跑）、未 commit / push；`stock_daily` 与 `worker/` 未触碰。

### 7.8 去邮箱化决策与四端点契约（2026-11-04，本地，UI 另行并行）

**决策**：SaaS 自建登录全面改为「中国大陆手机号 + 短信」，`POST /api/saas/auth/code`、`/register`、`/login`、`/reset` 只接受手机号，邮箱通道（SMTP / `EmailSender`）整体删除。背景：生产未配 `SAAS_SMTP_*`，邮箱验证码注册与找回密码在生产不可用；短信已走阿里云个人开发者通道（`SmsSender`），个人实名即可下发。

**代码变更（`src/quant_research_engine/gui/saas/app.py`）**

- 删除 `smtplib` / `EmailMessage` / `SMTP_TIMEOUT_SECONDS` / `EmailSender` 类；`_SENDERS = {"sms": SmsSender}`；`_get_sender` 默认 `sms`，`stub`→`StubSender`，`auto`→`sms`，未知值抛 `RuntimeError("未知 SAAS_AUTH_CHANNEL: …")`。
- 新增 `_MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")` 与 `_is_cn_mobile()`；`_consume_email_code` 更名 `_consume_sms_code`。
- 注册只写 `users (phone, password_hash, tier, last_login_at)`；验证码首登自动建档也只写 `phone`，`users.email` 不再作为自建登录标识，仅保留历史数据。
- `sms_codes.phone` 列名沿用，存手机号；`channel` 固定 `sms`。
- 2026-11-04 起 Authing 路径已不存在（`authing.py`、`/saas/login/authing`、`/api/saas/auth/authing`、`/api/saas/auth/bind`、登录页入口已删除，见 §7.9）；Casdoor 为唯一 OIDC 入口。`GET /api/saas/me` 仍返回 `email`（新用户可能为 `NULL`，UI 不应依赖）。

**四端点契约（字段名以此为准）**

| 端点 | 请求 | 成功 | 失败 |
|---|---|---|---|
| `POST /api/saas/auth/code` | `{"target"}`（兼容 `{"phone"}`），11 位 `1[3-9]…` | `200 {"ok": true, "channel": "sms", "expires_in": 300}`；`SAAS_STUB_ECHO=1` 时另含 `dev_code` | 400「请输入正确的手机号」；429「发送过于频繁，请稍后再试」（target 60s / IP 窗口限流）；502 短信发送失败（含通道错误文案） |
| `POST /api/saas/auth/register` | `{"phone", "code", "password"}`（`target`/`email` 为兼容别名） | `200 {"ok": true, "token": "...", "user": {"id", "phone", "quota_daily", "tier"}}` | 400「请输入正确的手机号」/「密码至少 8 位且需同时包含字母和数字」/「缺少验证码」；409「该手机号已注册，请直接登录」（先于验证码校验）；401「验证码错误或已过期」 |
| `POST /api/saas/auth/login` | `{"phone", "code"}` 或 `{"phone", "password"}`（`target`/`email`、`code`/`password` 别名兼容） | `200 {"ok": true, "token": "...", "user": {"id", "phone", "quota_daily", "status"}}` | 400「请输入正确的手机号」/「缺少验证码或密码」；401「验证码错误或已过期」/「手机号或密码错误」；429「密码错误次数过多，请 N 分钟后再试」；403「账号已被禁用，请联系运营方」（仅已存在账号） |
| `POST /api/saas/auth/reset` | `{"phone", "code", "new_password"}` | `200 {"ok": true}`，吊销该用户全部旧 session，不自动登录 | 400「请输入正确的手机号」/「缺少验证码」/密码规则文案；404「该手机号未注册，请先注册」；401「验证码错误或已过期」 |

**登录语义细节**：手机号存在且有 `password_hash` → 密码路径（含 5 次失败锁 15 分钟）；否则按短信验证码校验。手机号不存在时验证码正确会自动建档；密码登录一个未注册手机号只会得到 401「验证码错误或已过期」（无 hash 即视为验证码路径）。内置测试账号改为 `SAAS_TEST_ACCOUNT_PHONE`（兼容旧 env 名 `SAAS_TEST_ACCOUNT_EMAIL`，值必须是合法手机号才生效）。

**测试**：`tests/test_saas_sms_sender.py`（4 例重写：auto→sms / 默认 sms / stub 优先 / 未知通道抛错）、`test_gui_saas.py`、`test_saas_membership_auth.py`、`test_gui_saas_console.py` 合计 **133 passed**；`test_gui_saas_pages.py`、`test_saas_casdoor.py`、`test_no_silent_failure_patterns.py` 合计 **163 passed**（原同批的 `test_saas_authing.py` 已于 2026-11-04 随 Authing 移除删除）；补充回归 `test_saas_agent_api.py` **79 passed**，`test_saas_access_hardening.py` / `test_saas_public_beta_ops.py` / `test_saas_first_success_ux.py` / `test_saas_oidc_client.py` 合计 **117 passed**。

**剩余风险（Authing 移除后）**：生产库 `users.authing_id` 列与 `idx_users_authing`、ECS `/etc/qre-saas.env` 的 `AUTHING_*` 需运维按本文件 schema 清理（本仓库 `cloud_schema.sql` 已改为幂等 DROP）；外部调用方若仍请求 `/api/saas/auth/bind` 将得到 404，老 Authing 用户须改用手机号 + 短信验证码登录/找回（依赖 `users.phone` 数据质量与阿里云短信通道）；`users.email` 列与历史数据保留且 `/api/saas/me` 仍返回（可能 `NULL`）；QQ 登录仍未真实接入。本轮未部署、未 commit。

### 7.9 Authing 完全移除（2026-11-04，本地，未部署/未 commit）

**决策**：Authing 不再作为任何入口或兜底；身份权威只有两套——自建手机号 + 密码/短信（业务库直接签发 session），以及 Casdoor OIDC（`auth_identities(provider, sub)` 映射到 `users`）。会员/配额仍以 `users`/`tier_policies` 为唯一权威。

**删除项（用户点名）**

| 项 | 处置 |
|---|---|
| `src/quant_research_engine/gui/saas/authing.py` | 删除 |
| `tests/test_saas_authing.py` | 删除（含 bind 老账号用例） |
| `GET /saas/login/authing` | 删除 |
| `POST /api/saas/auth/authing` | 删除 |
| `POST /api/saas/auth/bind` | 删除，**不提供替代端点**；老用户改走手机号 + 短信登录/找回（按 `users.phone` 匹配，与 `authing_id` 无关） |
| `users.authing_id` / `idx_users_authing` | `cloud_schema.sql` 改为 `DROP INDEX IF EXISTS idx_users_authing;` + `ALTER TABLE users DROP COLUMN IF EXISTS authing_id;`（新旧库幂等；**生产存量列待运维 apply**） |
| 登录页 Authing 链接 / `.auth-authing` 样式 | 删除（`templates/login.html`、`static/account.css`） |

**改动项**：`gui/saas/app.py` 登录页上下文只保留 `oidc_client`；删 `_user_from_authing_claims`；callback 固定 `provider="casdoor"`（`pop_state(app,"casdoor",state)`、`casdoor_next`、`exchange_code(app,"casdoor",code)`、`_user_from_oidc_claims(conn,"casdoor",claims)`）；`gui/saas/oidc_client.py` 的 `get_config` 只接受 `casdoor`。测试同步：`test_saas_oidc_client.py` 7 例、`test_saas_casdoor.py` 18 例、`test_gui_saas_pages.py` 断言登录页含 Casdoor 入口且不含 `/saas/login/authing`。

**验证**：`uv run pytest tests/test_saas_casdoor.py tests/test_saas_oidc_client.py tests/test_gui_saas_pages.py -q` → **119 passed**；`tests/test_saas_signals.py tests/test_saas_worker_status.py` → **36 passed**；关键字批量（auth/login/membership/sms/casdoor/console/register/template_inline_js/silent_failure）→ **224 passed, 11 skipped**，另有 2 个 teardown error 为这两个文件共用临时库 `DROP DATABASE … WITH (FORCE)` 的竞争，测试本体通过、单跑全绿，非本次改动。全量数值见 `05_PROGRESS.md` 同日条目。

**未做 / 后续**：生产 ECS 部署与库列/env 清理、老 Authing 用户迁移通知、QQ 真实端到端、staging 验证；本轮未重启任何 qre 服务、未 commit / push。
