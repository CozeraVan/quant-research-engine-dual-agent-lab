# 45_WINDOWS_UI_GAME_SEPARATION_2026-11-11.md — UI 与《我不是股神》Windows 分离（方案 A）

> **用户裁定（2026-11-11）**：采用**方案 A（同仓库、分目录、分分支）**——
> 把当前项目的 UI 与《我不是股神》都放到 **Windows 系统下开发**；
> **WSL 只保留核心功能开发，保持环境干净整洁**。
> 本文件是两侧唯一的目录归属与协作契约，与 `43_GAME_WINDOWS_DEV_2026-11-11.md` 配套。

## 1. 目录归属（权威，按此表执行，不许越界）

### Windows 拥有（UI / 游戏）

| 路径 | 内容 | 备注 |
|---|---|---|
| `src/quant_research_engine/gui/saas/templates/` | 公网 SaaS 全部 21 个模板 | 结果页/个人中心/登录/新建/展示等 |
| `src/quant_research_engine/gui/templates/` | 8081 lab 的 12 个模板 | 旧 lab 界面 |
| `src/quant_research_engine/game/templates/` | 游戏模板 | 《我不是股神》 |
| `src/quant_research_engine/game/`（全部 .py + templates） | 游戏逻辑与路由 | 分离后 Windows 也负责游戏逻辑，不只是 UI |
| `src/quant_research_engine/gui/static/` | 34 个静态文件（CSS/JS/图标） | 含 `lab-theme.css`、`card-class.css`、`factor-layout.js`、`replay.js`、`price-scale.js`、`risk-stress.js`、`kline-order-markers.js` 等 |
| `scripts/win/` | Windows 预览/验收脚本 | `start-ui-preview.ps1`、`ui-smoke.py` 等 |

### WSL / 主 Agent 拥有（核心功能）

| 路径 | 内容 |
|---|---|
| `src/quant_research_engine/worker/` | 回测 worker、槽位、容量、回传 |
| `src/quant_research_engine/data/` | 数据装载、复权、宇宙规则 |
| `src/quant_research_engine/portfolio/` | 回测与组合计算 |
| `src/quant_research_engine/strategies/` | 策略规格与结构策略 |
| `src/quant_research_engine/orchestration/` | 研究编排 |
| `src/quant_research_engine/security/` | YAML 安全 |
| `src/quant_research_engine/apps/` | CLI |
| `src/quant_research_engine/gui/**/*.py` | **后端逻辑**：`engine.py`、`app.py`、`lab.py`、`lab_result.py`、`nl_compiler.py`、`saas/app.py`、`saas/*.py` 等 |
| `deploy/`、`scripts/`（除 `scripts/win/`） | 部署与运维 |
| `tests/` | 全部测试（Windows 侧可新增 UI 测试，但需与主 Agent 对齐） |

**关键边界**：`gui/` 下的 **`.py` 是后端（WSL），`templates/` 与 `static/` 是 UI（Windows）**。
`gui/saas/app.py` 虽在 saas 目录，但它是**后端 API/路由**，归 WSL；只有 `saas/templates/` 归 Windows。

## 2. 分离准确性核查结论（2026-11-11 实测）

- 模板三处目录完全独立：`gui/saas/templates`（21）、`gui/templates`（12）、`game/templates`（1）——**没有交叉引用到后端目录**。
- 静态资源集中在 `gui/static/`（34 个文件），**没有散落在别处的 CSS/JS**。
- 游戏逻辑在 `src/quant_research_engine/game/` 子包，**不与回测引擎混写**；游戏测试独立在 `tests/test_trading_game_*.py`。
- 唯一需要小心的混合点：`gui/saas/app.py` 同时承载「API + 页面路由」，
  **Windows 侧改模板即可，不要改 app.py**；若必须新增/改路由，写清需求交给主 Agent。

## 3. 分支与提交流程

- UI 工作：`ui/<topic>` 分支（如 `ui/auth-pages`、`ui/profile-center`）
- 游戏工作：`game/windows-dev` 分支
- **Windows 侧不直接动 master、不 push master**；最终提交与推送由主 Agent 统一执行
- 回传格式：分支名 + commit + 改动文件清单 + Playwright 验收输出 + 截图路径
- 主 Agent 复核 → 必要时部署 ECS → 用户验收 → 提交/推送

## 4. WSL 干净规则（保持核心环境整洁）

1. Windows 侧所有临时稿、截图、试验页面一律留在 Windows（`.tmp/ui-review/`），**不要同步回 WSL**
2. WSL 仓库只允许出现：核心代码、文档、部署与测试；**不留 UI 草稿/截图/视频素材**
3. `.tmp/` 为 scratch 且不入库；任何「被文档引用的证据文件」落盘后才许引用
4. 不在 WSL 做 UI 视觉验收（那是 Windows 的职责），主 Agent 只做代码复核与部署

## 5. Windows 侧验收命令

```powershell
# 起预览（默认 8091，SAAS_AUTH_BYPASS=1 仅本地）
.\scripts\win\start-ui-preview.ps1

# 验收（桌面 1280×900 + 移动 375×812，零 pageerror/console error/横向溢出）
uv run python scripts/win/ui-smoke.py --base http://127.0.0.1:8091 --paths /saas/,/saas/new,/saas/showcase,/game
```

## 6. 数据与口径约束（不变）

- 因子库后复权（`raw × adj_factor`），K 线前复权锚点；价格型因子按 `factor_basis` 契约换算
- Windows 预览用 `qre_ui_dev` 预览库或本地样本快照，**不直连生产行情库**
- 游戏不做全市场回测；UI 不改回测语义

## 7. 当前状态

- 已按方案 A 完成目录归属划分与核查；**代码未物理搬离仓库**（方案 A 本就不需要搬离）
- Windows 侧已有 UI 工作流（ui-preview/ui-verify/ui-style）；游戏侧待 Windows agent 按 43 号文档接入
- 下一步：Windows agent 在 `game/windows-dev` 跑通 `/game` 预览并回传验收
