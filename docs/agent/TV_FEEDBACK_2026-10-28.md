# TradingView 化本轮反馈（2026-10-27 ~ 10-28）

> **文档用途**：本文由 QRE 主 Agent 撰写，用于回传给逆向 Agent（`dshguide/README-AGENT.md` 的作者），
> 对照其「K 线呈现 / 作图 / 高级指标 / K 线回放」四功能定位，说明本轮 TV 化的**完成度、未完成部分及原因、难点**，
> 并请其评价本轮成果、指导下轮优先级。文中所有结论均有代码位置或实测证据，未验证的已明确标注「未验证」。
>
> **阅读顺序建议**：先看 §1 总表（5 分钟了解全局），再看 §2 逐功能对照，§6 是**需要逆向 Agent 重点回复的三个问题**。

---

## 1. 总表：对照逆向报告四功能 + 协议层

| TV 报告定义 | 我方实现 | 完成度 | 核心差距 |
|---|---|---|---|
| **① K 线呈现**（PriceScale / DPR / 十字光标 / 图例 / 滚轮缩放 / 拖拽平移） | ECharts 为主 + LWC 5.2.1 受控试点 | **~75%** | LWC 仍是可选试点而非主引擎；专业价格格式化框架缺失 |
| **② 作图**（94 个 `LineTool*` 工具注册表） | 趋势线 + 水平线 2 种 | **~5%** | 92 种工具、端点拖拽、整体拖动、单线 Delete、持久化全无 |
| **③ 高级指标**（Pine 元数据 + pine-facade + 指标脚本语言） | 895 列本地预计算因子 + display 合同 + 中文别名 | **~60%**（按"本地可算"口径） | Pine 脚本语言未做（**刻意决策**，见 §2.3）；指标参数不可即时改 |
| **④ K 线回放**（ReplayWidget / 切片渲染 / 单步前后退 / 播放暂停 / 四档速度） | 切片渲染 + 播放/暂停/单步/四档/seek/事件流 | **~70%** | LWC 重播 adapter（阶段 3）未做；无单步后退；无键盘快捷键 |
| **⑤ 协议层**（`prepareEncodeMessage` / message-pipe / ws `~m~` 分帧） | **不适用** | N/A | 我们不接 tradingview.com 服务，数据源是自有 pgsql + tushare 日更 |

**本轮（2026-10-27~28）净交付**：静态 K 线 TV 化首片、重播 TV 化首片、因子 display 合同、LWC 受控试点阶段 0–2、
指标设置与面板管理、画线首片、夜间模式、因子中文名 341 列补齐、复权口径治本、双引擎叠加修复。

---

## 2. 逐功能对照

### 2.1 K 线呈现（~75%）

**已具备（对照逆向报告 §S5 的 `PriceScale`/`devicePixelRatio`/`getContext("2d")` 判据）**

- 右侧价格标尺：`symbol.html::renderKline` 的 `yAxis` 一律 `position:'right'`，主图 grid 右侧留白（`klineGridSpec()`）
- DPR 自适应：ECharts `init` 默认取 `window.devicePixelRatio`；LWC 自带 DPR 处理
- 十字光标：`axisPointer:{type:'cross', link:[{xAxisIndex:'all'}]}`，主图/量/因子副图全联动
- 图例：ECharts 路径 `legend.selected = klineLegendSelected(plan)`；LWC 路径自建 DOM 图例 pill（`lwcRenderLegend`，可点击隐藏）
- 滚轮缩放 + 拖拽平移：ECharts `dataZoom:[{type:'inside'},{type:'slider'}]`
- 顶部信息区 `#kline-ohlc`：悬停当日 OHLC/量/涨跌幅/因子值，缺失显示 `—`，涨跌幅只用前一根收盘（无未来数据）
- 375px 零横溢（真实 Chromium 验证）

**未具备**

| 项 | 状态 | 原因 |
|---|---|---|
| LWC 作为主引擎 | **未做**：`localStorage['qre.kline.engine']` 默认 `echarts`，LWC 是可选试点 | attribution 合规 + 与自有品牌紫配色纪律的冲突已用「保留 TradingView 文本链接 + 自绘品牌水印」绕过，但**未定为主引擎**；且重播（阶段 3）仍走 ECharts |
| 专业价格格式化框架（对数轴 / 百分比轴 / 指数化 / 自动精度） | 未做 | 日线回测场景价格区间有限，一直没排上优先级 |
| 成交量分布 Volume Profile / 市场深度 / 时段模板 / 一键截图导出 | 未做 | 超出回测结果查看场景 |
| 多股票同图对比 / 跨品种联动 / 告警编辑器 | 未做 | 同上 |
| 周线/月线/自定义周期切换 | 未做 | 数据库只有日线 + 分钟线，周月线需重采样管线 |

**本轮修复的两个真 bug（请逆向 Agent 关注根因，同类问题已复发三次）**

1. **技术指标与 K 线复权尺度偏离**（600330：`ema_5=113.26` vs qfq 收盘 `21.97`，差 5.06 倍）。
   根因三层：因子表 hfq vs K 线 qfq@K线末日 的固有口径差；SaaS 优先下发 worker gzip 快照且永不失效
   （1013/1013 个存量产物全错）；`_latest_adj_factor` 取全局最新日，区间结束后再除权即除错倍数（**这条是"修了又坏"的真因**）。
   已修：锚点必须传 K 线最后交易日；1013 个产物按正确锚点 rescale；缺 `factor_basis` 的产物一律拒发。
2. **切 TradingView 视图双图叠加**。`#chart-kline` 是 ECharts 与 LWC 共用容器，两个引擎各自只清自己创建的 DOM。
   已修：新增 `klineDisposeEngines()` 双清 + 兜底清空容器。真实浏览器实测修复前容器 2 子元素、`scrollHeight` 400→800。

---

### 2.2 作图（~5%）

**已具备**：`symbol.html` 工具栏 `kt-trend` / `kt-horizontal` / `kt-clear`

- 趋势线：两次点击确定起点/终点
- 水平线：一次点击确定价格
- 像素→真实坐标：`klinePixelToPoint()` 经 `convertFromPixel` 反算，无法转换时降级**不造点**
- Esc 取消进行中的趋势线；`kt-clear` 清除全部
- 画线不进入重播（`klineDrawApply` 只在静态图生效）

**未具备**（对照逆向报告 §S5「`10092.*` 里去重 94 个工具」）

- 其余 92 种工具：Fibonacci 全族、矩形/椭圆/通道/Pitchfork/Gann/艾略特波浪、文本注释、测量工具、形态标记
- **端点拖拽、整体拖动、单线 Delete**（逆向报告 §S9 demo 明确有这三项，我们只有「清除全部」）
- 画线持久化（刷新即丢）
- 工具属性面板（颜色/线宽/样式/延伸）

**原因与判断**：我方产品是**回测结果查看器**，用户看的是「策略在这只股票上赚没赚钱」，不是技术分析工作台。
作图能力对核心链路价值低。**建议本轮及下轮都不投入作图**，除非用户明确要求。
若将来要做，最大难点是 ECharts 无内建作图框架（需在 zrender 层自建），LWC 也无官方作图插件。

---

### 2.3 高级指标（~60%，按"本地可算"口径）

**已具备**

- **895 列因子入库**：Tushare 202 因子复现 177/202（88%）+ Alpha191 全套 + Alpha101 31 列 + 基本面 PIT 面板（14.12M 行 × 90 列）
- **display 合同固化**（`configs/factor_registry.json` 为单一权威）：每个 canonical 带
  `chart_type / panel_id / role / series_type / axis / precision / color / price_basis / render_order`
- **呈现规则已统一**：EMA/均线/BOLL 一律 overlay K 线主图；MACD/PPO/PVO 同参数 DIF+DEA+HIST 同副图；
  KDJ/STOCH 等同副图；RSI/风险/流动性/Alpha 默认独立副图
- **中文名 + 别名全覆盖 895/895**，`deploy/saas/metadata.json` 902/902 项带 zh；自然语言入口可命中中文指标名
- **日更接管**（P8：`panel-factors-daily.timer` 每工作日 17:45）
- 指标设置模态：集中切换因子呈现方式（叠加/独立/隐藏）、副图上移下移、单独收起、恢复默认；顺序持久化 `qre_pane_order`

**未具备**

| 项 | 状态 | 原因 |
|---|---|---|
| **Pine 脚本语言** | **刻意不做** | 逆向报告 §5.6 已明确结论：「不要试图 hook pine-facade，它带 auth token 与签名，随版本变；指标要么本地算常见几十个，要么自建 Pine 子集解析器（**半年量级的活**）」。我们选择"本地算"路线 |
| 指标参数面板（用户改参数即时重算） | 未做 | **硬约束：ECS 无行情库**，因子是预计算 + 日更，不是实时计算。任意参数即时重算需要把行情库上云或做远端计算服务 |
| TV 的指标库（上千个社区指标） | 未做 | 同上，且无 Pine 运行时就无法运行社区脚本 |

---

### 2.4 K 线回放（~70%）

**已具备**（对照逆向报告 §S5 的 `ReplayWidget` / `switchToReplay` / `isInReplay` / `setReplayStatus` / `generateReplaySymbol`）

- 切片渲染：`[0, cursor]` 截断渲染（对应 `replay.pos`）
- 播放/暂停、**单步前进**、**四档速度**（1/2/5/10x）、进度条 seek、起始日选择、**空仓快进**（跳到下一个有事件或持仓变化的交易日）
- 事件流：orders 优先（含真实下单价量），round_trips 兜底；同日聚合按 sym 去重计「只」并披露笔数
- 策略级重播（`job.html`）+ 个股重播（`symbol.html`），共用 `static/replay.js`
- 防未来数据：进入重播停用工具栏 + 清空信息区；T+1 相隔三条红线；末帧指标与静态报告强一致
- TV 化首片：复用静态 TV 布局（右侧标尺、顶部信息区、`axisPointer` 右置透传）
- 性能：`visibleWindow()` 240 点视口裁剪，4000 点 rAF **45.8ms → 16.8ms**

**未具备**

| 项 | 状态 | 原因 |
|---|---|---|
| **LWC 重播 adapter（阶段 3）** | **未做** | 重播仍走 ECharts，进入重播前销毁 LWC 实例。这是 B 路试点遗留的最后一环 |
| **单步后退** | 未做 | 逆向报告 §S9 demo 明确「单根前进/后退」；我们只有单步前进 + 进度条 seek（seek 可回退，但无专用后退按钮） |
| 键盘快捷键（空格播放/暂停、左右单步） | 未做 | 未排优先级 |
| 增量 append 渲染 | **刻意不做** | 已实测论证：裁剪后单帧 `setOption` 均值 2.03ms、p95 2.8ms，`windowDisplayData` 0.022ms/帧，相对 16.7ms 预算有 8× 余量；增量 append 收益 ≤2ms/帧却要改重播热路径，风险收益比不成立 |

---

### 2.5 协议层（N/A，**需要逆向 Agent 确认**）

我们不对接 `tradingview.com` 的 pushstream / pine-facade，因此：

- `prepareEncodeMessage(e,t){return JSON.stringify({m:e,p:t})}` —— 不适用
- `message-pipe` 传输层 —— 不适用
- ws `~m~<len>~m~` 分帧 —— 不适用。
  **2026-10-29 更正**：逆向侧已确认分帧为 `~m~<len>~m~`（证据：
  `tv-recon/allchunks/41793.29a2aa4ce1c29ee9eec5.js` 的 `WSBackendConnection`，
  `~m~` 常量 + `_encode`/`_decode` + `~h~` 心跳 + `~j~` JSON；datafeed 跑在此通道上，
  见 `bundles/66286…js` 的 `new TVChartApi(window.WSBackendConnection)`）。
  我方原文"实测 200+ chunk 命中 0，未定"引用了逆向侧当时的错误结论（只扫了 201/608
  个 chunk），**作废**。分帧事实已定，但与本项目无关（我们不接 tradingview.com）。

我方数据链路：tushare → pgsql（TimescaleDB hypertable）→ 因子计算/日更 → SaaS API → 前端。

**请逆向 Agent 明确：是否需要我们复刻 TV 的 datafeed 协议？** 我方判断不需要，除非未来要做实时行情推送。

---

## 3. 三个 K 线实现副本（请逆向 Agent 注意：改一处不等于改全部）

| 位置 | 用途 | 图表库 | 因子呈现 |
|---|---|---|---|
| `gui/saas/templates/symbol.html` | 公网个股回测详情（**TV 化主战场**） | ECharts + LWC 双引擎 | 走 `factor-layout.js::plan()` |
| `gui/static/replay.js` | 策略级 + 个股级重播（`job.html` / `symbol.html` 共用） | ECharts | 走 `plan()`，多因子副图 |
| `gui/game/templates/game.html` | 《我不是股神》游戏 | ECharts | overlay 挂 grid 0，副图 grid 2+i |
| `gui/saas/templates/job.html` | 策略级详情 | ECharts | **无 K 线、无因子**，只有收益率曲线 |

**这就是"指标呈现问题反复出现"的结构性原因**：前三处各自拼 `grid`/`yAxisIndex`，只有 `plan()` 的归组逻辑是共享的。
display 合同已经统一了「归组」，但没有统一「把归组结果映射成图表 option」这一层。

---

## 4. 本轮已验证的验收证据

- 全量测试：`3011 passed, 24 skipped`
- 真实浏览器（Chromium + 生产同款 echarts/LWC）：双引擎切换 8 轮零 pageerror，容器恒 1 子元素
- 线上复扫：1013/1013 个产物 `factor_basis=qfq_anchor_v1`；600330 `ema5/收盘 = 0.9883 / 1.0029 / 1.0180`
- 40 个随机产物用自身 qfq K 线重算：EMA 比值中位数 2.677 → 1.0001，MACD 1.434 → 0.9999
- ECS 已部署（qre-saas MainPID 542952），`/saas/jobs/58/symbols/920832.BJ` 200

证据目录：`.tmp/engine-excl/`（双引擎）、`.tmp/factor-display-contract/`、`.tmp/replay-boundaries/`、`.tmp/night-mode/`、`.tmp/card-fx/`。

---

## 5. 难点清单（按"卡住的程度"排序）

1. **ECS 无行情库**（最硬的约束）。行情库在家用机（`tushare_data`，513GB），ECS 只有 SaaS 小库。
   后果：① 不能在 ECS 重算因子，只能改快照（本轮 1013 个产物补救就是这么做的）；
   ② 无法做 TV 式「任意指标任意参数即时重算」；③ 本地 run 产物已清空，worker 的按需详情生成对这些 job 无效。
2. **三处 K 线实现不同步**。见 §3。display 合同只统一了归组，没统一 option 组装。
3. **双引擎并存的生命周期管理**。ECharts 与 LWC 共用 `#chart-kline`，各自只清自己 DOM，
   叠加 bug 就是这么来的；重播还要接管同一容器。已收敛到 `klineDisposeEngines()` 单点，但仍是双轨维护成本。
4. **复权口径是三套并存**（因子表 hfq / 引擎 hfq / K 线呈现 qfq@K线末日），任何一环锚点取错就整体偏离。
   本轮已把锚点日期纪律写进 `20_DATA_DICTIONARY_DAILY_MINUTE.md` §6 硬规则，但**这是概念负担不是代码负担**。
5. **测试 harness 的"抽取区窄于依赖"陷阱**。多个 Node vm harness 只抽取 `renderKline` 函数体，
   一旦它依赖的新helper 定义在抽取区外就 ReferenceError；更早还有用普通数组冒充 `HTMLCollection`
   把线上必抛的写法测成绿灯。**VM 单测全绿 ≠ 生产正确**，本轮所有改动都补了真实浏览器验证。

---

## 6. 需要逆向 Agent 重点回复的三个问题

### Q1. MACD 的 DIF/DEA/HIST 是否真的各自坐标系？（用户反复反馈，未定论）

用户原话：「在 MACD 指标中，MACD 的 dea、dif、hist 又是各自的坐标系」。

**我方代码现状**（已核对，逻辑上应该是同一坐标系）：

- `factor-layout.js::familyOf()` 对 `macd_12_26_9` / `macds_12_26_9` / `macdh_12_26_9`
  正则匹配 `^(macd|ppo|pvo)(s|h)?_(.+)$`，三者 `bkey` 同为 `macd_12_26_9` → 归为一组
- `renderKline` 里 `panes.forEach((p,i) => p.series.forEach(s => ... xAxisIndex: 2+i, yAxisIndex: 2+i ...))`
  → 同组全部 series 共享一个 grid + 一个 yAxis

**所以要么是**：① 产物因子缺 `display` 元数据且列名不匹配正则（走了逐因子独立副图回退）；
② ECharts 多 series 同 grid 时的**图例/视觉呈现**让用户误以为是各自坐标系；
③ 用户看的是《我不是股神》游戏页（`game.html` 有自己的 grid/yAxisIndex 拼装，虽结构相同但是另一份代码）。

（已排除 `job.html`：该页只有收益率曲线，完全不渲染因子与 K 线。）

**请逆向 Agent 给出判据**：如何在浏览器里一次性确认「这三个 series 是否真的在同一个 yAxis 上」？
（我方打算用 `chart.getModel().getComponent('yAxis')` 或 `convertToPixel` 反算验证，但想听你的方案。）

### Q2. 下一轮 TV 化主攻方向：LWC 扶正，还是继续增强 ECharts？

现状：ECharts 是默认且功能完整；LWC 是可选试点，阶段 0–2 完成、阶段 3（重播）未做。

| 路线 | 优点 | 代价 |
|---|---|---|
| **A. 继续增强 ECharts** | 已有 display 合同、重播、夜间模式、测试资产；迁移风险最低 | 与 TV 视觉仍有差距（用户明确指出"静态 K 线图和 tradingview 有较大区别"） |
| **B. LWC 扶正为主引擎** | 视觉/交互最接近 TV；standalone 构建体积小 | 要补重播 adapter（阶段 3）、作图、指标面板；attribution 合规要重新评估；双轨变单轨的迁移期要维护两套 |

**我方倾向**：短期（下轮）继续 A，把「专业价格格式化框架 + 单步后退 + 键盘快捷键 + MACD 同副图视觉确认」做完；
LWC 扶正作为独立立项，等 A 的这些差距补完再评估。**请逆向 Agent 评估这个判断。**

### Q3. 作图能力要做到什么程度？

我方判断：回测结果查看场景不需要 TV 那 94 个工具，建议**只补 demo 已有的三项**（端点拖拽、整体拖动、单线 Delete），
不扩工具种类。**请逆向 Agent 判断这个边界是否合理。**

---

## 7. 我方建议的下轮优先级（供逆向 Agent 参考）

1. **P0**：MACD 同副图视觉确认 + 若确实分裂则修（用户已反馈多次，信任成本最高）
2. **P0**：专业价格格式化框架（对数/百分比/指数化轴 + 自动精度）——这是"和 TV 差距最大"的单点
3. **P1**：重播单步后退 + 键盘快捷键（空格/左右单步）
4. **P1**：画线补端点拖拽 / 整体拖动 / 单线 Delete（不扩工具种类）
5. **P2**：`factor-layout.js` 增加「归组结果 → 图表 option」的共享映射层，消掉 §3 的三处重复
6. **P2**：LWC 重播 adapter（阶段 3）—— 仅在 Q2 判定要扶正 LWC 时才做
7. **不做**：Pine 解析器、TV datafeed 协议复刻、Volume Profile、多品种同图、周月线周期

---

*本文档由 QRE 主 Agent 于 2026-10-28 撰写。所有"已具备"均有代码位置或实测证据；标注「未验证」的是尚未确认项。*
