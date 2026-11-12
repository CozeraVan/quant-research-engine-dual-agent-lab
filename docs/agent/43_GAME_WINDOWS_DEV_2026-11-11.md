# 43_GAME_WINDOWS_DEV_2026-11-11.md — 《我不是股神》Windows 开发交接

> **用户裁定（2026-11-11）**：把《我不是股神》游戏项目从 WSL 分离到 **Windows 系统下开发**。
> 原因与 UI 分工一致：WSL 不适合即时试玩与视觉验收；Windows 侧已有浏览器、Playwright 与预览环境。

## 1. 分工边界（与现有 UI 分工同构）

| 侧 | 负责 | 不负责 |
|---|---|---|
| **Windows（游戏开发）** | 游戏 UI、交互、视觉、动效、试玩与截图验收 | 回测内核、行情/因子库、生产部署、git 主分支 |
| **WSL / Linux（主 Agent）** | 回测引擎、worker、库表、API、生产 ECS、最终提交 | 游戏的视觉细节与试玩验收 |

游戏相关的**唯一权威设计文档**仍是 `docs/agent/22_TRADING_GAME.md`，本文件只管「在哪里开发、怎么协作」。

## 2. 工作区与拉取

- 复用 Windows 侧已有的仓库检出：**`D:\workzone\webui`**（与 UI 工作同一工作区，避免两套检出漂移）
- 游戏代码在仓库的 **`game/`** 目录；前端模板/静态在 `src/quant_research_engine/gui/` 下（与 QRE 共用 UI 基座）
- **分支**：新建 `game/windows-dev` 分支开发，**不直接动 master**；最终提交由主 Agent 统一执行
- 上游 master 含 Windows 非法文件名（`*`/`]` 等）导致直接 checkout 失败的问题若仍在，按 UI 工作当时的做法剔除该条目后再检出，**不要推回上游**

## 3. 本地运行与验收

- 预览实例沿用 UI 的预览链路：`scripts/win/start-ui-preview.ps1`（默认 **8091**，`SAAS_AUTH_BYPASS=1` 仅本地）
- 游戏页入口：`/game`（历史 demo 在 **8092**，Windows 下统一走 8091 预览，避免与 WSL 转发端口冲突）
- 验收命令：`uv run python scripts/win/ui-smoke.py --base http://127.0.0.1:8091 --paths /game`
  （桌面 1280×900 与移动 375×812 两视口，零 pageerror、零 console error、零横向溢出）
- 截图落 `.tmp/ui-review/`

## 4. 数据口径（硬约束，别踩坑）

- 游戏用**前复权 K 线 + 因子**。因子库是**后复权**尺度（`raw × adj_factor`），K 线是**前复权 @ 最后交易日**锚点。
  价格型因子必须按 `factor_basis` 契约换算（`value / qfq_anchor`），**禁止再造第三套 `qfq_anchor` 平行实现**。
- 数据源用 Windows 侧**预览库 `qre_ui_dev`** 或本地样本快照；**不要直连生产行情库**，不要在游戏开发里跑全市场回测
- 复用 `factor-layout.js` 呈现层（主 K 线 / 成交量 / MACD / RSI 一体化终端），不要另起一套图表框架

## 5. UI 约定（继承 ui-style 契约）

- 复用 QRE 设计令牌与玻璃卡、**红涨绿跌**；不新增灰色小字备注（`.opt` / muted 说明文字），
  解释一律走 `tip-trigger` + `data-tip` + `LabUI.helpTips`
- 游戏是交易终端形态：主 K 线 + 成交量 + MACD + RSI 一体化，右侧集中操作区；不做专门美术/Steam/排行榜
- 保留既有能力：交易状态机、随机窗口、匿名揭盲、限价成交、T+1、整数手、费用模型

## 6. 协作流程

1. 主 Agent 在本文件/22 号文档里写明本轮游戏需求与验收标准
2. Windows agent 在 `game/windows-dev` 分支实现并自验（Playwright 双视口）
3. 回传：分支名 + commit + 截图路径 + 验收输出
4. 主 Agent 复核 → 必要时部署 ECS → 用户验收 → 主 Agent 统一提交/推送

## 7. 当前状态与待办

- 现状（22 号文档）：交易状态机、随机窗口、匿名揭盲、前复权、限价成交、T+1/整数手/费用已具备；
  WSL demo 在 8092 可跑，主 Agent 复核过专项 28 passed 与双端截图
- 待办：
  1. Windows 侧检出 `game/` 并跑通 `/game` 预览（第一条要做的事）
  2. 复权口径接入 `factor_basis` 契约（或显式声明独立口径并记录理由）
  3. 呈现层复用 `factor-layout.js`
  4. 持久化与公网中继、独立化（后续单独立项，远期）
- 2026-11-12 派单：待办 1 已由 Windows 侧完成（`game/windows-dev` 分支 `d10cfb1` + `f6385d8`，
  主 Agent 复核 34 passed）；本轮整改与四问裁定见 `46_GAME_WINDOWS_TASKS_2026-11-12.md`
  （T1 样本单位 100 倍偏差为唯一阻塞项，T2 测试入库 / T3 factor_basis / T4 average_price 口径 /
  T5 真实脱敏样本）。待办 2 对应 46 号 T3，待办 3、4 不变。
