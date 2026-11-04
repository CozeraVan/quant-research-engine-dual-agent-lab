# 36 · 自建登录与会员系统（Casdoor 私有化）设计文档

- 日期：2026-11-04
- 状态：设计中 → 本地实施（§5 步骤 1–3 已完成，见 §7；**未触生产**，上线需用户单独批准）
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
| Authing | 仅 `authing.py` OIDC 换票验签 + 登录页跳转入口 | 被 Casdoor OIDC 平替 |

**结论**：QRE 的用户/会员/会话体系本来就是自建的，Authing 只是可拔插的 OIDC 入口。本次改造 = 把入口从 Authing 换到 Casdoor + 补齐密码登录 UI + QQ 登录。

## 3. 目标架构

```
浏览器
  ├─ 密码登录/注册 ────────────────► QRE /api/saas/auth/*（自建，现有）
  └─ QQ 登录 ─► Casdoor(8000) ─OIDC─► QRE /saas/login/callback（换 authing.py 为通用 OIDC 适配器）
                                        │
                                        ▼
                              业务库 users（sub→本地 user 映射）
                              tier_policies（会员/配额，业务侧权威）
Casdoor 只做：身份、凭证、第三方绑定、OIDC 签发。
QRE 只做：会员、配额、用量、业务数据。
```

### 可复用边界（未来项目）

- 新增 `src/quant_research_engine/gui/saas/oidc_client.py`：**通用 OIDC 适配器**（authorize URL / state / code 换 token / JWKS 验签），provider 由配置决定（`OIDC_ISSUER/CLIENT_ID/CLIENT_SECRET/REDIRECT_URI`）。
- `authing.py` 逻辑迁入该适配器；`AUTHING_*` 与 `CASDOOR_*` 都只是它的一组配置。
- 未来任何 Flask 项目复用 = 拷 `oidc_client.py` + 三个环境变量 + 一张 `users(external_sub)` 映射列。
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
2. 抽 `oidc_client.py` 通用适配器（Authing 逻辑平移，配置化）。
3. QRE 增加 Casdoor 登录入口（与 Authing 并存可切换，默认仍 Authing）。
4. 密码登录 UI 补齐（注册/登录/找回）。
5. QQ provider 配置与绑定合并逻辑。
6. staging 验证 + 老用户迁移脚本（草稿）。
7. **上线评审**：用户批准后才切生产、才改 ECS。

## 6. 验收标准

- 本地 Casdoor 可登录、可签发 OIDC。
- QRE 经 Casdoor OIDC 完成一次完整登录（staging），`users` 正确建档/映射。
- 密码注册→登录→退出→再登录全通过；找回密码走邮箱验证码。
- Authing 配置存在时行为不变（回归不破坏现有生产）。
- 新增适配层有测试；不改 `stock_daily`/行情库；不干扰在跑的 CF 全量队列。

## 7. 实施状态（2026-11-04，本地）

对应 §5 步骤：**1（本地）、2、3（登录入口）已完成**；4（密码登录 UI）、5（QQ 绑定合并）、6（staging + 迁移脚本）、7（上线评审）**未开始**。

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
- `users.authing_id` **保持原样**，Authing 存量路径不受影响。
- **provider 隔离语义**：同一自然人先 Authing 后 Casdoor 会得到两行 `users`，需人工关联（合并/绑定流程属 §5 步骤 5，未做）。
- 首次 Casdoor 登录：有 `phone` claim 且未与现有 `users.phone` 冲突则写入，冲突置 NULL（不夺占用）；`nickname`/`avatar_url` 走 COALESCE 增量更新；**不写 email**；新建 user 默认 `tier='member'`。
- 已存在身份但 `users.status != 'active'` → 抛 `OidcError("账号已被禁用，请联系运营方")`，回落 403。

### 7.4 路由与适配层

- `src/quant_research_engine/gui/saas/oidc_client.py`（新）：通用 OIDC 适配器 —— discovery 缓存、JWKS 取键、id_token RS256 验签（iss/aud/exp/nonce）、state 签名 + 一次性消费（`new_state`/`pop_state`）、`build_authorize_url`、`get_config`。Authing 逻辑已平移为配置驱动，行为逐字一致。
- `GET /saas/login/casdoor`：写 `session["casdoor_next"]` 后 302 到 authorize；未配置时返回 `503 {"ok":false,"error":…}`。
- `GET /saas/login/callback`（与 Authing **共用**）：先 `authing.pop_state`，未命中再试 `oidc_client.pop_state("casdoor")`，据 state 归属选 `authing_next`/`casdoor_next`；换票与建档按 provider 分流，异常分别映射 502/403。Authing 分支未改动。
- `GET /saas/login`：`casdoor_ready` 由 `oidc_client.get_config("casdoor")` 判定，仅就绪时渲染「使用 Casdoor 账号登录（自建认证）」ghost 按钮（`templates/login.html`）；生产未配 `CASDOOR_*` 时零变化，无灰色说明小字。
- 未新增 `/api/saas/auth/casdoor` JSON 端点（当前计划不需要）。

### 7.5 测试与真实端到端

- `tests/test_saas_oidc_client.py`：**8 passed**（验签/iss/aud/nonce/state 重放/discovery 等，假 RSA 密钥 + monkeypatch HTTP）。
- `tests/test_saas_casdoor.py`（新，18 例）：临时 PG 库 `qre_casdoor_test_<hex>` 跑 `cloud_schema.sql`、结束 DROP；覆盖授权跳转、首登建档、幂等、`/api/saas/me`、state 重放/伪造 400、未配置 503、坏签名/错 aud/错 iss 502、禁用 403、手机号冲突置空、provider 隔离、Casdoor state 不走 Authing 换票、登录页入口显隐 —— **18 passed**。
- Authing 回归：`tests/test_saas_authing.py` + `tests/test_saas_oidc_client.py` → **38 passed**。
- 真实 E2E（无 mock，本地 Casdoor + 临时 PG + `create_saas_app().test_client()`）：`/saas/login` 200 且含入口 → `/saas/login/casdoor?next=/saas/` 302 到 `127.0.0.1:8000` → 真实 `POST /api/login` 取 code → `callback` 200「登录成功」并内嵌 `saas_token` → `/api/saas/me` 200（`tier=member`、`role=user`、phone 来自 Casdoor admin 资料）。二次登录幂等，DB `users=1, identities=1`，`sub=31ee6f17-8731-4157-a20d-67843806c72f`。

### 7.6 已知缺口与风险

| 项 | 状态 |
|---|---|
| QQ 登录 | 仅配置位 + mock，**未真实端到端**（无 appid/secret，需 QQ 互联个人开发者审核） |
| 短信验证码 | 仍为占位实现，未接真实网关 |
| 密码注册/登录/找回 UI（§5 步骤 4） | 未做 |
| 老用户迁移脚本、staging 验证（§5 步骤 6） | 未做 |
| 生产 Casdoor（PG 独立库、TLS、备份纳入 pg_dump） | 未做 |
| redirect URI | 默认按 `8099`（本地 SaaS 端口），生产端口/域名待定 |
| `client_secret` | 明文，上线前轮换 |
| dockerd 代理 | 系统级 `/etc/systemd/system/docker.service.d/http-proxy.conf`，非仓库内容，需在部署文档声明 |

**边界**：本轮未部署 ECS、未改生产库、未重启任何 qre 服务（本机 CF 经典策略全量队列在跑）、未 commit / push；`stock_daily` 与 `worker/` 未触碰。
