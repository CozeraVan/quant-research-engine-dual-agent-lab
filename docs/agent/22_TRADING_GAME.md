# 22_TRADING_GAME.md — 《我不是股神》长期设计与实施手册

> 状态：V1 方向已获用户批准，WSL 本地 Demo 阶段。
> 本文是游戏项目的唯一长期事实来源之一。后续需求、规则、数据口径、实施进度、独立化决策均须回写本文，不以 CLI 对话为长期记忆。
> 主线 QRE/SaaS 的任务见 `14_LAUNCH_ROADMAP.md`；游戏采用并行推进，不打断主线 backlog。

## 1. 产品定位与独立化边界

《我不是股神》是一款随机单股票、随机历史区间的匿名日线模拟交易游戏。用户只能看到当前已经公开的 K 线、成交量、指标和账户信息，通过买入、卖出和时间推进训练历史决策，最终得到完整成绩。

未来可能：

- 作为 `aguhuice.com` 的新页面持续运营；
- 独立为单独 Web 应用；
- 发展为桌面/独立游戏（包括 Steam 的可能性）。

因此必须坚持两条边界：

1. **游戏规则引擎与 QRE 回测引擎分离**：回测回答“某策略历史表现如何”，游戏回答“用户逐日主动决策的结果如何”。不得把游戏变成回测引擎的按钮集合。
2. **数据读取与展示可替换**：行情、复权、指标、费用、结果展示通过明确的只读适配层复用 QRE；独立化时可换数据包或独立前端，不依赖 SaaS 数据库、账号或 worker。

当前不做 Steam、专门美术、卡牌、经营、排行榜和商业化。

## 2. V1.0 范围

### 初始条件

- 初始资金：`1,000,000`，页面只显示数值，不显示货币单位。
- 日线、单股票、只做多、无杠杆、无做空、无利息。
- 默认游戏长度 5 年，另提供至少 1 年预热历史用于 EMA200 等指标。
- 股票池要求：具备至少 6 年可用日线与必要指标数据；剔除历史不足、长期停牌和关键字段缺失标的。
- 随机股票与随机窗口由服务端生成并保存随机种子，刷新不得重新抽取。

### 匿名与时间映射

- 真实股票名、代码、真实日期不返回前端。
- 示例匿名映射：股票名 `B`、代码 `X00001B`、时间显示为相对游戏时间。
- 推荐使用 `第 Y 年-第 M 月-第 D 交易日`，避免伪造真实日历；产品视觉文案可映射为 `T年-1月-1日`。
- V1 使用真实前复权 OHLCV 与指标，不展示公司更名、公告、除权除息、分红等事件。
- 复权锚点在一局开始时固定，整局不得改变，避免中途价格序列漂移。

### 指标与界面

- 复用 aguhuice.com 现有 UI 风格，不做额外美工。
- 主界面为国内主流交易软件首页精简版：K 线为主视图，账户、订单、时间控制、成交详情集中在右侧操作栏，不做简单上下堆叠。
- V1.1 起开放数据库内全部技术类因子目录，按分组/搜索选择并懒加载所选序列；不一次性读取全库。基本面、估值、财务面板与元数据不纳入技术指标目录。
- EMA、均线、BOLL 轨道等 overlap 指标与 K 线同图；MACD 等独立指标使用动态副图，复用 `factor-layout.js` 分组规则。
- 新 UI 继续遵守 R-UI-001：不得新增灰色小字备注，必要解释统一 `tip-trigger + data-tip + LabUI.helpTips`。

### 时间控制（V1.1 回合制）

- 每个交易日固定为「决策 → 揭盲/结算 → 下一回合」；默认停在决策阶段，不自动出现下一根 K 线。
- 决策阶段只公开次日开盘价、前收盘 ±10% 委托区间和当前可交易信息；播放/结算只收束当前一根 K 线，随后立即停止，不得跨日自动连播。
- 结算后当日禁止再买卖，展示成交/未成交与完整 K 线；用户点击“进入下一回合”后才进入下一次决策。
- 只能前进，不能回退；不得通过进度条或 API 回看尚未公开的行情。

## 3. 交易与成交规则

### 基础约束

- 买入、卖出只允许当前匿名股票。
- A 股 T+1：当日买入下一交易日才可卖。
- 100 股一手，按整数手交易；最小价格变动 0.01。
- 买入不超过可用现金，卖出不超过可卖持仓；不允许负现金、负持仓。
- 订单提交和成交必须幂等，刷新、双击、重试不能重复成交。

### 限价委托与逐日判定

- 委托价必须在前收盘价 ±10% 范围内，并按 0.01 修正。
- 次日开盘价可以在该日公开，但当日最高、最低、收盘及未来信息在结算前不得泄露。
- 当日最低价 ≤ 委托价 ≤ 当日最高价才成交，成交价为委托价，滑点为 0。
- 未触及则当日未成交；一字涨停禁止买入，一字跌停禁止卖出。
- 每个交易日每个有效委托只判定一次，成交/未成交结果以服务端为准。

### 交易磨损

- 复用 QRE 当前市场配置：佣金、最低佣金、卖出印花税、过户费；滑点为 0。
- 不另造第二套费率常量；若未来允许用户调节磨损，必须另行立项并保持配置单一来源。

## 4. 结束与结算

满足任一条件即结束：

1. 用户设定的游戏时间跑完；
2. 当日收盘总权益低于初始资金的 10%。

`总权益 = 现金 + 持仓数量 × 当日收盘价`，不得用现金代替总权益判断破产。

结果至少包括：总收益率、收益曲线、买卖与未成交详情、持仓、交易磨损、费用勾稽、最大回撤等。结果默认私有，不自动公开或进入经典策略。

## 5. 防作弊硬规则

1. **服务端权威**：真实股票、真实日期、完整未来行情、成交判定只能由服务端掌握。
2. **逐日揭盲**：初始化只返回匿名信息与一年预热数据；推进一天才返回该日数据，指标也只覆盖已经公开的区间。
3. **禁止整包未来数据下发**：不得复用当前把全期 K 线一次性发给浏览器的回放模式。
4. **可复现随机**：session 保存随机种子、股票、窗口、复权锚点、当前日、现金、持仓、订单与成交；刷新不重新随机。
5. **接口防篡改**：订单价格/数量由服务端校验，前端不能直接声明成交；所有写操作幂等。
6. **会话隔离**：游客/用户只能访问自己的游戏 session，禁止 IDOR。
7. 未来做价格/成交量加权处理时，必须在变换后的 OHLCV 上重新计算指标，禁止展示加权 K 线却沿用原始指标。

## 6. 复用与新建清单

直接复用：

- WSL PostgreSQL 日线、复权因子与指标口径；
- EMA/MACD/BOLL/RSI 的计算结果或计算逻辑；
- ECharts 与播放、暂停、单步、倍速交互；
- QRE 交易费用配置和结果指标；
- aguhuice.com 淡紫 UI、提示组件与测试模式。

新建但保持小边界：

- `GameSession`：随机种子、匿名映射、当前状态；
- `GameDataProvider`：只读抽样、复权、逐日数据；
- `GameEngine`：时间、订单、成交、现金、持仓和结算；
- `GamePresenter/API`：匿名逐日响应与结果展示；
- `GameSessionStore`：持久化与恢复。

不为“未来可能独立”提前建立庞大插件框架；只要求这些边界清楚、可测试、可替换。

## 7. 环境与公网路径

### Demo 阶段

全部在 WSL 开发测试，Windows 仅用于浏览器预览。不得用 Windows 原生 Python 另造数据环境。

### 公网阶段

当前 ECS 不保存行情明细，且家庭宽带无公网入站。公网链路建议：

`浏览器 → ECS 游戏接口 → 家庭 WSL 游戏数据服务 → 匿名/逐日结果`

家庭端主动建立安全 WebSocket 中继，ECS 只转发，不持久化原始行情。公网中继不在 WSL 可玩 Demo 的首个验收范围内，独立估算约 15万～30万 Token 和 1 个工作日。

## 8. 实施阶段与验收

### 阶段 0：规则和小样本数据合同

- 股票池过滤、随机种子、复权锚点、匿名映射；
- 订单/成交/费用/总权益公式；
- 10～20 只股票小样本验证，不做全市场游戏化计算。

### 阶段 1：WSL 可玩 Demo

- 创建随机局、预热、匿名 K 线/指标；
- 播放/暂停/单步/倍速；
- 买入、卖出、未成交、一字板失败、T+1；
- 时间耗尽或总权益低于 10% 后结算并展示结果。

### 阶段 2：正确性与防作弊验收

- API 无真实代码、真实日期和未来数据；
- 刷新不重新随机，订单不重复；
- 跳空、未触及、一字板、T+1、整数手、资金不足；
- 费用与最终权益完全勾稽，时间只能前进；
- 游客/用户 session 隔离。

### 阶段 3：aguhuice.com 新页面与中继

- 接入新页面、结果默认私有；
- 实现家庭端到 ECS 的主动安全中继；
- 公网验收后再考虑独立应用和后续玩法。

## 9. 测试矩阵（V1 必做）

- 委托价触及/未触及、跳空、上下限、一字涨跌停；
- T+1、100 股整数手、0.01 价格单位、资金/持仓不足；
- 刷新、双击、重试不重复成交；
- 佣金、最低佣金、印花税、过户费和总权益勾稽；
- 游戏结束两个条件、时间不可回退；
- 随机结果可复现，匿名响应无未来数据；
- 桌面 1280 与 375px 不横向溢出，零 JS error。

## 10. 工期与 Token 估算

仅作工程估算，不是保证值；实际取决于子代理返工、测试失败和浏览器调试。

- 可开始并完成一局：约 25万～40万 Token、4～8 小时；
- WSL 完整 V1：约 39万～63万 Token、7～14 小时（1～2 天）；
- 公网中继另加约 15万～30万 Token、约 1 个工作日。

为控制范围，优先砍指标数量和辅助展示，不得砍匿名逐日数据、成交正确性、费用勾稽与幂等。

## 11. 后续独立化方向（只记录，不启动）

- 独立 Web/桌面前端；
- 分时、月线、财报、利息、杠杆和可调磨损；
- 加权/扰动行情及对应因子重算；
- 排行榜、挑战关卡、卡牌或经营机制；
- 数据授权与独立数据包（商业再分发前必须核查）。

任何独立化或 Steam 工作必须重新立项，明确数据许可、打包方式和用户群体，不与 V1 同时进行。

## 12. 当前实施进度（2026-10-26，WSL 可玩 Demo 已跑通）

- `game/engine.py`：纯交易状态机，复用 `core.models` 与 `AShareMarketProfile`，支持限价成交、未成交、T+1、整数手、费用、总权益和 10% 结束条件。
- `game/session.py`：随机股票/窗口、匿名映射、开盘/收盘两阶段；开盘只显示 open，收盘才显示完整 OHLCV 和当日指标。
- `game/data.py`：原始价 + adj_factor 生成固定锚点前复权；现有因子按日对齐（Timestamp 标准化）；EMA 使用库内 ema_5/20/60/250（库内无 ema_200，不临时造因子）。
- `game/web.py`：WSL 内存 session API，创建/推进/下单/收盘/结果，owner Cookie 隔离，响应无真实代码、真实日期或未来数据。
- `game/templates/game.html`：复用淡紫 UI 与 ECharts，K 线/成交量/EMA/MACD/BOLL/RSI、交易、账户、时间控制和成交记录；下单与收盘请求做防竞速处理。
- 验证：22 项游戏专项测试通过；全量 **2753 passed + 6 skipped**。真实 WSL 数据库抽样通过，真实 Chromium 完成开盘买入并显示费用，1280/375 无横向溢出、无 JS error。截图 `.tmp/trading-game/`。
- 本地试玩：`http://127.0.0.1:8092/game`，使用真实数据库，创建随机局需等待抽样。当前未部署 ECS、未做公网中继、未 commit/push；V1 只做 WSL 验收。
- 2026-10-27 复核补丁：因子目录补齐「风险」「流动性」两组（25 + 35 个）；因子缓存键由裸列名改为 canonical，同一列名在不同价格口径（close / typical_price）下互不覆盖。游戏专项 41 passed，真实 Chromium 复核通过，证据 `.tmp/trading-game-v11/`。
- 2026-10-27 复核补丁二：游戏内 `buildPlan` 按成员 canonical 重写圆片/pane key（不改共享 `factor-layout.js`），两个同名 `ema_5` 圆片三态互不联动；新增 Chromium 回归 `chip_key_audit.py`，专项 41 passed、全量 2864 passed（2 项既有时间依赖失败独立记录）。证据 `.tmp/trading-game-v11/chip-keys.png`、`chip-key-audit.log`。

## 13. V1.1 试玩反馈实施任务书（2026-10-26，DeepSeek 实施，Kimi 复核）

### 13.1 六项反馈的统一解释

1. **开局切换**：随机局创建成功后隐藏 `#game-start`，显示主界面；创建期间保留等待状态，失败才可重试。
2. **K 线主导**：桌面采用「左侧大 K 线 + 右侧操作栏」双栏布局，K 线占主要宽度与高度；股票匿名信息、回合控制、交易、账户、成交详情集中右侧，禁止所有卡片简单上下排列。
3. **指标布局**：复用 `QREFactorLayout.plan`，均线/EMA/BOLL 等 overlay 到 K 线主图，MACD 等多线同副图，其余独立副图；grid 和容器高度随面板数变化。
4. **全技术因子目录**：从 `configs/factor_registry.json` 的真实目录生成可选清单，只含技术/量价/Alpha 类，排除 `_pit_financial_panel`、基本面/估值/财务/元数据。目录仅含 canonical、中文/英文标签、表列和布局元数据，不含时间序列；用户选择后才按 canonical 白名单懒加载，禁止任意表名注入和全库一次性读取。原 EMA/MACD/BOLL/RSI 作为默认已选指标。
5. **回合制操作**：服务端继续只暴露 open→closed 两阶段；前端将其明确呈现为决策和结算。决策时展示下一开盘价、上下限、委托价和数量，K 线用 markLine/markArea 显示前收 ±10% 区间、次日开盘和当前委托价；播放只调用 close，收束一根 K 线后立即停下。closed 时禁用交易，展示结算结果，只有“进入下一回合”才调用 advance。
6. **空仓与幂等**：无 pending 委托可直接结算表示空仓；若已有委托，提供开盘阶段撤销，撤销后才能按空仓结算。下单、撤销、advance、close 均防双击/竞速，重复请求不得重复成交或推进。

### 13.2 建议最小 API/数据合同

- `_state` 在既有字段上补充 `decision`：`previous_close/limit_lower/limit_upper/next_open/can_trade`；上下限与 `DailyGameEngine` 同一价格边界函数，不能在前端另写一套规则。
- 结算信息包含当根完整 OHLC、成交/未成交原因、成交价量（有成交时）；不得提前返回 high/low/close 或任何未来日数据。
- 新增只读因子目录接口与按 session/selected canonical 加载接口；canonical 必须来自服务端目录白名单，每个 session 只加载用户所选列，并缓存已加载列避免重复读库。
- 保持现有 `phase=open|closed`、owner Cookie、匿名映射、T+1、整数手、费用与结束条件，不改 QRE 回测引擎。

### 13.3 验收矩阵

- 开局 div 消失；1280 桌面 K 线为主、右侧完整操作，375 无页面横溢。
- EMA/BOLL 与 K 线同图，MACD 同副图；0/1/多副图动态布局正常；目录至少覆盖 overlap/momentum/volatility/volume/trend/performance/statistics/candle/alpha 类实际存在项，基本面目录不出现。
- 决策时只见 open 和区间，不见 high/low/close；播放一次只新增/收束一根 K 线并停止；触及按委托价成交，未触及不成交；closed 不能下单，下一回合才重新开放。
- 空仓、撤单、连续点击、刷新后阶段与账户一致；T+1、费用、权限隔离零回归。
- 先跑游戏专项和全量测试，再用真实 Chromium 完成「开局→限价买入→结算→下一回合→卖出」及目录选择、区间显示、375 检查。证据保存 `.tmp/trading-game-v11/`。
- 本切片仅 WSL `http://127.0.0.1:8092/game`，不部署 ECS、不 commit/push、不推进公网中继、独立游戏、Steam 或主线任务。

### 13.4 实施结果（2026-10-26，V1.1 完成）

**改动文件**

- `game/engine.py`（148 行）：抽出与 session 共用的涨跌停价格边界函数；新增 `cancel_order`，撤单与下单共用同一 pending 校验与幂等语义。
- `game/session.py`（199 行）：`_state` 输出 `decision`（前收、上下限、次日开盘、可交易）与 `settlement`（当日 OHLCV、成交/未成交原因、成交价量与费用）；新增撤单入口；`history` 只含已结算 bar。
- `game/factors.py`（123 行）：从 `configs/factor_registry.json` 生成技术/量价/Alpha canonical 白名单与分组（含 `risk`/`liquidity`），按 session 已选 canonical 懒加载并缓存，拒绝任意表名列。
- `game/web.py`（221 行）：新增 `POST /api/sessions/<id>/cancel`、`GET/POST /api/sessions/<id>/factors`；`/result` 增补 `trades` 与 `events`；401 统一为“游戏不存在或无权访问”。
- `game/data.py`（128 行）：配合因子懒加载的列读取与前复权对齐，未改变 V1 数据口径。
- `game/templates/game.html`（复核轮后 786 行）：桌面双栏（左 K 线 + 右操作栏）、决策/结算两态展示、时限价区间与次日开盘 markLine/markArea、委托/撤单/结算幂等按钮、因子目录搜索与圆片三态（overlay→pane→hidden）、移动端单栏；开局隐藏起始卡并显示“第 N / M 个交易日”。
- 测试：`tests/test_trading_game_data.py`（60）、`session`（145）、`engine`（180）、`factors`（163）、`web`（272）。

**验证**

- 游戏专项：`.venv/bin/python -m pytest tests/test_trading_game_*.py -q` → **41 passed in 0.57s**（复核轮复跑；V1.1 初次交付时为 38 passed）。
- 全量回归：`.venv/bin/python -m pytest -q --ignore=tests/data_test` → **2864 passed, 6 skipped, 4 warnings in 140.33s**；另有 2 项失败 `tests/test_saas_public_beta_ops.py::TestConsoleOps::test_metrics_math` 与 `test_conversion_ratio_never_computed`，属既有时间依赖（`window=today` 按上海自然日统计，造数用 `now()-1h`，在 00:00–01:00 CST 运行时落到前一天导致 `total=0`），与本切片无关，测试文件本轮未改动。
- 真实 Chromium（Playwright，1280×900 与 375×812，脚本 `.tmp/trading-game-v11/browser_audit.py`）一次完整通过：
  1. 起始卡可见，建局后隐藏；`#kline` 有 canvas；回合显示“结算阶段 · 第 1 / 1250 个交易日”。
  2. 进入决策：前收盘价/次日开盘价/涨停价/跌停价/交易状态齐全，`#order-price` 的 min/max 与页面一致；未下单时撤单按钮禁用。
  3. 限价买入 100 股 → 撤单（成功且按钮回到禁用）→ 再买入 → 结算：账户 100 股，成交记录 1 行，结算显示成交结果与费用。
  4. 下一回合卖出 100 股 → 结算：成交记录 2 行，账户 0 股（随机局曾出现一字板导致挂单未成交，引擎按规则拒绝成交；脚本在下一回合重试后成交）。
  5. 因子目录搜索并勾选 `ema_10` 成功加载（默认 EMA/MACD/BOLL/RSI 圆片共 10 个），圆片点击进入副图、再点回到隐藏态；再加载 `rsi_14` 正常。
  6. 1280 与 375 均无横向溢出；复用同一 session 恢复移动端正常；桌面与移动端均无 pageerror、无 console error。
- 证据：`.tmp/trading-game-v11/desktop.png`（1280×1355）、`.tmp/trading-game-v11/mobile.png`（375×3118）；复核轮重新生成并覆盖，运行日志 `audit-fixes.log`、全量日志 `full-suite.log`。
- 可玩地址：`http://127.0.0.1:8092/game`（WSL，真实数据库；启动需 `QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data`）。

**复核轮（2026-10-27）：两处修复**

修复内容（范围仅游戏源码、游戏测试与本文档）：

1. 目录补 `risk` / `liquidity`：`game/factors.py` 的 `TECHNICAL_CATEGORIES` 增加两类，`_TABLE_GROUPS` 把 `stock_daily_risk` / `stock_daily_liquidity` 归组，`GROUP_LABELS` 新增「风险」「流动性」，`GROUP_ORDER = (*TECHNICAL_CATEGORIES, "alpha")`；value/size/quality/growth/_pit 继续排除。
2. 缓存键 canonical 化：`game/session.py` 用 `loaded_canonicals` 取代裸列名集合，`session.factors` 与 `GET /game/api/sessions/<id>/factors` 返回的 `loaded` 一律为 canonical；`game/data.py::load_selected` 只对未加载的 canonical 增量读库，`frame.empty` 也已计入已加载；前端 `game.html::buildPlan` 用 canonical 取 `h.factors[canonical]`，`meta.column` 仅保留给 `QREFactorLayout` 做布局识别。

RED→GREEN：新增 5 项测试（risk/liquidity 分组与表名白名单、默认选择只加载一次且不重复读库、新增 canonical 懒加载、同 column 两价格口径互不覆盖、两口径 EMA5 各自成序列）；修复前 **36 passed / 4 failed**，修复后 **41 passed**。

真实库 API 抽查（`GET /game/api/factors`）：646 项 / 11 组 —— overlap 95、momentum 108、volatility 50、volume 21、trend 41、performance 19、statistics 20、candle 10、risk 25、liquidity 35、alpha 222；白名单表名仅 `stock_daily_{alpha101,alpha191,candle_close,liquidity,momentum_average_price,momentum_close,overlap_close,overlap_typical_price,performance_close,risk,statistics_close,trend_close,volatility_close,volume_close}`。新局默认加载 11 个 canonical；增选 `factors.stock_daily_risk.return_std_21d`、`factors.stock_daily_liquidity.avg_turnover_5d` 与两个 `ema_5` 后全部同时进入 `selected` / `loaded`，两口径 EMA5 在 250 根中有 235 根不同（末值 20.79 / 20.83）。

Chromium 复核（同一脚本一次通过，日志 `audit-fixes.log`）：分组标题显示「风险 25」「流动性 35」；两个新因子在 history 中各 253/253 非空，副图出现「收益标准差(21)」序列；`ema_5` 两口径同时在 K 线生成 2 条「指数移动均线(5)」且 246 个点不同；`#factor-error` 为空；桌面与移动端零 pageerror、零 console error；1280 与 375 无横向溢出。

**补充复核轮（2026-10-27）：圆片 key 按 canonical 重写**

问题：`gui/static/factor-layout.js:34` 的 `fkey(f) = f.col || f.name` 用裸列名做圆片/pane key，两个 `ema_5`（close 与 typical_price 口径）共用一个 key，点击任一圆片会把两者一起切三态。共享模块属主线文件，本轮不改，改为在游戏内解决。

做法（`game/templates/game.html::buildPlan`，未改共享 JS）：

1. 先以空 `layoutStates` 调 `LAYOUT.plan(factors, {})` 取得全量默认分组；`factors[].values` 是每个 canonical 独立 `history.map(...)` 的产物，用值数组引用即可反查成员 canonical（`canonicalOf` Map）。
2. 按输出重写 key：单因子组 = 该 canonical；MACD/家族组 = 成员 canonical 以 `|` 连接（如 `...macd_12_26_9|...macds_12_26_9|...macdh_12_26_9`），overlay/MACD 分组规则不变。
3. `layoutStates` 因此原生以 canonical 为键（点击处 `layoutStates[chip.key]` 直接命中），无需新旧键映射表；隐藏某 overlay 时其余 overlay 颜色不再重排（颜色更稳定，可接受）。
4. overlay 组切到 pane 的路径复用共享规则的单因子面板实现。

验证：

- 游戏专项：`.venv/bin/python -m pytest tests/test_trading_game_*.py -q` → **41 passed**。
- 新增浏览器/JS 回归 `.tmp/trading-game-v11/chip_key_audit.py`（真实 Chromium，日志 `chip-key-audit.log`）：默认 9 个圆片 key 全唯一；`MACD` 仍是单圆片且 key 为三成员组合，点击整面板消失/恢复；加载两个 `ema_5` 后出现两个不同 key 的圆片、两条 overlay 与各自 canonical 历史逐点相等且 246 点不同；点 typical 圆片只有它变 pane（close 数据不变）→ 再点变 hidden 而 close 仍 overlay → 点 close 只影响 close、typical 保持 hidden → 两者恢复 overlay；零 pageerror、零 console error；截图 `chip-keys.png`。
- 旧回归 `.tmp/trading-game-v11/browser_audit.py` 复跑通过（10 个默认圆片、点圆片进副图、风险/流动性分组、两 `ema_5` 246 点、移动端无横向溢出）。
- 全量：`pytest -q --ignore=tests/data_test` → **2864 passed, 6 skipped；2 failed**，仍仅为 §13.5 末条记录的 `tests/test_saas_public_beta_ops.py` 两项既有时间依赖失败，未改未跳过。

**范围声明**

本切片未 commit/push、未部署 ECS、未推进公网中继、独立游戏或 Steam。`AGENTS.md` 第 12 条“改代码后直接部署 ECS”与任务书 §13.3“仅 WSL、不部署”冲突，本次以任务书为准执行。

### 13.5 遗留与后续

- 建局耗时 37–60s：真实库抽样、250 根 warmup 与因子批量读写叠加。后续先 profile，再考虑抽样索引/样本缓存，暂不改变数据口径。
- MACD 在目录中按 dif/dea 分列，需同时勾选才会成组显示；后续可在目录聚合层做组合项。
- session 仍为进程内存，服务重启即清空；前端 localStorage 会在 401 后自清并回到起始卡。
- 涨跌幅边界目前统一按 `AShareMarketProfile` 10%，未覆盖创业板/科创板 20% 与 ST 5%。
- `closed` 状态下 `decision` 不返回 `next_open`（仅 open 提供），前端据此禁用下单。
- 已修复 dataZoom 监听重复注册（改为一次性绑定）与开局把 warmup 计入天数的问题。
- ~~同名 column 共享圆片 key~~（已解决，2026-10-27）：游戏内 `buildPlan` 按成员 canonical 重写 key，两个 `ema_5` 圆片独立三态，证据见 §13.4 补充复核轮。
- `tests/test_saas_public_beta_ops.py::TestConsoleOps` 的 `test_metrics_math` 与 `test_conversion_ratio_never_computed` 在 00:00–01:00 CST 运行时必失败（`window=today` 取上海自然日，造数用 `now()-1h` 落到前一天），属既有时间依赖缺陷，非本切片引入，也未在本轮修复。

## 14. V1.1 DeepSeek 方案否决与 Kimi 重做任务书（2026-10-27）

### 14.1 用户裁决

用户试玩后明确「这版本不通过」，要求全盘抛弃 DeepSeek 的 V1.1 优化方案，由 Kimi 接手重做。§13 仅保留为否决方案的过程档案，不作为当前实现依据。当前工作先备份再替换，不在 DeepSeek 的实现上继续叠补丁。

### 14.2 重做原则

1. 回到 V1 已验证的 open→closed 状态机、匿名逐日行情、T+1、限价成交与费用边界，优先保证流程稳定。
2. 不沿用 DeepSeek 的 UI、因子分组/芯片映射、目录缓存或浏览器脚本。所有生产代码与测试由 Kimi 重新编写。
3. 交互只保留一个清晰回合：**进入决策 → 委托或空仓 → 播放并收束一根 K 线 → 查看结算 → 进入下一回合**。禁止跨日自动连播。
4. 桌面左大 K 线、右侧统一操作栏；开局卡成功后消失。EMA/BOLL 直接叠加 K 线；其他指标按选择生成副图。
5. 因子以 canonical 为唯一键，支持风险/流动性/Alpha 与同列不同价格口径。目录与序列分离、选择后懒加载，不使用共享芯片三态或同名 remap。MACD 默认作为一组展示，其他因子按选择逐项显示，避免不必要的交互复杂度。
6. 先完成 API、规则与模板测试，再做真实 Chromium 逐回合验收；未通过不展示为可验收版本。仅 WSL，不部署 ECS、不 commit/push，不修改主线。

### 14.3 Kimi 重做实施与验收记录（2026-10-27）

- 已完整替换 `game/{engine,session,data,factors,web}.py` 与 `game/templates/game.html`，未沿用 DeepSeek 的芯片 remap 或连播逻辑。否决版备份在 `.tmp/trading-game-v11-rejected/`。
- 当前交互：开局隐藏起始卡；桌面左大 K 线、右侧操作栏；决策显示前收、次日 open、上下限和委托价；播放只收束一根 K 线，结算后禁止交易，点击下一回合才推进；支持空仓、撤单、T+1 和重复 close 幂等。
- 因子目录改为 canonical 数据键，覆盖 overlap/momentum/volatility/volume/trend/performance/statistics/candle/risk/liquidity/alpha；同列不同价格口径独立懒加载，不使用共享芯片三态。MACD 同副图，EMA/BOLL overlay。
- 用户批准后已为 `qre_worker_ro` 补齐 14 张技术因子表 `SELECT` 权限；仅授权，不改数据或表结构。验证 14 表均可读。
- 游戏专项 **22 passed**；最终全量回归 **2847 passed + 6 skipped**（4 个既有 warnings）。真实 Chromium 审计 `Kimi V1.1 browser audit = OK`：开局→撤单→空仓结算→买入→下一回合→卖出→风险/流动性与同列双口径选择→375 无横溢、无 JS error。证据 `.tmp/trading-game-v11-kimi/`（desktop.png、mobile.png、browser_audit.py、服务日志）。
- 本地服务 `http://127.0.0.1:8092/game`。当前仍未部署 ECS、未 commit/push；游戏与主线 UI 候选预览分离。

## 15. CR-2026-10-27 数据口径与交易终端修复（2026-10-27）

需求原文：`docs/agent/change_requests/CR-2026-10-27_game_terminal_repair.md`。用户试玩 Kimi V1.1 后报告「K 线 OHLC 只有 5～11，EMA/BOLL 却到 14～30，指标与图表布局都不像交易软件」。本节是这条 CR 的实施与验收记录。

### 15.1 根因：因子表 hfq 与游戏 K 线 qfq 量纲不一致

`21_FACTOR_LIBRARY_PLAN.md:129`（以及 `:232`）与 `23_KLINE_IMPLEMENTATION.md:230` 已写明两套口径：因子表按 **hfq**（原始价 × adj_factor）落库，游戏 K 线按 **固定锚点前复权** `qfq = raw / adj_factor(末根)`。V1.1 把因子表原始值直接当展示值，于是出现系统性倍差，倍差正是锚点本身。

真实只读数据复现（`.tmp/trading-game-terminal/repro_price_scale.py` → `repro_price_scale.txt`），603408.SH、1511 根、锚点 `1.3069`：

| 交易日 | 原始收盘 | adj_factor | 游戏收盘 | 表内 ema_5 | 表内 ema_20 | ema_5 / 锚点 | ema_20 / 锚点 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2021-08-02 | 14.09 | 1.0440 | 11.2556 | 14.76 | 15.09 | 11.2939 | 11.5464 |
| 2023-01-31 | 11.50 | 1.0800 | 9.5034 | 12.29 | 12.17 | 9.4039 | 9.3121 |
| 光标当日 | — | — | 11.0639 | — | 表内 14.77 | — | 11.3016 |

结论：`表内值 / 锚点 ≈ 游戏收盘`，误差仅来自 EMA 窗口内价格本身的波动。用户看到 11 与 27 并列，就是同一根 bar 上 hfq 与 qfq 两个尺度。

全族扫描（`.tmp/trading-game-terminal/scan_all_families.{py,txt}`，237 族 / 304 列）用于确认哪些族需要换算：价格或价格差类（ema/sma/bbm/hhv/atr/stdev/median/dpo…）中位比值集中在 1.0、与收盘相关系数 >0.9；无量纲类（rsi/adx/natr/bb_width/dd_log/dd_pct…）比值与收盘无关。据此把「换算」做成白名单，而不是按数值范围猜测。

### 15.2 修复：`game 值 = 表内值 / 锚点`，且只作用于价格型列

- `game/data.py::qfq_anchor(rows)`：取可用行最后一根 `adj_factor` 作为会话锚点，与 `23_KLINE_IMPLEMENTATION.md:230` 一致；开局固定，整局不变。
- `game/data.py::load_selected`：先由 `price_scaled_canonicals()` 判定每个 canonical 是否需要换算，读取后对价格型列除以锚点（锚点为空/0 时按 1.0 降级）。多张因子表按 `trade_date` 合并后统一换算，避免同列不同价格口径互相覆盖（沿用 §13 的 canonical 缓存键规则）。
- `game/factors.py`：`PRICE_SCALED_FAMILIES`（80 族）、`NON_PRICE_FAMILIES`（10 族，供排查与防止误加的显式清单）、`MIXED_FAMILY_PRICE_PREFIXES`（`psar` 只有 `psarl_`/`psars_` 前缀是价格，`psaraf`/`psarr` 是加速度与比率；`zigzag` 该表当前读取报 `DatabaseError`、整列为 NaN，按不换算处理）。未知族保守返回「不换算」，宁可不缩放也不误缩放 RSI 这类 0–100 序列。
- 因子表读取失败不再让开局 500：批量读取抛异常时逐 canonical 重试，失败者以异常类名记入 `session.factor_errors`；`factor_errors` 与 `price_anchor`、`factor_audit` 一起出现在 `_state`，异常可见、不隐藏。

### 15.3 独立校验：`game/validation.py`

`audit_price_factors()` 只用游戏已复权 OHLC 重算，不读因子表、不用经验常数：

- EMA：SMA 种子 + `alpha = 2/(span+1)`（TA-Lib 口径）。实测若改用 `pandas ewm`（无种子），ema_20 残差会放大到 0.65、max_rel 2.7e-2，说明种子必须按 TA-Lib。
- SMA / BOLL：`ddof=1`。`diag_boll.txt` 显示 `df=0` 时 bbu 残差 0.084（超出 0.02 容差），`ddof=1` 后降到 0.005。
- 判定：`abs_diff > 0.02 且 relative > 2e-3` 才算 mismatch，两条同时满足以容忍 0.01 级报价精度与浮点尾差。
- 输出 `{checked, mismatches, max_abs_diff, max_rel_diff, canonicals{...}}`，随 `_state` 回前端，浏览器脚本直接读。

### 15.4 交易终端布局（`game/templates/game.html`，446 行）

- 顶栏一条：匿名股票、回合状态、指标按钮、图表提示；没有新增说明卡。
- 主体两列：左列整块是图表工作区（K 线 + 成交量 + 副图共用一块 ECharts 实例，`chartLayout()` 按 `#kline.clientHeight` 换算像素 grid，不写死高度）；右列 322px 集中回合、委托、账户、成交四张卡。
- 指标目录改为 `<dialog>` 弹窗（搜索 + 分组勾选），不再占用 K 线上下空间。
- 保留紫色品牌、红涨绿跌、匿名相对日期、回合状态机、owner Cookie 隔离；未新增灰色小字，说明只走既有 `tip-trigger + data-tip + LabUI.helpTips`。
- 断点：≤980px 右栏收窄到 300px；≤860px 单列、图表 64dvh、侧栏两列；≤620px 图表 62dvh、弹窗全屏。

### 15.5 验证

- 游戏专项：`.venv/bin/python -m pytest tests/test_trading_game_*.py -q` → **28 passed**（新增 `tests/test_trading_game_price_basis.py` 6 项：锚点与 K 线同尺度、价格型换算/无量纲原样、未换算可被审计捕获、审计对游戏 K 线直接报错、族分类与扫描证据一致、因子表异常降级不抛）。修复前该断言先红（`ImportError: qfq_anchor`）。
- 相邻回归：`pytest tests/test_data_catalog.py tests/test_factor_display_contract.py tests/test_postgres_store.py tests/test_trading_game_web.py -q` → **68 passed**。
- 真实数据复核（`.tmp/trading-game-terminal/verify_fix_real.py` → `verify_fix_real.txt`，603408.SH，1511 根，锚点 1.3069）：`factor_errors={}`；audit `checked=10189, mismatches=11`；ema_5/20/60 各 1507/1492/1452 点全部命中，`max_abs_diff ≤ 0.003826`（0.01 报价精度内的尾差）。
- 真实 Chromium（`.tmp/trading-game-terminal/browser_audit.py`，1280×900 与 375×812）：开局→决策→买入成交→结算→下一回合→卖出成交（2 笔）；指标弹窗勾选 bbl/bbu/macd 后关闭正常；`#kline` 902×808（视口 900，占 89%）、副图高度 `[456,100,96,96]`；右栏 x=942 宽 322，四卡最低 873.34 ≤ 900；K 线蜡烛与 `state.history` OHLC 逐点相等；同 bar `ema_20=18.1065 / close=19.6105`、`bbu=20.4089 / close=19.6105` 同尺度；`price_anchor=2.5582`、`factor_errors={}`；宽度扫 1440/1280/980/900/860/820/700/620/480 全部 `scrollWidth == innerWidth`（K 线高 808/566/548），375 无横溢、K 线 329×493；零 `pageerror`、零 console error。
- 证据目录：`.tmp/trading-game-terminal/`（`audit.log`、`audit-1280x900.png`、`audit-1440x900.png`、`audit-375x812.png`、`repro_price_scale.txt`、`scan_all_families.txt`、`diag_boll.txt`、`verify_fix_real.txt`）。
- 服务：`http://127.0.0.1:8092/game`（`QRE_PRICE_BASIS=raw`、`QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data`），单一进程供用户验收。

### 15.6 遗留项：`factors.stock_daily_overlap_close.ema_250` 尾部 11 根上游异常

audit 的 11 处 mismatch **全部**来自这一列（`audit mismatch canonicals` 输出仅此一项），且都在区间末端：

- 位置：2026-10-12 … 2026-10-26 连续 11 个交易日。
- 数值：表内 11.4469～11.4852，按游戏 K 线重算 11.1801～11.1996，`abs 0.2668～0.2879`、`rel ≈ 2.5%`；同批 ema_5/20/60 在同日残差 ≤ 0.004，`public.stock_daily` 价格正常。
- 性质：因子表这一段与「用 hfq close 重算 ema_250」同样差 ~2.5%，即上游补数批次写入了与其余区间不自洽的值，属数据侧问题，不是本次换算引入。
- 处置：**照实暴露，不裁剪、不隐藏、不改容差**；audit 审计全区间并原样回前端。建议后续重跑该段 `ema_250` 的补数批次后再复核；在那之前该列尾部 11 个点不应作为判断依据。

### 15.7 范围声明

本切片只改 `src/quant_research_engine/game/`（`factors.py`、`data.py`、`validation.py`、`session.py`、`web.py`、`templates/game.html`）、游戏专项测试与本文档。未部署 ECS、未 commit/push、未跑回测、未改主线共享源码。`AGENTS.md` 第 12 条「改代码后直接部署 ECS」与 CR 的「不部署」冲突，本切片按 CR 执行。