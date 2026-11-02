# Windows UIUX Agent 工作指南（QRE / A股回测台）

> 适用对象：在 **Windows** 上负责 UI/UX 设计与实现的 agent。
> 目标：在 Windows 完成 UI 开发、即时预览和浏览器验收；WSL 继续负责引擎、数据库、后端 API、测试与 ECS 部署。
> **不要修改后端业务逻辑，不要部署生产环境。**

---

## 1. 工作边界（必须遵守）

### 你可以做
- 修改 SaaS/lab 的 **HTML 模板、CSS、前端 JS、图表与交互**。
- 在 Windows 启动 UI 预览实例，调试布局、配色、字号、间距、卡片、K 线与指标展示。
- 用 Playwright 做浏览器验证、截图和交互回归。
- 提交 UI 相关测试（静态断言或浏览器断言）。

### 你不可以做
- **不修改引擎、worker、回测计算、数据库结构、NL 编译器、权限/配额逻辑。**
- 不修改 `src/quant_research_engine/gui/saas/app.py` 的 API 行为（如确需改字段，先通知主 Agent 写 CR）。
- 不连接生产数据库、不使用生产 token、不跑全量回测。
- 不部署 ECS、不重启 worker、不执行 `git push` 到 `master`（除非主 Agent 明确授权）。
- 不新增「灰色小字备注」；解释统一使用 `tip-trigger` + `data-tip`。
- 不随意新增色板、字体、UI 框架或构建链。

---

## 2. 项目拉取（Windows PowerShell）

```powershell
# 1) 克隆项目
git clone git@github.com:CozeraVan/quant-research-engine-dual-agent-lab.git
cd quant-research-engine-dual-agent-lab

# 2) 避免 Windows 换行符干扰
git config core.autocrlf false

# 3) 查看当前基线
git log --oneline -5
git status --short
```

**不要**通过 `\\wsl.localhost\...` 共享目录开发。Windows 使用独立 clone，WSL 通过 Git 同步。

---

## 3. UI 预览环境搭建

### 3.1 安装运行依赖

任选一种：

**方式 A：使用 uv（推荐，与 WSL 一致）**

```powershell
# 若未安装 uv
pip install uv
uv sync
```

**方式 B：使用 venv**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

### 3.2 准备预览数据库（二选一）

#### 方案 A：Windows 本地 Docker PostgreSQL（自包含，推荐）

```powershell
# 需要 Docker Desktop
docker run --name qre-ui-pg `
  -e POSTGRES_PASSWORD=ui_dev_pwd `
  -p 15432:5432 `
  -d postgres:16

# 创建预览库并导入 SaaS schema
docker cp deploy/saas/cloud_schema.sql qre-ui-pg:/tmp/
docker exec qre-ui-pg psql -U postgres -c "CREATE DATABASE qre_ui_dev"
docker exec qre-ui-pg psql -U postgres -d qre_ui_dev -f /tmp/cloud_schema.sql
```

预览连接串：

```text
postgresql+psycopg://postgres:ui_dev_pwd@127.0.0.1:15432/qre_ui_dev
```

#### 方案 B：使用 WSL 提供的预览库

请主 Agent 提供：WSL 主机/IP、只读账号、预览库名。然后在 Windows 建隧道：

```powershell
ssh -L 15432:127.0.0.1:5432 van@<WSL_IP>
```

连接串：

```text
postgresql+psycopg://<只读账号>:<密码>@127.0.0.1:15432/<预览库名>
```

### 3.3 启动 UI 预览实例

在仓库根目录执行：

```powershell
$env:SAAS_DB_URL="postgresql+psycopg://postgres:ui_dev_pwd@127.0.0.1:15432/qre_ui_dev"
$env:SAAS_UPLOAD_DIR=".tmp/ui-dev-uploads"
$env:QRE_TEMPLATE_AUTORELOAD="1"
$env:SAAS_DEV_AUTH="1"
$env:SAAS_WORKER_TOKEN="ui-dev-token"
$env:SAAS_AUTH_CHANNEL="stub"
uv run qre saas --host 127.0.0.1 --port 8081
```

打开：

```text
http://127.0.0.1:8081/saas/
```

- `QRE_TEMPLATE_AUTORELOAD=1`：改 HTML 保存即生效；
- JS/CSS 改动刷新浏览器即可；
- 预览库和上传目录都只在 Windows 本地，**不要指向生产**。

---

## 4. UIUX 文件地图

### 4.1 SaaS 页面模板

目录：`src/quant_research_engine/gui/saas/templates/`

| 文件 | 页面/职责 |
|---|---|
| `base.html` | 全站基础布局、导航、公共脚本、主题切换 |
| `new.html` | 新建策略、三个回测入口、参数面板 |
| `job.html` | 策略回测详情（收益、FRM、热力图、风险、回放） |
| `symbol.html` | 个股回测详情（K 线、买卖点、因子、下载详情） |
| `symbols.html` | 个股明细列表 |
| `profile.html` + `_records_body.html` + `_records_scripts.html` | 个人信息、我的策略库、回测记录、分享 |
| `showcase.html` | 经典策略展示 |
| `strategy.html` | 策略详情与信号监控 |
| `console.html` | 9090 管理后台 |
| `help.html` | 使用说明与侧边导航 |
| `login.html` / `login_callback.html` | 登录与回调 |
| `signals.html` | 信号中心 |
| `feedback.html` / `factor_request.html` | 反馈与因子申请 |

### 4.2 静态资源（JS/CSS）

目录：`src/quant_research_engine/gui/static/`

| 文件 | 职责 |
|---|---|
| `lab-theme.css` | 全站主题与组件样式 |
| `card-class.css` | 小数据卡片、磨砂玻璃、卡片族 |
| `night-mode.css` / `night-mode.js` | 夜间模式（当前整体暂停，勿擅自启用） |
| `lab-ui.js` | 通用 UI 工具与格式化 |
| `replay.js` | K 线重播 |
| `factor-layout.js` | 因子面板布局（overlap/独立副图） |
| `vol-regime.js` | 波动率状态与时序曲线 |
| `kline-core.js` / `kline-*.js` | K 线相关实现 |

### 4.3 另一套 lab 页面

目录：`src/quant_research_engine/gui/templates/`
- `lab_result.html`：lab 版回测结果页。

### 4.4 游戏页面（如非任务需要不要动）
- `src/quant_research_engine/game/templates/game.html`

---

## 5. UI 开发规范（必须遵守）

1. **不新增灰色小字备注**
   - 说明统一用 `tip-trigger` + `data-tip`；
   - 不新增 `.opt`、muted/faint 解释性长段落。
2. **风格保持一致**
   - 淡紫品牌色、红涨绿跌、白底磨砂玻璃数据卡；
   - 卡片圆角/阴影/间距沿用 `card-class.css` 与 `lab-theme.css`；
   - 不引入第四色相或另一套 UI 框架。
3. **K 线与指标**
   - EMA/MA/BOLL 等价格型指标可 overlap 在 K 线上；
   - MACD/RSI 等独立指标放独立副图；
   - 同族多曲线（DIF/DEA）必须在同一坐标系，hist 为柱状；
   - 不要机械地把所有指标拆成独立窗口。
4. **复权与数据口径**
   - 不在前端私自换算价格或收益；
   - 不显示「新旧口径」按钮/说明；
   - 异常大数按「—」或原因展示，不能科学计数法爆表。
5. **可读性与响应式**
   - 桌面与 375px 窄屏都不能横向溢出；
   - 按钮、卡片、表格在窄屏可折叠/换行；
   - 不随意缩小字号或行距（`line-height` 基线冻结）。
6. **权限与只读**
   - 游客/分享/showcase 只读页面不能出现写操作按钮；
   - 分享链接、下载详情、删除操作等必须与既有权限语义一致。

---

## 6. 验证要求（交付前必须做）

### 6.1 静态/后端回归

在仓库根目录：

```powershell
$env:SAAS_UPLOAD_DIR=".tmp/test-uploads-isolated"
uv run pytest -q -p no:randomly
```

如只改 UI，可至少跑相关测试文件；**不要跳过全量回归而不说明**。

### 6.2 浏览器验证

安装 Playwright：

```powershell
pip install playwright
playwright install chromium
```

检查：
- 页面 HTTP 200；
- 无 `pageerror`、无 console error；
- 1280px 与 375px 均无横向溢出；
- 关键交互可用（按钮、折叠、切换、K 线、指标、下载详情、删除等）；
- 保存截图到 `.tmp/ui-review/`。

### 6.3 交付物

完成后提供：
1. 改动文件清单；
2. 页面/交互说明；
3. 测试命令与结果；
4. 桌面与窄屏截图；
5. 已知遗留或需要主 Agent 协助的后端事项。

然后通知主 Agent（Kimi）做集成验收与部署。**不要自行部署 ECS。**

---

## 7. 快速命令清单

```powershell
# 拉最新代码
git pull

# 启动预览
$env:SAAS_DB_URL="postgresql+psycopg://postgres:ui_dev_pwd@127.0.0.1:15432/qre_ui_dev"
$env:SAAS_UPLOAD_DIR=".tmp/ui-dev-uploads"
$env:QRE_TEMPLATE_AUTORELOAD="1"
$env:SAAS_DEV_AUTH="1"
$env:SAAS_WORKER_TOKEN="ui-dev-token"
$env:SAAS_AUTH_CHANNEL="stub"
uv run qre saas --host 127.0.0.1 --port 8081

# 跑测试
$env:SAAS_UPLOAD_DIR=".tmp/test-uploads-isolated"
uv run pytest -q -p no:randomly

# 提交前自查（不要直接 push master，等主 Agent 验收）
git status --short
git diff --stat
```

---

## 8. 一句话工作方式

**Windows 负责「看得见的 UI」，WSL 负责「算得准的内核」。**
你只在 Windows 改模板/CSS/JS 并做浏览器验收；后端、数据库、部署由 WSL 主 Agent 统一处理。
