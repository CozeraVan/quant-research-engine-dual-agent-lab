# CR-2026-10-29 · 回放单步后退 + 键盘快捷键（TV_ROUND2 T3）

- **任务书**：`docs/agent/TV_ROUND2_TASKS_2026-10-29.md` §7 T3（P1，0.5 人日）
- **验收口径**：后退复用 `seek(pos-1)`；空格播放/暂停、←/→ 单步；键盘不劫持输入框与
  模态焦点；前进/后退 100 次后光标与指标值与静态报告一致（防未来数据红线不破）
- **实施日期**：2026-10-29

## 1. 实施内容

全部改动集中在 `src/quant_research_engine/gui/static/replay.js`（策略级 `job.html` 与
个股级 `symbol.html` 共用同一组件，改一处两处生效），**未触碰任何后端与模板逻辑**。

### 1.1 后退按钮

- 新增 `btnBack`（内联 SVG `stepBack` 图标 + 「后退」文字 + `aria-label="单步后退"`），
  插入主控组 `[播放][后退][单步][速度]`，与单步前进成对；
- `stepBack()`：`pause()` 后 `seek(cursor - 1)`，首帧 `seek(0)` 夹紧。
  **不另造渲染路径**——与进度条 seek、日历 seekDate 走同一个 `seek()`，
  事件流重建、rAF 节流渲染、滑块/计数器同步全部复用；
- `attach()` 返回值新增 `stepBack` / `stepForward` 出口（页面可编程驱动）。

### 1.2 键盘快捷键

- `空格` = 播放/暂停（`ev.repeat` 时忽略，长按不得连续切换播放态）；
- `←` = 单步后退，`→` = 单步前进；
- 处理过的键一律 `preventDefault()`（否则空格滚动页面、方向键滚动页面）；
- `Ctrl/Meta/Alt` 组合键一律不接管；
- 无关按键不动作；
- 监听在 `attach()` 注册、`destroy()` 撤销（重播退出后不得继续劫持按键）。

### 1.3 不劫持输入框与模态焦点

模块级纯函数 `keyTargetBlocked(el)` + `KEY_BLOCK_SELECTOR`（导出到 `QREReplay.core`）：

```text
input, select, textarea, button, a, [contenteditable="true"],
[role="dialog"], .ind-mask, .cal-pop, .rp-calpop, .rp-bar
```

焦点落在上述任一区域（含其子孙）时 `onKey` 直接 return，交还原生行为。覆盖的真实场景：

| 焦点位置 | 若接管会怎样 |
|---|---|
| 起始日输入框 `input.rp-date` | 空格切换播放、← 同时改日期和步进 |
| 速度下拉 `select.rp-sel` | ← 同时改速度和步进 |
| 播放/后退/单步按钮 | 空格触发按钮 click **再加一次** 切换（双触发） |
| 进度条滑块 `input[type=range]` | ← 同时改滑块值和步进 |
| 指标设置对话框 `.ind-mask` / `[role=dialog]` | 模态打开时仍驱动背后重播 |
| 日历浮层 `.rp-calpop`（replay.js 自建）/ `.cal-pop`（lab 页） | 日期选择器自身方向键被吃掉 |
| 链接 `a` | 空格激活链接 |

> 两个日历类名都要拦：`replay.js` 自建的浮层是 `.rp-calpop`，lab 页复用 `LabUI` 时是
> `.cal-pop`（真实浏览器验证时发现只写 `.cal-pop` 拦不住自建浮层，已补）。

### 1.4 可发现性

按钮 `title` 补快捷键提示（「播放 / 暂停（空格键）」「单步后退一帧（← 键）」
「单步推进一帧（→ 键）」），不新增灰色小字备注（R-UI-001）。

## 2. 测试与验证

### 2.1 Node vm 单测（`tests/test_replay_step_back_keys.py`，12 例）

跑**真实 replay.js 源码**（不写桩），自建 DOM/echarts/setInterval/document 桩：

- 源码合同（`stepBack`/`btnBack`/`seek(cursor-1)`/注册与撤销/core 导出/三个 title）；
- `keyTargetBlocked` 对 16 种焦点形态的判定（含对话框内部、输入框内部、画布放行、null）；
- 后退按钮与 `stepBack()`：递减、首帧夹紧、**必须走渲染出口**（option 次数 +1）；
- 键盘：空格播放/暂停、`repeat` 忽略、→/← 单步、首帧夹紧、修饰键不接管、无关键不接管、
  **必须 `preventDefault`**（调用计数断言）；
- 不劫持：INPUT/SELECT/BUTTON/TEXTAREA/对话框内部 × 三个键全部无动作；画布焦点放行；
  **播放按钮焦点时空格只切换一次**（原生 click，组件不得再叠一次）；
- **往返 100 次**（260 根序列）：前进 100 → 后退 100，光标回到原值，
  `totalRet / maxDD / sharpe / winRate / plRatio / closedTrips / positions / exposure`
  八项与 `QREReplay.core.frameMetrics` 直接算出的静态口径逐一相等（1e-12）；
- 防未来数据：往返后 x 轴数据最后一根 === 当前帧日期，长度 ≤ cursor+1；
- 后退必须重建事件流，未来事件行不得残留；
- `destroy()` 撤监听，撤掉后再按键无动作。

**RED 验证**（5 条变异真实源码，全部转红）：

| 变异 | 结果 |
|---|---|
| 去掉 `keyTargetBlocked` 守卫 | 1 failed |
| 后退不走 `seek`（直接改 cursor + renderFrame） | 1 failed |
| `destroy` 不撤 keydown 监听 | 2 failed |
| `seek` 不清事件流 | 1 failed |
| 空格不 `preventDefault` | 1 failed |

> 备注：`if (cursor <= 0) { seek(0); return; }` 这层夹紧**无法**做 RED——`seek()` 自身
> 就 `Math.max(0, …)`，删掉它行为不变。它是显式化契约的防御性代码，保留。

### 2.2 真实浏览器验证（`.tmp/perf-browser/t3_verify.py`）

Chromium + 真实 `symbol.html` + 真实 `replay.js` + **生产 job 58 真实产物**
（`000014.SZ`，4063 根 K 线、76 笔交易）。

```text
控制条按钮：[播放/暂停（空格键）, 单步后退（← 键）, 单步前进（→ 键）, 空仓快进]
后退按钮：3577 → 3576 → 0（连点 3582 次不越界）
键盘：空格 playing true→false；→ cursor+1 且不进播放态；← cursor-1
不劫持：起始日输入框 / 速度下拉 / 播放按钮 / 日历浮层(.rp-calpop) 四个焦点全部无动作
        （播放按钮焦点时空格只切换一次 = 原生 click，组件不叠第二次）
往返 100 次：光标 2015 → 2115 → 2015，八项指标值逐一相等（<1e-9）
防未来数据：x 轴末根 = 当前帧日期，x 轴长度 ≤ cursor+1
退出重播：kreplayCtl 置空、键盘监听已撤、再按键无动作无报错
```

截图 `.tmp/perf-browser/t3-replay-keys.png`，机器可读 `.tmp/perf-browser/t3_result.json`。

## 3. 踩到并修掉的一个真问题

只写 `.cal-pop` 拦不住重播自建的日历浮层——`replay.js` 建的容器类是 `rp-calpop`
（`lab-ui.js` 的 `.cal-pop` 是 lab 页的用法）。真实浏览器验证时浮层内按键仍能驱动重播，
补上 `.rp-calpop` 后才通过。这也说明"选择器要对着真实 DOM 写，不能对着 CSS 类名猜"。

## 4. 影响面

- **`job.html` 策略级重播**：同一组件，自动获得后退按钮与键盘；T2 引入的
  `axisLabelOf` 默认路径逐字节不变（由 `test_saas_replay_tv.py` 覆盖）。
- **`game.html`**：不使用 `replay.js`，零影响。
- **`symbol.html` 模板**：零改动（按钮由组件内部创建）。
- **防未来数据**：后退走 `seek()`，事件流整体重建，与前进/进度条/日历同一语义。

## 5. 复现方式

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
.venv/bin/python .tmp/perf-browser/verify.py                        # 渲染真实模板页
.tmp/browser-venv/bin/python .tmp/perf-browser/t3_verify.py         # 真实浏览器断言
.venv/bin/python -m pytest tests/test_replay_step_back_keys.py -q   # Node vm 单测
```
