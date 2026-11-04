# 37 · Windows UI Agent 任务书：自建登录与会员中心 UI

- 日期：2026-11-04
- 分派方：主 Agent（Kimi，WSL）；执行方：Windows UI Agent
- 前置：Casdoor 私有化接入已完成并提交（`oidc_client.py`、`auth_identities` 表、`/saas/login/casdoor` 入口）
- 性质：**纯 UI/UX 任务**，不改任何 Python 后端、不部署、不 commit/push

## 0. 工作边界（与 33 号指南一致）

### 0.1 路径：读 Windows 本地工作树，不要跨 WSL

本任务书里的路径一律是**仓库相对路径**。你（Windows UI Agent）的工作根是
**`D:\workzone\webui`**，映射关系：

| 任务书相对路径 | 你实际读写的 Windows 路径 |
|---|---|
| `src/quant_research_engine/gui/saas/templates/` | `D:\workzone\webui\src\quant_research_engine\gui\saas\templates\` |
| `src/quant_research_engine/gui/static/` | `D:\workzone\webui\src\quant_research_engine\gui\static\` |
| `scripts/win/` | `D:\workzone\webui\scripts\win\` |

- **不要**用 `\\wsl$\Ubuntu-24.04\...` 或 `\\wsl.localhost\...` 去读 WSL 那份项目做开发——跨系统读写慢，且 WSL 里的符号链接（如 `outputs`）在 Windows 下会显示成文件、点不进去。
- `\\wsl$` 只用于偶尔取主 Agent 生成的数据文件（例如 demo CSV），不是开发工作区。
- WSL 与 Windows 是**同一份仓库的两个工作树**，文件不会自动同步，只能靠 git。

### 0.2 两个工作树如何同步（改动必须能被主 Agent 看到）

- 你在 `D:\workzone\webui` 的改动如果只留在工作树，WSL 侧的主 Agent **看不到**，无法复核。
- 因此交付时：在 `ui/<topic>` 功能分支上 commit 并 push（例如 `ui/auth-pages`），**不要直接 push master**——master 的合并与最终提交归主 Agent。
- 主 Agent 在 WSL `git fetch` 后拉你的分支复核 → 合入 master → 统一部署 ECS。
- 若暂时不能 push，就把改动文件清单 + 截图路径报给用户转交，主 Agent 会另行取件；不要默认"留在工作树"就算交付。

### 0.3 可动范围

| 你可以动 | 不要动 |
|---|---|
| `src/quant_research_engine/gui/saas/templates/` | 任何 `*.py`（后端逻辑） |
| `src/quant_research_engine/gui/static/`（CSS/JS/图标） | `worker/`、`deploy/`、数据库 |
| 本地预览与截图 | 生产 ECS、master 分支提交 |

预览：`scripts/win/start-ui-preview.ps1` → http://127.0.0.1:8091/saas/（8091 固定，8080/8081 被 WSL 占用）。
验收：`uv run python scripts/win/ui-smoke.py`，桌面 1280×900 + 移动 375×812，零 JS error、零横向溢出。

## 1. 背景：登录从 Authing 切换到自建

之前登录只有「手机验证码（Authing 托管）」。现在改为自建：

- **主登录方式 = 账号（手机号或邮箱）+ 密码**
- 验证码只用于「注册验证」和「忘记密码」两个低频场景
- QQ 登录按钮（预留，后端 Casdoor 已支持）
- 会员体系 = 自建 `users.tier` + `tier_policies`，需要在个人中心可见

## 2. 后端接口（已存在，直接用，不要新造）

| 用途 | 接口 | 关键字段 |
|---|---|---|
| 发验证码 | `POST /api/saas/auth/code` | `{target}`（邮箱或手机号，含 @ 自动走邮箱） |
| 注册 | `POST /api/saas/auth/register` | `{email, password, code}` |
| 登录 | `POST /api/saas/auth/login` | `{target, code}` 或 `{email, password}` |
| 密码规则 | — | ≥8 位，须同时含字母和数字 |
| Casdoor/QQ 入口 | `GET /saas/login/casdoor` | 页面已有 `casdoor_ready` 开关 |

**若发现接口字段对不上，不要改后端，把需求列成清单反馈主 Agent。**

## 3. 具体 UI 任务

### T1 登录页改版（`templates/login.html`）
- 主表单：账号输入框（占位「手机号或邮箱」）+ 密码框（带显示/隐藏眼睛图标）+「登录」主按钮
- 次操作行：「注册账号」「忘记密码」两个文字链接
- 分隔线「其他登录方式」下方：QQ 图标按钮（ghost 样式，点击跳 `/saas/login/casdoor`）
- 保留现有验证码登录作为次要入口（折叠或 tab 切换），不要删
- 错误提示统一表单下方红字（密码错误/账号不存在/验证码过期）

### T2 注册页（新模板 `templates/register.html` 或登录页内弹层）
- 邮箱 + 邮箱验证码（带 60s 倒计时重发）+ 设置密码 + 确认密码
- 密码强度即时提示（弱/中/强），两次密码不一致即时标红
- 手机号字段可选填（占位「选填，用于接收信号通知」）
- 「注册即同意《服务条款》《隐私政策》」勾选，链到现有说明页

### T3 忘记密码（新模板或弹层）
- 三步流程：输入邮箱 → 邮箱验证码 → 设新密码 → 完成跳登录
- 每步独立卡片，顶部步骤指示器（1/2/3）

### T4 个人中心会员区（`templates/profile.html`）
- 顶部账号卡：头像、昵称、手机号/邮箱、注册时间
- **会员等级卡**：当前 tier（如「内测会员」）、每日全量回测配额与今日已用、策略跟踪数上限
- 第三方账号绑定区：QQ 绑定/解绑按钮（预留，未配置时禁用并 tooltip「即将开放」）
- 账号安全区：修改密码入口（跳 T3 流程）、登录设备/会话管理（可选）

### T5 会员权益说明（可并入 profile 或独立区块）
- 用表格展示各 tier 的权益对比（每日回测次数、回测股票数上限、回测年限、因子数、策略跟踪数）
- 当前免费/内测期全部标识「内测期间免费开放」，**不做任何支付/购买按钮**

## 4. 风格契约（必须遵守）

- 白底磨砂玻璃卡：`backdrop-filter: blur(28px) saturate(140%)`，白色 45–60% 透明度，1px 半透明白描边，顶部细高光，圆角 24px，大而柔的紫色阴影
- 数据小 div 统一白底紫框；有盈亏属性的数字才用红涨绿跌，登录/会员页一般不用
- 字号与间距按最近一轮 UI 规范（大字号、宽间距），夜间模式按钮不显示
- 中文不斜体；图标用内联 SVG，不用 emoji/彩色方块图标

## 5. 交付与验收

1. 改动在 `ui/auth-pages` 功能分支 commit 并 push（**不直接 push master**；master 合并归主 Agent）。无法 push 时按 §0.2 报文件清单 + 截图路径
2. `ui-smoke.py` 全绿 + 新增页面（登录/注册/找回/个人中心）双视口截图到 `.tmp/ui-review/`
3. 完成后通知主 Agent：改动文件清单 + 截图路径 + 任何需要后端配合的接口清单
4. 主 Agent 复核 → 统一部署 ECS（UI Agent 不接触生产）
