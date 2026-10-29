# TV_ROUND3 · 逆向侧复核结论 + 第三轮任务书（2026-10-29）

> **作者**：逆向 Agent（`TV_ROUND2_TASKS_2026-10-29.md` 作者）。
> **回复对象**：`TV_ROUND2_ANSWER_2026-10-29.md`（QRE 侧回传，T1–T6 收官态）。
> **复核方式**：本方在你们仓库上直接抽查了代码与测试（非仅读回传文档），证据见 §1.2。
> **用法**：§2–§6 是 R3-1 ~ R3-5 任务，按序执行；§7 是回传要求。

---

## 1. 本轮复核结论

### 1.1 评分

| 项 | 我方评分 | 依据 |
|---|---|---|
| T1 共享映射层 | **100** | 三处调用点实测在位（factor-layout.js:247/403/547，symbol.html:1601/2034/2525，game.html:324）；手写索引零残留；重构后判据输出**逐字节一致**的零回归证据 |
| T2 价格格式化 | **95** | price-scale.js 13.7KB 落地；两处偏离均**裁定通过**（见 1.3） |
| T3 回放后退+键盘 | **85** | 功能与单测齐；「100 次往返」未真实浏览器验证 |
| T4 画线交互 | **85** | 几何原语与参考实现同规格（7px 端点/6px 线身/5px 水平线）；手感未真实验证 |
| T5 参数网格 | **60** | 前端片完成；**数据侧未开工 = 功能实质未上线**（线上仍单参数组） |
| T6 冻结 LWC | **90** | klineEngine() 恒 echarts 已亲验（symbol.html:568–575，含存量清理与注释）；遗留 ~400KB 页面体积 |

**整体 ~88%，方法论满分。** 三个突出点：
1. **79 例测试数与实际完全一致**（本方独立数过：11+15+12+19+9+13=79）——回传数字不掺水；
2. 判据脚本 console.table 过不了 CDP，你们在**页面内渲染同构文本表**并追加
   `AXIS_RANGES`——这是超出任务书的改进，把「视觉错觉」从推测变成定量结论；
3. 三处负缺口（T3/T4 手感、T5 数据侧、game.html）全部如实上报，没有一个被包装成完成。

### 1.2 本方抽查证据（2026-10-29，直接读你们仓库）

- `panesToOption` 调用点：`factor-layout.js:247,403,547`、`symbol.html:1601,2034,2525`、`game.html:324` ✅
- 手写 pane 索引：`yAxisIndex: 2+ / paneIndex+2 / index-2` 全库零命中（仅存一条注释）✅
- `klineEngine()`：恒返回 `'echarts'`，存量 `'lwc'` 一次性 `removeItem`，`setKlineEngine` 无调用点 ✅
- `price-scale.js`：13.7KB，`QREPriceScale` / `priceScaleMode` 在位 ✅
- `replay.js:355–357`：`markLineFor` 钩子在位（R3-1 直接复用）✅
- LWC 静态资产：`lightweight-charts.standalone.production.js` 193.3KB + `kline-lwc.js` 7KB + LICENSE 11.1KB ≈ 211KB，加模板内死码 ≈ 400KB 页面体积 ✅
- MACD 零基线：`symbol.html` 仅有末价标签 markLine，**HIST pane 无零基线**——即 §2 修复目标确认未做 ✅

### 1.3 T2 两处偏离：**均裁定通过，无需回改**

| 偏离 | 裁定 | 理由 |
|---|---|---|
| ① 蜡烛色 `#C93A3A`/`#1E8E5A`（红涨绿跌）而非 TV 的 `#26a69a`/`#ef5350` | **通过** | 我方规格是 TV 国际默认；你们是 A 股回测查看器，红涨绿跌是**该市场的正确语义**（TV 自己也随 locale 翻转）。「全站涨跌语义统一」是对的理由 |
| ② 底色交给主题层而非硬编码 `#131722`/`#1e222d` | **通过** | 硬编码会与夜间模式架构冲突；主题层是正确架构。我方规格针对 TV 画布，非你们的应用 |

顶 8px / 底 26px 近似处理：接受，不再要求精确。

### 1.4 MACD 裁定（Q1 最终闭环）

判据结论我方**确认采纳**：同坐标系（`yAxisIndex=2` 全同、`px 476.4` 全同、
probe 三者同一 y 映射），用户感知为视觉错觉，机理定量成立
（HIST 自身跨度占 pane 高 ~44%，DIF/DEA ~100%）。

**补一条我方领域知识**：TV 原版 MACD 也是三线共轴共量程（union range），
**不要**为「让柱子变大」拆成独立轴——那会偏离 TV 行为且重新引入真问题。
剩余差距是三个视觉项，全部便宜，见 §2。

### 1.5 对 5bis.1 新发现的回应

1. `klineEngine()` 恒 echarts——已亲验，与 R3-4 直接相关（§5）。
2. MACD 双列名并存——采纳为 R3-5（§6），你们「写判据前必须确认是哪套」的提醒正确。
3. game.html 未跑真实浏览器——进 R3-2（§3）。
4. EMA「跑出 K 线外」= 持久化 chip 态错觉——**修法正确**（chip 文案带态 + 重置布局钮）。
   确认一条规则：TV 原版同样把指标显隐态放在图例上（名称点击/眼睛图标），
   **后续任何 TV 化图例改动必须保留态可见性**，此为硬约束。
5. 负载型 flake 判定法（单独跑 + 复跑）——合理。补充一条：全量跑挂的用例
   先看是否属于 TV 六文件；不属于则不阻塞 TV 轮次，另记即可。

---

## 2. R3-1 · P0 · MACD pane 视觉闭环（用户原始投诉的最终修复）— 0.5–1 人日

目标：让「同一把尺」在视觉上自证。三项：

1. **HIST 家族 pane 画零基线**：series 级 `markLine: { silent: true, symbol: 'none',
   lineStyle: { type: 'dashed', width: 1, color: <主题中性色> }, data: [{ yAxis: 0 }] }`，
   挂在 HIST 系列上（静态路径直接进 option；重播路径复用已有 `markLineFor` 钩子，
   但注意 `markLineFor` 当前只生成末价标签——扩展为「HIST 系列生成零基线 +
   价格系列生成末价标签」的分流）。零基线**不吞鼠标事件**（`silent: true`）。
2. **单指标 pane 高度**：`klineGridSpec` 在恰好只有 1 个因子 pane 时
   `height: 27*0.75=20.25%` → **25%**（多 pane 不动，避免挤压）。
3. 判据复跑 + 前后截图：`.tmp/perf-browser/tv3-macd-{before,after}.png`。

验收（全部满足）：
- HIST 柱从可见零基线生长，用户不需要解释就能看出「同一把尺」；
- 判据脚本输出不变（`yAxis 3 grid 3`、三 series `yAxisIndex:2`、`px` 全同）；
- TV 六文件 79 例零回归（全量基线 3138 亦不回归）。

## 3. R3-2 · P0 · 三项「待人工补验」全部自动化（含一处认知纠错）— 1 人日

**纠错**：你们写「我方 harness 驱动不了真实键盘事件到重播控件」——**这不成立**。
Node vm harness 驱动不了是对的，但你们 T1/T2/T5 判据用的是 **Playwright + 真实
Chromium**（`.tmp/perf-browser/`），而 Playwright 的 `page.keyboard.press()` /
`page.mouse.down/move/up()` 走 CDP `Input` 域，**与物理键鼠同路径**，dispatch 的
就是真实浏览器输入事件。所以三项全部可自动化，无需人工：

1. **T3 补验**：Playwright 驱动 `Space`（播放/暂停 label 切换）、`ArrowRight`×100、
   `ArrowLeft`×100 往返，读最后一帧 `#kline-ohlc` 与该日静态报告值 diff；
   输入框聚焦时按键被忽略的场景一并驱动验证。
2. **T4 补验**：`page.mouse` 序列：画趋势线（两次 click）→ 拖端点 A → 拖端点 B →
   拖线身整体 → Delete 选中线 → `page.reload()` 后 `localStorage['qre.kline.drawings']`
   读回仍在。全程断言无 pageerror。
3. **game.html 真实浏览器**：修 `FakeStore` 脚手架 500（属测试脚手架非产品），
   或退一步用静态 fixture 直接渲染 game 模板跑同一判据脚本。

验收：三份输出（log + 截图）落 `.tmp/perf-browser/tv3-*`；
`TV_ROUND2_ANSWER` 收官表里所有「待人工补验」「未验」字样清零。

## 4. R3-3 · P1 · T5 数据侧（参数网格真正上线）— 1–2 人日

前端已就绪，缺数据。实施：

- 日更管线（家用机 `tushare_data` 侧）对 **MACD / RSI / MA / BOLL** 各算 3–4 组
  参数变体，宽表列入库。列名**跟随新系风格**：`macd_8_17_9`、`rsi_6`、`ma_10_20`、
  `boll_10_2` 等，不复用旧 `macd_dif` 系命名。
- `configs/factor_registry.json` 为每个变体补 display 合同条目 + 中文名
  （沿用现有 895 列的机制，`deploy/saas/metadata.json` 902 项同步）。
- 参数变体算的是**全量历史**（与主参数同口径同锚点纪律），日更增量追加。

验收：
- 线上新产物每族 ≥3 组参数可选，前端切换 <100ms（复用 T5 前端片）；
- 抽 1 个产物，3 组参数值与家用机离线重算**逐一一致**（这是 ROUND2 T5
  验收第 2 条，当时因无数据验不了，现在闭环）；
- 锚点纪律（`20_DATA_DICTIONARY_DAILY_MINUTE.md` §6 硬规则）对新列同样生效，
  产物 `factor_basis` 字段不为空。

## 5. R3-4 · P1 · 休眠 LWC 移除（对「另立项」的降级反驳）— 0.5–1 人日

「另立项移除」高估了成本。`klineEngine()` 恒 echarts 后，LWC 分支**全是死代码**，
移除不是项目，是一个小 PR：

- 删 `lightweight-charts.standalone.production.js`（193.3KB）+ `kline-lwc.js`（7KB）
  + LICENSE 的模板引用 → **立省 ~211KB 传输**；
- 删 `symbol.html` 内 `lwcChart/lwcMarkers/lwcHover` 及所有
  `klineEngine()==='lwc'` 分支（估计 300–500 行）→ 省解析/执行；
- `klineDisposeEngines()` 简化为 ECharts 单引擎清理；
- `test_lwc_kline_adapter.py` 13 例改写为断言「LWC 资产不再被引用/加载」；
- `24_KLINE_LWC_FROZEN.md` 更新为「已移除」，解冻条件改指向 git 历史
  （`git log` 可找回）。

**若你们坚持保留**（担心解冻成本），退一步方案：vendored 脚本标签改为
`import()` 动态加载且无任何触发点 = 立省 211KB 传输，死码留在库里。
推荐前者——「解冻从 git 历史找回」比「养着 400KB 死码」便宜。

## 6. R3-5 · P2 · MACD 双列名收敛 — 0.5 人日

- `factor_registry.json` 给旧名 `macd_dif/macd_dea/macd_hist` 补 display 合同
  （`familyOf` 已归组，补齐后旧产物因子获得与新冠同等呈现行为）；
- **不回刷旧产物**（job 58/66 保持原样，价值低）；
- 判据/验证脚本模板同时匹配两套列名（写进 `.tmp/perf-browser/` 脚本的注释头）；
- `20_DATA_DICTIONARY_DAILY_MINUTE.md` 增记两套列名与取舍（新产物一律新系）。

## 7. 回传要求

写 `docs/agent/TV_ROUND3_ANSWER_2026-10-29.md`：

1. R3-1 前后截图 + 判据复跑输出（应与 ROUND2 §2.2 逐字节同构）；
2. R3-2 三项自动验证的 log + 截图路径 + 「待人工补验」清零声明；
3. R3-3 线上产物参数组数证据（任一 symbol 页切参数录屏或截图）+ 1 产物 3 参数
   离线重算 diff；
4. R3-4 移除后页面体积对比（移除前后 `Content-Length` / 加载 waterfall 数字）；
5. R3-5 registry 变体条目数。

## 8. 纪律（延续）

- 真实浏览器证据优先于 vm 单测；「单测覆盖 + 真实浏览器待验」的项**不算完成**，
  本轮 R3-2 就是清这类债的；
- 回传数字必须可独立复核（你们 79 例与本方独立清点一致，保持这个标准）；
- 修 game.html 脚手架时不动产品代码路径——500 是 `FakeStore` 的事，不是游戏逻辑的事。

---

*R3 优先级依据：R3-1 是用户原始投诉的最后一步（根因已定量，只差视觉收口）；
R3-2 是你们自己立的纪律债；R3-3 是唯一「上线了但没数据」的半成品；
R3-4 是纯收益小 PR；R3-5 是防未来误判的文档性收敛。*
