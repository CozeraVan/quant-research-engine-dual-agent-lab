# Agent State

This file is the source of truth for single-agent workflow recovery.

### 2026-10-26 STANDING RULES（每次交互必须执行）

1. **先部署后验收再提交**：任何 AI agent 的代码/UI 改动完成后，备份生产文件并直接部署 ECS，不再询问部署许可；用户人工验收通过后才 commit/push，不通过立即恢复上一版本。文档-only 无需同步 ECS。详见 `02_LOCKED_REQUIREMENTS.md` R-DEPLOY-001。
2. **新 UI 禁止灰色小字备注**：任何新页面/UI 改动不得新增 `.opt`、muted/faint 辅助段落或灰色小字行内说明；必要解释统一使用 `tip-trigger` + `data-tip` + `LabUI.helpTips`。详见 R-UI-001。
3. **完整 TodoList 不得被阶段短清单覆盖**：只允许更新单项状态或调整优先级，挂起项保留。
4. **权限改动必须同步 9090**：权限/配额/限流变更在 commit/push 前必须完成管理台可视化，展示真实生效值及必要计数；展示与执行共用权威策略来源。详见 `02_LOCKED_REQUIREMENTS.md` R-ADMIN-001。

### 2026-10-28 HELP-SIDEBAR-GLASS-PILL-V2 竞稿已部署，等待用户在 V1/V2 间择优，未 commit/push

V1 上线后用户反馈「不满意」（未给具体点），本稿为重做竞稿。**同一份 CR 内追加「V2 竞稿（step-5，2026-10-28）」一节，文件与选择器全部不变**（`static/help-nav.js` / `lab-theme.css` / `night-mode.css` / `help.html` 的 `.help-pill` 与 `aria-current="true"`），两版可在生产直接对调；`help.html` 本轮未改（V1 的胶囊元素与脚本引入原样够用）。**玻璃**：V1 是一层实底 `rgba(103,80,164,.12)` + 纯色 1px 边框 + 顶/底两条 inset 白线；V2 改成五层叠成——半透明紫底 `.13` + 顶部受光渐变（白 52%→透明 48%）+ `::before` 配 `mask-composite:exclude` 的 **1px 渐变描边环**（顶 100% 白→两侧 32% 紫→底 16% 紫，四圈一圈细高光）+ 顶部 1px 高光与底部 1px 压深（玻璃厚度）+ 贴地接触影与环境投影；`backdrop-filter:blur(7px) saturate(1.35)`；`@supports not` 降级仍为不透明 `--tint`。**位移**：V1 是 5 段 WAAPI 关键帧；V2 改为 **rAF 弹簧数值积分**（半隐式欧拉，子步 1/240s），角速度恒定 12.25 rad/s、**阻尼比随距离在 0.62→0.80 自适应**，绝对过冲稳定 3~6px；连点中断从当前速度续滑。**拉伸/回弹**：V1 按**位移量**算 `scaleY`（`1+clamp(|dy|/h*.09,0,.18)`）且恒定 `scaleY` + `top/bottom center` 切换——**≤760px 双列 grid 里横向移动却仍做纵向拉伸，方向与形变相反**；V2 由**速度在移动方向上的投影**导出（`|投影|/1500` 归一，上限 12%），朝目标飞是拉伸、过冲回冲时投影转负自动翻成压扁，并按主轴做**体积补偿**（垂直轴反向收窄 34%），`transform-origin` 固定 `center`；到位另有一条**闭式阻尼振荡** `amp·sin(ω_d t)·e^{-ζωt}` 补压扁，相位锁在积分器**实测穿过目标那一帧**，幅度按距离给（有下限），短距移动也有清晰回弹。**辅助视觉**：当前项 `--lav-deep`/600；hover 只作用于非当前项且不画描边（V1 悬停当前项会再描一个边框与胶囊高光抢戏）；`:focus-visible` 改 `--lav-deep`；首次出场用闭式阶跃响应从 0.82 弹到 1。**顺带修复**：① 滚动监听改 rAF 节流；② `#hash` 打开先锁 1.5s；③ 点击锁定释放时若被点节仍在可视区则保持它（否则滚到页面最底部高亮会跳回上一节）。**测试**：`tests/test_saas_help_nav.py` 仍 7 例、覆盖扩充（五层玻璃 token、mask 合成、`moveParams`/`springStep`/`oscillate`/`stepResponse`/`impactScale`/`deformScale`/`axisFor`/`scaleFor`/`crossedTarget`）；相关 127 passed；全量 2988 passed, 24 skipped。**生产（R-DEPLOY-001）**：MainPID 522582，回滚副本 `/tmp/qre-deploy-20261028T050502Z.bak`；无头 Chromium 按 25ms 采样 `getComputedStyle().transform`：139px 位移峰值 `scaleY 1.060`（`scaleX` 0.980）→ 过冲 5.6px → 压扁 `scaleY 0.961`（`scaleX` 1.013）→ 回冲 1.010 → 725ms 整定归 1；278px 远跳峰值 1.097、压扁 0.953；375 横向跨列峰值 `scaleX 1.066`（`scaleY` 0.978）、压扁 `scaleX 0.966`；夜间五层 token 全生效、文字 `rgb(200,172,214)`/600；375 无横向滚动、跨列对齐 148 vs 147.5；reduced-motion `anims=0`/`sy=1`；焦点环 `solid 2px rgb(74,58,120)`；`#hash` 与末项锁定均正确；零 pageerror/console error。截图与采样表 `.tmp/help-pill-v2/`，V1/V2 并排对比 `.tmp/help-pill-v2/ab/`。**未 commit/push**：等待用户择优；若选 V1，恢复 V1 三个静态文件并同步回退测试与 CR。

### 2026-10-28 DATA-INCIDENT 已恢复待人工复核，未 commit/push

**主 Agent 操作失误造成的数据事故，已完整恢复。** 清洗 26 只 920xxx.BJ 的上游坏 tick（79 行）时，UPDATE 漏掉 `low < 0.2*close` 守卫，条件退化为 `low < LEAST(open, close)`——这是「当天跌破开盘价与收盘价」的**正常行情**描述，全市场命中 13,292,037 行。污染：`stock_daily.low` 13,292,072 行 + `open` 38 行；`high/close/vol/amount` 未动。**无备份可用**（PITR off、无 tushare_data dump、ECS dump 是 SaaS 库）。**恢复**：Tushare `pro.daily(ts_code=...)` 按 symbol 全量重拉，5779/5779 成功 0 失败、16,907,061 行进影子表 `stock_daily_repair_20261028`（69 分钟）；先验证「重拉值与我备份的 79 行逐列一致」+「20 只 76,602 行上 high/close/vol/amount 与现有数据 100% 吻合」，再回写 open/low，影响 **13,292,072 行（与污染数精确相等）**；最后用正确作用域清洗 open 38 行 / low 79 行。**校验全绿**：清洗后 `open<0.2*close`/`low<0.2*close` 均 0；全市场 OHLC 不变量违反 0；未污染样本上 low 偏差 79（即已知坏 tick）、pre_close/change/pct_chg 偏差 225/1,580,772（0.014% 上游 revision）。**残留风险**：1329 万行原值不可恢复，现为 Tushare 当前值；按未污染样本的 revision 率估计最多数百行 `low` 为上游 revision 值而非库内原值。**纪律已写入 AGENTS.md「Data Mutation Discipline」四条**：①生产表 UPDATE 前必须跑同 WHERE 的 COUNT 并与已知量级对账，差一个数量级即中止；②数据修复一律先影子表 + 审计表 + 人工换名（参考 `quant_ts/rebuild_daily_raw.py`）；③备份范围必须覆盖改动范围；④分析到落地的条件逐字核对。影子表 `stock_daily_repair_20261028`（17,378,586 行）暂留作审计，用户确认后可 DROP。详见 `docs/agent/change_requests/CR-2026-10-28_data_incident_low_overwrite.md`。

### 2026-10-28 HELP-SIDEBAR-GLASS-PILL 已部署待人工验收，未 commit/push

DeepSeek 实施、Kimi 复核部署。`/saas/help` 侧边栏原**无当前项高亮、无任何 JS**，本轮全新实现。**实现**：`static/help-nav.js`（IIFE，导出 `window.QREHelpNav`：纯函数 `clamp/round/direction/stretchScale/transform3/transformFor/motionKeyframes` + `init()`，带 `typeof document` 守卫供 Node vm 断言）；`help.html` nav 内加单个 `<span class="help-pill" aria-hidden="true">` 并在 `{% block scripts %}` 引入；`lab-theme.css` 追加 `.help-jump{position:relative}` 与 `.help-pill` 玻璃/高光/`@supports not (backdrop-filter)` 降级/`prefers-reduced-motion` 规则；`night-mode.css` 末尾覆盖 4 个 token + 当前项文字色。**动画**：用 `Element.animate` 播 5 帧关键帧（外层 `easing:'linear'`，每帧自带 easing，避免二次平滑）：0%(起点 scaleY=1) → 46%(路程 55% 处 scaleY=stretch) → 72%(终点压扁) → 88%(终点过冲) → 100%(终点 1)；前段 `cubic-bezier(.22,1,.36,1)` 缓出、后段 `cubic-bezier(.34,1.56,.64,1)` 回弹；`stretchScale(dy,h)=1+clamp(|dy|/h*0.09,0,0.18)`（上限 18%，由位移距离驱动）；`transform-origin` 按上移/下移切 `bottom center`/`top center` 保证朝移动方向拉伸。**玻璃**：`rgba(103,80,164,.12)` + `1px rgba(103,80,164,.22)` + `backdrop-filter:blur(6px) saturate(1.15)`；**细高光**：`inset 0 1px 0 rgba(255,255,255,.78)` + `inset 0 -1px 0 rgba(255,255,255,.18)`。**功能**：`IntersectionObserver` 追踪七个 `.help-sec`（点击锚点立即移胶囊 + 平滑滚动；带 hash 打开正确定位；resize 重算不播动画）；`aria-current="true"` 写当前项；`:focus-visible` 焦点环。**降级**：`prefers-reduced-motion` 关闭全部动画（实测 `anims=0`、`transitionDuration=0s`）；`@supports not (backdrop-filter)` 用不透明 `--tint`；窄屏 ≤760px 双列 grid 下按 `offsetLeft/offsetTop` 定位（375 实测 `scrollWidth==innerWidth`、跨列定位正确）。**测试**：新增 `tests/test_saas_help_nav.py` 7 例（模板合同/无新增灰字/CSS 胶囊合同/布局锁定规则未动/夜间 token/JS 接线/Node vm 纯函数）；相关 127 passed；**全量 2988 passed + 24 skipped**。**生产（R-DEPLOY-001）**：MainPID 520962，回滚副本 `/tmp/qre-deploy-20261028T040519Z.bak`；Kimi 用无头 Chromium 独立复测（采样 computed transform，非内联样式）：点击跨 5 项时 `scaleY 1→1.18`（t=25~251ms 移动中持续拉伸）、到位先压扁至 0.90 再过冲 1.048 最后归 1.0，位移 0→231 平滑收敛；夜间 `rgba(155,132,216,.2)`/`rgba(200,172,214,.34)`/高光 `rgba(241,237,248,.26)`/文字 `rgb(200,172,214)`；375 无横向滚动；reduced-motion 零动画；全程零 pageerror/console error；截图 `.tmp/help-pill/`。**未 commit/push。** 建议提交 `feat(ui): 使用说明侧边栏玻璃胶囊当前项指示器`。详见 `docs/agent/change_requests/CR-2026-10-28_help_sidebar_glass_pill.md`。

### 2026-10-28 ANNUAL-FLOOR 已部署待人工验收，未 commit/push

job#66 的 920556 个股详情「持仓期年化收益 5051142288902.57%」已修。**根因**：该股 3 笔交易全在 2015-03~05，持仓暴露度仅 1.05%（约 24/2295 交易日），区间收益 945.61%；原公式 `(1+9.456117)^(252/24)−1` 属**外推**，指数把收益放大到失真。上一轮 a1516f0 只把分母从「equity 条目数」换成「实际持仓交易日」，对本例反而让指数更大。**修复**：`lab-ui.js` 新增 `ANNUAL_MIN_TRADING_DAYS = 252` + `holdingAnnualized(sRet, heldDays)` + `holdingAnnualNote(heldDays)` 单点实现（`sRet` 非有限 / `1+sRet<=0` / `heldDays<252` 一律 null，结果非有限也 null）；`symbol.html` 与 `job.html` 的 `exposureCards()` 改调 helper 并**删除模板内自带的 `Math.pow(1 + sRet, 252 / heldDays)` 公式**（收敛单点防漂移）；tooltip 补明年化下限。**测试**：`tests/test_lab_ui_holding_days.py::TestAnnualFloor` 覆盖 920556 复现数、251/252/253 边界、两年几何年化、null/NaN/Inf/-100%/-200%/0 天等非法输入、达到下限后的极大收益有限；源码合同要求两模板必须用 helper 且不得再自带公式；相关 7 passed；**全量 2975 passed + 24 skipped**。**生产（R-DEPLOY-001）**：MainPID 519969，回滚副本 `/tmp/qre-deploy-20261027T023846Z.bak`；920556.BJ 显示「—」且悬停为「持仓期不足一个完整年度（24 < 252 交易日），年化不成立」，爆表值消失；920932.BJ `350.70%`、920284.BJ `121.65%`、job#66 策略页（暴露度 80.91%）`-2.38%` —— 长持仓年化仍生效。**数据体检（未修，待用户决断）**：`stock_daily` 中 `low < 0.2×close` 的异常行全市场仅 **79 行 / 26 只**（占 5860 只的 0.44%），**26 只全是 `920xxx.BJ`**，年份集中 2015(51)/2016(19)/2017(8)/2020(1)——与「新三板-era 数据质量差」判断一致；920556.BJ 有 9 行（如 2015-03-16 low=0.01 / close=19.1）。只污染 `low`（个别 `open`），收盘价类信号不受影响，intrabar 止损与 ATR/波动率因子在那些日期失真。**未改任何数据、未跑回测。** 建议提交 `fix(saas): 持仓期年化加完整年度下限，修复 920556 爆表`。详见 `docs/agent/change_requests/CR-2026-10-28_annual_floor_and_neeQ_ticks.md`。

### 2026-10-28 B 路 LWC 试点阶段 0–2 已部署待人工验收，未 commit/push

TradingView 化 B 路（Spike 续篇）。**阶段 0 决断**：产品负责人提供品牌资产（`/home/van/logo/A股回测台-brand-assets/`），attribution 采用「保留 LWC 默认文本链接 + 自绘品牌水印」（`attributionLogo:false`），其余 UI 设计由 DeepSeek 子代理决断；LWC 5.2.1 vendored 进 `static/chart-core/vendor/`（禁 CDN，与 echarts.min.js 同级），Apache-2.0 LICENSE 随包分发，版本锁死 sha256 `e21cc5caa0226ef30bd8549c50b9ef926615f2a4ee6b4e486353477a55f598cf`，升级必须重跑 Spike 基准。**阶段 1**：`static/chart-core/kline-lwc.js` 的 `QRELwcAdapter` 纯函数适配层（不碰 DOM、不依赖 LWC 全局，Node 可断言）：OHLC 合同序 open/close/low/high → LWC open/high/low/close、日期升序去重（后写覆盖）、`null` → `{time}` 空点、成交量/overlay/histogram 逐点正红负绿、marker 红买绿卖（arrowUp/belowBar、arrowDown/aboveBar、size:2）、阈值线挂 pane 第一条 line、主题双套（红绿色相恒定 + 暗色紫系提亮，与 night-mode.js 映射一致）、高度公式与 replay.js 同源。**阶段 2**：`symbol.html` 新增 `renderKlineLwc()`、引擎开关 `localStorage['qre.kline.engine']`（默认 `echarts`，ECharts 路径逐字节保留作回滚）、DOM 图例 `#kline-legend`（LWC 无图例）、attribution 行 `#kline-attrib`（品牌水印 24px + TradingView 链接）；三处渲染调用点走 `renderKlineDispatch`；「指标设置」模态底部加引擎切换按钮；重播进入前 `lwcDispose()` 防同容器双 canvas；`document.addEventListener('qre:themechange')` 给 LWC 换肤。**API 三处实测校正（勿再凭记忆）**：standalone 构建无 `addCandlestickSeries/addLineSeries/addHistogramSeries`，必须 `chart.addSeries(LWC.CandlestickSeries, opts)`；`createChart` 用 `autoSize:true` + 容器显式高度（固定 width 会 375 溢出）；`qre:themechange` 是 non-bubbling CustomEvent，必须监听 `document`（window 收不到）；`createSeriesMarkers` 首参必须是 series。**阶段 3 未做**：重播仍走 ECharts。**测试**：新增 `tests/test_lwc_kline_adapter.py`（适配层纯函数 + 源码合同）；四个 Node harness 补 `localStorage`/`document.addEventListener`/`setChipState`；三处源码抽取正则放宽为 `klineResizeBound → load() 前`；`test_no_forbidden_deps` 改为禁 CDN/绝对 URL 资源并允许 attribution 外链；相关 132 passed；**全量 2972 passed + 24 skipped**（2 例存量 ConsoleOps 失败与本次无关）。**生产（R-DEPLOY-001）**：MainPID 518848，回滚副本 `/tmp/qre-deploy-20261028T015314Z.bak`；真实浏览器验证蜡烛红绿/成交量/MACD 副图（DIF/DEA + 正红负绿柱 + 0 轴阈值线）/买卖三角 marker/右侧标尺/图例 4 pill/顶部信息区全因子值/TradingView 链接 + 品牌水印（深色自动换白版）/图例隐藏恢复/主题换肤/切回 echarts 后 attribution 与图例正确隐藏/重播进出无双 canvas/375 `scrollWidth==innerWidth`，全程零 pageerror 与 console error；截图 `.tmp/replay-bench/shot-lwc-final-dark.png`。**未 commit/push、未跑回测、未改 job.html/lab/游戏。** 建议提交 `feat(chart): LWC K 线受控试点阶段 0-2（适配层 + 双引擎开关）`。详见 `docs/agent/change_requests/CR-2026-10-28_lwc_kline_pilot.md`。

### 2026-10-28 TV-INDICATOR-SETTINGS 已部署待人工验收，未 commit/push

TradingView 化第二阶段。**A 路增量 append 经实测论证不做**：真实生产文件受控基准（`.tmp/replay-bench/bench.py`，route 指向仓库真实 echarts/replay.js，4000 点/3 grid/6 series/200 帧）显示单帧 `setOption` 均值 2.03ms、p95 2.8ms，`windowDisplayData` 0.022ms/帧、`frameMetrics` 0.007ms/帧——Spike 记录的 40.7ms/帧是 `visibleWindow` 裁剪上线前的全量重绘口径，裁剪后总成本 ~2ms，相对 16.7ms 预算有 8× 余量；增量 append 收益 ≤2ms/帧却要改重播热路径，风险收益比不成立，结论写入长期文档防重复立项。**指标设置与面板管理**：工具栏新增 `kt-ind` 入口 → 模态面板（`role=dialog`/`aria-modal`）集中切换因子呈现方式（叠加K线/独立面板/隐藏）、副图上移/下移、单独收起、恢复默认；`factor-layout.js::plan()` 新增可选第三参 `paneOrder`（列出的键前置并去重，未列出的保持相对顺序置后，只动 panes），缺省/空/null/非数组行为逐字节不变；副图顺序持久化在单一 localStorage 键 `qre_pane_order`，非法输入一律降级空数组。`renderKline` 与 `mountKlineReplay` 都传 `paneOrder()`，静态图与重播同序。**边界**：只管理详情产物内已有因子（ECS 无行情库，任意指标取数需另立项）。**测试**：`plan()` 第三参 6 组断言 + DOM 源码合同 + Node harness 交互流（持久化/越界/未知键/hidePane/第三参透传），harness 补 `localStorage` 与 `setChipState`；相关 162 passed；**全量 2964 passed + 24 skipped**（2 例存量 ConsoleOps 失败与本次无关）。**生产（R-DEPLOY-001）**：部署 `symbol.html` + `factor-layout.js`，新 MainPID 512078，回滚副本 `/tmp/qre-deploy-20261027T175206Z.bak`；真实浏览器验证面板开合、MACD 切换隐藏后面板节显示空态、恢复默认后 K 线重建、Esc 关闭，全程零 pageerror/console error；job58/920832、job58/301308、job66/300308 回归 200 正常。**过程教训**：机械移动函数区块时误删 `renderFactorChips` 的 `const slot = $('#kline-chips');`，`ReferenceError` 被 `load()` catch 吞成「加载失败」——VM 单测全绿但生产炸（harness 从不跑 `renderFactorChips`），已用真实页面逐段复现定位；今后对模板的机械移动必须额外跑一次真实页面渲染。**未 commit/push、未跑回测、未改 lab/游戏。** 建议提交 `feat(chart): 指标设置与面板管理`。详见 `docs/agent/change_requests/CR-2026-10-28_indicator_settings_panel_management.md`。

### 2026-10-28 QRE-SAAS-SYMBOL-REFRESH-HTMLCOLLECTION 已部署待人工验收，未 commit/push

job#78 个股详情「加载失败」第二根因已修复。**根因**：`symbol.html::showSymbolDetailRefresh()` 用 `(host.children || []).some(...)` 去重，而真实 DOM 的 `Element.children` 是 `HTMLCollection`（无 Array 的 `some`/`find`），浏览器必抛 `TypeError`，被 `load()` 的 catch 吞掉 → 整页「加载失败，请稍后重试」。**触发条件**：`factor_basis !== 'qfq_anchor_v1' && !readonly`，即「私人 job + 2026-10-27 前写入的旧产物」；经典策略 58/66/74 是 showcase 只读，入口被跳过，所以上一轮只验证只读页面全部通过仍未暴露。**测试盲区（已修）**：`tests/test_gui_saas_pages.py::_SYMBOL_JS_HARNESS` 用普通数组冒充 `element.children`（数组有 `some`），把线上必抛的写法测成绿灯；现改为 `htmlCollectionView()` 的 HTMLCollection 形态（`length`+索引+`item`，无数组方法），并新增 `childById()` 与 `calls.failure === 0` 断言。**修复**：`Array.prototype.some.call(host.children || [], fn)`。**测试**：harness 改完先 RED（复现线上：刷新入口不出现），源码修复后 GREEN；`test_gui_saas_pages.py` 94 passed；**全量 2960 passed + 24 skipped**（2 例存量 ConsoleOps 失败已在 pristine HEAD 复现，与本次无关）。**生产（R-DEPLOY-001）**：部署 `symbol.html`，新 MainPID 510277，回滚副本 `/tmp/qre-deploy-20261027T165032Z.bak`；真实 DOM 断言 `children` 为 `[object HTMLCollection]`、`children.some === undefined`，调用函数不再抛错且幂等（count=1）；用**真实 job#78 产物**（缺 `factor_basis`、`readonly=false`）灌进 `apiFetch` 端到端跑 `load()` → `showSymbolLoadFailure` 0 次、K 线 canvas 渲染、`sym-note` 正常、无「加载失败」文案；job58/920832、job58/301308、job66/300308 回归 200 正常。**未 commit/push、未重写历史产物、未跑回测。** 建议提交 `fix(saas): 修正刷新入口 HTMLCollection 误用导致的个股详情加载失败`。详见 `docs/agent/change_requests/CR-2026-10-28_symbol_detail_refresh_htmlcollection.md`。

### 2026-10-28 QRE-SAAS-SYMBOL-JSON-FINITE 已部署待人工验收，未 commit/push

线上「打开个股回测详情显示加载失败，请稍后重试」已定位并修复。**根因**：`job_58/_symbol_details/301308.SZ.json.gz` 等历史产物因子序列含裸 `NaN`（MACD/EMA warm-up 段在 PG 存的是 `double precision NaN` 而非 NULL）；SaaS 读取出口 `_jsonable` 不过滤非有限浮点，Flask `json.dumps` 默认 `allow_nan=True` 把 NaN 原样写进响应体——非法 JSON，浏览器 `resp.json()` 抛 `SyntaxError`，`symbol.html` 走 catch 显示加载失败。同类问题 2026-10-12 只在 worker 写产物侧修过（`_json_sanitize`），读取出口与历史产物不在保护范围，故复发；job58 抽样 40 只中 8 只失败（全部 301xxx.SZ / 001309.SZ，上市晚、warm-up NaN 占比高）。**修复**：`lab_result.json_safe()` 成为唯一实现（datetime/date→ISO 串、NaN/±Inf→None、dict/list 递归），lab 详情路由、SaaS `_jsonable`（全量 JSON 出口）、worker `_json_sanitize` 三处共用，杜绝「写时干净、读时带毒」；`_fetch_factor_panels` 两处因子查询加 `math.isfinite` 过滤，DB NaN 按缺口处理，新产物自身干净。**测试**：新增 `tests/test_json_finite_contract.py` + SaaS/lab 两处回归，TDD 先 RED 3 例后 GREEN；相关 152 passed；**全量 2960 passed + 24 skipped**（另 2 例 `test_saas_public_beta_ops.py::TestConsoleOps` 为存量失败，已在 pristine HEAD worktree 复现，与本次无关，window=today 口径）。**生产（R-DEPLOY-001）**：`deploy/saas/deploy-ecs.sh app.py lab_result.py`，新 MainPID 508963，回滚副本 `/tmp/qre-deploy-20261027T163118Z.bak`；原始 API `NaN` token 归零；无头 Chromium 打开 job58 的 301308/001309/301018/920832.BJ 全部 200、K 线 canvas 正常、console 干净；job58 + job66 各 80 只严格 JSON 扫描 bad=0。**未 commit/push、未重写历史产物、未跑回测、未改前端交互。** 建议提交 `fix(saas): JSON 出口非有限浮点硬化，修复个股详情加载失败`。详见 `docs/agent/change_requests/CR-2026-10-28_symbol_detail_json_finite.md`。

### 2026-10-27 QRE-FACTOR-ZH-COVERAGE 已部署待人工验收，未 commit/push

剩余 341 列中文显示名维护完成，**341/341 全部维护、未维护 0 列**，中文名覆盖 **554 → 895/895（100%）**，`deploy/saas/metadata.json` 902/902 项带 zh。**命名依据（无一条凭感觉翻译）**：alpha191 191 条逐条对照 `indicators_tushare/alpha191/formulas.py` docstring（GTJA191 编号口径 + DolphinDB 实现口径与 errata 注释）；alpha101 31 条逐条对照官方 486 文档表达式表（`change_requests/factor_specs_p4p5p7.md` §三）；quality 87 / growth 16 逐条对照 `panel_factors/quality.py::compute_all`、`panel_factors/growth.py` results 与 `change_requests/factor_specs_p1p3.md` §三/§四；`_pit_financial_panel` 14 列按 `panel_factors/pit_panel.py` FAMILIES（inc=利润表/bs=资产负债表/cf=现金流量表/fi=财务指标，流量列 `_ttm` 后缀）+ Tushare 标准字段语义；`cdl_doji_10_0_1` = `factors/candle_factors.py` 的 ta.cdl_doji 十字星；`etp5_rank` 与既有 `etp5` 同源。**实现**：`scripts/gen_factor_registry.py` 新增 `ALPHA191_ZH`(191)/`ALPHA101_ZH`(31)/`FINANCIAL_ZH`(119) 与 `_coverage_zh(table, column)`，在 `build_registry()` 的 `if manual.get("zh")` 后以 `elif not entry["zh"]` 挂载——只补空不改名；FAMILY_RULES/MANUAL_ENTRIES/别名/common/core/display 逻辑零改动。`_rank` 列统一「·排名」后缀，未新增别名。**三处口径注记**：`gpm_q` 实现与 `gpm_ttm` 同为 TTM 口径 → 「毛利率(TTM口径)」；`ar_ap_to_revenue` 含 contract_liab 兜底并扣预付款项 → 「预收预付净额/营业收入(TTM)」；`npm_tsh` 按官方语义（非笔误文本）→ 「归母净利润/平均总股本」。**零漂移**：重新生成前后逐字段比对，除 zh 外 0 差异；341 条 null→中文名、0 条覆盖既有条目；与生产旧版（554 zh）比对同样只有 341 处 zh 差异，display 合同未回归。**测试**：注册表/呈现/相关 10 文件 321 passed；**全量 2890 passed + 6 skipped**（与基线一致）；两处测试随覆盖状态更新但契约更严（`test_no_fabricated_zh` 改为「不得空串/不得英文列名冒充 + 覆盖须 100%」；`test_build_factor_groups_zh_falls_back_to_none_for_unregistered` 改用未注册列 `alpha999_unregistered` 验回退）。**真实浏览器（本地 staging 8099 + 生产 SSH 隧道 9090 各一遍）**：902/902 带 zh 且无英文列名冒充；`/saas/new` → 自选因子交易 → 因子弹窗三栏逐级进「Alpha191 量价因子」因子列 30 条全中文名；中文搜索命中（毛利率 13 / 十字星 1 / 五年盈利价格比 2 / 产权比率年度变化 2）；英文列名搜索仍可用；空态正常；零 JS error；证据 `.tmp/factor-zh-coverage/`。**ECS（R-DEPLOY-001）**：核对生产两文件 SHA256 与上一轮基线一致并拉回本地逐字段比对 → 备份 `/tmp/qre-factor-zh-pre-20261027/`（configs/factor_registry.json + deploy/saas/metadata.json）→ scp 两文件并改回 deploy 属主 → **仅重启 qre-saas（新 MainPID 491196）**，`qre-worker` inactive 未触碰 → 两文件生产 SHA256 与本地逐一相等；generator 为开发工具不同步生产。应用层验证（ECS 上 `curl -H "Host: www.aguhuice.com" http://127.0.0.1:8090/...`）：`/api/saas/factors` 902/902 带 zh，`/saas/new`、`/saas/`、`/saas/help`、`/saas/login` 均 200。**未 commit/push、未跑真实回测、未碰游戏与 8092；不通过恢复 `/tmp/qre-factor-zh-pre-20261027/` 两文件重启 qre-saas。** 建议提交 `feat(factors): 维护剩余 341 列中文显示名`。

### 2026-10-27 QRE-DATA-CLEANUP-EXECUTION DONE，未 commit/push

用户批准后删除 `akshare_data`、`aguhuice_test`、`quant_hub`、`aguhuice_local` 和指定旧回测/实验产物；`qre-outputs` 27G→536M，磁盘可用 386G→418G。留档 `/home/van/quant-workspace/backups/local-cleanup-20261027/`：aguhuice_local 全量 dump、akshare 结构+行数（本体不可恢复）、旧文件 manifest。`refresh` 活配置、`saas_uploads`、`market_risk`、`video_packages` 及两个待验收 staging 库保留。8080/8092 HTTP 200；8081 staging 下次使用前必须重建/替换 aguhuice_local。新增 20261019/20/21 三份分钟 CSV 只读检查通过，审计和分钟表仍至 10-16、三日 pending；timer enabled/active，2026-10-27 17:20 CST 自动入库、校验、删 CSV。本轮未手动入库、未清洗、未压缩。M10.4 依赖已批准且 `.venv-ml` 已有 scikit-learn 1.9.0 / pandas 3.0.5 / numpy 2.5.1，未重复安装。

### 2026-10-27 QRE-DATA-CLEANUP-AUDIT 历史只读盘点（当时未清理任何文件/表/库）

**任务书两项前提与事实不符（已如实记录）**：`/home/van/mindata` **已空**（0 文件/24KB，只剩 `mindata/` 与 `mindata/2026/` 两个空目录 inode）；任务书提到的 `qre_saas`/`dbg` **均不存在**。**三项高风险（待用户决定，均未动手）**：①`public.stock_daily_qfq_legacy` **已不存在**（全 schema 搜 `%legacy%`/`%qfq%`=0 条），本地无 `tushare_data` dump ⇒ 方案A（qfq→原始价+adj_factor）**回滚能力永久失去且不可恢复**；②**分钟线压缩缺口 140GB**——922 chunk 中 708 已压缩仅 396MB、214 未压缩 140GB（压缩比 350:1），其中 **213 个早于 T-7 未压缩**（2022-09-01→2026-10-08），违反 20 §3.4；未压缩 chunk 内部 ID 高于已压缩集合，说明是 10-11 那次压缩后新建、再未压；重跑 `compress_minute_chunks.sh` 预计回收 ~139GB；③**分钟线落后日线 10 天**（分钟 2026-10-16 vs 日线 2026-10-26），定时器每天空转。**「已入库」≠「可安全删除」实证**：日志只记录 5 个 CSV 走过先校验后删除；`import_minute_csv.py` 无删除代码 ⇒ 4308 个历史 CSV 属脚本外删除（`mindata/` mtime 23:19 晚于审计最后写入 20:10，顺序对但无轨迹）；数据侧完整（审计 4318 条全 `rows_csv==rows_db`、双向差集 0、抽查 8 日期含磁盘打满重试的 2022-08-22/25/29 → 8/8 MATCH），**但源 CSV 不可恢复**。**可删候选（待确认）**：`aguhuice_test`(7.5MB,0 表)、`quant_hub`(10MB,0 public 表)、`aguhuice_local`(8.9MB,3 users/15 jobs)、`qre-outputs/refresh/incremental` 17G、`gui-console/runs` 5.4G、`backtests` 4.3G、`gui-run` 442M 及约 20 个 7 月 `*_check` 目录。**勿动**：`refresh/registry.json`/`state.json`/`delta/`（活配置）、`saas_uploads`、`market_risk`、`video_packages`、`.tmp/ms-playwright`+`.tmp/browser-venv`、两个上一任务 staging 库。**高风险单项**：`akshare_data` 5.8GB（4 月 tick、无消费者）。**备份缺口**：本地无 `tushare_data` 逻辑备份。**文档修正**：20 §3.6 日志名 `minute_daily_ingest.log` → 实际 `minute_import.log`；20 新增 §7 盘点与 7 项待确认清单、§6 新增 3 条硬规则。**未 commit/push、未跑真实回测、未碰生产/WSL 数据与游戏。** 建议提交 `docs(data): 盘点遗留数据并修正数据字典（qfq_legacy 已失、分钟线压缩缺口）`。

### 2026-10-27 QRE-ECS-SSH-HARDENING 已生效待人工验收，未 commit/push


root SSH 直连已禁，deploy+sudo 为唯一运维入口。**审计先行且抓出锁死风险**：`deploy` 密码锁定（`L`）且 sudoers 仅放通 `systemctl`/`docker` ⇒ `sudo -n` 改动前不可用；直接禁 root 会失去文件安装、PG 备份恢复、证书、防火墙能力。先补 `/etc/sudoers.d/90-qre-deploy`（`deploy ALL=(ALL:ALL) NOPASSWD: ALL`，0440，`visudo -c` 全绿）并修 `sudoers.d/deploy` 0644→0440，之后才动 sshd。deploy 五项实证（改 SSH 前）：密钥登录 uid=1000、`sudo -n`→uid=0、业务文件可读、`/tmp→sudo install→sudo rm` 链干跑成功、deploy 隧道 9091 应用层 200 且 factors 902/902 带 zh。**sshd**：新增 `/etc/ssh/sshd_config.d/99-qre-hardening.conf`（`PermitRootLogin no`/`PasswordAuthentication no`/`KbdInteractiveAuthentication no`/`PubkeyAuthentication yes`/`AllowTcpForwarding yes`，TCP 转发显式保留供 9090 隧道）。**机制记录（防误判）**：sshd 同关键字取先出现者、drop-in 按字典序展开，`99-aguhuice-hardening.conf` 排在前，其 `PermitRootLogin prohibit-password` 会遮蔽新文件的 `no`（实测证明），故该行改 `no`（另两行未动）。`sshd -t` 通过 → `systemctl reload ssh`（不断会话）。**验证**：root 新连接 `Permission denied (publickey)`；既有 root 隧道 reload 后仍 200；deploy 新连接/`sudo -n`/qre-saas active/qre-worker inactive/nginx/ssh 全过；deploy 隧道 9092 与 `admin-tunnel.sh`(deploy@) 起的 9090 均 `/saas/new` 200、`/saas/console` 200；`sudo -n fail2ban-client status sshd` 正常；陈旧 root 隧道已停，现网无 root 会话。**脚本**：新增 `deploy/saas/deploy-ecs.sh`（deploy+sudo 唯一部署入口，`--dry-run`，自带 /tmp 回滚副本，只重启 qre-saas），已用与生产 SHA256 相同的 metadata.json **真实端到端跑通**（MainPID 493988、api 200、生产字节未变），并修掉两个真 bug（scp 远程嵌套目录、内联 `bash -c` 二次转义）；`admin-tunnel.sh`/`pull-ecs-backup.sh` 默认改 `deploy@`；`sync_saas_metadata.py` 注释同步。**测试**：无 `src/` 改动、无测试引用这三脚本；`bash -n` 全过；**全量 2890 passed + 6 skipped**（零回归）。**备份/回滚/救援**：`/tmp/qre-ssh-hardening-pre-20261027/`；回滚两步（删 99-qre-hardening.conf + 改回 prohibit-password → reload ssh；删 90-qre-deploy）均不断业务；云控制台 VNC 救援见 `16_ECS_DEPLOYMENT.md` §6。**未 commit/push、未跑真实回测、未碰 WSL 数据库/worker/因子/UI/游戏。** 建议提交 `chore(ecs): 禁 root 直连并落地 deploy+sudo 部署纪律`。

### 2026-10-26 QRE-SAAS-NL-A1 DONE（DeepSeek 裁判，用户验收发布）


用户批准提交，自然语言规则前置校验与 DeepSeek 裁判已部署 ECS，本次以 `feat(saas): 增加自然语言输入校验与 DeepSeek 裁判` commit/push。最终专项 67 passed、全量 2840 passed + 6 skipped；真实 DeepSeek 分层 12 条评估 0 失败，生产缓存命中零裁判、裁判拒绝占配额、admin 同样裁判、force 与 DB 回退路径一致。游戏内容不纳入本提交。下一主线：P2 重播边界（同日聚合、orders 事件源、多因子副图页）；挂起任务放最后。

### 2026-10-26 QRE-SAAS-NL-A1 复核修正（主 Agent 3 项 Required Fixes 已解决，实施过程）

①领域语境门槛：`DOMAIN_WORDS`/`STRONG_TRADING_WORDS`/`_has_domain_context`——有入出场词但无股票/价格/指标/交易语境至少 review 不得 pass（修「我想买房，之后卖房」「今天买菜后卖给邻居」在无 Jev 生产直接放行）；54 条样本（含 4 条对抗）规则层 54/54，50 条合法样本零误杀。②strategy.html 重编译区隐私/校验 tip-trigger 与 new.html 同源；new.html review 模态补 role=dialog/aria-modal/aria-labelledby。③`force = data.get("force") is True`，字符串 "false"/"true" 不视为确认。TDD RED=8→GREEN；guard 60 passed；相关 6 文件 230 passed + 1 skipped；**全量 2833 passed + 6 skipped**；Chromium 6/6（对抗样本 review 模态；截图几何稳定后拍摄）。ECS 备份 `/tmp/qre-nl-a1-review1-pre-20261026/` 后同步四文件仅重启 qre-saas；公网两条对抗文本 422 review、force 字符串 422、合法 MACD cache_hit=true 不回归；9090 隧道两页 200 且新标记齐全。整任务回滚点仍为 `/tmp/qre-nl-a1-pre-20261026/`。**未 commit/push，待用户人工验收。**

### 2026-10-27 QRE-FACTOR-DISPLAY-CONTRACT 已部署待人工验收，未 commit/push

Step 5 实现，Kimi 复核与部署收尾：canonical 注册表新增完整 display 数据成员（chart_type/panel_id/role/series_type/axis/precision/color/price_basis/render_order），所有页面统一消费；EMA/BOLL 必须 overlay，MACD/PPO/PVO 同副图，panel_id 含价格口径。专项与注册表 59 passed，全量 2890 passed + 6 skipped；真实 Chromium 验证 replay 与夜间切换、375 无横溢。Step 5 两次 2 小时超时后由 Kimi 完成验证部署；ECS 备份 `/tmp/qre-factor-display-pre-20261027/`，仅重启 qre-saas，未跑真实回测、未 commit/push。建议提交 `feat(factors): 统一因子呈现属性与图表合同`。

### 2026-10-27 QRE-SAAS-NIGHT-MODE 已部署待人工验收，未 commit/push

SaaS 全部页面（含 9090 console）新增夜间模式，浅色 token/配色/视觉/排版/文案/数据零变化，唯一新增交互是主题切换按钮（文字 + aria），红涨绿跌保留。7 个产品文件：新增 `gui/static/night-mode.css`（270 行，`html[data-theme="dark"]` 作用域下 8 token：bg `#17153B`/card `#2E236C`/line `#433D8B`/text `#F1EDF8`/muted `#C8ACD6`/accent `#7E60BF`/accent-deep `#C8ACD6`/accent-soft `#2E236C`）与 `night-mode.js`（275 行，`QRETheme` 三态 + `localStorage('qre-theme')` + `prefers-color-scheme` 跟随 + meta theme-color 同步 + `themeChart`）；`static/replay.js` 加图表主题挂钩；`saas/templates/base.html`、`login_callback.html`（内联防闪 + `tt-btn tt-float` 浮动按钮 + 深色 `:root` 兜底）、`job.html`、`symbol.html`。默认跟随系统偏好、手动选择后持久；首帧内联脚本防 FOUC；ECharts 背景/轴/文字/tooltip/系列色随主题改、保留红绿与数据、切换不重算不重排；`#guest-note` 深色告警（`#B4761F`/`#3D3118`）刻意保留；8080/8081 未改。测试：新 `tests/test_saas_night_mode.py` 24 passed，相关 6 文件 148 passed，**全量 2871 passed + 6 skipped**（与基线一致）；真实 Chromium 审计 **138 ok / 0 FAILURES**（exit 0，浅/夜 × 1280/1000/375、切换、reload 持久、系统偏好、无白底岛屿、正文与按钮焦点可读、375 不横溢）；两处判据修正为工具层修正（`<details>` 关闭时 `content-visibility:hidden` 读到过期值 → 先展开再断言；job `tagChart` 为 treemap 无笛卡尔轴 → 仅对含笛卡尔系序列断言轴色）。ECS：5 文件与生产基线 diff 仅夜间模式行 → 备份 `/tmp/qre-night-mode-pre-20261027/` → scp 7 文件（SHA256 与本地逐一相等）→ **仅重启 qre-saas（MainPID 487122）**，worker 未触碰、无 schema 变更；应用层（`Host: www.aghuice.com` → `127.0.0.1:8090`，因域名 DNS/代理不可达，TLS/nginx 未改）new//saas//help/login/console 与 css/js 全 200 且标记齐全。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-night-mode-pre-20261027/` 七文件重启 qre-saas。** 建议提交 `feat(saas): 新增夜间模式（浅色不变）`。

### 2026-10-27 QRE-SAAS-REPLAY-BOUNDARIES 已部署待人工验收，未 commit/push

重播边界核验完成（先证明再修，只改 4 个文件）。**核验已完整（零改动）**：展开/收起、seek 回退、重播重置、重复初始化、markPoints 无未来事件、symbol orders 优先+兜底、多因子 overlay/MACD 同面板/chip 三态/动态 grid·height/接管退出/末帧与静态一致——补 7 例回归锁定。**修复 1**：replay.js 聚合头部原按事件数计「只」（symbol 6 笔同日买单误显示「6 只」）→ `aggHead` 按 sym 去重计「只」+「（M 笔）」披露，`evChipText` 统一 chip 文案（缺字段不拼装）。**修复 2**：`lab_result._trade_points` 在 round_trips.csv 有价量列时补足 quantity/entry_price/exit_price（缺列不加键、仅新 run 生效、不回填）；job/symbol 事件带 sym+价量；旧产物降级纯标的 chip。测试：TDD RED=5→GREEN，新 7 例，相关 6 文件 188 passed，**全量 2863 passed + 6 skipped**；Chromium 10/10 零 JS error 零横溢（job「当日入场 5 只（6 笔）」+6 笔价量明细；symbol「1 只（6 笔）」+末帧 478.00 强一致；375 不破版）。ECS 备份 `/tmp/qre-replay-boundaries-pre-20261026/` 后 scp 四文件仅重启 qre-saas；无 schema 变更。公网匿名 job58 重播全程零 JS error。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-replay-boundaries-pre-20261026/` 四文件重启 qre-saas。** 建议提交 `fix(saas): 修正重播同日聚合计数并补足事件价量`。

### 2026-10-26 QRE-SAAS-NL-A1 路径一致性复核修正已部署待人工验收，未 commit/push

主 Agent 复核 2 个路径一致性 Required Fixes 已解决：①删除 admin 裁判豁免（`if not force`）——管理员不限编译配额，但与会员一样经过 DeepSeek 裁判（原绕过是未经要求的新权限差异）；②DB 故障回退路径仅 `not force` 时裁判（原无条件裁判导致 force 用户在 DB 故障时又被拦回），规则硬拒仍在最前不可绕过。回归：`test_admin_also_refereed`、DB 故障+force 跳过裁判/裁判拒绝拦截/乱码硬拒。TDD RED=2→GREEN；guard 67 passed；相关 6 文件 237 passed + 1 skipped；**全量 2840 passed + 6 skipped**；Chromium 7/7（裁判 prompt 未变，未重复真实评估）。ECS 备份 `/tmp/qre-nl-a1-deepseek-review1-pre-20261026/`（app.py）后仅重启 qre-saas；公网最小复核：MACD 缓存命中 200 零裁判零配额（配额 5→5）、乱码+force 仍 422、jobs/cache 不变、公网三页与 9090 隧道 200。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-nl-a1-deepseek-review1-pre-20261026/` 并重启 qre-saas。**

### 2026-10-26 QRE-SAAS-NL-A1 DeepSeek 方向落地已部署待人工验收，未 commit/push

用户明确暂不配置 Jev，改用现有 DeepSeek（`QRE_NL_LLM_*`）。**删除** Jev/TypeSafe 客户端、环境变量、requests 依赖与 `scripts/nl_jev_eval.py`（无死代码）；裁判复用 `nl_compiler.call_llm` 注入独立裁判 prompt（严格 JSON 三分类 strategy/not_strategy/unclear，无置信度不伪造），故障降级规则层。**编排**：规则层（reject 不可绕过/review 可 force）→ 缓存快路径+锁内复检（**命中零裁判**）→ 配额计数 → **DeepSeek 裁判**（仅 cache miss + 配额后；force 不再裁判；admin 豁免已于同日复核删除，见下条）→ 编译；裁判 not_strategy/unclear → 422 review（不硬拒）且占配额；DB 回退路径同序（`_referee_gate` helper）。缓存 key/YAML/配额数值不动；隐私 tip 改 DeepSeek 措辞。测试：TDD RED=29→GREEN，guard 67 passed，相关 6 文件 237 passed + 1 skipped，**全量 2840 passed + 6 skipped**；Chromium 7/7（新增裁判 review 场景）。真实评估：ECS 生产凭证跑 ≤12 条分层小样本，deepseek-flash 0 失败、延迟 533–1590ms、not_strategy 4/4、strategy 3/4。ECS 备份 `/tmp/qre-nl-a1-deepseek-pre-20261026/` 后同步四文件仅重启 qre-saas；公网计数 jobs 10→10、cache 3→4、events 5→7、guest 配额 3→5（裁判拦截占配额不写缓存；缓存命中零裁判）。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-nl-a1-deepseek-pre-20261026/` 四文件重启 qre-saas。** 建议提交 `feat(saas): 增加自然语言输入校验与 DeepSeek 裁判`。

### 2026-10-26 QRE-SAAS-NL-A1 已部署待人工验收，未 commit/push

NL 编译入口前置校验落地（规则层 + 可选 Jev 第二裁判）。**合同**：`POST /api/saas/nl/compile` 在 empty 检查后执行纯规则校验——reject=422 `nl_input_rejected`（<6 字符/无中英文字符/纯数字/乱码率≥40%/无交易语义且<16 字符）**不可绕过**；review=422 `nl_input_review`（缺入场 missing=entry/缺出场 missing=exit/无交易语义长文本）可由用户确认后 `force=true` 重发（**force 只豁免 review，reject 仍硬拒**）；pass=其余。guard 位于 prompt/缓存/配额/LLM 之前，不占配额、不写缓存、不调 LLM、不建 job。**Jev**：官方 `POST https://api.typesafe.ai/v1/systemone`（Bearer + Choice input_kind=strategy/not_strategy/unclear），`TYPESAFE_API_KEY` 环境读取、`QRE_NL_JEV_MODEL` 缺省 jev-latest、阈值 0.7，直接 requests 无 SDK；strategy 高置信维持结论、not_strategy 高置信/unclear/低置信只升级 review、未配置/超时/非 2xx/结构异常降级规则层；不记录策略文本与密钥。**未真实运行 Jev**（无凭证，评估标记 not_run_missing_credentials，未伪造）。测试：新 `tests/test_nl_input_guard.py` 48 passed；相关 6 文件 265 passed + 1 skipped；全量 **2821 passed + 6 skipped**（基线 2773+6 零回归）。真实 Chromium 5/5 零 JS error 零横溢（`.tmp/nl-input-guard/`）。ECS 备份 `/tmp/qre-nl-a1-pre-20261026/` 后 scp 四文件仅重启 qre-saas（无 schema 变更）；公网 reject/review/force/合法编译合同全部符合，jobs 10→10，nl_compile_events 2→4；9090 隧道两页 200。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-nl-a1-pre-20261026/` 并删除 nl_input_guard.py 重启 qre-saas。** 建议提交 `feat(saas): 增加自然语言输入前置校验与 Jev 可选裁判`。下一主线：按灰度反馈继续修正公网体验；小游戏暂停。

### 2026-10-26 QRE-SAAS-PUBLIC-BETA-OPS DONE（用户验收发布）

用户批准提交，公测运营指标、反馈分类闭环与关键浏览器自动化资产已部署 ECS，本次以 `feat(saas): 新增公测运营指标与反馈分类闭环` commit/push。发布前聚焦 20 passed，全量 2773 passed + 6 skipped；游戏内容不纳入本提交。下一主线：P2 NL A1 输入校验与 Jev 小样本评估；小游戏、移动端/App、压测性能、硬件上云继续挂起。

### 2026-10-26 QRE-SAAS-PUBLIC-BETA-OPS 实施与验收过程

按批准计划完成 §11.3 条目 4「运营反馈闭环」：9090 管理台新增「公测运营」tab（`GET /api/saas/console/ops`，窗口 today/7d/30d/all，admin 门禁不变）——NL 编译次数/成功率/缓存命中率/失败原因 Top5/统计起点（新表 `nl_compile_events`，只存 ok/cache_hit/error_class/scope/created_at，**不存策略文本/API key/原始 IP**，自功能上线起统计、上线前显示「—」）；回测（kind='full'，smoke 与 canceled 不计入）成功率/平均排队/平均执行/失败原因 Top5；游客到注册转化（游客独立会话=guest_key 去重——仅覆盖提交过任务的游客、未提交访客不可见；新增注册=users.created_at；**二者无关联，不计算转化率**——ratio=null + measurement=unlinked，未扩展用户追踪 schema）；反馈按类型/状态计数；分母为 0 → null → 「—」，不编造历史；**today 窗口按 Asia/Shanghai 自然日**。**反馈分类闭环（最小可用）**：feedback 增 category（bug/experience/factor/other，缺省 other）/status（open/doing/done/closed，缺省 open）；提交 allowlist、本人列表透出、console 筛选 + `POST /api/saas/console/feedback/<id>/status` 流转；用户隔离/每日 20 条/admin 鉴权全保留。**NL 编译事件**在四个终态记录（超限 403/429 不计入）。**测试**：TDD RED=17 errors → GREEN；新 `tests/test_saas_public_beta_ops.py` 17 passed；相关 5 文件 227 passed + 1 skipped；**全量 2770 passed + 6 skipped**（基线 2753+6 零回归）。**浏览器自动化资产**（可重复执行）：`deploy/saas/public-beta-audit/`（seed/browser_audit/run_audit，复用 `.tmp/browser-venv` Playwright + `.tmp/ms-playwright` Chromium，未进生产依赖）；真实 Chromium 9/9 零 JS error 零横溢（游客/登录、新建页、NL 编译 stub、任务等待/失败恢复、结果只读与权限、反馈分类、管理台运营指标、375 不破版），证据 `.tmp/public-beta-ops/`。**生产缺陷热修**：feedback_id_seq 缺 USAGE → 提交反馈 500（该特性此前从未部署 ECS；同 share_links 序列坑），已 GRANT 并写入 schema 幂等 DO 块。**ECS**：四文件与 HEAD 基线 SHA256 一致 → 备份 `/tmp/qre-public-beta-ops-pre-20261026/` → postgres apply → scp 五文件 → 仅重启 qre-saas（worker 在家未动）。**生产验证**：临时 admin/member 会话完成 ops 鉴权三态/空口径/反馈闭环；游客真实 DeepSeek 编译两次 cache_hit false→true 且 YAML 一致（A2A3 无回归）；ops all 窗口 nl.total=2/first_event_at=2026-10-26；临时数据清理后 temp_users=0/feedback=0、真实 sessions 未动；9090 隧道 console 200 含 ops 标记、ops API 无 token 401；公网五页 200、/saas/console 仍 404。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-public-beta-ops-pre-20261026/` 并重启 qre-saas。** 建议提交 `feat(saas): 新增公测运营指标与反馈分类闭环`。下一主线：按灰度反馈继续修正公网体验；小游戏/Steam、移动端/App、压测性能、硬件上云继续挂起。

### 2026-10-26 TRADING-GAME-V1-CORE WSL 可玩 Demo 已跑通（未 ECS/未 commit/push）

Kimi 完成 `game/engine.py`、`session.py`、`data.py`、`web.py`、`templates/game.html`：纯交易状态机、随机窗口、匿名逐日揭盲、前复权与现有因子、最小 Web API 和可玩页面。开盘只显示 open，收盘才显示完整 K 线/指标；真实代码/日期/未来数据不下发。复用 core.models、AShareMarketProfile、现有因子和淡紫 UI，ema_250 替代库内不存在的 ema_200。专项 22 passed，全量 2753 passed + 6 skipped；真实 DB 抽样和真实 Chromium 开盘买入通过，1280/375 无横溢/无 JS error，证据 `.tmp/trading-game/`。试玩 `http://127.0.0.1:8092/game`。后续持久化与公网中继另做；不做美术/分时/财报/杠杆/扰动/Steam。主线 9090 NL 可视化已完成并仍待用户验收提交。

### 2026-10-26 TRADING-GAME-V1 长期文档已立项（Kimi 负责，WSL Demo）

用户批准双轨并行：Step 5 继续主线 backlog，Kimi 负责《我不是股神》。长期权威文档为 `docs/agent/22_TRADING_GAME.md`，已写明 V1 随机股票/随机窗口、匿名逐日揭盲、真实前复权数据、限价成交、T+1/整数手/费用、总权益结束条件、复用边界、WSL 环境、公网中继、测试矩阵、Token/工期估算和未来独立化边界。Demo 不做专门美术、分时、财报、杠杆、数据扰动、排行榜或 Steam；先完成 WSL 可玩一局，再考虑公网。主线 9090 NL 可视化仍由 Step 5 推进，A2/A3 未 commit/push。

### 2026-10-26 QRE-SAAS-NL-A2A3 已部署待人工验收，未 commit/push

按批准计划 `mister-terrific-echo-vision.md` 完成 NL 持久限频（A2）与版本化编译缓存（A3）并直接部署 ECS（R-DEPLOY-001，未跑真实回测）。**Schema**：`cloud_schema.sql` 新增 `nl_rate_limits`（scope/subject_hash/window_start/hits/updated_at，PK 三元组；scope=guest_daily 游客每日 10 次 / member_minute 会员每分钟 6 次；admin 不计数）与 `nl_compile_cache`（cache_key PK/description/result JSONB/model/prompt_hash/cache_version/created_at/last_hit_at/hit_count + last_hit_at 索引）；两表无序列，按 share_links 模式角色存在时幂等 GRANT aguhuice CRUD；生产已 postgres apply 并核实表结构与授权。**新模块 gui/saas/nl_compile_support.py**：normalize_description（NFKC+trim+空白折叠）、build_cache_key（规范化描述+model+规范化 base_url+完整 build_system_prompt 哈希+NL_COMPILER_CACHE_VERSION="2026-10-26.1"）、consume_quota_on（单条 INSERT…ON CONFLICT DO UPDATE…WHERE hits<limit RETURNING 原子计数）、cache get/store/touch、pg_advisory_xact_lock(hashtext(key)) 同 key 防重复 LLM（不同 key 不串行）、游客 subject 复用 _guest_key(ip)、会员 sha256("nl:user:"+uid+salt) 截断不落原始 IP。**app.py 编排**：快路径缓存→同 key 咨询锁+复检→配额（游客超限 403/code=guest_nl_limit 原文案不变；会员超限 429/code=nl_rate_limited+scope+reset_seconds，每日仍不限；admin 放行）→compile_nl→仅 ok=true 写缓存→响应补 cache_hit；不改 nl_compiler 编译/纠错/YAML 校验，not_configured 仍 503 且不缓存，`_guest_nl_hit` 文件计数保留为 DB 故障回退（会员 503 fail-closed）。**测试**（TDD 先 RED 后 GREEN，证据 `.tmp/nl-a2a3/` 与 `.tmp/nl-console/`）：RED=24 errors（A2A3 表缺失）+ console 4 failed；GREEN=新 `tests/test_saas_nl_compile_cache.py` 23 passed + 1 skipped（本地无 aguhuice 角色跳过 grants 断言）；console +5 例（常量一致/改动跟随/两表计数/鉴权/页面卡）；相关 4 文件 206 passed；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2731 passed + 6 skipped**（基线 2703+5 零回归）。**临时 PG+8099 staging 真实 HTTP**（stub LLM，不触真实 DeepSeek、不跑回测）A2A3 10/10 + console 3/3（含 Node harness 渲染核验）。**ECS**：基线 SHA256 一致 → 备份 `/tmp/qre-nl-a2a3-pre-20261026/` 与 `/tmp/qre-nl-console-pre-20261026/` → postgres apply → scp app.py/nl_compile_support.py/cloud_schema.sql + app.py/console.html → 仅重启 qre-saas（active，worker 未动）。**公网验证**（临时游客会话，真实 DeepSeek）：经典 MACD 描述纯编译两次，第一次 cache_hit=false（真实调用 LLM），第二次 cache_hit=true 且 YAML 逐字节一致；jobs 表 10→10 未创建回测；缓存行无 API key、model=deepseek-flash、hit_count=1；guest_daily hits=1（命中未占额度）。**管理台同步（R-ADMIN-001）**：`api_console_overview` 新增 `nl` 对象（guest_daily/member_minute 直接读执行常量、admin=不限、cache_version、两表 rate_limit/cache 真实计数），console.html 总览在 Worker 资源卡前新增「自然语言编译」卡（metric 卡 + tip-trigger，无灰色小字）；9090 隧道临时 admin session 验证 overview nl 字段与常量/两表计数一致（匿名/错 token 401），临时 admin 与会话已清理、未输出 token。**踩坑**：①SQLAlchemy 2.0 `engine.connect()` 退出不提交，锁事务须用 `engine.begin()`；②持锁事务内再取连接（配额独立事务）会耗尽连接池死锁——配额改锁事务内同连接执行；③同会员同分钟共享配额行，行锁使该会员并发编译自然串行（原子计数固有属性），「不同 key 不串行」用例改用两个会员验证。**未解决/遗留**：缓存版本覆盖 prompt 与因子目录，后处理变化须手动 bump；同会员同分钟并发按行锁串行；缓存表无自动清理（仅索引）。**未 commit/push，待用户人工验收；不通过立即恢复 `/tmp/qre-nl-a2a3-pre-20261026/` 与 `/tmp/qre-nl-console-pre-20261026/` 并重启 qre-saas。** 验收通过后建议提交 `feat(saas): 增加持久编译限流与策略缓存`。下一主线：公测运营反馈与关键浏览器自动化；小游戏/Steam、移动端/App、压测性能、硬件上云继续挂起。

### 2026-10-26 QRE-SAAS-CLASSIC-ACTIONS-UI + SHARE-HOTFIXES DONE（用户验收发布）

用户批准提交，实现 `e6f4f77` 已 push + ECS。经典策略与结果操作卡精修、分享序列权限热修、分享完整公网 URL 热修均验收通过。最终全量 2703 passed + 5 skipped；生产创建返回完整公网 URL，公开页面与撤销均 200，临时数据清理，app.py/schema/模板/CSS 均已部署。以下同任务实施记录保留作历史。下一主线：NL A2 持久限频与 A3 编译缓存，随后公测运营反馈与关键浏览器自动化。

### 2026-10-26 QRE-SAAS-SHARE-ABSOLUTE-URL 已部署待人工复验，未 commit/push

用户认为新建分享链接无效。核查其实际 summary=200、readonly_kind=share、真实 Chromium 只读渲染正常，token 与权限均有效；问题是创建响应只有相对路径。`api_share_link_create` 改为 `SAAS_PUBLIC_BASE_URL`（缺省 request.url_root）+ 分享路径，生产固定 `https://www.aguhuice.com`。新增绝对 URL 回归，access_hardening 68 passed，全量 2703 passed + 5 skipped。生产创建返回完整公网 URL、公开页面 200、撤销 200，临时数据清理，app.py 哈希一致。备份 `/tmp/qre-share-absolute-url-pre-20261026/`（app.py + 0600 env），未跑真实回测。既有相对链接仍有效，无需撤销。

### 2026-10-26 QRE-SAAS-SHARE-SEQUENCE-GRANT 已部署待人工复验，未 commit/push

用户点击分享结果报 HTTP 500。生产日志确认 `share_links_id_seq` 缺 USAGE（postgres 建表，aguhuice 表 CRUD 已有、序列权限遗漏）。生产 GRANT 后真实创建/撤销 API 均 200；`cloud_schema.sql` 写入角色存在时幂等表+序列 GRANT，新增静态回归。全量测试另暴露 showcase 新库懒建表时序问题，将既有 showcase/showcase_daily 同构定义纳入权威 schema，最终全量 2702 passed + 5 skipped。ECS 已 apply 并验证序列 USAGE=true、两表存在、schema SHA256 一致；临时 session/link 清理，share_links=0。备份 `/tmp/qre-share-sequence-grant-pre-20261026/`，未跑真实回测。请用户再次点击分享结果复验，通过前不提交。

### 2026-10-26 QRE-SAAS-CLASSIC-ACTIONS-UI 已部署待人工验收，未 commit/push

按批准计划 `amadeus-cho-cannonball-cyborg.md` 完成并直接部署 ECS（R-DEPLOY-001，未跑真实回测）：①showcase 删除页头灰字备注/`#sc-hint`/底部灰字长文与弱链接，页头信息移入 H1 旁问号提示，底部改「复现经典策略」tip +「新建同款策略」`btn-primary`（链接仍 `/saas/new`），subtitle 保留；②job 将 `#box-actions`/`#box-share` 合并进 `#result-actions-card`「结果操作」卡（标题 + 问号提示），保存/确认信号=主按钮、信号/分享=次按钮，`action-status`/`share-status` 改 `result-action-status`，信号面板 T+1 风险提示移入扫描范围问号提示；新增空安全 `syncResultActionCard()`（任一组可见才显示外层；游客/只读/无 strategy 整体隐藏），init 两函数全分支同步，不重复绑定；③lab-theme.css 仅加局部规则（按钮 ≥44px、≤768px 纵排/全宽、375px 不横溢）。TDD 先 RED（新 11 + access_hardening 2 失败）后 GREEN：新 `tests/test_saas_classic_actions_ui.py` 12 例（静态断言 + Node 可见性矩阵四形态/连续初始化/失败重试/空安全），3 处既有断言随行为更新；相关 10 文件 289 passed、access_hardening 66 passed、**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2701 passed + 5 skipped**（基线 2689+5 零回归）。真实 Chromium（临时库 `qre_readonly_share_browser` + 8099 临时 staging，worker 协议模拟 completed，未启动真实 worker/未跑真实回测）9/9 零 JS error 零横溢：showcase CTA 与删除标记、三操作按钮层级 44px、信号面板三 scope、confirm 端到端、分享模态、375px 登录态、游客与 showcase 只读整体隐藏；证据 `.tmp/classic-actions-ui/`（7 截图 + browser-evidence.json + red/green/public-verification）。ECS 三文件与 HEAD 基线 SHA256 一致，备份 `/tmp/qre-classic-actions-pre-20261026/` 后 scp 同步 `showcase.html`/`job.html`/`lab-theme.css`，仅重启 qre-saas（worker 未动）；公网 showcase 200（主按钮/删除标记为零/仅剩 subtitle 一处 `.opt`）、job58 200（新卡/sync/只读清单）、`/static/lab-theme.css` SHA256 与本地一致、`/saas/` help login new symbols 两页均 200。**未 commit/push，待用户人工验收；不通过立即恢复 `/tmp/qre-classic-actions-pre-20261026/` 并重启 qre-saas。** 验收通过后建议提交 `refactor(saas): 精修经典策略与结果操作按钮`。小游戏/Steam 继续挂起；下一主线：NL A2 持久限频与 A3 编译缓存，随后再做公测运营反馈与关键浏览器自动化。

### 2026-10-26 QRE-SAAS-UI-DECLUTTER-001 DONE（已发布）

Kimi 按用户三项要求直接完成并发布 `8accb66`：①job/showcase/个人回测记录的结果合同、验证徽标、版本与新旧口径全部隐藏，系统内 `result_contract`、verified 门与分享权限不变；②job/symbol 所有 `/saas/help#...` 模块深链删除，tip-trigger 与曲线口径提示保留；③help 改 190px sticky 侧边栏目、20px 标题，≤760px 双列静态导航，并删除验证状态文案。相关 138 passed，全量 2689 passed + 5 skipped；真实 Chromium 6/6 零 JS error 零横溢，证据 `.tmp/ui-declutter/`。ECS 备份 `/tmp/qre-ui-declutter-pre-20261026/`，六文件哈希一致，公网五个页面 200 且删除标记为零。仅重启 qre-saas，未重启 worker、未跑真实回测。小游戏/Steam 挂起；下一主线为经典策略按钮与结果操作卡 UI 精修。

### 2026-10-26 QRE-SAAS-READONLY-SHARE DONE（P1 第三切片已发布）

用户批准 commit + push + ECS；实现 `08b4a27` 已推送并发布。最终全量 2688 passed + 5 skipped，真实 Chromium 12/12。ECS 备份 `/tmp/qre-readonly-share-pre-20261026/`，postgres apply `share_links`（owner=postgres）后同步六个文件，仅重启 qre-saas；未重启 worker、未跑真实回测。公网用临时哈希链接完成创建→匿名只读→撤销验证，job74 撤销 401；生产复核并修复“显式失效 share 在 showcase job 上回退公开通道”边界，job58 无参数 showcase=200、bogus/撤销 share=401，有效 share=200。临时链接全部删除，share_links=0。下一项：经典策略按钮与结果操作卡 UI 精修；移动端/App、压测性能、硬件与云迁移仍挂起。

### 2026-10-26 QRE-SAAS-READONLY-SHARE IMPLEMENTED（P1 第三切片：默认私有的可撤销只读分享，待用户验收）

只读分享已落地。**范围铁律**：不改回测引擎、worker 执行逻辑、结果数值、配额、NL A2/A3、策略库与默认私有语义；不跑真实回测；不做压测/性能/硬件；不做移动/App 专项（仅 375 验证不破版）；未 commit/push、未部署 ECS。**Schema**：`cloud_schema.sql` 新增 `share_links`（id/token_hash UNIQUE/job_id ON DELETE CASCADE/owner_id/expires_at/revoked_at/created_at + 两索引；无明文/前缀/guest_key/last_used）；应用层 `_ensure_share_links` information_schema + 进程 guard 懒自愈，CREATE 失败按「分享不可用」降级（不报错、不放权）；**生产须先由 postgres 幂等 apply `cloud_schema.sql` 再发代码**（owner 踩坑同 results.result_contract）。**令牌**：`secrets.token_urlsafe(32)`；库中只存完整 `sha256("share:"+token+SAAS_AUTH_SALT)`；明文仅创建响应一次；URL `/saas/jobs/<id>?share=<token>`；校验=未撤销+未过期+job 一致。**API**：`POST /api/saas/jobs/<id>/share-links`（登录+本人+completed；游客 401、他人/不存在 404、未完成 409；有效期整数 1/7/30/0 默认 7）；`GET /api/saas/share-links`（仅本人 50 条，状态 active/expired/revoked，不回 hash/token）；`POST /api/saas/share-links/<id>/revoke`（仅创建者，重复/他人/不存在 404，立即失效）。**公开只读通道**：`_require_completed_result` 有效 `?share=` 绑定单 job 放行（`readonly_kind="share"`，不看登录/游客会话；未验证结果同样放行、徽标保留）；无效/过期/撤销/错 job 不降级（匿名 401、登录他人 404，错误体与不存在逐字节一致）；范围仅 7 个结果 GET，不开放 jobs/results 列表、策略/信号/me/console/worker；generate 对 share/showcase 都 403；写端点原权限。**前端**：job.html 分享卡+自定义模态+只读 input+复制（Clipboard API 回退手动选择）+「只显示一次」+不写 localStorage；分享视图 chip「只读分享」+「← 返回首页」，showcase 仍「经典策略展示 · 只读」+「← 返回经典策略」；取消/保存/信号/下载/游客引导全隐藏；profile「我的分享」+撤销二次确认；symbols/symbol token 随行。**测试**（TDD 先 RED 后 GREEN，证据 `.tmp/readonly-share/`）：RED=65 errors；GREEN=`test_saas_access_hardening.py` 65 passed（P0-2 31 例零回归 + 新增 34 后端 + 10 前端 Node）；`test_gui_saas_pages.py` 三 harness 加透传桩；相关 22 文件 655 passed；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2688 passed + 5 skipped**（基线 2651+5，零回归）。**真实 Chromium**（`.tmp/browser-venv`+chromium，临时库 `qre_readonly_share_browser`+8099 临时 staging，seed/worker 协议模拟，未启动真实 worker/回测）：12/12 通过、零 JS error、零横溢——创建+复制+localStorage 零痕迹；游客无入口；匿名只读全渲染（chip/返回/徽标/无操作入口）与个股两页；异 job/过期/撤销统一无权；撤销二次确认；未验证徽标保留；375 零横溢。**踩坑与修复**：①`_ensure_share_links` 失败后不能永久报可用——拆「已尝试/可用」两状态；②`int(1.5)` 静默取整——allowlist 改严格 isinstance；③审计脚本三处（相对 URL 补 BASE、异 job 断言须匿名上下文、撤销行按 job_id 定位）。**主 Agent 截图复核 2 项 Required Fixes 已聚焦修正**：①公开只读页（share 与 showcase）隐藏 base 全局游客条 `#guest-strip`（分享视图解析时即隐藏，symbols/symbol 同步；base 逻辑与无权页零改动）；②创建 modal 与 profile 我的分享的时间统一走 `LabUI.fmtLocalTime`（本地 YYYY-MM-DD HH:mm，无微秒；缺失回退原值；NULL=永久）。复跑 access_hardening 66 passed、相关 23 文件 656 passed、真实 Chromium 12/12（新增 showcase 游客条用例，share-job-1280.png 顶部已无游客条）。**未解决/遗留**：链接为持有即读（bearer 语义，只能整体撤销）、无访问审计、单 job 可多条链接、salt 轮换使历史链接失效（预期）。建议提交 `feat(saas): 增加可撤销的只读结果分享`，commit/push/ECS 待用户批准。详细报告 `.tmp/readonly-share/report.md`（04/08/09/10 同节）。

### 2026-10-25 QRE-SAAS-RESULT-UNDERSTANDING IMPLEMENTED（P1 第二切片，待用户验收）

结果理解与集中帮助已落地。**范围铁律**：不改 schema、收益/风险/费用数值、回测引擎、worker 执行逻辑、配额、NL A2/A3；不跑真实回测；不做压测/性能/硬件；未 commit/push、未部署 ECS。**新增公开帮助页** `GET /saas/help` + `gui/saas/templates/help.html`（游客与登录用户均可访问，无新增 API/表）：七锚点小节 contract/metrics/benchmark/fees/risk/attribution/replay，表格化极简可扫描；两种收益口径由 `result_contract` 常量同源注入；主导航「使用说明」入口沿用 active 与移动样式；`lab-theme.css` 仅加 `.help-sec`/`.help-jump`。**结果页深链 + 合同同源**：job/symbol 模块标题「说明 →」跳对应锚点，个股数据截止链 `#contract`；`renderContract` 用合同口径更新 `#curve-tip`，无合同保留静态回退；**主指标卡保持 6 张**（`renderMetrics` 6 个 card 被测试锁定），盈亏比只在帮助页与重播解释。**口径提示**（全部复用 `LabUI.helpTips` 事件委托）：job/symbol 五类磨损卡卡级 tip + 毛/净标签 tip、job 费率 chip 默认/自定义 tip、`bench-bar` 基准含义 tip、`replay.js` 盈亏比/暴露度/当前持仓 tip；费率与风险数值零改动。**symbol 数据截止与符号统一**：`api_result_symbol_detail` 两路径注入 `data_until`（不改 gzip 产物、不回填）；`#sym-note` 显示数据截止 + 口径链接（缺字段「未声明」）；VaR/ES 改损失正数展示（仅显示符号，风险原值与计算不动）。**测试**（TDD 先 RED 后 GREEN，证据 `.tmp/result-understanding/`）：RED=19 失败；GREEN=新 `tests/test_saas_result_help.py` 17 例 + help_copy +2 + symbol_ux +2 + pages +1；相关 502 passed；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2651 passed + 5 skipped**（基线 2629+5，零回归）；P0-2 权限与 P0-1B 结果合同语义回归全保留。**真实 Chromium**（`.tmp/browser-venv`+chromium-1248，临时库 `qre_result_help_browser`+8099 临时 staging，seed/worker 协议模拟，未启动真实 worker/回测）：10/10 通过、零 JS error、零横向溢出——帮助页七锚点+跳转+导航 active；模块深链全部到达正确小节；磨损五卡+费率 chip+毛净标签连续 hover/focus 完整说明；重播三卡 tip；symbol 真实 data_until 且 VaR/ES 与 job 同号（2.13%/3.05% 正数）；移动 375 登录态三页零横溢、导航单行（末项 368≤375）、tap 出完整说明。**踩坑与修复**：①移动模拟下内容过宽会撑大 innerWidth（布局视口扩展），溢出断言必须对比固定视口宽——据此发现并修掉真实缺陷：第 5 个导航项使 375px 登录态顶栏溢出 14px（lab-theme `.mainnav{gap:4px}` 后加载压制 base 内联规则），≤400px 断点补 `header.topbar .mainnav{gap:0}`+logo 24px+11.5px；②worker 认领正确路径是 `/api/worker/jobs/claim`（`/api/worker/jobs/lease` 不存在）；③页面 raw fetch 不带 Bearer，登录态提交须显式加 Authorization 头。**未解决/遗留**：帮助页为文字口径页，不含图表（符合极简定位）；例外表演进、console 展示列仍未做（既有范围外）。建议提交信息 `feat(saas): 增加结果指标帮助与费用口径说明`，commit/push/ECS 待用户批准。详细报告 `.tmp/result-understanding/`（09 号文档同节）。

### 2026-10-25 QRE-SAAS-FIRST-SUCCESS-UX-001 IMPLEMENTED（P1 首切片，待用户验收）

P1 首次成功路径首切片（等待状态、离线提示与失败恢复）已落地。**范围铁律**：不改 schema、回测引擎、worker 执行逻辑、结果数值、配额、NL A2/A3；不跑真实回测；不做压测/性能/硬件；未 commit/push/部署 ECS。**后端**（`app.py`）：新增只读 helper `_queue_position` / `_worker_online` / `_job_runtime_fields`（排队位置与 worker <3 分钟在线判定单一口径，GET job 与 summary 409 共用；只回布尔 `worker_online`，不暴露 worker 名称/地址/资源）；`GET /api/jobs/<id>` 在既有 `queue_position`（仅 queued）基础上补 `worker_online`（未终态）；`_require_completed_result` 的 409 体按现有任务数据增补 `queue_position`（仅 queued）/`worker_online`/`strategy_id`/`error_class`/`error_message`/`cancel_requested`——failed 从此返回真实 error_message/error_class，不再只有「任务未完成（failed）」；匿名 401/他人 404/不存在同体/showcase verified 公开只读语义零变化。**游客取消**：`POST /api/jobs/<id>/cancel` 复用 P0-2 `_guest_identity`/guest_key 归属——同会话可取消（queued 直接 canceled、running 置 cancel_requested），异会话/无 Cookie 401 且与不存在同体，登录用户他人 404，终态 409，401 响应顺手签发会话 Cookie。**new.html**：`pollJob` 每次成功轮询把 queued/running、queue_position、worker_online、已等待时间渲染进 wait-mask（queued N>0「排队中，前面还有 N 个任务」/N=0「排队中，等待计算节点领取」；worker_online=false「计算节点暂时离线，任务已保留，恢复后会继续；无需重复提交」；不虚构百分比/预计完成时间）；单次 15s AbortError 归为临时刷新超时继续下一轮，HTTP 500/无权限/终态仍立即 fail-fast；80 轮上限改为独立 `PollTimeoutError`（「任务仍在后台执行，请前往任务页查看」+ 任务页入口，不自动提交全量、不再写「策略在小样本上没跑通」——该文案仅保留给真实失败）；`createJob` 包裹 15s 提交超时，超时给可重试明确错误（提示避免重复提交）。**job.html**：`#status-card` 内新增操作区（不新叠卡片）——队列位置/离线提示/已等待时间（`#job-status-extra` 纯视觉无 aria-live）；活跃任务「取消任务」走既有自定义模态二次确认（非原生 confirm），queued 取消后停轮询，running 显示「取消请求已发送，最终状态以服务端为准」，cancel_requested 时「正在取消」+ 禁用重复取消；failed/expired 展示真实 error_message，登录用户有 strategy_id 显示「按原策略重新回测」跳 `/saas/new?strategy=<id>`（既有回填链路），游客仅「返回新建页」；completed/readonly 隐藏操作区且取消按钮禁用（showcase 只读零取消入口）。**wait-mask**：title/sub 挂 `aria-live="polite"`，新增 `.wm-meta` 秒数行（tabular-nums、aria-hidden、无 aria-live，避免每秒朗读）；禁 ESC/禁背板/keepMask/spinner 停转/reduced-motion 语义不变；`lab-theme.css` 仅加 `.wm-meta` 一条规则，未动 token/8080/18080。**测试**（TDD 先 RED 后 GREEN，证据 `.tmp/first-success-ux/test-evidence.txt`）：RED=新增 15 + pages 14 失败；新增 `tests/test_saas_first_success_ux.py` 21 例（运行态字段/409 契约/failed 真实错误/权限语义不变/游客取消矩阵/无 worker 泄露）+ `tests/test_gui_saas_wait_mask.py` 3 例（aria-live/meta/keepmask/CSS）+ `test_gui_saas_pages.py` 新增 25 例 Node harness（AbortError 重试、500/终态 fail-fast、PollTimeout 独立错误、queue/offline 文案、createJob 超时、job 409 渲染、取消模态全流程、登录/游客恢复链接、readonly 零取消）；改写旧 `test_new_login_url_and_poll_job_fail_fast` 的 body-pending 预期为「本次请求超时后继续轮询」、旧 job API 断言精确到 `/result` 旧嵌套路径。相关 231 passed；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2627 passed + 5 skipped**（基线 2590+5，零回归）。**真实 Chromium**（`.tmp/browser-venv` + chromium-1248，临时库 `qre_first_ux_browser` + 8099 临时 staging，seed/协议模拟 queued/running/failed/worker 心跳，未启动真实 worker/回测）：10/10 场景通过、零 JS error、零横向溢出——游客排队 N=2 + 离线提示 → worker 上线离线消失 → running + 已等待 → failed 真实原因 + 游客返回新建页；游客同会话取消（模态二次确认）→ 已取消停轮询；同 IP 异会话看/取消他人任务 401 不泄露；登录用户取消；登录用户 failed「按原策略重新回测」回填策略名；15s 临时超时→重试恢复；移动 375 取消按钮 44px 可点可取消。证据 `.tmp/first-success-ux/`（report.md、browser-evidence.json、13 截图、seed.py、browser_audit.py、run_audit.sh）。**未解决/遗留**：wait-mask 冒烟段文案由 Node harness 覆盖（真实浏览器跑冒烟需真实回测，属明确不做）；80 轮前台超时在真实浏览器需 ~4 分钟，未在浏览器复现（harness 已覆盖）；建议提交信息 `feat(saas): 完善回测等待状态与失败恢复`，commit/push/ECS 待用户批准。

**主 Agent 复核修正（同日，4 项 Required Fixes 已聚焦修正 + 回归 + 证据替换）**：①`pipeStopAt` 中性化（去掉 fail 类，「后台等待中」文案，失败红态仅归 `pipeFailAt`）；②`jobWaitStatus` 离线提示覆盖 queued/leased/running/uploading 全活跃态，`pollJob` 终态抛后端 `error_message`；③wait-mask `apply` 文本未变不写 DOM（aria-live 不再被轮询重复触发，API 不变）；④浏览器取消模态证据改为等待可见+动画稳定后断言 computed display/bounding box/按钮可见再截图（桌面/移动/登录用户三处，截图已肉眼复核）。文档 04/08/09/10 历史标题层级已恢复与 HEAD 一致（纯新增无格式化 churn）；09 归档 P0-2 Release Status 同步为已发布 `0799890`。测试证据与全量结果见 `.tmp/first-success-ux/test-evidence.txt`。

### 2026-10-25 QRE-SAAS-ACCESS-HARDENING-001 IMPLEMENTED（待用户验收）

P0-2 已落地。**ECS 测试账号移除**：只读核查确认存在（活跃键、移除前 bypass 实测 200、users 表 1 行遗留）；备份 `/etc/qre-saas.env.bak-access-hardening-20261025-173458`（0600）后注释两键、restart qre-saas active；正式登录 8 项验证全过（登录页 200 / Authing 302→demo.authing.cn / callback 假 code 400 / me 401 / 测试账号正确密码 401 / worker 错 token 401 / 游客越权 400 / showcase 200）；env 增补 `SAAS_GUEST_COOKIE_SECURE=1`（下次重启生效）。全程未输出凭证。**IDOR 矩阵**：`tests/test_saas_access_hardening.py` 31 例覆盖全部用户侧 job/result/symbol GET（匿名 401、他人 404、本人 200、不存在与他人错误体逐字节一致不泄露存在性、showcase verified 公开只读 200、未验证白名单 401-404）+ 写表面（delete 矩阵、showcase generate 403、worker token 不变）+ 游客 NL 限流仍按 IP。**游客归属改随机会话 Cookie**：`qre_guest_sid`（43 位随机/HttpOnly/SameSite=Lax/30 天/Secure 可配），归属键 `sha256("gsess:"+sid+salt)[:32]` 同形同列**无 schema 变更**；`_guest_identity` 缺失才签发绝不轮换；`_migrate_legacy_guest_jobs` 旧 IP 归属结果在新会话首次创建任务时一次性迁移（先迁移后计数、幂等+进程级 guard）；接入 POST /api/jobs（403 也带 Cookie）、GET /api/jobs/<id>、`_require_completed_result`（8 结果端点）、DELETE /api/results/<id>。**历史迁移语义**：只读不迁移；原访客下次创建任务恢复连续性；第二个同 IP 新会话见空档 401；迁移后旧 key 不归属不可访问；新会话彼此隔离。**不变式**：默认私有、Authing、worker token、结果合同、showcase verified、409/404 语义全不变；主动分享不做（P1）。**测试**：RED=collection ImportError → GREEN=31 passed；改写 2 个旧 IP 语义用例；相关 329 passed；**全量 2590 passed + 5 skipped**（基线 2559+5 零回归）。**真实 Chromium** 三上下文全部来自 127.0.0.1：A 提交得 HttpOnly/Lax 随机 Cookie，任务页与迁移来的旧游客结果完整渲染；B（同 IP 新会话）看 A 的任务与迁移后旧任务均显无权兜底零泄漏；B 自己任务正常且 A 回看被拒；showcase 仍只列 verified；移动 375 零 JS error 零横溢；证据 `.tmp/access-hardening/`。**未 commit/push、未 ECS 代码部署、未跑真实回测**；ECS 仍跑旧代码（纯 IP 归属）直到部署批准。遗留：游客清 Cookie 可重获当日配额（软限额，P1 A2）；users 表测试账号行未清；真人 Authing 登录待用户验收。详细报告 `.tmp/access-hardening/report.md`。

### 2026-10-25 QRE-SAAS-RESULT-CONTRACT-001 IMPLEMENTED（待用户验收）

P0-1B 结果合同已落地。**单一权威** `src/quant_research_engine/gui/saas/result_contract.py`：合同版本 `2026-10-25.1`、两种收益口径文案（曲线=日收益累乘交集口径剔注入；总收益=初始资金加权 Σfinal/Σinitial−1）、验证状态、**显式例外表**（58/66 verified、74 unverified、其余历史默认未验证）；分类函数无时间入参（签名被测试锁死），不存在按当前日期动态猜新旧。**注入点在 worker 回传接收层**（`api_result_meta` / `api_report_result_legacy`），worker/引擎零改动；`results.result_contract` 可空 JSONB + 懒自愈 ALTER + `cloud_schema.sql` 同步。**API 只增字段**（`/api/results`、`/api/results/<id>/summary`、`/api/saas/showcase`、`/api/saas/console/showcase`）。**公开展示只放行 verified**：`/api/saas/showcase` 与 showcase 公开只读通道对 74 关闭（匿名/他人得到与未挂白名单相同的 401/404），但 showcase 白名单行、job、产物全部保留，属主本人照旧可见自己的 74；默认私有、游客 guest_key、dev 后门、409/404 语义均未变。**前端**复用 badge + data-tip：`job.html` 合同徽标（已验证口径=绿 / 旧口径·未验证=红）+ 合同版本与数据截止 + 两种口径提示；`showcase.html` 页头与每行已验证徽标；`_records_scripts.html` 记录行合同标签。TDD 先 RED 后 GREEN：新测试文件 21 例 + `test_gui_saas_pages.py` +2 例（含 harness `renderContract` stub 修复 3 例旧失败）；相关 180 passed + 1 skipped；**全量 `pytest tests/ --ignore=tests/data_test` → 2559 passed + 5 skipped**。真实 Chromium 桌面 1280 与移动 375 各 3 页通过（showcase 只列 verified 且 74 不公开、新结果/74 徽标与口径提示可见、零 JS error、零横向溢出），证据 `.tmp/result-contract/`。**未 commit、未 push、未部署 ECS、未跑真实回测、未回填历史数值**；ECS 需 DBA apply `cloud_schema.sql` 新列，worker 不改不动。详细报告 `.tmp/result-contract/report.md`。

# Agent State

This file is the source of truth for single-agent workflow recovery.

### 2026-10-25 QRE-SAAS-FACTOR-PICKER-MODAL DONE（待用户验收）

自选因子条件行的三个堆叠下拉已改为「当前因子选择按钮 + 三栏弹窗 + 搜索」。`.wz-left`/`.wz-rfield` select 降级为隐藏数据字段但仍是唯一值来源，YAML、`usedFactors()`、`readGroup()`、`snapshotWzArea()`、固定值切换、策略还原、price basis 归一零改动；弹窗复用 `FACTOR_OPTIONS`/`factorGroups()`/`factorSubs()`，不新增 API 与依赖。TDD 先 RED 后 GREEN；真实 Chromium 桌面 1280 与移动 375 共 64/64 项通过（三级选择、搜索/清空/空态、连续三次开关、Esc/遮罩/关闭按钮、焦点返回与 Tab 焦点锁、按钮与 YAML 一致、固定值、条件增删、AND/OR、零 JS error、零横向溢出）。目标 10 passed、相关 242 passed、全量 2474 passed + 5 skipped；证据 `.tmp/factor-picker-modal/`。已部署 ECS（仅 new.html + lab-theme.css，重启 qre-saas，未重启 worker，未部署测试/文档），备份 `/tmp/qre-factor-picker-pre-20261025-124220/`，SHA256 与公网 200/弹窗标记已核对。**未 commit、未 push**，等用户实机验收后由用户批准提交。

### 2026-10-25 QRE-NL-HOLDING-DEFAULT-001 IMPLEMENTED（待用户验收）

真实 NL 抽查发现模型漏 holding/编造 999，非因子别名错误。已按用户要求统一未说明期限 `max_holding_days: 0`（不限），明确期限保留，其他 YAML 原文不动。staging 已配置真实 NL 编译（现有 OpenAI 兼容配置，凭证不入仓）；MACD/RSI/BOLL/KDJ/MA 五例均编译成功、holding=0、canonical 正确，未创建回测。全量 2534 passed + 5 skipped；未 commit/push/ECS。

### 2026-10-25 QRE-GUI-FACTOR-REGISTRY-001 IMPLEMENTED（待用户验收）

单一因子语义来源已落地：`configs/factor_registry.json`（v1.0，895 字段条目 + market_fields/
tables/families/extra_aliases）+ 只读加载层 `gui/factor_registry.py` + 生成器
`scripts/gen_factor_registry.py`（规则生成 + 特殊人工维护）。canonical/YAML/回测/隐藏 select/
条件快照/策略还原零改动；`/api/saas/factors` 只增 `zh/canonical/price_basis/aliases`。
弹窗按钮/三栏/搜索中文名为主 + 价格口径可见 + canonical 悬停对照；搜索匹配中文名/canonical/
列名/全部别名。NL 解析四级：canonical 精确 → 归一化别名 → family+params → 同名多口径默认
close 并 notice（显式 typical_price/average_price 可选），其他歧义返回 candidates 不猜；
MACD 三输出不混淆（DIF=macd / DEA·信号线=macds / 柱=macdh）。`COMMON_FACTOR_TARGETS`
由注册表 core 25 条派生，Prompt 不注入全量别名。防漂移校验接入
`gen_factor_catalog_llm.py` 与 `sync_saas_metadata.py`（当前均「校验通过」）。覆盖
554/895（61.9%），341 列未维护（Alpha191/Alpha101/`_rank` 族/少量财务报告期），展示回退
canonical、不伪造中文名。TDD 四阶段 RED→GREEN；注册表 40 passed、向导 38、弹窗 13、
saas pages 74、组合回归 95、全量 2533 passed + 5 skipped。真实 Chromium 8091 桌面 1280
与移动 375 各 13 项通过，零 JS error、零横向溢出，证据 `.tmp/factor-registry/`。
`deploy/saas/metadata.json` 已本地重新导出（367052 bytes / 因子 902 项）。
**未 commit、未 push、未部署 ECS、未跑真实全量回测、未调用真实 LLM**，等用户验收。
待复核：族名未给参数按族默认周期处理并提示（MACD 12,26,9 为批准项，其余族为同口径延伸）。

### 2026-10-24 QRE-SAAS-ACCESS-FALLBACK-FINAL-REVIEW DONE

已覆盖公共无权卡、next 安全回跳、job/symbol/records 有限轮询与重试、showcase 公开只读及 `can_generate` 业务 404。最终补齐 job 请求/响应体超时与 epoch、symbol 暂停语义、交互监听幂等、showcase readonly 和 new expired 终态；提交检查仅扫描新增行并有正反回归。相关测试 228 passed，未运行真实全量回测或真实浏览器自动化；实机矩阵留待部署后人工验收。

### 2026-10-24 FRM 缺失收口

已修复并回填，不再属于待办。重要教训：所有关键小文件（FRM 等）必须显式设置回传优先级，不能依赖文件名字典序；全市场任务 20MB 上限会静默截断。本地产物 Windows 路径为 `\\wsl.localhost\Ubuntu-24.04\home\van\qre-outputs\gui-console\runs`；仓库 `outputs` 是指向 `/home/van/qre-outputs` 的软链接。

### 2026-10-25 QRE-SAAS-HELP-COPY-002 DONE

001 已回退。002 由 Kimi 完成：事件委托 + 单例提示框，动态节点无需 refresh；全面清理表单和结果页灰色备注。真实 Chromium 连续 3 次 hover、指标卡正文、移动 tap 与 375px 已验收；相关 230 passed，全量 2462 passed + 5 skipped，证据 `.tmp/help-copy-v2/`。已部署 ECS，`qre-saas` active；用户批准通过并允许本地 commit，不 push。

### 2026-10-25 QRE-SAAS-ACCESS-HARDENING-001 RELEASED

实现 `0799890` 已 commit/push 并部署 ECS。发布前全量复跑 2590 passed + 5 skipped；ECS 仅同步 app.py 与 cloud_schema.sql 注释并重启 qre-saas，未重启 worker、未跑真实回测。公网双游客会话 Cookie 独立且 Secure/HttpOnly/Lax，私有 74 匿名 401、verified 58 匿名 200、showcase 仅 58/66、Authing 302；备份 `/tmp/qre-access-hardening-pre-20261025-release/`，证据 `.tmp/access-hardening-production/`。真人 Authing 登录留用户实机验收。

### 2026-10-25 QRE-SAAS-FIRST-SUCCESS-UX-001 RELEASED

实现 `a84a9a3` 已 commit/push 并部署 ECS。发布前全量复跑 2629 passed + 5 skipped；ECS 备份 `/tmp/qre-first-success-ux-pre-20261025/` 后仅同步 app.py、new.html、job.html、wait-mask.js、lab-theme.css 并重启 qre-saas，未重启 worker、未跑真实回测。公网五文件 SHA256 与仓库一致，新运行态/取消/恢复/ARIA 标记齐全；58 verified 200、74 匿名 401、Authing 302。生产证据 `.tmp/first-success-ux-production/`。

### 2026-10-25 QRE-SAAS-RESULT-UNDERSTANDING RELEASED

实现 `9fd3b3d` 已 push 并部署 ECS。全量 2653 passed + 5 skipped；ECS 备份 `/tmp/qre-result-understanding-pre-20261025/`，公网 `/saas/help` 200、七锚点齐全、58 个股详情返回 data_until=2026-10-09、74 匿名 401，文件 SHA256 与仓库一致。生产证据 `.tmp/result-understanding-production/`。DeepSeek 生产配置保持 `deepseek-flash`。

## Current Phase

P3 数据治理盘点中：**QRE-DATA-CLEANUP-AUDIT 只读盘点完成，未清理任何文件/表/库**（2026-10-27；3 项高风险 + 7 项待用户确认）。当日 QRE-ECS-SSH-HARDENING 已生效待人工验收（root 直连已禁），QRE-FACTOR-ZH-COVERAGE 已部署待人工验收（341 列中文名全覆盖）。下一项：按用户对数据清理各项的决策逐项立项。游戏继续由用户在 WSL 本地试玩，优化反馈另列，不与主线提交混合。移动端与 App 端按用户要求暂时跳过（挂起）。

## Current Task

见 `14_LAUNCH_ROADMAP.md` §11。**2026-10-25 用户最新范围约束：不做任何压力测试、深度性能测试、硬件扩容或硬件相关推进，只做公网用户直观可见、可感知的产品体验。移动端、App 端与可访问性深化暂时挂起，不主动启动。** 当前顺序：
1. ~~P0-2 权限加固~~ 已发布 `0799890`。
2. ~~P1 首次成功路径首切片~~ 已发布 `a84a9a3`；NL A2/A3 仍仅作减少等待和重复编译的体验支撑，另行立项。
3. ~~结果理解、集中帮助、数据截止与费用口径说明~~ 已发布 `9fd3b3d`。
4. [挂起] 移动端、App 端与可访问性深化（用户 2026-10-25 明确暂时跳过）。
5. ~~默认私有的可撤销只读分享~~ 已发布 `08b4a27`；~~经典策略及结果操作 UI 精修~~ 已验收发布 `e6f4f77`。
6. ~~NL A2 持久限频与 A3 编译缓存（含 9090 管理台同步）~~ 已验收发布（2026-10-26；发布前全量 2753 passed + 6 skipped）。
7. **公测运营反馈与关键浏览器自动化，依据真实用户反馈继续修正公网体验。**
8. 容量实测、磁盘/备份演练、深度性能、硬件扩容和整体上云全部暂停，仅保留在长期 backlog；第四入口外部 AI Agent API 仍排最后。

DATA-REBUILT-2026-10-11 **数据侧已全部完成**（2026-10-12 10:45 链条收官）：
- 分钟线入库 `public.stock_minute_1m` 4313 天全量（TimescaleDB 压缩已开）；WSL 侧 /home/van/mindata CSV（324G）待用户确认后删除
- stock_daily 已换名为原始价（旧表 `stock_daily_qfq_legacy` 留作回滚，验收后删）
- 因子 10 表全历史重算 5853 只零失败；alpha191 全量 191 因子 1608 万行
- 抽查通过：000001.SZ sma_20 与手工 close×adj_factor 一致；920195.BJ MACD 已修复全期无空值
- alpha149/181/182 "benchmark missing" 告警系误报（000300.SH 数据完整），实测覆盖率正常，无需补救
- **坑（已修复）**：表重建 RENAME 后 GRANT 不随迁 → qre_worker_ro 失 stock_daily SELECT 致 job 56 失败；已重新授权
- **剩余**：小样本回测对账验收（用户侧跑一次即可）→ quant_ts / indicators_tushare 两仓库 commit（代码已改完待提交）

SAAS-SYMBOL-2026-10-12（已部署 ECS，commit 93cb0eb + de3cc23）：
- 个股级 FRM 模块（risk 节随详情产物，VaR/ES/EWMA波动/状态/夏普/压力测试）
- 个股详情按需生成链路（kind=symbol_detail 轻量任务，幂等，产物落父 job 目录）
- 板块/标签榜单列头排序；FRM 修复 run 级回传（risk_report.json 登记 artifacts）
- NaN→null 序列化修复（前端 JSON.parse 卡死根因）

## Current Owner

KIMI_CODE (sole development agent; user is final approver)

## Current Task

详见上方 Current Phase（2026-10-12 已更新）。以下为历史任务存档：

**（存档）DATA-REBUILT-2026-10-11 实施步骤**：
1. **分钟线入库**（后台）：`quant_ts/import_minute_csv.py` 6 worker 把 /home/van/mindata（2009→2026，4313 天，324GB CSV，原始价）入库 `public.stock_minute_1m`（hypertable 7天chunk，量/额已换算手/千元），审计表 `stock_minute_1m_audit` 幂等断点续跑。预计 3-4 小时。
2. **方案A 日线重建**（后台）：`quant_ts/rebuild_daily_raw.py` 按 trade_date 拉 pro.daily 原始价+adj_factor 建影子表 `public.stock_daily_raw`（4372 天，含 2009 扩展段），预计约 2 小时。**验收后人工换名**（SQL 在脚本尾注释）。
3. **代码已改未生效（flag 门控，默认旧行为）**：
   - quant_ts `handlers/daily_handler.py`：fetch_data 弃 qfq 改 pro.daily 原始价（fetch_snapshot 本就是原始价——混合锚点根因）
   - indicators `core/db_manager.py`：`_adjust_prices`（IND_PRICE_BASIS=raw 激活，价格列×adj_factor）
   - indicators `alpha191/panel_loader.py`：同样 flag 门控复权
   - QRE `data/settings.py` + `data/postgres.py`：`price_basis`/QRE_PRICE_BASIS=raw 时 load_daily_bars 复权并携带 raw_open/raw_pre_close
   - QRE `portfolio/{shared,single_symbol,single_symbol_vectorized}.py`：涨跌停判定优先用 raw_open/raw_pre_close（交易所规则必须原始价）
   - QRE `gui/lab_result.py`：区间收益 ×adj_factor；K线展示锚定最新价
   - 验证：QRE 测试 2330 passed 零回归
4. **换名后待办**：systemd 各服务加 IND_PRICE_BASIS=raw / QRE_PRICE_BASIS=raw 环境变量并重启 → 因子 11 表全量重算 → 小样本回测对账 → ECS 同步。

上一任务：QRE-SAAS-SMOKE-INCIDENT (DONE 实现完成、**未 commit 待用户批准** — CR-2026-10-11 job 54 smoke
全市场超时事故四 bug：①apply_precheck 空 codes 按 run_id seed 随机抽样不再放行全市场 +
worker smoke 跳过全量后处理；②max_holding_days 0/null=不限（校验/编译/三引擎执行层全链）
顺带 risk.*_pct=0=不启用；③心跳连续失败 3 次判 lease 丢失终止子进程释放槽位；
④build_symbol_detail_files O(n²) 改一次解析逐股复用；测试 +9，`-k saas` 238 passed 零回归；
commit 批准后 push+ECS 部署+重启本机 qre-saas-worker，无 DB 迁移)

上一任务：QRE-NL-FACTOR-PIPELINE (DONE 实现完成、**未 commit 待用户批准** — CR-2026-10-09 NL 编译
因子名四层防线：真实目录快照注入 prompt（configs/factor_catalog_llm.txt + gen 脚本）/
别名字典（factor_aliases.json + auto_fix_column 第 0 层）/compile_nl 修复回路
（回喂最多 2 次，fix_attempts 透出）/兜底报错补申请新因子指引；测试 +12 全绿含
macd_signal→macds 精确案例；顺手修信号测试日期 flake；`-k saas` 237 passed 零回归；
commit 批准后再 push+ECS 部署（快照入仓库即生效，无 DB 迁移）；2026-10-10 已部署 ff0e39e + 生产实测 hotfix（平铺目录 + 快照 lookup 回退）另 commit)

上一任务：QRE-SHARED-COST-BREAKDOWN (DONE 已部署 — 交易磨损卡佣金/印花税 0 值 bug：
shared.py 四路径改 calculate_cost_breakdown + lot 级组件分摊 + _trade_row 补 6 拆分列
（键名同 vectorized）+ full_market_report shared_cash 补读聚合；存量不回填；
真库实测 fees_summary 佣金 70/印花税 32.88/过户费 1.31（修复前为 0）；
`-k saas` 237 passed + portfolio 族 482 passed 零回归；06+CR 已登记；
站立批准有效 → commit+push+ECS 部署+重启本机 qre-saas-worker)

上一任务：QRE-SAAS-RESULT-ACTIONS (DONE 已部署 — CR-2026-10-05 结果页显式入库+信号入口：
核心语义=没超额收益的策略不进策略库；jobs FK 约束下用 strategies.in_library 旗标
（提交建行不入库，显式保存/建 watch 才入库；存量一次性 backfill true）；
结果页末尾「下一步」卡（保存三态 + 信号面板三 scope）；游客整卡隐藏；
/api/results/<id>/summary 补 strategy_id（轮询走它）；测试 +2 + 断言 4，
`-k saas` 237 passed 零回归，staging 双端实测通过；站立批准有效 → commit+push+
ECS 部署+手工 apply in_library 列)

上一任务：QRE-SAAS-TIER-BETA-RELAX (DONE 已部署 — 内测期两层权限调整（用户 2026-10-05 拍板）：
游客 10 只随机补齐（云端 codes_auto_fill 标记 + worker fill_guest_codes）/近 10 年/
随机 N≤10，每日 1 次与次日清空不变；member/paid 三值全 0 不限；tier_policies 种子
不随代码更新的运维坑登记 19 号文档；测试重写+worker +4，`-k saas` 235 passed 零回归；
staging 8092（bypass=0 游客态）双端实测通过；已 push（4b1c083）+ ECS 部署 +
生产库 tier_policies 三行 UPDATE 验证 + 生产游客探针 job 43（3 自选+补齐，10 年区间）
completed、8 只不同股票成交证明补齐执行；本机 qre-saas-worker 已重启加载新 runner)

## 挂起 backlog（用户确认知悉，非进行中）

1. **深度性能优化**（用户指示"放最后"）：回测详情缓存已做过一轮；剩余为更深的
   引擎/前端性能项 + 引擎压力测试（每小时可处理多少全期全量回测/并发上限实测）。
2. **信号监控「板块」范围二级选择 UI**：当前监控范围支持 最近回测快照/全A/自定义，
   板块名单选择器未做（spec 留待细化项）。
3. **重播已验证边界**（非缺陷，首次真实场景出现时再处理）：全市场任务「同日几十只
   入场」聚合展开、orders 明细事件源路径（现走 round trips 兜底）、多因子副图页。
4. **付费体系**：信号监控 scan_enabled / max_watches 已入 tier_policies 占位；
   积分制 vs 会员制未定（用户明确暂缓）。
5. **分时策略回测**：依赖分时数据源选型（用户曾寻找稳定便宜的 A 股分时数据源，未决）。
6. **小程序/APP 端**：移动 web 适配已完成（2026-10-04）；原生端为远景项。

上一任务：QRE-SAAS-REPLAY-LAYOUT-FIX (DONE — 重播速度档换行 bug 系统性调试：根因=base.html:56
全局 select{width:100%} 使 .rp-sel 恒独占整行（五档宽度探针 width=bar 全宽实证，
与视口无关）；修复=.rp-sel 显式宽度+36px 等高 + 控制条两语义分组
（.rp-group-main 播放/单步/速度 nowrap 恒同排 / .rp-group-aux 允许折行）+
去除重复「起始日」label；同一探针五档宽度中心 y 差 0px 前后对照证明修好；
`-k saas` 235 passed；已部署 ECS，生产 asset_v 缓存破除确保用户端自动拿到新版）

上一任务：QRE-SAAS-WAIT-MASK + QRE-SAAS-REPLAY-LAYOUT (DONE — ①长等待遮罩组件 wait-mask.js
（禁 ESC/背板/全锁、z-95、护栏弹层级冲突已处理）+ new.html 生成策略与运行回测两段式
接入（「继续等待/后台运行」分流，踩坑 keepMask 短路已修）；②重播布局：倍速与播放
同排、进度条移至图表正下方（.rp-slider-row，两端生效）；staging 锁定探针/两段式
临时 worker 真执行双路径/布局断言/移动 375 全过，`-k saas` 235 passed 零回归；
awaiting git approval（站立批准有效）→ 部署 ECS)

上一任务：QRE-SAAS-REPLAY-POLISH (DONE — 重播组件两项优化（用户批准）：①接管模式——replay.js
opts.chartEl + destroy(keepDom)，symbol/job 删独立重播卡接管原 K线/收益曲线容器，
退出内存重建静态+缩放/基准条/区间卡恢复（踩坑 classList.add 链式抛错已修）；
②控制条打磨——SVG 图标+文字标签、cursor/hover/:focus-visible 紫环、transition 0.2s、
prefers-reduced-motion 降级、36px 等高 8px 网格；staging 单容器 DOM 断言/退出还原/
末帧 0.59% 强一致/UI 探针/reduced-motion 仿真/移动 375 全过，`-k saas` 235 passed；
awaiting git approval（站立批准有效）→ 部署 ECS)

上一任务：QRE-SAAS-REPLAY-S2 (DONE — CR-2026-10-04 切片2 K线级重播：replay.js 向后兼容扩展
（series type/extra 透传、ev.price 定位、initialCursor/height、yAxes pct:false 修全轴%
bug）；symbol.html #box-kreplay——K线/量/因子副图逐日推进、侧边信息卡（OHLC/因子/
持仓/浮动盈亏·毛随帧跳动/已实现累计）、默认近 2 年起播；staging 全链路实测——
浮动盈亏 −18.00==手算、末帧已实现 587.45==静态 total_pnl、切片1 回归 0.59% 不变、
移动 375 零横滚零报错；模板断言 +5，`-k saas` 235 passed 零回归；
awaiting git approval（站立批准有效）→ 部署 ECS)

上一任务：QRE-SAAS-REPLAY-S1 (DONE — CR-2026-10-04 切片1 策略级回测重播+可复用重播引擎组件：
static/replay.js（core 纯逻辑+attach UI：播放/单步/速度档/日历起始日/拖拽/空仓快进，
[0,cursor] 截断渲染+rAF 节流）+ lab-theme.css .rp-* 样式族；job.html #box-replay——
曲线逐日生长/事件流弹入聚合/8 卡指标随帧重算/「信」T 与「入出」T+1 相隔呈现；
staging 全操作链路实测 + **末帧强一致性断言（重播累计收益==静态总收益）** +
core 探针/日历联动/事件流 16 行/桌面+375 零横滚零报错；模板断言 +5，
`-k saas` 235 passed 零回归；awaiting git approval（站立批准有效）→ 部署 ECS；
切片2（symbol K线级）留待后续，组件已全参数化)

上一任务：QRE-SAAS-SIGNAL-CONSOLIDATE (DONE — 模块二 UX 收编（用户拍板：信号集成进「我的策略库」，
不做独立栏目）：顶栏「信号」项移除、未读红点改挂「个人信息」导航；策略列表 API 聚合
watch/latest_signals/signal_unread（两查无 N+1，最近信号日口径=max(trade_date) 当日
entry/exit 计数）；策略库行加监控徽标/最近信号摘要/未读红点 + 卡标题「查看全部信号 →」；
详情页加「该策略信号记录」分页区（进入即 mark-read）；/saas/signals 保留不进主导航；
测试 +2，`-k saas` 235 passed 零回归；staging 桌面+375 红点闭环与三态实测零报错；
awaiting git approval（站立批准有效）→ 部署 ECS)

上一任务：QRE-SAAS-SIGNAL-CENTER (DONE — CR-2026-10-04 模块二 策略信号监控+站内信号中心：
新表 strategy_watches/signal_events + users.signals_last_read_at + tier_policies
scan_enabled/max_watches（懒自愈+cloud_schema 同步）；用户侧 watch CRUD（默认
last_run_universe 快照/上限 403/scan 关闭 403/他人 404）+ signals 筛选分页 +
unread-count/mark-read；worker 侧 watches 下发 + signals 幂等回传；扫描脚本
deploy/saas/signal_scan.py（复用 evaluate_expression_signal，按股分组求值防 shift
跨股，挂 qre-refresh ExecStartPost=-）；strategy.html 监控卡做实 + 新页 /saas/signals
信号中心 + 顶栏「信号」红点（信号中心页跳过查询防竞态）；测试 +15，staging 全链路
实测（watch→回传→红点→mark-read 灭点）；awaiting git approval（站立批准有效）→
ECS 新表手工 apply + 生产扫描实跑)

上一任务：QRE-SAAS-STRATEGY-ASSETS (DONE — CR-2026-10-04 模块一 策略库→策略资产：strategies 加
entry_mode/wizard_state（懒自愈+存量推断+06 决策）；保存与 job 提交链路落模式与向导快照；
新页 /saas/strategies/<id> 三模式源文件还原（nl 重编译/wizard 快照+跳向导编辑/yaml 编辑）+
操作区+历史回测表+模块二占位注释；策略库行入口标签+详情链接；new.html 回填按
entry_mode/mode 还原入口并修 staging bypass 回填失效；测试 +10，`-k saas` 218 passed 零回归，
Playwright 桌面+移动截图零报错、向导回填逐键实测正确；awaiting git approval（站立批准有效）
→ 部署 ECS 需手工 apply strategies 新列)

上一任务：QRE-SAAS-MOBILE-ADAPT (DONE — 移动端 web UI 适配：Playwright 375×812 逐页审计
（records/job/symbol 三页页级横滚，根因=表格溢出/长 chip nowrap/磨损块固定宽）→
修复全集中在 base.html 新增 @media(max-width:768px) 规则块（表格块级横滚、chip 折行、
触达 44px、输入 16px/44px 防 iOS 放大、磨损块 2 列+grid 三段）；踩坑 lab-theme.css
后加载压掉同优先级覆盖 → .chart-box 前缀，登记 12 号新 §10；全页零横滚零 JS 报错 +
移动端交互冒烟（三入口/日历/提交流水线）通过 + 桌面 1280px 回归无破坏；
`-k saas` 208 passed 零回归；awaiting git approval（站立批准有效）→ 部署 ECS 后
公网 375px 复测)

上一任务：QRE-SAAS-R3-SLICE2 (DONE 已部署 — R3 切片2 资源调配封装（方案 C=A+B 混合，用户批准）：新表
worker_configs（worker_id 主键/期望四值/version+1/updated_by，懒自愈+cloud_schema 同步）；
status 响应回带 desired_config，worker _check_desired_config 比对记日志（同 version
一次/恢复一致记「已生效」）；console Worker 卡「当前 vs 期望」高亮 + 可复制
worker-tune.sh 命令 + 设为期望表单（POST /api/saas/console/worker-config admin 门禁）；
deploy/saas/worker-tune.sh sed 更新 /etc env+备份+重启 qre-saas-worker（本机 tmp 实测）；
测试 +11（saas 7 + worker 4），`-k saas` 207 passed 零回归，闭环冒烟通过；
awaiting git approval（站立批准有效）；部署：ECS 首次手工建 worker_configs 表)

上一任务：QRE-WORKER-CONSOLIDATION (DONE — worker 单例收敛：R2 调试期用户级 qre-worker(home-pc)
与系统级 qre-saas-worker(wsl-home-pc) 双跑，收敛为唯一系统级 qre-saas-worker；
/etc env 并入槽位/闸门/代理置空/QRE_MARKET_DB_URL 新密码；MemoryMax 16G→26G；
用户级 unit/env 退役 *.retired；ECS workers 表 home-pc 僵尸行已清；
收敛后 smoke job#35 completed(attempts=1) 端到端验证通过；docs 04/05/16 已同步；
awaiting git approval（本会话用户已站立批准 commit+push）)

上一任务：QRE-SAAS-R3-SLICE1 (DONE 已部署 — worker 实时状态上报 + 管理台「Worker 资源」卡)

上一任务：QRE-CALENDAR-YEAR-PICKER (DONE — 共享日历组件年→月→日钻取：点 .cal-title 标题上钻年份九宫格（12 年/页 ±12 年翻页）→月份视图→日视图，Esc 逐级返回/关闭；新增可选 opts.minDate 下界，年/月超界格子置灰禁点，maxDate 禁未来与「数据截至」页脚不变，调用方零改动兼容；.cal-cell.sel 紫底与选中日一致；仅改共享 lab-ui.js + lab-theme.css，lab/SaaS 模板零改动两端同步升级；全量 2212 passed + 4 skipped 零回归（复跑确认）；staging 8091 Playwright 三视图/禁未来/选值/Esc 实测零 JS 报错；12 号文档 §3.7+变更记录已登记；未 commit 未部署；awaiting git approval)

上一任务：QRE-SAAS-EXPOSURE-METRICS (DONE — 区间信息卡加持仓暴露度/持仓期年化两张随滑块联动卡：round trips entry/exit 展开逐日持仓掩码（同日重叠去重），暴露度=持仓日数/区间日数，持仓期年化=(1+区间收益)^(252/持仓天数)−1，无持仓显示「—」口径入 title；#range-strip 改 auto-fit minmax(130px,1fr)；job.html/symbol.html 同步，lab 侧零改动；全量 2212 passed + 4 skipped 零回归；staging 8097 宽+窄屏 Playwright 探针实测联动与数值正确、零 JS 报错；12 号文档已登记；未 commit 未部署；awaiting git approval)

上一任务：QRE-SAAS-DETAIL-CARD-UI (DONE — 公网详情页卡片 UI 四项验收修改：区间五卡 repeat(5,1fr) 整行均分、job.html 交易磨损+FRM 移到收益曲线后、symbol.html 顶部 7 卡 auto-fit 舒展布局、总结性卡片统一 --tint 淡紫底；仅改 saas/templates 的 job.html/base.html，lab 侧零改动；全量 2212 passed + 4 skipped 零回归；staging 8097 宽+窄屏 Playwright 截图验证零 JS 报错；12 号文档变更记录已登记；未 commit 未部署；awaiting git approval)

上一任务：QRE-SAAS-SYMBOL-UX-SHARED-FIX (DONE — shared 模式 per-symbol 产物缺陷修复：runner._enrich_shared_symbol_detail 从任务级产物补齐 orders/failed_orders/wear/单票净值；job 21 存量产物已重算覆盖 ECS；公网 demo01 job 23 全链路验证全模块渲染；测试 +5 全量 2212 passed + 4 skipped 零回归；已 scp 临时部署；awaiting git approval)

上一任务：QRE-AUTH-MEMBERSHIP (DONE — Authing OIDC 登录接入 A2-A6：schema 加 authing_id/avatar_url/member_*、新 authing.py 换票+JWKS 验签+自动建档+绑定旧账号、login.html 托管页主入口+邮箱密码折叠降级、测试 +22 全量 2207 passed + 4 skipped 零回归；env 已写 ECS/本地 0600、ECS venv 依赖已装；代码未部署；awaiting git approval + Authing 控制台回调白名单确认)

2026-09-27：细节见 04_TASK_HANDOFF.md 与 05_PROGRESS.md 同名条目。要点：
授权码+托管登录页流程（替代 §6 原 Guard 方案，已注记）；/saas/login/authing 302 →
/saas/login/callback 验签建档发本地 session；POST /api/saas/auth/bind 迁移旧账号。
**遗留用户操作**：Authing 控制台「登录回调 URL」白名单需含
https://www.aguhuice.com/saas/login/callback（实测报 redirect_uri_mismatch）；
部署待办：commit 批准后 ECS git pull + psql apply cloud_schema.sql + restart qre-saas。

上一任务：QRE-SAAS-FEEDBACK-FACTOR-REQ (DONE — 内测意见反馈页 + 申请新因子页 + 缺因子拦截跳转 + 全站统一侧边栏；全量 2185 passed + 4 skipped 零回归；仅本地+staging 验证未部署 ECS；awaiting git approval)

2026-09-27：细节见 04_TASK_HANDOFF.md 与 05_PROGRESS.md 同名条目。要点：
base.html 新增 .sidenav 侧边栏（意见反馈 / 申请新因子两入口，全页面自动获得）；
新表 feedback（仅登录用户提交，日 20 条上限，决策见 06）+ console「反馈」tab
（只读）；新页 /saas/factor-request（factor_requests 幂等补 formula/purpose 列）；
new.html 缺因子弹层改「当前数据库中不含此因子」+ 跳转申请页按钮（预填），
向导/YAML 提交前 unknownYamlFactors 兜底校验。测试 +21
（tests/test_saas_feedback.py）。未 commit、未部署 ECS（schema 需先 apply）。

上一任务：QRE-SAAS-LARGE-UNIVERSE-GUARD (DONE — 公网大范围板块/全市场提交耗时护栏，阈值口径同 lab 版 3000；全量测试零回归；仅本地+staging 验证未部署 ECS；awaiting git approval)

2026-09-27：细节见 04_TASK_HANDOFF.md 与 05_PROGRESS.md 同名条目。要点：
全部 A 股计数补为元数据字段 all_a_count（universe.py 新 all_a_count() =
reference.stock_basic 行数；sync_saas_metadata.py 生成逻辑更新，metadata.json
已重生成 5531 只）；/api/saas/universes 双路径透出（缺失降级 None）；
new.html 流水线第③步提交前按 LARGE_UNIVERSE_THRESHOLD=3000 判定，
超阈弹 #big-univ-modal（规范 .modal-mask 组件）说明预计股票数与耗时，
确认才提交。lab 侧零改动。测试 +3，全量零回归。未 commit。

上一任务：QRE-SAAS-SYMBOL-UX (DONE — 股票代码规范化+显示脱敏、超额收益 vs 持有不动修复、worker per-symbol 产物回传打通公网个股详情、板块弹层列补齐+点击跳转；已 rsync 临时部署 ECS 并公网验证；全量测试零回归；awaiting git approval)

2026-09-27：四项改动（细节见 04_TASK_HANDOFF.md 与 05_PROGRESS.md 同名条目）。
要点：新 gui/saas/symbol_norm.py；worker runner 新增 _fill_excess_return +
build_symbol_detail_files（_symbol_details/<ts_code>.json.gz 随 result/files 上传，
15MB 截断）；ECS api_result_symbol_detail 优先读上传 gzip；saas 模板
base/job/symbol/symbols/new 五处渲染层改动。顺手修 ECS workers 表缺授权导致的
claim 500 生产事故（已 GRANT）。测试 +31（tests/test_saas_symbol_ux.py），
test_gui_saas.py 一处断言更新。未 commit。

上一任务：QRE-SAAS-ADMIN-TUNNEL + QRE-SAAS-UI-ALIGN-FIX (DONE — 管理台撤公网改 SSH 隧道 + PG 每日备份 ECS→本地 + 公网顶栏/入口卡选中态/回测区间日历对齐 lab 版并已部署；全量 2130 零回归；awaiting git approval)

2026-09-27（方案 A，用户拍板）：nginx 对 /saas/console 与 /api/saas/console/* return 404
（仓库 deploy/landing/nginx-aguhuice.conf 同步线上）；base.html 删顶栏管理台入口注入
（断言反转，注意注释含 "/admin" 子串会撞禁链）；新增 deploy/saas/admin-tunnel.sh
（ssh -N -L 9090:127.0.0.1:8090）与 deploy/saas/pull-ecs-backup.sh；ECS cron 03:17
pg_dump 留 7 天 + 本地 cron 04:23 scp 拉取留 7 份，两端验证落地。决策入 06 日志，
运维速查入 16 号文档第 5 节。同日追加 UI-ALIGN-FIX：base.html 覆盖块对齐 lab 版
顶栏/选中态/日历（探针提取计算样式，禁用字「lab 版」代称），rsync gui/ 部署后公网
管理台入口消失、console 404 保持。未 commit。

上一任务：QRE-SAAS-ADMIN-E1E3 (DONE — SaaS 后台管理三件套：/saas/console 总览+用户/因子审核+worker 运维；users+role/status、workers 表；测试 +12 全量 2130 零回归；awaiting git approval)

2026-09-27：按 15 号文档 E 阶段落地 SaaS 管理后台（本地开发不部署）。users 加
role/status 幂等迁移、新 workers 心跳表；_require_admin 门禁；/api/saas/console/*
八端点（overview/users tier+status/factor-requests review/workers/jobs retry+cancel）；
console.html 五 tab 页面遵守 12 号设计系统；顶栏管理台入口仅 is_admin 注入。
前缀弃 /admin 改 /console（禁链纪律含注释），E3 指令下发/家里 PG 状态卡裁剪留后续，
决策入 06 日志。未 commit。
上一任务：QRE-UI-DESIGN-SYSTEM-DOC (DONE — 纯文档：12_UI_STYLE_GUIDE.md 重写为完整设计系统 25.3KB，每条规范标注源码 文件:行号；8081 lab 代码零改动；check-progress-docs.sh 通过；awaiting git approval)

2026-09-27：应用户要求把 8081 UI 设计知识从源码蒸馏进文档（根因：UI 对齐工作反复重读源码烧 token）。通读 lab-theme.css/lab-ui.js/lab.html/lab_result.html/lab_symbols.html/lab_symbol.html + SaaS base.html 复刻方式后重写 12 号文档：新增文件地图、36px 行内控件等高硬规则、ECharts 图表约定（纠正初版过时的 SVG 手绘描述）、treemap 三档显隐与 zr.off 陷阱、SaaS 复刻约定、禁链含注释教训。文档头部加「新页面开发前必读、改动规范需用户批准」。未 commit。

上一任务：QRE-LAB-UI-LANDING-R6 (DONE — OOM 限额 2G→8G + 僵尸 run 自愈 + 重提 5 年全量回测；awaiting git approval)

2026-09-08（R2 纠偏，用户驳回 R1 适配改写）：以 synthesis.html 为唯一真相源 1:1 移植——lab-theme.css=设计稿 CSS 全量+母板类映射，模板区块/类名逐段对齐，数据全走真实 API（fees_summary/symbols 路由沿用 R1 新增），echarts 图按规则 4 保留但配色/区间卡/tooltip/三级显隐对齐设计稿。测试 2067+4 绿。R1 细节（已部分被 R2 覆盖）：把已定稿设计稿 synthesis.html（docs/agent/12_UI_STYLE_GUIDE.md 为其规范）
原位落地 8081 lab 版（qre-gui-lab），8080 管理台零改动（git diff 仅 lab_* 模板 +
gui/lab_result.py + lab 两个测试文件 + 新增 lab-theme.css/lab-ui.js/lab_symbols.html）。
新建策略页：三入口并列卡 + PCB 排线（static/lab-ui.js）、预览栏（#strategy-yaml
迁入参数区之后成唯一 YAML 真相源 + 参数合并行 + 复制）、策略 ID 公共项
（param-sname，提交时 applyNameToYaml 写入 name；用户手改后不再自动覆盖）、
日历选择器（LabUI.attachCalendar，最大可选日 = /api/admin/refresh 的
state.last_data_date，禁今天及以后防未来函数）、唯一「运行回测」流水线
（①/api/validate 含 ID 校验 → ②saveToSandbox+smoke+waitForCheck → ③/api/run
沿用原参数 payload 与 >3000 只护栏；后端零改动；失败红字停留定位）。
回测记录：「股票数量」列 + 状态徽章 + 删除改二次确认弹层（API 不变）。
策略详情页：模块顺序 概述→收益曲线→交易磨损（新 box-fees，chart-data 新增
fees_summary：round_trips.csv 真实费用列聚合，缺失则整块隐藏）→FRM→归因热力图
→「查看个股回测明细 →」大入口卡；dataZoom 区间卡重算 rAF 节流；echarts 配色换
淡紫规范（策略 #6750A4 / 基准虚线 #8B7FBE / 直方图 #B7A6E8，红绿只给涨跌）。
新页 /lab/runs/<id>/symbols（lab_symbols.html + lab_result.py 新路由）：归因 A 层
聚合成全量个股表，点列头排序、搜索框模糊过滤、完整代码回车直跳个股详情。
个股详情页：顺序 概述→收益曲线（补区间卡五卡 + 滑块 rAF 重算）→交易磨损（该股
orders/trades 聚合）→K线→交易明细→下单记录；配色同步规范。
可见文案纪律：「沙箱/晋升」仍禁止；「冒烟测试：单股票 × 短期区间」为本轮用户
批准的流水线文案（test_gui_lab 去术语断言同步放行冒烟一词）。
测试：lab 两测试文件更新断言 + 3 新用例（fees 聚合、symbols 页、symbol 页结构）；
lab 65 全绿；全量 `pytest tests/ -q` → **2067 passed + 4 skipped**（2065 + 2 净增）
零回归。验证：restart qre-gui-lab 后 /、结果页、symbols、symbol、两个静态文件、
chart-data 全 200；chart-data.fees_summary 真值（18,346 笔，佣金 133.05 万 +
印花税 111.22 万 + 过户费 4.44 万 = 总磨损 248.70 万，毛收益 1,348.69 万）。
未 git commit，等用户审批（commit message 需先出示）。
上一任务：QRE-WORKER-ARTIFACT-PERSIST (DONE — 2065 tests green；awaiting git approval)

2026-09-08 QRE-UI-STYLE-GUIDE（规范文档 + 性能审计已 commit：127200b）。

2026-09-07（用户决策）：**8081 = SaaS staging（预发），ECS aguhuice.com = 生产**。
发布流程约定：改动 → 8081 验证 → 用户验收 → 部署 ECS。
8081 服务（qre-gui-lab，沿用服务名）ExecStart 已切换为 `qre saas --port 8081`
（lab*.py 代码保留在仓库，仅不再起服务；8080 qre-gui 不动）。环境变量在
`.env.saas-staging`（0600，gitignore .env.* 覆盖）：SAAS_DB_URL=本地库
aguhuice_local、SAAS_AUTH_CHANNEL=stub + SAAS_STUB_LOG + SAAS_STUB_ECHO=1
（staging 专用，生产严禁）。新系统服务 qre-saas-worker（轮询 8081，5s，
只读账号连本地大库）。新 `qre saas` CLI 子命令。端到端已验证：
dev_code 登录 → smoke job → worker done（65s）。全量 2054+4 绿。
未 git commit。
上一任务：QRE-SAAS-007 (DONE — 2052 tests green + 4 skipped；awaiting git approval)

2026-09-05: NL 编译链路因子名自动纠错层（用户直接指派；8081 gui/lab*.py
冻结页零改动，改动全在 8080/8081 共用的引擎/编译器侧）。痛点：DeepSeek
编造库中不存在的因子列名（rsi14/MACD 等），YAML 因缺因子失败、用户
只见红错。新 `gui/factor_correction.py` 纯函数层（零 DB 零 IO）：
auto_fix_column 保守三规则——归一化（小写+去下划线）等价 / 唯一候选
编辑距离 1 且次优差距 ≥3 / 唯一前缀（macd 系列多列并列则不纠正给候选）；
suggest_similar_columns Top-5；correct_factor_fields（同表候选优先、
同表空跨 8 个标准因子表兜底、列名对表写错直接换表，就地改写 target，
alias 与信号表达式不动）；COMMON_FACTOR_TARGETS 18 条常用已落库列。
compile_nl 在 missing_factors 判定前先纠错：全纠正成功重写 YAML 正常
返回（warnings 标「已自动纠正 X→Y」+ corrections 字段）；仍有未解决项
照旧入补因子队列，error 改 actionable（Top-5 候选 + 常用因子清单 +
suggestions 字段）。build_system_prompt 注入「严禁编造因子名」硬约束 +
常用已落库列。strategy_lab_routes 手工 YAML 通道（/api/strategies/create
mode=manual）同逻辑生效。测试 tests/test_gui_factor_correction.py +17。
未 git commit。
上一任务：QRE-GUI-POOL-MOM-007 (DONE — 1943 tests green + 4 skipped；awaiting git approval)

2026-09-04: 「聚类动量」页 v7 前端渲染性能（用户反馈卡顿，排查确认
瓶颈纯在前端 DOM：concept 1066 行 × 20 列 ≈ 2.1 万单元格 + 首列
sticky 重绘）。纯前端优化，API/数据/pool_momentum.py 零改动：
①默认 Top/Bottom 50 截断（MOM_EDGE_N=50 + momShowAll，.mom-gap 行
「显示全部 N 行」/「收起」按钮）；②精简列模式不再输出 mom-col-x
td/th（原 display:none 删除，展开更多列时才渲染）；③CSS 行级
content-visibility: auto + contain-intrinsic-size；④首列 sticky 仅
展开模式启用（.mom-scroll.mom-sticky）；⑤展开/收起只重渲本分区
（renderMomentumTable(poolType)），排序两表共享键仍同刷。单元格数
21,656 → 默认 ≈1,091（−95%）。改动 admin.html + style.css +
tests/test_gui_pool_momentum.py（+1，79 总；v5 断言同步删
mom-compact、加 v7 标记）。qre-gui 已重启 active；curl /admin 200
含新标记，overview API 200（988KB/0.12s）。未 git commit。
上一任务：QRE-GUI-POOL-MOM-006 (DONE — 1942 tests green + 4 skipped；awaiting git approval)

2026-09-04: 「聚类动量」页 v5 榜单可读性（用户反馈两 UI 问题）。
①concept 榜单 17+ 列横向溢出 → momTable 包 .mom-scroll 横向滚动 +
首列池名 sticky（热力行 background:inherit，行仅 heat 非空才输出
style）+ 默认精简列（池名/股票数/当前窗口 fwd/速度/加速度/共振/
⚠回避/事后×3），扩展列标 mom-col-x、.mom-compact 隐藏，
「#btn-mom-cols 展开更多列」开关切全量列。②点池名详情不再落页面
底部 → 删底部 data-section="mom-detail" 折叠区，新 #mom-detail-panel
固定于 #mom-summary 之下、榜单之上（标题 + 关闭按钮 + scrollIntoView，
点其他池原地替换）；成员明细 .mom-members-scroll 限高 420px 内部滚动
（表头 sticky 沿用全局）。改动集中 admin.html + style.css +
tests/test_gui_pool_momentum.py（+2，78 总）；pool_momentum.py 零改动。
qre-gui 已重启 active；curl /admin 200 含新标记，overview（真库
2026-09-03：concept 1066/state 14）与 detail API 200。未 git commit。
上一任务：QRE-GUI-POOL-MOM-005 (DONE — 1940 tests green + 4 skipped；awaiting git approval)

2026-09-02: 「聚类动量」页 v4 底部减速回避名单（M7 全历史结论：
fwd_ret_3 最弱 Bottom10 未来 3-5 日继续跑输约 0.2%/日，NW t=−3.86，
FDR q=0.001，20 日后消失；顶部信号全部无效）。纯函数
compute_bottom_avoid（组内最低 10 个标 avoid，None 与 n_stocks<10
剔除）+ avoid_list；overview payload 加 avoid 三键；榜单行「⚠ 回避」
徽章（白底红框区别于热力背景，title 注依据）+ 顶部 #mom-avoid 汇总卡
（点击跳详情）+ 声明卡补「顶部无选股价值，主要价值=底部回避名单」。
历史回看按选中日截面 point-in-time。测试 +11（76 总）。qre-gui 已重启
active；真库 2026-08-31 concept 回避居首「申万L3:疫苗」−5.73%，state
14 有效池取最低 10（跳空:低开 −2.35% 居首）。未 git commit。
上一任务：QRE-GUI-POOL-MOM-004 (DONE — 1929 tests green + 4 skipped；awaiting git approval)

2026-09-01: 「聚类动量」页 v3 历史回看。overview 加 trade_date 参 + fwd
可选日期下拉（249 日，point-in-time 榜单）；事后验证列 post_3/5/20
（compute_post_returns 纯函数，∏(1+fwd_ret)−1 over (T,T+w]，未满窗口→
NULL）；验证摘要条（accel_top_summary 纯函数，加速度 Top10 post_5 均值/
中位/胜率 vs 全体）；detail 加 end_date、members 传选中日期。测试 +11
（65 总）。qre-gui 已重启 active；真库 2025-09-05 concept 加速度 Top10
post_5 +0.19% vs 全体 +0.88%（该日无超额，如实呈现）。未 git commit。
上一任务：QRE-GUI-POOL-MOM-003 (DONE — 1918 tests green + 4 skipped；awaiting git approval)

2026-09-01: 「聚类动量」页升级 M7 v2 前瞻口径。速度/加速度/热力/共振全切
fwd_ret_w（compute_acceleration/compute_heat 加 metric 参、resonance 判
fwd）；回看 ret_w 降级对照列；overview 默认展示最近 fwd 已补齐日
（fwd_lag 红色提示末日 NULL=正常 T+1 滞后）；state 分区 8 个 artifact
池加事件 4 列（次日溢价/存活/胜率，对标同花顺涨停复盘）；详情主线 fwd、
回看浅色辅线；声明卡改写。测试 +9（54 总）。qre-gui 已重启 active；
真库榜单日 2026-08-31，concept fwd_ret_3 榜首「昨日打二板以上表现」。
未 git commit，等用户审批。
上一任务：QRE-GUI-POOL-MOM-002 (DONE — 1909 tests green + 4 skipped；awaiting git approval)

2026-09-01: 「聚类动量」页三项优化。①池内个股明细：新 API
/api/admin/pool-momentum/members（concept=company_tags 快照、state=当日
daily_tags；compute_member_metrics 纯函数即时算 stock_daily，口径与 M7
管线逐位一致——成员等权 ret_3 与池表值完全相等、有效成员数==n_stocks；
名称 reference.stock_basic 降级可选），详情区新增可排序成员表。②主榜单
全数值列+成员表点击表头排序（▼/▲、None 恒末位）。③行热力 compute_heat
（ret_w 截面分位 heat∈[-1,1]，红涨绿跌）随窗口重算；长弱短升改左侧绿边
+加粗。测试 +21（45 总）。qre-gui 已重启 active，curl 全 200。
未 git commit，等用户审批。
上一任务：QRE-GUI-POOL-MOM-001 (DONE — 1888 tests green + 4 skipped；awaiting git approval)

2026-09-01: 8080 管理台新增「聚类动量因子研究」tab（data-tab="mom"），
只读 cluster.pool_momentum_daily（cluster-ashare M7 产物）。新
gui/pool_momentum.py（market_risk.py 同款只读数据层 + 纯逻辑
rank_desc/compute_acceleration/resonance_flag/sort_by_acceleration）；
app.py +/api/admin/pool-momentum[/detail]；admin.html +tab（偏差声明
卡 + 窗口 3/5/20/50 切换 + concept/state 双榜单 15 列 + 长弱短升高亮 +
点击池名 250 日 inline SVG 详情）；style.css 纯追加。8081 零改动。
测试 tests/test_gui_pool_momentum.py +24。qre-gui 已重启 active，
真库 curl 三端实测 ok（2026-09-01：concept 1066 / state 14）。
未 git commit，等用户审批。
上一任务：QRE-GUI-LAB-RESULT-030 (DONE — 1840 tests green + 4 skipped；awaiting git approval)

2026-08-31: B 层关键词换代（cluster-ashare 东财+同花顺概念板块成分替换 jieba
碎片词，旧数据已删 97,838 行）+ 8080 总览「概念标签源（B 层）」卡片
（admin.py overview_concept_tags / app.py payload / admin.html 卡片）；
8081 归因端零改动实测受益（B 层真概念词：华为概念/CPO概念/PCB 等）。
cluster-ashare 204 passed。遗留：东财接口当日断连，504 板块入库 290，
网络恢复后重跑幂等补齐。未 git commit，等用户审批。
上一任务：QRE-GUI-LAB-RESULT-023~026 (DONE — 1824 tests green + 4 skipped；awaiting git approval)

2026-08-24: ①NL 示例编译失败无法复现（curl 4/4 + jsdom 点击流均成功，
疑 DeepSeek 抖动/缓存旧页）②高级选项七输入补 change+input 监听即时刷新
YAML 预览 ③向导页加「存入沙箱+冒烟测试」主按钮（saveAndSmoke 共用流程），
「去高级 YAML」降为次按钮，向导全程鼠标闭环不强制跳 tab。8080 零改动。
上一任务：QRE-GUI-LAB-ENTRY-021 (DONE — 1809 tests green；见 05/09)
两步确认显性化：晋升按钮改「正式回测（晋升）」confirm 带冒烟摘要。
selectedFactors 改由条件行使用推导（usedFactors），删除 #wz-factor-groups。
style.css 纯追加；零新前端依赖；API 契约零变化。测试 test_gui_lab.py +1。
冒烟：qre-gui-lab 重启 active，8081 / 200 含三 entry-tab 标记，8080 / 200；
node 语法自检三个 script 块全过。无 CR。未 git commit，等用户审批。
上一任务：QRE-GUI-LAB-PORT-017 (DONE — 1807 tests green + 4 skipped；见 05/09)

2026-08-23: 回测台新端口移植——「新增策略」+「回测管理（策略状态）」
两页面原样移植到独立 Flask 应用 @8081（纯移植零优化）。路由共享：
新 gui/strategy_lab_routes.py::register_strategy_lab_routes(app)，
create_app 与 create_lab_app 共用；新 create_app 路由表与 git HEAD
逐条相等（59/59）。try_acquire_run_slot/release_run_slot/run_backtest
在 app.py re-export 并经 gui.app 调用时解析（兼容既有测试 monkeypatch）。
新 gui/lab.py + templates/lab.html（两 tab 内容脚本切片组装，含排序
JS/搜索/toggle/删除/gate 徽标；附 /runs 页面）。CLI：qre gui --lab
（默认 8081）。systemd：deploy/hardened/qre-gui-lab.service 已安装
enable --now（enabled/active，SyslogIdentifier=qre-gui-lab）。
测试 tests/test_gui_lab.py +12。冒烟：8081 / 双 tab、/api/admin/refresh
stopped 118/118（8080 一致）、策略详情 200；8080 / 与 /admin 200。
两个 service 均已重启。无 CR（纯移植）。未 git commit。
上一任务：QRE-GUI-SORT-016 (DONE — 1795 tests green + 4 skipped；见 05/09)

2026-08-23: 策略状态表客户端排序（回测起止/股票数量/超额收益/最大回撤
四列可点击，升降序切换，null 恒排末位；纯模板 JS）。下游补跑链验证：
四 service 补跑 exit 0，stock_daily/factors/cluster.daily_tags/
market_risk.daily watermark 全到 2026-08-21，周五事故清零。qre-gui 已重启。
上一任务：QRE-GUI-DERIV-FRESH-015 (DONE — 1795 tests green；见 05/09)

2026-08-23: 风向标 M3 落地（CR 状态改「✅ M1–M3 已完成」）。
deploy/hardened/qre-barometer.{service,timer}（Mon..Fri 18:30、Persistent、
默认最近交易日，未 sudo）；barometer_job latest_trade_date 默认日期 +
`qre barometer` CLI；admin TIMER_UNITS/PIPELINES 登记；/admin 新「大盘
风险」tab（gui/market_risk.py 只读 market_risk.daily + 仪表盘/五序列
SVG/双口径热力表/预警详情，复用现有样式）；阈值首轮校准观察入 06
（red 11/1850=0.59% 全为已知风险事件，初值保留）。真库冒烟 ok。
1778 tests green（+14）。未 commit、未重启 qre-gui、未装 timer。
详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-BAROMETER-M2-009 (DONE — 1764 tests green；commit b0713d7)

2026-08-23: 大盘/板块风险风向标 M2 落地（CR_2026-08-23_market_risk_barometer
§5 M2 阶段；M1 = commit 64addd7）。新 risk/barometer_job.py（risk 包唯一
读写 DB 层：pct_chg/100 收益 + total_mv 市值 + industry 行业 +
daily_tags 当日簇 <5 跳过 → M1 纯函数 → 独立 schema market_risk.daily
表（PK (trade_date,scope)、ON CONFLICT 幂等 upsert）+ JSON 产物
outputs/market_risk/<date>.json；年分块 + 312 交易日 buffer）。真实回填
2019-01-02→2026-08-20：220,034 行 / 1,850 日 × 120 scope，~21min。
方向性验证全过：2020-02-03 red（突破 85.2% P100）、2024-02 微盘连续
red（总分 P99–100）、常态 green；全样本 red 11 天均为已知风险事件。
1764 tests green（+10）。未 commit、未重启 qre-gui。详见
09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-BAROMETER-M1-008 (DONE — 1754 tests green；commit 64addd7)

2026-08-23: 大盘/板块风险风向标 M1 落地（CR_2026-08-23_market_risk_barometer
§5 M1 阶段）。risk 包新增 cross_section.py（纯函数零 DB、向量化：EWMA
方差面板与 volatility 单列口径 atol 1e-15 一致、截面波动率中位/90 分位、
等权/市值加权离散度、滚动 60 日平均两两相关等权 + w_i·w_j 偶权近似、
VaR 突破计数/占比、summary 一把梭 σ shift(1) 防前视）与 barometer.py
（组合法 100% 复用 volatility/tail、252 日滚动分位分数 warmup 降级
None、红/黄/绿双判据预警、build_barometer 全市场+板块统一 dict、分组
映射调用方传入）；constants.py 加 BAROMETER_CORR_WINDOW=60/
SCORE_WINDOW=252/ALERT_CORR_LOOKBACK=20/ALERT_CORR_JUMP=0.10/
ALERT_BREACH_RATIO_MAX=0.03/BREACH_CONFIDENCE=0.99/
CROSS_SECTION_SIGMA_QUANTILE=0.90 全回显（阈值初值待 M3 校准）。
1754 tests green（+30：cross_section 17 + barometer 13）。全量首跑
test_gui_risk_report.py::test_post_conflict_409 flake，复跑全绿。
未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-PORTFOLIO-007 (DONE — 1724 tests green；awaiting git approval)

2026-08-23: FRM 风险模块 R7 落地（CR_2026-08-23_risk_derivatives_extension
R7 阶段，CR 状态改「R5–R7 已完成」；R5=5472832、R6 待审批）。新
risk/portfolio.py（纯函数零 DB，summarize_mixed_portfolio：股票腿沿用
R1–R4 收益序列法、债券/转债腿 DV01 可加 + D/C 市值加权 + 可选 KR01 按
节点加总、期权腿组合 Greeks 加权求和、config 显式给 dgv.spot_shock_sd
才计算 DGV-VaR；仅股票退化为仅 equity 节）；risk/report.py 显式传入
bond_positions/option_positions/bond_kr01 才追加 portfolio 节 +
markdown「组合与衍生品风险」渲染；GUI run_detail 有节才追加「衍生品风险
（组合层）」卡片（_risk_display + risk-card 模式）；constants.py 加
GATE_DV01_MAX/GATE_GREEKS_MAX（默认 None=不启用），evaluate_gate_risk
启用时追加组合 DV01/Greeks 限额判据、默认关闭时返回与 R4 逐键一致。
1724 tests green（+28：portfolio 14 + report 7 + gui 7）。默认 run 产物
零变化，老格式 report 向后兼容专项测试覆盖。未 commit、未重启 qre-gui。
详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-OPTIONS-006 (DONE — 1696 tests green；awaiting git approval)

2026-08-23: FRM 风险模块 R6 落地（CR_2026-08-23_risk_derivatives_extension
R6 阶段；R5=5472832）。risk 包新增 options.py（BSM 式 15.6–15.9 无股息/
q/离散股息 S₀−D、Black's 式 15.12/15.13、隐波 brentq IV_BRACKET、CRR
式 14.4–14.7 欧式+美式含 q + 第一层 delta + 可选全节点网格、美式 Greeks
数值差分（书4 Ch16）、Greeks 解析全组 Table 16.2 含 q 版与期货期权版
rho=−f·T、组合 Greeks 加权）与 derivatives_var.py（DGV 近似 P&L
式 2.3+vega 项、非中心卡方累积量解析矩、正态/Cornish-Fisher 分位 VaR、
VaR 序列对接 backtest_var_summary 复用 HIT/LR）；constants.py 加
IV_BRACKET/DEFAULT_TREE_STEPS=50/GREEK_SHOCK_*（全部 dict 回显）。
教材数值全复现：BSM 例 c=8.3069/p=7.9715+parity、隐波 7.00→25.14%、
美式 put 节点 3.058/0.494/5.699（欧式 2.838，参数 S=29,K=30,r=3%,σ=25%,
T=1 经教材原文 p193 核对）、收敛 3.082/3.067/3.059/3.055、PDE 恒等式
1e-10、纯 gamma 解析二阶矩、CF-VaR 对 MC rel 5%、VaR 序列回测违约率
≈1% 不拒绝。自审修正 Black76 theta 符号（有限差分自检发现）。
纯函数零 DB 零行情，既有 risk 模块零行为改动。1696 tests green（+39）。
未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-RATES-005 (DONE — 1657 tests green；awaiting git approval)

2026-08-23: FRM 风险模块 R5 落地（CR_2026-08-23_risk_derivatives_extension
R5 阶段；R1=96db59d / R2=f52c0f4 / R3=6852eaa，R4 待审批）。risk 包新增
rates.py（式 16.1–16.5 复利换算、PV/FV、spot↔折现因子、书4 Ch9 附息债
bootstrap 零息曲线、线性/对数线性插值、远期利率、par yield 式 16.7/10.4）
与 bonds.py（YTM brentq、actual/actual+30/360 应计利息、式 12.6 久期凸性、
effective duration/convexity、DV01 与 D↔DV01、组合聚合与对冲配比、
式 12.4 二阶近似、书4 Ch13 KR01（ΣKR01=DV01 自检）、书3 Ch16/17 转债
债底+spread duration）；constants.py 加 DEFAULT_DAY_COUNT/
CURVE_INTERPOLATION/KEY_RATE_TENORS/RATE_SHOCK_BP/YTM_BRACKET（全部
结果 dict 回显）；pyproject.toml 补 scipy 显式依赖。教材数值全复现：
bootstrap d=0.991909/0.980944/0.969406/0.956909、par yield 2.2103%、
年金解析解 P/D/C、ΣKR01=DV01、+100bp 二阶近似 rel 偏差 1.9e-5。
纯函数零 DB 零行情，既有 risk 模块零行为改动。1657 tests green（+52）。
未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-GATE-004 (DONE — 1605 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R4 落地（R1=96db59d / R2=f52c0f4 / R3=6852eaa）。
晋升全量回测闸加入风险判据：risk/constants.py 加 GATE_ES99_MAX=0.03 /
GATE_VAR_CONFIDENCE=0.99；gui/risk_report.py 加 evaluate_gate_risk（读
runs/<run_id>/risk_report.json，ES99 超阈或 99% 覆盖率 Kupiec LR 拒绝 →
risk=warning，缺失 → unavailable 不阻断）；finalize_promotion_gate 写
gate json risk 节（主判据照旧）；gate_blocks_daily 扩展 failed 或
risk=warning 非 forced 即阻止日更（force 照评估不阻断）；admin.html
闸列 warning 追加「⚠ 风险警示」徽标（tooltip ES99 + VaR 回测结论）
+ style.css .gate-risk。存量 gate json 无 risk 节行为不变。1605 tests
green（+6）。未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-INTEGRATION-003 (DONE — 1599 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R3 落地（R1=96db59d / R2=f52c0f4）。risk 包集成进
回测报告与 GUI：risk/report.py + render_risk_markdown（汉化风险分析节，
两位小数，分布与尾部/VaR回测/波动率/压力/绩效分区，error 降级）；
新 gui/risk_report.py（组合级 equity_curve.csv daily_return 提取 +
benchmark_close 可选 + finalize 钩子写 runs/<run_id>/risk_report.json +
幂等追加 summary.md 风险节 + daily_jobs 按需 job bootstrap 开）；
engine.py:354-361 收尾钩子（try/except 兜底同 smoke/promotion_gate）；
app.py run_detail risk 视图 + POST/GET risk-report 端点（404/400/409）；
run_detail.html 风险分析六卡片 + 老 run 按需生成按钮。#4 admin badge
未加（refresh_overview 无 risk_report，硬塞超范围）。真实 E2E：mr01a
5 股×2024-2025，n=484，99% VaR 1.50%/1.79%、ES 1.72%/2.19%，JB
p<0.0001，VaR 回测两级均不拒绝，summary.md 风险节落盘。未 commit、
未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-CORE-002 (DONE — 1578 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R2 落地（R1 = commit 96db59d）。risk 包新增
backtest_var（书2 Ch6：HIT、覆盖率 Bernoulli LR + 精确二项、独立性
Christoffersen 转移矩阵 LR——摘要未点名 Kupiec/Christoffersen 如实标注、
多重检验假阳性 1−(1−α)ⁿ）、stress（书4 Ch8：A 股四情景库、回放累计损失/
峰谷/Peak/VaR + 相关性崩溃提示、reverse stress β 穿透反查市场冲击分位/
σ 倍数）、inference（书2 Ch13：arch CBB 块长 √n 给年化收益/夏普/最大
回撤 CI + iid 对照 + MC 标准误 σ/√b）；report.py 升 R2（var_backtest
默认开用 EWMA μ=0 VaR 防前视，stress/bootstrap config 可选开启）。
46 个新测试全为已知答案核对（LR 手算 4.13085、转移计数手算、回放
−0.119179/0.05/2.5、reverse β=2、bootstrap 固定 seed CI 含真值 +
AR(1) 下 iid 低估 CBB）。未 commit、未重启 qre-gui。详见
09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-CORE-001 (DONE — 1532 tests green；commit 96db59d)。

2026-08-20: deep-validate 501 骨架落地为真功能。cluster-ashare 新增薄脚本
analysis/pool_from_conditions.py（条件 JSON→逐日池 parquet，DB 全留 cluster
侧，表达式求值复用 QRE evaluate_expression_signal；未走 factor_executor——
其分位/tag 语义与 QRE 布尔 DSL 不匹配）；QRE 新增 gui/deep_validate.py
（spec_to_conditions 纯函数转换器/locate_strategy_yaml/parse_report_summary/
start_deep_validate_job，复用 daily_jobs 基建，lock_key=deep-validate:<name>，
price/eval 缓存键含区间断点续跑）；app.py POST/GET deep-validate 真实现
（404/400×3/500/409 分层，缺因子自动入队）；index.html 沙箱行按钮+通用
入口+10s 轮询不设放弃上限。真实 E2E：mr01a 全历史 → NO-GO（gate3 净超额
-0.130% t=-10.75），报告落 cluster outputs/factor_mining/validation/。
未重启 qre-gui，GUI HTTP 链路待重启验证。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-GUI-PROMO-GATE-001。

2026-08-20: 全量回测结果成为晋升后的状态闸。晋升 mark 加 promotion_gate/
promotion_forced（线程启动前预合并）；engine 收尾新钩子 →
strategy_create.finalize_promotion_gate（写死判据：交易≥30 且超额>0 →
passed）原子写 outputs/refresh/gates/<name>.json（catalog 不动）；refresh_batch
日更跳过 gate=failed 非 forced（日志 + config.gate_skipped），refresh_overview
行加 gate 字段；admin.html 策略状态表加「全量回测闸」四态列（绿/红+tooltip/
灰/橙强制在库）；force 晋升评估照跑不阻止日更（API gate_note 注明）；新增
POST /api/strategies/<name>/deep-validate 501 骨架（策略→信号池转换器待实现）。
未重启 qre-gui，真实 E2E 待重启验证。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-GUI-CREATE-GAPS-001。

2026-08-20: GUI 新增策略/因子闭环四缺口补齐——①策略冒烟 sidecar 闭环
（engine 终态钩子 + mark 预合并消竞态 + list_sandbox 自愈 + 前端三色渲染）；
②晋升冒烟状态闸（promote/promote_factor 加 force，smoke_not_passed → 409）；
③因子冒烟同步改异步（复用 daily_jobs lock_key 机制，POST 返回 job_id +
GET 轮询端点 + 前端轮询）；④删 .p3c-hidden 死代码。未重启 qre-gui，
真实 E2E 待重启验证。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-ADMIN-FACTOR-FRESH-001。

2026-08-19: dashboard 新增「聚类分析」tab（只读展示 cluster-ashare 因子工厂
产出）：gui/cluster_admin.py（QRE_CLUSTER_REPO，分区降级+TTL 300s 缓存），
app.py +/api/admin/cluster 与 /api/admin/cluster/artifact/<path> 下载白名单，
admin.html 第 6 tab 四分区（38 因子注册表/M4 轨迹+traj13 成员/衰减监控
9-23-5/13 个产物链接）。重启 qre-gui 实测全 ok。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-M5C-MINED-FACTOR-STRAT-001。

2026-08-18: 因子工厂 Top3（cluster.mined_factors MF_001/002/003）转译为
cs07a/b/c（catalog/cross_sectional/），截面分位由 cluster-ashare 物化表
cluster.mined_factor_flags 承载（QRE 三段式寻址 cluster schema，零引擎改动）。
闭环：沙箱 3/3 → 冒烟 20 股×半年 3/3 → 晋升 → 全市场 3820 股×近 1 年
（成本/止损 8%/universe 过滤/基准 000300.SH，批次 b21f1008ec98）3/3 ok →
report-audit 6/6 ok。结论：近 1 年未复现 M3b 超额（-11.1/-11.3/-11.6% vs
基准），建议三因子转「衰减观察」（cluster 侧 status 调整待用户确认）。
详见 09_CODING_HANDOFF 顶部。上一任务：QRE-ADMIN-TIMERS-001。

2026-08-12: GUI 首页三 tab → 两 tab（新增策略一页三入口 + 新增因子路径 A/B，fc-create 迁入首页，tab-builder 删除，app.py 零改动）。详见 09_CODING_HANDOFF 顶部。上一任务：QRE-ADMIN-STRAT-INCREMENTAL-FIX-001（策略状态 tab 增量合并）。

2026-08-12: GUI 新因子创建闭环 P2（/api/factor-create/* + indicators sandbox 冒烟 + 晋升 validate→backfill job）。真实 E2E：vidya 因子 DeepSeek 生成 → 冒烟过 → 晋升 job 20260812T030850074330。详见 09_CODING_HANDOFF 顶部。上一任务：QRE-ADMIN-CONSOLE-P3A-001 + QRE-ADMIN-FACTOR-HEALTH-FIX-001 (1264 tests green)。

2026-07-28: admin console read-only slice (dashboard/timers/query) + factor-health fix (managed-table whitelist from indicators config; vortex orphan table demoted to informational). quant_ts upstream fix: normalize_reference_frame numeric coercion (daily_basic text→NUMERIC staging conflict), daily rerun completed, watermark 2026-07-27. Health: green.

Earlier 2026-07-27: GUI workbench P1 (params form/async/precheck/compare) + P1.5 (factor-first wizard + factor-admin panel) + P2 (NL→YAML compiler). Design docs: gui_backtest_workbench.md, gui_factor_first_wizard.md, gui_admin_console.md.

## Pending Decisions (user)

1. GUI acceptance on `http://localhost:8080` (+ `/admin`); NL channel needs QRE_NL_LLM_* env.
2. Optional: drop orphan empty table `factors.stock_daily_vortex_close` (destructive, needs explicit OK).
3. P3b: manual daily-trigger buttons + integration center (refresh registration) + timer log tail; P3c: maintenance tab. qre-refresh.timer install needs sudo (user runs command).
4. TimescaleDB hypertable re-registration project — unscheduled.

Then (user-directed): output-file optimization based on user inspection of `outputs/backtests/full_history_check2/ef8006cb8f4d/` (2 strategies × full market × 2010-2026).

Progress:
1. Verified canonical project `/home/van/quant-workspace/indicators_tushare` and systemd timers (quant-ts 16:30, indicators 16:40, both enabled; yaml-config factors auto-join daily updates).
2. Edits made (indicators repo, no git action): `config/factors.yaml` sma periods += 7/9/26/50/52 + `atrraw` entry; `factors/volatility_factors.py` new `ATRRawFactor` class (raw `atr_{n}` naming; same values as existing `atrr_10`).
3. Project flow: validate (success, 0 failures) → plan (all 7 target columns present; superset: other pending config columns in overlap/volatility categories also covered) → small-sample backfill of 000001.SZ → value parity vs hand-computed SMA/Wilder-ATR within storage rounding, 100% non-null.
4. Full-history backfill (`backfill --categories overlap volatility --execute --max-workers 4`) RUNNING in background.

Next when backfill completes: `factor_request_queue.py recheck` → fulfilled; small-sample re-run of the 5 shelved strategies (R-QRE-009); then user decides on full re-run.

## Standing Instructions (user)

- 2026-07-19: No full-scale backtest runs until the core engine work is mostly complete; after that, full-history (M9.4) runs start with small samples (R-QRE-009). Current slices (M10.1 analysis of existing artifacts) comply — zero backtest execution.

Parent change request: `docs/agent/change_requests/CR-0002-strategy-research-validation.md` (Milestone 9: Strategy Research Validation).

## Last Completed Step

**QRE-ANALYTICS-CONCAT-001 (DONE, finalized 2026-07-19, commit `b72b9af`):** backtest stage 25.852s — M9.1b ≤30s target MET (66.5×).

**QRE-TRAILING-STOP-BATCH-001 (DONE, finalized 2026-07-19, commit `77b8897`):** stop family complete in batch path.

**QRE-MISSING-FACTOR-QUEUE-001 (DONE, finalized 2026-07-19, commit `5c60b8b`):** queue store + shelve semantics + auto-queue + CLI + `docs/handoff.md`; 7 pending requests tracked.

**QRE-PREFLIGHT-MISSING-FACTOR-ROBUSTNESS-001 (DONE, finalized 2026-07-19, commit `6628631`).**

**QRE-BATCH-FULL-VALIDATION-001 / M9.4 pilot (DONE, finalized 2026-07-19, commit `f90567c`):** handoff emitted (7 requests); small-sample full-history pilot OK; ~3h full-scale estimate. Full-scale trigger + upstream factors remain user decisions.

**QRE-CONTINUOUS-REFRESH-001 / M10.3 (DONE, finalized 2026-07-19, commit `1345471`):**

1. `orchestration/refresh.py`: watermark query, RefreshState, rolling window, per-strategy delta computation, delta report writer with manifest.
2. `scripts/refresh_batch.py`: check-only/force/window/codes flags; idempotent vectorized re-run; state + delta persisted.
3. `deploy/qre-refresh.{service,timer}` documented (daily 18:30), NOT installed; README 7b-2 with install commands.
4. Small-sample e2e on real data: first run 106 ok/111; check-only side-effect free; same-watermark no-op; delta manifest audit ok.
5. 1118 tests green (9 new). No full-scale execution (standing instruction honored).

**QRE-STOPS-BATCH-ENGINE-001 / M10.2b (DONE, finalized 2026-07-19, commit `24c284d`):**

1. stop_loss_pct/take_profit_pct honored in both engines: close-based evaluation vs fill price, next-open execution, precedence pending retry > expiry > stop_loss > take_profit > exit_signal; dense candidates in vectorized engine when enabled.
2. Opt-in wiring: `apply_stops` + request overrides (None = spec values); shared mode passthrough incl. trailing_stop_pct; runner `--apply-stops/--stop-loss-pct/--take-profit-pct`.
3. Verification: 50 new tests (40 randomized-with-stops equality seeds); real-DB dual-engine identity (tf01a, mr04a); A/B effect + real stop_loss exit observed; default runs unchanged.
4. 1109 tests green. Trailing stop remains follow-up (shared engine already has it).

**QRE-PARAM-OVERRIDE-001 / M10.2a (DONE, finalized 2026-07-19, commit `a16d6c5`):**

1. `portfolio/universe.py`: metadata loader (stock_suspend/stock_st as-of, daily-derived list_date) + `apply_universe_filter` with complete drop accounting and honest `unavailable_rules`; `validate_profile_overrides`.
2. research_run: `profile_overrides` (dataclasses.replace + validation) and `universe_filter` (opt-in) wired for batch/shared modes; `universe_report.json` backtest artifact; manifest records overrides + flag.
3. Runner flags: `--universe-filter`, `--commission-rate/--min-commission/--stamp-tax/--transfer-fee/--slippage-buy/--slippage-sell`.
4. Small-sample verified: overrides measurably change results; unavailable rules honestly reported on real data; default runs unchanged.
5. 1059 tests green (14 new). Stops split to M10.2b (engine exit logic, dual-engine equality).

**QRE-STRATEGY-FIT-ANALYSIS-001 / M10.1 (DONE, finalized 2026-07-19, commit `d514c4c`):**

1. `analysis/strategy_fit.py`: exact binomial significance tiers (90/99/99.9%), magnitude gate (net + excess vs buy-hold), free-rider accounting, strategy meta-test vs false-positive expectation, hypergeometric enrichment, BH-FDR, deterministic outputs + manifest.
2. `scripts/strategy_fit_report.py` + `strategy_fit_report_manifest` kind registered (report-audit passes); runner `--metadata-columns` passthrough.
3. Metadata reality: `reference.stock_basic` EMPTY upstream — metadata composed from `daily_basic` snapshot + `derive_board`; `industry_group` = unknown (gap documented).
4. Real batch (2024, 106 strategies): **all below 90% meta tier** (significant-stock counts below false-positive expectation — hand-verified true result); 25 stocks at 99% tier recorded as leads in `strategy_fit_stocks.csv`.
5. 1045 tests green (11 new); R-QRE-008 screening-evidence caveat in report.

**QRE-VECTORIZED-ENGINE-001 / M9.1b (DONE, finalized 2026-07-19, commit `c86441b`):**

1. Vectorized trade-level single-symbol engine: event-level loop on candidate bars, one-pass groupby pre-split, vectorized equity reconstruction; `position_sizing` (`full_compound`/`fixed_cash`).
2. Vectorized window/rolling analytics collectors (`risk.py` untouched, used as equality oracle); shared research frame between eval and backtest stages.
3. Equality evidence: 61 synthetic + 40 randomized tests, 106/106 catalog × 50 symbols byte-identical, full-market artifacts identical to simulator baseline.
4. Benchmark: backtest stage 1,718.9s → 40.2s (**42.8×**); quick batch estimate 11.1h → ~25-30 min. Runner `--engine-impl` defaults to `vectorized` (simulator kept as fallback); 1034 tests green.

**QRE-BATCH-PERF-SLIM-001 / M9.1 (DONE, finalized 2026-07-19, commit `24699ce`):**

1. Batch runner core moved into `orchestration/batch_runner.py`; `--jobs N` process-pool parallelism; `--compact` output mode (9 files vs ~26k per strategy, metrics byte-identical).
2. Per-stage timing in research-run manifests; `PostgresDataStore.close()` engine disposal; resume scan fixed (both directory levels).
3. Profiling baseline: tf01a quick mode serial = 1742.5s (backtest stage 98.6%); data-load reuse ruled out by evidence.
4. Quick batch `f365c8a07b33` (2026-07-19 06:32 +08): **106 OK / 5 error** (known missing-factor strategies), wall time **11.1h** with 4 jobs (vs ~51h serial), per-strategy mean 1459s (-16%), **2,013 files / 2.8GB** (~99.9% fewer files, ~89% fewer bytes); `qre report-audit` on compact manifests → ok.
5. Milestone 10 planned (CR-0003): M10.1 strategy-fit clustering, M10.2 parameter overrides, M10.3 continuous refresh, M10.4 optional ML clustering; M9.2/M9.3 merged into M10.1.
6. R-QRE-009 locked (user standing instruction): small-sample validation before any full-scale run.

## Git State

- Current branch: `master`
- Last commit: `96db59d` feat(risk): FRM 风险模块 R1 核心包（R2+R3 未 commit，工作树含两者改动）
- Working tree: R2/R3 改动 + untracked `.claude/scheduled_tasks.lock` (lock file, intentionally untracked)。
- **Run outputs now live outside the repo**: `outputs` → symlink to `/home/van/qre-outputs/` (all 19GB preserved there); `QRE_OUTPUT_DIR` env var overrides the batch runner output root.
- Remote: none configured.

## Latest Validation Evidence

```
uv run pytest -q → 1960 passed, 4 skipped, 4 warnings（2026-09-05, QRE-NL-FACTOR-AUTOCORRECT-001；基线 1943 + 17 净增）
纠错演示（内存 column_lookup 桩）：编造 rsi14 + macd_x_12_26_9 → 自动纠正 rsi_14 + macd_12_26_9 并标注「已自动纠正」；
  rsi_99 无可靠匹配 → 报错附 Top-5 候选（rsi_14/rsi_6/…）+ 常用因子清单，照常入补因子队列
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest -q → 1795 passed, 4 skipped, 4 warnings（2026-08-23, QRE-DERIV-ADAPTER-013；基线 1784 + 11 净增）
带库：QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data pytest tests/test_data_derivatives.py → 15 passed
真实冒烟：scripts/derivatives_adapter_smoke.py 2026-08-21 → 曲线 8 节点 1.164%–2.110%；
  转债债底 5 只 99.14–101.74 vs bond_value 105.4–111.2（赎回溢价差异可解释）；
  50ETF 平值 K=3.0 call/put IV 13.67%（parity 标的 2.9931）
基线首跑 test_gui_admin_p3b.py::test_daily_job_lock_per_pipeline 失败，单独复跑绿（已知 flake 家族）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1778 passed, 4 warnings（2026-08-23, QRE-RISK-BAROMETER-M3-010；基线 1764 + 14 净增）
真实冒烟：market_risk_overview() 真库 ok（2026-08-20 总分 63.3 green，252 日序列，105 行业，14 簇）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1764 passed, 4 warnings（2026-08-23, QRE-RISK-BAROMETER-M2-009；基线 1754 + 10 净增）
真实回填：2019-01-02→2026-08-20，8 年块，220,034 行 / 1,850 交易日 × 120 scope，~21min
方向性验证：2020-02-03 red（breach 85.2% P100）、2024-02-05 red（score 99.4 P100）、常态 2023-06 green（P10–21）；red 11 天全为已知风险事件
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1754 passed, 4 warnings（2026-08-23, QRE-RISK-BAROMETER-M1-008；基线 1724 + 30 净增）
风险新单测 30/30 绿（cross_section 17：面板对单列一致/相关==np.corrcoef/离散度手算/突破计数；barometer 13：组合法对 tail+volatility 逐键一致/预警三态/warmup 降级/等权 vs 市值加权差异）
scripts/check-progress-docs.sh → passed
git diff --check → clean
注：全量首跑 test_gui_risk_report.py::test_post_conflict_409 失败，单独与全量复跑均绿（环境敏感 flake）
```

```
uv run pytest tests/ -x -q → 1724 passed, 4 warnings（2026-08-23, QRE-RISK-PORTFOLIO-007；基线 1696 + 28 净增）
风险新单测 28/28 绿（组合层退化/混合合并/KR01 加总/DGV 开关 + report 节开关与渲染两态 + GUI 卡片两态 + 闸默认关闭逐键一致与启用判据）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1696 passed, 4 warnings（2026-08-23, QRE-RISK-OPTIONS-006；基线 1657 + 39 净增）
风险新单测 39/39 绿（BSM/隐波/二叉树收敛/PDE/Black76/美式 Greeks/DGV 解析矩/CF/MC/回测集成全教材数值核对）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1657 passed, 4 warnings（2026-08-23, QRE-RISK-RATES-005；基线 1605 + 52 净增）
风险新单测 52/52 绿（bootstrap/par yield/年金解析解/DV01/KR01/情景/债底全教材数值核对）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1599 passed, 4 warnings（2026-08-22, QRE-RISK-INTEGRATION-003；基线 1578 + 21 净增）
scripts/check-progress-docs.sh → passed
git diff --check → clean
真实 E2E：run 20260822T114522831346（mr01a 5股×2024-2025）→ risk_report.json + summary.md 风险节
注：首跑 test_gui_factor_wizard.py::test_job_lock_conflict 失败，全量复跑 1599 全绿（已知 flake）
```

```
uv run pytest tests/ -x -q → 1578 passed, 4 warnings（2026-08-22, QRE-RISK-CORE-002；基线 1532 + 46 净增）
风险包单测 107/107 绿（R2 46 新：LR/转移计数/情景回放/reverse/bootstrap 全手算核对）
scripts/check-progress-docs.sh → passed
git diff --check → clean
注：基线首跑 test_gui_factor_wizard.py::test_job_lock_conflict 失败，单独+全量复跑均绿（环境敏感 flake，非本任务引入）
```

```
uv run pytest tests/ -x -q → 1532 passed, 4 warnings（2026-08-22, QRE-RISK-CORE-001；基线 1471 + 61 净增）
风险包单测 61/61 绿（教材例题/解析解/手算/scipy 对照全覆盖）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1471 passed, 4 warnings (2026-08-20, QRE-GUI-DEEP-VALIDATE-001)
node --check index.html 三段内联 JS → OK
真实 E2E：mr01a 全历史（2015-01-01~2026-08-19）池 2826 信号日/均 3770 只；
四关验证 ~14min → NO-GO（gate1 -0.087% t=-13.12 / gate3 -0.130% t=-10.75 /
gate4 等权 -0.080% t=-18.64）；parse_report_summary 对真实报告逐关解析正确
未重启 qre-gui（用户约束）；未 commit
```

```
uv run pytest tests/ -x -q → 1454 passed, 4 warnings (2026-08-20, QRE-GUI-PROMO-GATE-001)
node --check admin.html 内联 JS → 随 test_gui_admin 通过
未重启 qre-gui（用户约束）；未 commit
```

```
uv run pytest tests/ -x -q → 1437 passed, 4 warnings (2026-08-20, QRE-GUI-CREATE-GAPS-001)
node --check index.html 三段内联 JS → OK
grep .p3c-hidden / TODO-P3c → 全仓零引用（仅剩「断言不存在」测试）
未重启 qre-gui（用户约束）
```

```
uv run pytest tests/ -x -q → 1412 passed, 4 warnings (2026-08-19, QRE-ADMIN-CLUSTER-001)
curl /admin → 200；/api/admin/cluster 四分区全 ok
下载白名单：md/json 200，parquet 404，路径穿越 404
systemctl restart qre-gui.service → active
```

```
uv run pytest -q → 1034 passed, 4 warnings (2026-07-19, M9.1b final)
scripts/check-progress-docs.sh → passed
git diff --check → clean
equality ladder: 61 synthetic + 40 randomized + 106/106 catalog × 50 + full-market artifacts identical
benchmark: backtest stage 1718.9s → 40.2s (42.8×)
```

## Pending Decisions (user)

1. ~~CR-0002/0003 slices~~ — ALL DONE through M10.3 (commits `24699ce`/`c86441b`/`d514c4c`/`a16d6c5`/`24c284d`/`1345471`).
2. **Trigger full-scale full-history batch?** (~3h estimate, `outputs/full_history_pilot/feasibility.md`) — ready when you are.
3. ~~Upstream factor computation~~ — DONE (QRE-UPSTREAM-FACTOR-DELIVERY-001): backfill 5,544 stocks/0 failed; queue 7/7 fulfilled; 5/5 strategies unblocked; daily timer covers new columns from tomorrow. Full 111-strategy re-run (incl. formerly-shelved 5) is now a user decision alongside the full-history trigger.
4. ~~M10.4 ML clustering dependency/first slice~~ — DONE (2026-10-27)：隔离 sklearn 环境、DBSCAN/noise、CLI、manifest 与真实只读产物均已复核；后续 UI/元数据扩展另行立项。
5. Follow-up micro-slices (optional): groupby-aware signal evaluation; runner-level cross-strategy frame caching (frame load ~17s is now the dominant cost). ~~Preflight UndefinedColumn robustness~~ — DONE. ~~Trailing stop~~ — DONE. ~~Cross-symbol analytics (≤30s)~~ — DONE, target MET at 25.852s.

## 2026-10-27 Current State

- Phase：`USER_DIRECTED`（本周“工程收口 + M10.4 sensitivity”已由 DeepSeek 实施、Kimi 复核；等待用户验收，未 commit/push）。
- Night Mode、重播边界、因子呈现合同、341 中文名、SSH 加固五项已获用户验收通过。
- 游戏：8092 本地可试玩，28 项专项通过；待用户验收。`ema_250` 上游 11 点异常未修。
- M10.4：真实 manifest 校验通过；新增 `--eps-grid` sensitivity，默认真实拟合 eps=1.0/1.5/2.0 成簇策略 0/2/5，noise 490/451/396；未跑回测。
- 全仓：`2906 passed, 24 skipped, 4 warnings`；此前唯一外部 YAML 夹具失败已修复，未恢复旧产物。
- SaaS FRM 日收益直方图修复已部署 ECS：job 58/66 现返回 40 箱直方图；全量 `2909 passed, 24 skipped, 4 warnings`；未 commit/push。
- TradingView 化 Spike 完成：推荐 A 增强 ECharts 为主、B Lightweight Charts 受控试点、C 自研不做；B 的 attribution 为硬阻塞。等待用户决定下一阶段实施范围。
- TradingView 化 A 路首片已部署：ResizeObserver + 重播 240 点视口裁剪；4000 点 rAF 45.8→16.8ms；全量 2914 passed/24 skipped + 1 环境性 teardown error；未 commit/push。
- A 路遗留已修补并部署：job dispose resize 守卫 + 重播策略/基准左端回 0；全量 2917 passed/24 skipped；未 commit/push。
- 静态 K 线 TV 化首片已部署：左侧工具栏、顶部 OHLC/因子信息区、右侧价格标尺；全量 2927 passed/24 skipped；未 commit/push。
- MACD 旧别名拆面板已修复并部署：`macd_dif/macd_dea/macd_hist` 现在合并成一个 MACD 副图；全量 2926 passed/24 skipped + 1 已知 timing flake；未 commit/push。
- 因子呈现复权口径系统性修复已部署：价格型因子按最新 adj_factor 换算到 K 线前复权口径，引擎语义不变；全量 2930 passed/24 skipped；未 commit/push。
- K 线重播 TV 化首片已部署：重播右侧标尺、底部时间轴、x 联动、顶部信息区随帧更新；全量 2936 passed/24 skipped；未 commit/push。
- 持仓期年化分母修复已部署：稀疏 equity 日期不再把年化分母压成条目数；920832.BJ 从 e+35 修正为约 75064.63%；全量 2939 passed/24 skipped；未 commit/push。
- 同类指标防护加固已部署：年化/区间收益/基准收益除零与负基数保护；全量 2940 passed/24 skipped；未 commit/push。
- 重播遗留清理已部署：tooltip 单位、高度 helper、375 信息区换行；全量 2946 passed/24 skipped；未 commit/push。
- 重播灰字备注清理已部署：`#kreplay-note` 迁到 `#btn-kreplay` data-tip；全量 2948 passed/24 skipped；未 commit/push。
- 历史旧个股详情按需刷新已部署：新详情带 `factor_basis`，旧详情可 `refresh=1` 重算；只读详情隐藏刷新入口；全量 2956 passed/24 skipped；未 commit/push。
- K 线画线工具首片已部署：趋势线/水平线/清除；只作用于静态 K 线，画线坐标来自真实 K 线；全量 2961 passed/24 skipped + 1 已知 timing flake；未 commit/push。
- 《我不是股神》WSL 本地实现已获用户批准提交：价格型因子与游戏 OHLC 口径对齐、一体化交易终端、回合制与审计字段；仅本地 8092，不部署 ECS。
- 下一主线候选：P2 会员分层、付费权益与微信信号推送；用户 2026-10-27 明确暂缓推进。

### 主模型切换交接预案（2026-10-27）

用户考虑将 Step 5 切为主模型、DeepSeek 保持 subagent。该调整只改变规划/实施/评审分工，不改变代码、数据库、产物、定时任务或部署架构；模型能力差异只影响后续工作质量与风格。CLI 对话上下文不会自动完整转移，因此 `docs/agent/` 仍是唯一权威记忆，新主模型接手前必须阅读根 `AGENTS.md` 及其中文档并核对 `git status`、后台任务和当前生产状态。

当前边界：游戏 `src/quant_research_engine/game/`、游戏专项测试、`22_TRADING_GAME.md` 与游戏 CR 保留本地未提交，等用户试玩反馈；其余已验收改动由用户批准提交与部署。Step 5 主接手后不得误把游戏局部文件混入提交，不得恢复已删除回测产物，也不得把全仓唯一外部 YAML 夹具失败误报为全绿。DeepSeek 任务必须由主模型给出明确文件边界并独立复核。

## Quick Batch In Flight

- `outputs/backtests/quick_batch_106/f365c8a07b33/`, launched 2026-07-18 ~18:40, `--jobs 4 --compact --skip-preflight --resume`.
- Per-strategy ≈ 27-30 min (CPU-bound engine loop); expected total ≈ 13h. User decided to let it finish at `--jobs 4`.
- On completion: record batch results in `09`, verify compact output size reduction, then propose commit.

## Quick Batch Final (2026-07-19 06:32 +08)

- 106 OK / 5 error (only the known missing-factor strategies); wall time 11.1h; per-strategy mean 1459s (-16% vs baseline); 2,013 files / 2.8GB (≈99.9% fewer files, ≈89% fewer bytes vs standard mode); report-audit on compact manifests → status=ok, 0 issues.
- Remaining before commit: user approval.

## Phase Vocabulary (single-agent, since 2026-07-18)

- `PLANNING`: writing/updating `08_IMPLEMENTATION_BRIEF.md`
- `IMPLEMENTING`: executing the brief; records go to `09_CODING_HANDOFF.md`
- `SELF_REVIEW`: writing `10_REVIEW_REPORT.md`; Required Fixes send the task back to `IMPLEMENTING`
- `AWAITING_GIT_APPROVAL`: review passed, commit message proposed, waiting for user approval
- `DONE`: finalized (or docs-only task completed without commit need)
- `USER_DIRECTED`: no active workflow task; user decides the next move

## Standing Approvals

None. Every git commit requires explicit user approval in the current session.

## Completion Status

Engine feature-complete (947 tests green); single-agent workflow active; batch pipeline committed. Next phase (Strategy Research Validation) planned and awaiting user go-ahead: CR-0002 + first-slice brief `QRE-BATCH-PERF-SLIM-001` are drafted in `docs/agent/`.

## Next-Week Backlog（2026-10-05 用户定稿，本周不动代码）

用户原话：下周 token 恢复后推进，本周不做任何具体任务。优先级即以下顺序。

### A. 自然语言编译入口加固与进化（下周主线）

1. **NL 输入前置校验**（防随意输入）
   - 第一层零成本规则：长度下限、必须含入场语义（买入/入场/金叉/突破等）+ 出场语义（卖出/止盈/止损/离场/死叉等）、乱码/纯数字直拒
   - 第二层轻量裁判：**首选 Jev 决策模型**（TypeSafe AI，只返回类别+置信度不生成文字；用户 2026-10-05 提议并确认方向）——低成本低延迟、输出天然结构化；置信度 <0.7 的边界输入不硬拒，弹窗提示缺失项并允许用户选择继续编译
   - Jev 动手前三项验证：①接入方式与中文交易策略文本实测效能 ②隐私口径（策略文本发第三方，需知情说明）③阈值用真实输入样本校准，勿信厂商宣传；Jev 不可用时降级 规则层+便宜 LLM，不做单点
   - 拒绝弹窗给具体缺失原因 + 合法示例
2. **生成策略按钮服务端限频**（防恶意刷 token）
   - 按 IP（游客）/账号（会员）记每日编译次数，建议初始值：游客 5 次/日、会员 20 次/日（管理台可调）
   - 超限 429；前端按钮 pending 期间禁用只是体验层，后端配额才是防线
   - 复用现有每日回测配额的同一套计数机制
3. **编译缓存 + 一致性 + 语料进化**
   - 规范化文本（空白/标点归一）哈希 → 编译缓存，命中即返回同一份 YAML（字面一致、零 token）
   - 编译时 temperature=0 + 锁定模型版本；YAML 落库前规范化（键序/空白统一）
   - 缓存表带命中计数 → 高频策略统计 → 管理台热门策略榜
   - 同 YAML + 同参数 + 数据未更新 的回测结果可缓存复用（二期，先编译缓存）
   - NL→YAML 编译对（含用户修改终版、失败案例）入库 = 策略语料库；短期做 few-shot 示例注入提升复杂策略编译成功率；长期（几千条后）评估微调小模型替代大模型
   - 诚实口径：相同 YAML 在不同时点跑结果会因数据更新而不同，展示层须区分「编译一致」与「结果随数据变化」

### B. 分时（分钟级）回测立项 —— ⏸️ 已挂起（2026-10-11 用户指示）

**挂起原因**：等用户获取到可靠的分钟级数据源后再重启。小样本试点已完成（CR-2026-10-10_minute_data_pilot.md，tests/data_test 40 文件验证 B+ 级、因子引擎零改动可用、回测引擎 gap list G1-G7 与工作量分级），重启时直接读该 CR 文档续接，不要重跑试点。

试点结论速记：数据源是第一前置（现有样本止于 2021-06、B 型缺 amount、复权锚点陈旧）；数据到位后仍需 1~2 天工程出「研究级」单标的分钟回测（G1 订单时间戳保真 + 数据接入层 bar_time + 清洗管线固化），「可信级」（T+1/日界/涨跌停拦截/年化口径）再 1~2 周；全市场分钟回测（G6 向量化重写）不做。tick 级数据已判定不需要（波段策略分钟粒度足够，tick 只对打板/微观结构有意义）。stk_mins 权限未实测（重启时第一件事）。

重启后的原路径（顺序不可跳）：
1. 分钟表结构设计与入库（分钟线体量 ≈ 日线 240 倍，存储方案先评审）
2. 分钟级因子预计算管线（少量因子起步）
3. 引擎日内模式原型：日内进出场、T+1 规则分钟级口径
4. 信号监控从「收盘后批量」向「盘中实时」演进（远期，依赖分时）
- 架构级事项，单独立项，不与 NL 优化混迭代

### 既有挂起项（不变）

深度性能优化（用户指示放最后）、信号监控板块二级选择 UI、重播三处验证边界、付费体系层级/定价（用户暂缓）、结果页操作卡 UI 精修（用户说下周做）、小程序/APP 远景。

### 2026-10-12 公网两项修复（FRM 数据链路 + 板块榜单排序）

- **FRM 风险模块上公网**：根因是 worker 端 engine 收尾钩子生成的 `risk_report.json` 写在 run 目录根部，从未登记进 `record["artifacts"]`，`collect_result_files` 不上传 → ECS `output_dir/risk_report.json` 不存在 → job 页 FRM 模块（UI 早已就位）恒 `has_report=false` 隐藏。修复：`worker/runner.py` 在 `_persist_artifacts` 后把 run 目录的 `risk_report.json` 登记进 artifacts，随 files 通道上传到云端 job 目录根。仅对新 run 生效；历史 job 如需回填可单独做。
- **板块/标签榜单排序**：saas `job.html` 的 `renderTagRank` 原来写死 total_pnl 降序；改为 TAG_COLS + tagSort 状态，列头点击切换排序（板块名/总净盈亏/交易笔数/平均每笔/胜率），null 恒排末位，行点击下钻个股不变。下钻个股表本来就有排序。
- **权限坑补记**（20 号文档踩坑节待补）：方案A 表重建 RENAME 后 PostgreSQL 表级 GRANT 不随迁，`qre_worker_ro` 失去 stock_daily SELECT 导致 job 56 冒烟失败；已重新 GRANT。今后任何表重建必须随迁授权。
- **已知缺口**：alpha191 重算日志告警 `reference.index_daily` 缺 000300.SH 基准 → alpha149/181/182 输出全 NaN；验收后需补指数行情并重算这三因子。
- 8081 lab 与公网的 FRM 均只存在于策略回测（run）层面；个股级 FRM 两侧都没有，属新开发项。

### 2026-10-12 个股 FRM + 个股详情按需生成（QRE-SAAS-SYMBOL-ONDEMAND）

- **个股级 FRM**：`build_lab_symbol_detail` 末尾嵌入 `risk` 节——基于个股区间日收盘价收益（DatetimeIndex，stress 节需要）调 `risk.report.build_risk_report`，轻量配置（var_backtest/bootstrap 关、stress 开）；批量与按需产物都带。前端 symbol.html 新增 FRM 卡片块（VaR/ES 95/99 历史法、EWMA 年化波动率、波动率状态、夏普、最好/最差单日、压力测试最差情景）。
- **按需生成链路**：ECS `POST /api/results/<id>/symbols/<ts>/generate`（幂等：产物在→ready；同父job+股票有未完结任务→复用；否则建 kind=symbol_detail / weight_class=light / priority=10 的任务，params 带 parent_job_id+run_id+ts_code）→ worker `runner._execute_symbol_detail` 从本地 RUNS_DIR/<run_id> 读 status.json，复用 build_lab_symbol_detail 生成 gzip 写回 run 目录 _symbol_details/，走既有 meta/files 通道回传 → ECS api_result_files 完成分支把 symbol_detail 产物复制到父 job 目录 → 前端轮询 `gen-status` 到 ready 后重载。产物缺失时 404 改返回 can_generate=true + 生成按钮（替换原误导性"无交易"文案）。
- **口径备忘**：历史 job 的旧详情文件无 risk 节（前端整块隐藏，不报错）；该股真实无交易时 worker 抛错、gen-status 返回 failed 并允许重试文案。

### 2026-10-12 NaN 序列化修复（symbol_detail 卡"加载中"根因）

risk 节含 NaN（如 GARCH 拟合失败/零方差 sharpe），`json.dumps` 默认把 NaN 写成裸 token = 非法 JSON → 浏览器 `resp.json()` 抛 SyntaxError，load() 中断，页面停在"详情已生成，加载中…"。修复：`worker/runner.py` 新增 `_json_sanitize`（递归 NaN/Inf→None，含 numpy 浮点），批量与按需两条 gzip 路径都应用。已用 node 严格 JSON.parse 验证。**教训：任何产出给前端 fetch 的 JSON 都必须过 _json_sanitize。**

### 2026-10-20 周末交接（token 耗尽，其他 agent 接续指引）

**接手前必读**：根 AGENTS.md + docs/agent/00-21 全部；本周工作细节在 05_PROGRESS.md 2026-10-19/20 各节；commit 前必须同步更新 05_PROGRESS.md（pre-commit 钩子拦截）。

#### 本周完成（全部已 commit+push+ECS 部署核实）
- 经典策略展示页全套（85286a8/5c9319b）+ 滚动器 showcase_roller（5639ae1，工作日 18:10 timer）+ 预览卡简化（e242546）+ 徽章（799f218）。
- 因子图表 TV 风格布局（6799964）：均线 overlay/MACD 合并面板/chip 三态，CR 见 change_requests/CR-2026-10-20_factor_chart_tv_layout.md。
- 布局修复（c8259e5）：overlay 正则下划线 bug + 正则 `||` 链 bug + 家族归组扩展（KDJ/STOCH/AROON/VORTEX/PPO/PVO/s信号对）+ panel 补发 table 字段。
- HTML 禁启发式缓存（ddc7a74）：text/html 加 `Cache-Control: no-cache`。
- 运维备忘：qre-saas-worker（本机 systemd）重启需 `sudo -n systemctl restart qre-saas-worker`；8081 lab 是裸 `uv run qre gui --lab` 进程，改 GUI 代码后需手动重启（曾挂死）。

#### 新发现 bug：回测结果可见性（未复现，待与用户核实）
- 用户报告：job#76（私人回测）链接对游客可见。实测：#76 user_id=6，未登录 curl `/api/saas/jobs/76`、`/api/results/76/summary|chart-data|symbols/<code>` 全部 401——归属校验在码（`_require_completed_result`：本人 user_id / 游客 IP guest_key / showcase 白名单三条通道）。
- 疑似解释（待用户确认观察路径）：a) 另一设备登录了同一账号；b) 看到的是 #74（经典策略白名单，设计内公开）；c) 游客 job 按公网 IP 归属（`guest_key`），同 Wi-Fi 设备共享出口 IP → 游客结果对同网络他人可见（设计使然，但体感像泄漏）。
- 已批准方向（brainstorm 结论，下周实施）：
  1. **端点归属普查**：枚举所有含 job_id 的 GET 端点（worker 通道除外），补 IDOR 自动化测试（他人 job 一律 404/401，不暴露存在性）。
  2. **主动分享机制**：results 加 share_token（只读链接、可撤销、可设有效期），用户点「分享」生成链接；未授权访问一律 401/404。
  3. **游客归属加固**：guest_key 从纯 IP 改为 IP+会话 cookie 双因子，或接受同 IP 风险并在 UI 明示「同网络可见」。
  4. 用户回测结果默认私有；经典策略页是唯一公开通道。

#### 待办清单（优先级序，接替者按此推进）
1. 【下周主线】回测可见性核实与加固（上述 4 项，先与用户确认复现路径）。
2. Web 文案精简化：备注改悬停 tooltip + 帮助中心页（用户已批准方向）。
3. NL 入口加固：A1 输入前置校验（jev 判断是否可执行策略，含入场/出场条件）/ A2 生成策略限频防刷 token / A3 编译缓存一致性（高频策略模板复用、相同输入产出相同 yaml）。
4. 引擎高级参数扩展：买/卖价选项（次日开盘/均价/收盘）已 brainstorm 批准，待实施。
5. 经典策略按钮 UI 精修（用户说下周做）。
6. 【已挂起】分时因子计算 + B 项引擎分时适配（等用户提供可靠分时数据源）。
7. 【已挂起】worker price_basis=qfq 保真问题评估立项（滚动器发现：基线 job 实际跑 qfq 原始价尺度，疑似 worker 缺陷；修正需重跑基线，等用户决策）。
8. 【已挂起】分时 csv 入库后 mindata/2026 CSV 删除确认。
9. 【远景】性能优化（用户指示最后做）、信号监控板块二级 UI、付费体系分层（内测仅游客/注册两层，注册用户全权限仅并发限资源）、小程序/APP。

#### 2026-10-20 补充：可见性问题结论 + 无权页设计（已批准方向，下周实施）

- **可见性结论（用户确认）**：showcase 白名单 job（74/58/66）全链路公开只读为设计内行为，私人 job（如 #76）401 正常——无泄漏，公开/私有逻辑维持现状。
- **新需求（brainstorm 已批准）**：访问他人/不存在任务时前端停「任务加载中」死等，须改为统一无权页：
  1. 401/404/不存在 三态合一，文案统一「页面不存在或暂无访问权限」（GitHub 式，不暴露任务存在性，防 IDOR 探测）；
  2. 页面按钮：「登录/注册」（主紫）+「返回首页」；游客追加轻提示「登录后可查看并管理自己的回测记录」；
  3. 登录成功回跳原链接，仍无权则再显示无权页，逻辑闭环；
  4. 视觉遵守 12_UI_STYLE_GUIDE（主紫、既有 card 组件、零新色相）；
  5. 否决项：永久加载（现状）、区分"不存在"与"无权限"文案（暴露存在性）、申请权限按钮（无协作场景）。
  6. 范围：job 详情/个股详情/回测记录三处 401/404 处理统一；顺带修「排队中/运行中/失败」状态的加载兜底，消灭一切无限转圈。
- 待办第 1 项「回测可见性核实」已完结（无泄漏）；细化项 1（端点归属普查+IDOR 测试）与项 2（share_token 主动分享）保留在待办，优先级降至无权页之后。

### 2026-10-28 CARD-FROSTED-GLASS 已部署，等待用户验收，未 commit/push

- 全站卡片玻璃化 + 悬停光斑 + ≤4° 倾斜；`static/card-fx.js` 新增，`lab-theme.css` / `night-mode.css` / `base.html` 修改。
- 既有约束全部保持：无新增灰字（R-UI-001）、无外部依赖、夜间生效、reduced-motion 降级、焦点环不遮挡、图表卡不倾斜不发糊。
- 测试 `tests/test_card_fx.py` 18 例；全量 `3006 passed, 24 skipped`。
- 生产已部署，`.tmp/card-fx/` 有截图与 `report.json`。CR：`docs/agent/change_requests/CR-2026-10-28_card_frosted_glass.md`。

### 2026-10-28 FACTOR-QFQ-ANCHOR 已部署待人工验收，未 commit/push

600330 EMA 与 K 线偏离的**根因**修复（用户第三次报同类问题，明确要求"治本"）。

**三层根因**：① 因子表 hfq（raw × adj_factor）vs K 线 qfq@K线末日 的固有口径差，
价格型因子必须除以 K 线最后交易日的 adj_factor，该换算只在实时生成路径存在；
② SaaS API 优先下发 worker gzip 快照且永不失效 → 1013/1013 个存量产物全是旧口径
（线上复扫 `factor_basis` 缺失率 100%）；③ `_latest_adj_factor` 原来无条件取全局最新日，
区间结束后再除权就除错倍数——**这才是"修了又坏"的真因**。

**实证**：600330 `ema_5=113.26` vs qfq 收盘 `21.97`（5.0637 倍），比值全历史恒定；
用产物自身 qfq K 线重算，`ema_hfq/adj(latest)` 与收盘价比值 0.9883–1.1020（EMA5 滞后该有的样子），
rescale 后 1.0000。40 个随机产物：EMA 比值中位数 2.677 → 1.0001，MACD 1.434 → 0.9999。

**修复**：`_latest_adj_factor(conn, ts_code, as_of)` 加 `as_of` + SQL `AND trade_date <= :d`，
调用点传 `dates[-1]`；回归测试 `TestQfqAnchorDate` 2 例。1013 个存量产物 rescale 后回传 ECS
（线上复扫 100% 新口径）。app.py 对缺 `factor_basis` 的产物一律拒发 → 404 + 前端生成按钮
（宁可让用户点一下，不 silent 展示错尺度数据）。测试夹具 3 个文件补 `factor_basis`。

**环境约束备忘（决定了补救方式）**：ECS 无行情库 → 不能重算因子只能改快照；本地 run 产物已清空
（`outputs/gui-console/runs` 空、无 `status.json`）→ worker `_execute_symbol_detail` 不可用，
"刷新详情"按钮对存量 job 实际无效。

**测试**：全量 `3009 passed, 24 skipped`。CR：`change_requests/CR-2026-10-28_factor_qfq_anchor.md`。
**未 commit/push**，建议提交 `fix(data): 因子前复权锚点按K线末日，补救1013个存量产物并拒发旧口径快照`。

### 下一阶段重心（用户 2026-10-28 指定，接在本次验收后）

因子库因子的**别名、呈现方式、复权口径**要固化为因子的元数据属性（类似 C++ 数据成员），
不再每次调用 K 线/因子时临时判断——目标是"未来不想一而再再而三去解决 K 线和技术指标的呈现问题"。

### 2026-10-28 KLINE-ENGINE-EXCLUSIVE 已部署待人工验收，未 commit/push

修复「切 TradingView 视图后 K 线叠加」。**根因**：`#chart-kline` 是同一容器，ECharts 与 LWC
各自只清自己创建的 DOM——`renderKlineLwc()` 只调 `lwcDispose()`（只摘 LWC 节点），从不清
ECharts 实例，`LWC.createChart(el)` 再插一套 canvas 就叠在一起。反向当时没暴露只因引擎开关
处理器里手工补过一次 `lwcDispose()`。

**真实浏览器实测**：修复前 echarts→lwc 后容器 2 个子元素、`scrollHeight` 400→**800**（高度翻倍）；
修复后恒 1 个，8 轮反复切换零 pageerror。

**修复**：新增 `klineDisposeEngines()`（echarts `getInstanceByDom`+`dispose` → 兜底清空容器 →
`symbolKlineChart=null` → `lwcDispose()`），`renderKlineLwc` / `renderKline` / 引擎开关三处全改走它。
**硬规则（写入 12_UI_STYLE_GUIDE §3.16 附近）**：任何往 `#chart-kline` 挂图表的路径，
挂载前必须调 `klineDisposeEngines()`，不得只清自己那一侧。

**测试**：`tests/test_lwc_kline_adapter.py::TestKlineEngineExclusive` 2 例（Node vm 跑真实源码 +
源码合同，已 RED 验证）；四个既有 harness 抽取区扩展（`klineDisposeEngines` 在 `klineResizeBound`
之前，原抽取区不含它）并补 `firstChild`/`removeChild` DOM 桩；全量 `3011 passed, 24 skipped`。

**教训**：模块级 `_DRAW_BLOCK` 常量在构造 page 时就替换掉 `%SOURCE%`，"再替换一次"静默失效，
RED 检查第一版因此测出假绿灯——**RED 检查必须确认替换真的发生**。

CR：`docs/agent/change_requests/CR-2026-10-28_kline_engine_exclusive.md`。
已部署 ECS（MainPID 542952，回滚副本 `/tmp/qre-deploy-20261028T115036Z.bak`）。**未 commit/push。**

### 2026-10-28 TV 化反馈文档已产出（回传逆向 agent）

新增 `docs/agent/TV_FEEDBACK_2026-10-28.md`，对照逆向 agent 报告（`/home/van/dshguide/README-AGENT.md`，
四功能：K 线呈现/作图/高级指标/K 线回放 + 协议层）给出本轮完成度：

| 功能 | 完成度 | 核心差距 |
|---|---|---|
| K 线呈现 | ~75% | LWC 仍是可选试点非主引擎；专业价格格式化框架缺失 |
| 作图 | ~5% | 94 种工具只做 2 种；无端点拖拽/整体拖动/单线 Delete |
| 高级指标 | ~60% | Pine 脚本语言刻意不做（半年量级）；指标参数不可即时改（ECS 无行情库） |
| K 线回放 | ~70% | LWC 重播 adapter（阶段 3）未做；无单步后退；无键盘快捷键 |
| 协议层 | N/A | 不接 TV 服务，数据源自有 pgsql + tushare 日更 |

文档内含**三个待逆向 agent 回复的问题**：Q1 MACD DIF/DEA/HIST 是否真各自坐标系（用户反复反馈，
代码逻辑上已同 grid/yAxisIndex，需浏览器判据）；Q2 下轮主攻 LWC 扶正还是继续增强 ECharts（我方倾向后者）；
Q3 作图边界（我方建议只补 demo 已有三项，不扩工具种类）。
结构性原因已记录：`symbol.html` / `replay.js` / `game.html` 三处各自拼 grid/yAxisIndex，
只有 `plan()` 归组共享——display 合同统一了归组但没统一 option 组装。
