# 18 · Authing 身份层 + Flask 会员体系设计（QRE-AUTH-MEMBERSHIP）

> 2026-09-27 用户拍板：采用 Authing（身份认证）+ Flask（会员/权限数据层）组合；
> 积分制 vs 会员制的收费模式**搁置**，本阶段只做"用户资料 + 会员等级"入库与登录链路。
> 本文档是该子项目的单一权威设计文档；实施前读本文 + 15 号文档。

## 1. 目标 / 非目标

**目标**
- 登录方式从"内测邮箱+密码临时方案"切换为 Authing：手机号+短信验证码、微信扫码（后续公众号/小程序/App 复用同一用户池）
- 本地 PG（aguhuice 库）保留完整用户资料与会员数据（防供应商锁定的关键：Authing 只存身份凭证）
- 会员等级字段入库，配额按等级生效（沿用现有游客/会员/付费三级语义）

**非目标（本阶段不做）**
- 不做积分系统、不做支付、不做收费规则（模式未定）
- 不做公众号/小程序/App 端（身份池打通后后续直接接 SDK 即可）
- 不引入 Django/新框架（2026-09-27 已决策否决：现有 Flask 栈足够，Django admin 与 /saas/console 重复）

## 2. 架构

```
用户浏览器/未来多端
   │  Authing 登录组件（短信/扫码）
   ▼
Authing 用户池 ──签发 OIDC id_token/access_token──► 前端持有
   │                                                  │ Authorization: Bearer <authing token>
   │                                                  ▼
   │                                    ECS Flask（qre-saas）
   │                                    ① JWKS 公钥验签（缓存 jwks.json，无需每次回调 Authing）
   │                                    ② 取 sub（Authing userId）→ users.authing_id 查本地用户
   │                                    ③ 不存在则自动建档（首登即注册），下发/复用本地 session token
   │                                    ④ 配额/权限读本地 users.tier 等字段（现有逻辑不变）
   ▼
Authing 仅保存：手机号、微信身份、登录凭证
```

- **验签方式**：RS256 JWKS（`https://<用户池域名>.authing.cn/oidc/.well-known/jwks.json`），Flask 侧缓存公钥（内存 + 定时刷新），不引入重依赖——优先用 `PyJWT[crypto]` + requests，requirements 需确认 ECS 精简 venv 是否已有，没有则加这两条。
- **session 兼容**：验签通过后仍签发本地 `sessions` 表 token（现有前端 Bearer 逻辑零改动），Authing token 只在登录换票时出现一次。
- **首次登录自动建档**：authing_id 不在本地 → 插入 users 行（nickname 取 Authing 资料，手机号同步），tier 默认 member。

## 3. 数据模型（cloud_schema.sql 幂等追加）

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS authing_id TEXT;          -- Authing sub，唯一
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_authing ON users (authing_id) WHERE authing_id IS NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS member_since TIMESTAMPTZ; -- 成为会员时间（预留）
ALTER TABLE users ADD COLUMN IF NOT EXISTS member_expire_at TIMESTAMPTZ; -- 会员到期（预留，收费模式定后启用）
-- tier 字段已存在（member/paid），游客不落库（现有游客=无账号策略不变）
```

- 不建积分表、订单表（搁置项，06 日志记录决策）。

## 4. 存量账号迁移

- 现有内测账号（demo01、beta01、用户本人 gmail 账号等）保留 `email + password_hash` 字段不清空，作为**降级登录通道**（Authing 故障/欠费时兜底），但登录页默认只展示 Authing 入口。
- 迁移策略：不强制迁移。老用户用 Authing 手机号登录后若需关联旧账号，提供一次性"绑定旧账号"入口（输入旧邮箱+密码验证后写 authing_id）。内测期账号少，也可接受人工 SQL 关联。

## 5. 配置与密钥

- ECS `/etc/qre-saas.env` 新增：`AUTHING_APP_ID`、`AUTHING_APP_SECRET`、`AUTHING_HOST`（用户池域名）、`AUTHING_JWKS_URL`（可由 HOST 推导）。
- 密钥只进 env 文件（0600），不入库不入 git（同现有纪律）。
- staging 保留 `SAAS_AUTH_BYPASS` 供自动化测试，生产严禁。

## 6. 前端改动范围

- 登录页：~~接入 Authing Guard（Web SDK）或自建表单调 Authing API——倾向 Guard~~ **2026-09-27 实施改为 OIDC 授权码 + Authing 托管登录页跳转**（`/oidc/auth`，托管页自带短信/扫码 UI，与控制台配置的回调 URL 匹配，零前端 SDK 依赖）；邮箱密码折叠为降级次要入口。
- 其余页面零改动（Bearer token 机制不变）。
- 禁链纪律不变（Authing 域名是合法外链，不属于禁链范围）。

## 7. 阶段拆解（TODO）

- [x] A1 用户池开通（用户操作）：App ID/Secret、认证地址 xoba5deg87jk-demo.authing.cn 已交付，OIDC discovery/JWKS 可达
- [x] A2 数据模型迁移（cloud_schema.sql 幂等追加 users.authing_id 唯一索引/avatar_url/member_since/member_expire_at，aguhuice_local 已 apply 验证；ECS 待随部署 apply）
- [x] A3 后端：`GET /saas/login/authing`（302 + 内存 state 10min）→ `GET /saas/login/callback`（换票→JWKS 验签→建档→本地 session）；JSON 版 `POST /api/saas/auth/authing`；JWKS 内存缓存 1h + kid 未命中强制刷新；绑定旧账号 `POST /api/saas/auth/bind`。依赖新增 pyjwt[crypto]+requests（pyproject；ECS 精简 venv 已 pip install）
- [x] A4 登录页改造（login.html：Authing 主入口按钮 + 邮箱密码/绑定旧账号折叠次要入口；新增 login_callback.html 落 token 跳工作台）
- [x] A5 测试：tests/test_saas_authing.py +22（本地 RSA mock JWKS 验签正反例/kid 轮换刷新/首登建档/重复登录幂等/绑定四态/未配置 503/登录页元素）；全量 2207 passed + 4 skipped 零回归
- [x] A6 部署 + 实测手机号登录（2026-09-28 验收通过：commit 4fdae46 已部署；期间排掉三个 Authing 侧配置坑——回调白名单 redirect_uri_mismatch、应用访问授权「无权限登录此应用」、id_token 签名算法默认 HS256 需改 RS256。用户手机号建档成功并完成回测；手机号账号与 gmail 账号均已提为 admin，管理台经 SSH 隧道 localhost:9090/saas/console 验收）
- [ ] A7（可选）管理台用户 tab 展示 authing_id/手机号字段

## 8. 风险与开放问题

- **短信费用**：Authing 短信按量计费（以其官网为准），内测量小可忽略；免费额度/MAU 档位开通时确认。
- **微信扫码登录**要求在微信开放平台有网站应用（需企业主体认证——个人主体可能无法申请，A1 阶段验证；若不行则 Web 端先只开短信+账密）。
- **多租户隔离**：无（单用户池）。
- 收费模式（积分/会员）定稿前，`member_expire_at` 等字段只入库不生效。
