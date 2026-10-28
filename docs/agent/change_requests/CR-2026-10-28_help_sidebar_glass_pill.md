# CR-2026-10-28 使用说明页侧边栏玻璃胶囊当前项指示器

> **2026-10-28 V2 竞稿**：V1（下方「实现」节）上线后用户反馈「不满意」，
> 已由 V2 覆盖同一份实现，差异与取舍见文末
> [「V2 竞稿（step-5，2026-10-28）」](#v2-竞稿step-52026-10-28) 一节。
> 两版共用同一组文件与选择器，可逐项对调。

## 背景

`/saas/help` 的侧边栏栏目导航（`.help-jump`，七个锚点）此前只有 hover 底色，
没有「当前项」的持续反馈：滚动时用户看不到自己读到哪一节，点击后也无动画过渡。
本次只做这一片：给侧边栏加一个**玻璃胶囊**指示器，随当前项滑动，移动中沿移动
方向拉长，到位弹性回弹，边缘一圈细高光。

## 目标

1. 当前项以半透明玻璃胶囊作底（不是给每个 `a` 加背景）。
2. 切换时胶囊滑向新位置，移动中沿移动方向拉长，到位弹性回弹。
3. 胶囊边缘一圈细高光。

## 边界

- 只改 `/saas/help` 侧边栏与配套静态资源；不改 `base.html` 导航结构、其它模板、
  `night-mode.js`、因子/回测/游戏代码。
- 胶囊必须是导航内的**单个绝对定位元素**（`.help-pill`），不改变 `nav` 结构。
- 不新增灰色小字备注（R-UI-001）：不新增 `.opt`/muted 小号说明；现有 `.opt`
  段落为历史内容，未改动。
- 无外部依赖（无 CDN / unpkg / jsdelivr），全部本地静态资源。
- 复制并顺延既有合同：`.help-jump{display:flex;flex-direction:column}`、
  `.help-side{position:sticky`、`.help-content .card h2{font-size:20px` 原样保留，
  新规则另起 `.help-jump{position:relative}`。

## 实现

### 1. 单胶囊定位（`help.html` + `lab-theme.css`）

```html
<nav class="help-jump" aria-label="使用说明栏目">
  ... 七个 a ...
  <span class="help-pill" aria-hidden="true"></span>
</nav>
```

`.help-jump{position:relative}` 成为胶囊的定位上下文；胶囊
`position:absolute;left:0;top:0`，`width/height` 由 JS 按当前锚点的
`offsetLeft/offsetTop/offsetWidth/offsetHeight` 写入，`translate3d(x,y,0)` 移动。
锚点 `position:relative;z-index:1`，胶囊 `z-index:0;pointer-events:none`，不遮挡文字
与点击。窄屏 ≤760px 双列 grid 同样走 offset 定位，无降级分支。

### 2. 玻璃与细高光

```css
background:rgba(103,80,164,.12);
border:1px solid rgba(103,80,164,.22);
box-shadow:inset 0 1px 0 rgba(255,255,255,.78),   /* 顶部 1px 高光 */
           inset 0 -1px 0 rgba(255,255,255,.18),
           0 1px 2px rgba(74,58,120,.10);
backdrop-filter:blur(6px) saturate(1.15);
```

夜间由 `night-mode.css` 覆盖 token（`--pill-bg/--pill-border/--pill-glow/
--pill-shadow`），沿用 `--lav`/`--text` 派生色相：底 `rgba(155,132,216,.20)`、
描边 `rgba(200,172,214,.34)`、高光 `rgba(241,237,248,.26)`，只提亮度不换色相。
`@supports not (backdrop-filter)` 时降级为 `--tint` + `--tint-deep` 实色。

### 3. 三点动画（`help-nav.js`）

单个 `Element.animate()` WAAPI 关键帧序列，`MOTION_MS = 560`，`easing:'linear'`
（分段缓动写在关键帧上）：

| offset | transform | easing |
| --- | --- | --- |
| 0 | `translate3d(from) scaleY(1)` | `cubic-bezier(.22,1,.36,1)` |
| 0.46 | 55% 路程 `scaleY(1+clamp(|dy|/h×0.09,0,.18))` | `cubic-bezier(.34,1.56,.64,1)` |
| 0.72 | 终点 `scaleY(1−(s−1)×0.42)`（轻微压扁） | `cubic-bezier(.34,1.56,.64,1)` |
| 0.88 | 终点 `scaleY(1+(s−1)×0.22)`（反向过冲） | `cubic-bezier(.34,1.56,.64,1)` |
| 1 | 终点 `scaleY(1)` | — |

- **拉伸系数**：`stretchScale(dy,height) = 1 + clamp(|dy|/height × 0.09, 0, 0.18)`，
  上限 18%，避免远距离跳转时拉成条。
- **拉伸方向**：竖向即 `scaleY`；向下移动 `transform-origin:top center`（下沿先行），
  向上移动 `bottom center`（上沿先行），到位后复位 `top center`。
- **回弹曲线**：`cubic-bezier(.34,1.56,.64,1)` 的过冲段负责到位弹回；0.72/0.88
  两帧把「压扁 → 过冲 → 1」显式写出，避免依赖单一缓动的观感差异。
- 动画启动前同时写 `pill.style.transform = 最终 transform`（`fill:'none'`），
  动画结束自然沿用内联终值；新动画启动前 `cancel()` 旧动画，快速连点不会堆叠。
- `prefers-reduced-motion: reduce`：JS 直接跳帧（`behavior:'auto'`，无 animate），
  CSS 同步 `transition:none`。

### 4. 当前项与滚动联动

- `aria-current="true"` 只落在当前锚点（其余移除）；`:focus-visible` 2px `--lav`
  内嵌焦点环；当前项文字色改 `--lav`（夜间 `--accent-deep`）。
- `IntersectionObserver`（`rootMargin:'-76px 0px -58% 0px'`）监听七个 `.help-sec`，
  取最靠上的可见项；无可见项时回退「top ≤ 84 的最后一个 section」。
- 点击：`preventDefault`（保留 Ctrl/Meta/Shift/Alt 原生行为）、立即定位 + 平滑滚动、
  `history.replaceState` 同步 hash；锁定 1.2s，滚动结束后 160ms 解锁再交还 IO。
- 初始化：有匹配 `#hash` 用该锚点，否则第一个；`ready` 延迟 120ms 防止初始 IO
  回调覆盖 hash 定位。`resize`（debounce 120ms）与 `document.fonts.ready` 后仅重算
  几何、不播动画。

## 测试

`tests/test_saas_help_nav.py`（7 例）：

- 源码合同：单 `.help-pill` + `aria-hidden`、脚本经 `{% block scripts %}` 引入、
  nav 仍 7 锚点、侧栏无 `.opt`、页面 `.opt` 计数 ≤3。
- CSS 合同：`position:relative`、玻璃底/`backdrop-filter`/`inset 0 1px 0`、
  `@supports not` 降级、`aria-current` 与 `focus-visible`、reduced-motion 关过渡；
  夜间 token 含 `--pill-glow`、`--pill-border` 与 `155,132,216` 色相。
- Node vm 纯函数 harness：`stretchScale`（0/56/500 与零高度）、`direction`、
  `transformFor`（含 2 位小数）、`motionKeyframes`（5 帧、offset、首末
  `scaleY(1)`、中段 >1、0.72 帧 <1、0.88 帧 >1、上行终点）。
- 既有约束不变：`test_saas_help_copy.py`、`test_saas_result_help.py`、
  `test_gui_saas_pages.py` 全部通过。

验证命令：

```bash
uv run pytest tests/test_saas_help_nav.py tests/test_saas_help_copy.py \
  tests/test_saas_result_help.py tests/test_gui_saas_pages.py -q
uv run pytest tests/ -q   # 存量失败：test_saas_public_beta_ops.py::TestConsoleOps 2 例
```

## 验收

- 点击/滚动切换栏目：胶囊滑向新项，移动中纵向拉长，到位回弹，无残影。
- 当前项文字与胶囊对齐，文字不被遮挡，点击区域不变。
- 夜间模式：胶囊仍为紫色玻璃底、顶部高光可见、当前项文字对比度足够。
- 375px：双列 grid 下胶囊仍精确落在当前格子上。
- `prefers-reduced-motion: reduce`：无滑动动画，直接跳位。
- 键盘 Tab：焦点环可见；`aria-current` 随滚动/点击更新。

## 实现记录

- 新增：`src/quant_research_engine/gui/static/help-nav.js`、
  `tests/test_saas_help_nav.py`、本 CR。
- 修改：`src/quant_research_engine/gui/saas/templates/help.html`（胶囊元素 +
  `{% block scripts %}`）、`src/quant_research_engine/gui/static/lab-theme.css`
  （胶囊样式与降级）、`src/quant_research_engine/gui/static/night-mode.css`
  （暗色 token）。
- 部署：`./deploy/saas/deploy-ecs.sh`（help.html / lab-theme.css /
  night-mode.css / help-nav.js），部署后无头浏览器自验通过。
- 未提交：等待用户验收后由单代理流程执行 git finalization。

---

# V2 竞稿（step-5，2026-10-28）

V1 上线后用户反馈「不满意」，未给具体点。本节记录 V2 的取舍：**不新建第二个 CR，
直接覆盖同一份实现**，文件与选择器均不变（`.help-pill` / `.help-jump` /
`aria-current="true"` / `help-nav.js`），因此两版可以在生产环境直接对调。

## 与 V1 的差异对照

| 维度 | V1（DeepSeek） | V2（本稿） | 为什么这样改 |
| --- | --- | --- | --- |
| 玻璃质感 | 一层 `rgba(103,80,164,.12)` 实底 + 1px 同色边框 + 顶/底两条 inset 白线 | **五层叠成**：① 半透明紫底 `rgba(103,80,164,.13)` ② 顶部受光渐变（白 52% → 透明，48% 处收尽）③ `::before` + `mask-composite` 做出的 **1px 渐变描边环**（顶 95% 白 → 两侧 26% 紫 → 底 13% 紫，四圈一圈细高光）④ 顶部 1px 高光 + 底部 1px 压深（玻璃厚度）⑤ 贴地接触影 + 环境投影 | V1 的边框是**纯色**的，「细高光」只在顶部两条 inset 线上，四圈不连贯；受光渐变缺失导致底色发平，和白卡面分不出层次。渐变描边环让高光沿着圆角连续走一圈，才是「玻璃边缘」而不是「描了边的色块」 |
| 滑动态效 | 5 段 WAAPI 关键帧，外层 `easing:'linear'`，每帧自带 easing；位移用 `cubic-bezier(.22,1,.36,1)` 走到 55% 再切过冲曲线 | **rAF 下的弹簧数值积分**（半隐式欧拉，子步 1/240s）：位移是一条角速度恒定 12.25 rad/s、**阻尼比随移动距离在 0.62→0.80 之间自适应**的弹簧 | 关键帧的过冲量是写死的百分比（0.72/0.88 两帧），短距离移动和六行远跳用的是同一套比例：近跳几乎看不出回弹，远跳又容易拉皮。阻尼比自适应后，**绝对过冲量稳定落在 3~6px**（实测 2.9 / 4.7 / 5.5 / 4.1px，对应 46 / 92 / 138 / 276px 位移），任何距离都有可感知但不夸张的弹性。另外连点中断时 V1 会 `cancel()` 后从新起点重播，V2 从当前速度续滑，不跳帧 |
| 拉伸与回弹 | `stretchScale(dy,h)=1+clamp(|dy|/h*0.09,0,.18)`，**按位移量**算；`scaleY` 在 46% 路程处达到峰值，然后 72% 压扁、88% 过冲、100% 收 1 | ① 拉伸量由**速度在移动方向上的投影**直接导出（`|投影|/1500` 归一，上限 12%）：朝目标飞是拉伸，过冲回冲时投影转负、形变自动翻成压扁；② 到位那一下另有一条**闭式阻尼振荡** `amp·sin(ω_d t)·e^{-ζωt}` 补压扁，相位锁在**实测的穿过目标时刻**；③ 按运动主轴做**体积补偿**（主轴形变、垂直轴反向收窄 34%）；④ `transform-origin` 固定 `center` | 四个问题一次解决：**(a)** V1 按位移量算拉伸，所以「移一格」和「移六格」的拉伸比例只差在 clamp 上，没有速度感；V2 的拉伸跟随实时速度，快远跳拉满 12%、相邻轻移只 2%。**(b)** V1 的 0.72/0.88 帧锁在动画时间轴上，和胶囊**真正落位**的时刻没有绑定，缓动一改就错位；V2 的相位锁在积分器实测的穿过目标那一帧，永远对齐。**(c)** V1 恒定 `scaleY` + `top/bottom center` 切换，**在 ≤760px 双列 grid 里移动是横向的，却仍在做纵向拉伸**——方向与形变相反；V2 按主轴形变，横移就拉 `scaleX`。**(d)** V1 的 `top/bottom` 锚定让胶囊一边贴齐、一边探出，像渲染瑕疵；V2 绕质心对称形变 |
| 高光 | `inset 0 1px 0 rgba(255,255,255,.78)` + `inset 0 -1px 0 rgba(255,255,255,.18)` | 顶部 1px 高光 `rgba(255,255,255,.74)` + 底部 1px 压深 `rgba(74,58,120,.11)` + 上述渐变描边环 | 见「玻璃质感」行。底部白线在玻璃上不合物理（光从上方来），改成压深表示厚度 |
| 辅助视觉 | `aria-current` → `color:var(--lav); font-weight:500`；hover 仍会给当前项加 `--tint` 底 + `--tint-deep` 描边 | `color:var(--lav-deep); font-weight:600`（对比度更高）；hover **只作用于非当前项**且只给浅 tint、**不画描边**；新增 `:active` 按压；焦点环改 `--lav-deep`（在紫底上比 `--lav` 更容易看清） | V1 的 hover 规则 `.help-jump a:hover` 优先级低于 `.help-jump a:hover:not([aria-current])`，导致**悬停当前项时它会再描一个边框**，和胶囊的边缘高光抢戏。边缘高光应当归胶囊独有 |
| 初始出场 | 直接落到第一项（无出场） | 同一条闭式欠阻尼阶跃响应，缩放从 0.82 弹到 1（ζ=0.5，一次 3% 小过冲），叠加 0.2s opacity 过渡 | 首屏加载时胶囊「长出来」比「突然在那」自然，且不引入第四种运动机制 |
| 降级 | `prefers-reduced-motion` 关动画；`@supports not (backdrop-filter)` 退回 `--tint` 实底 | 同左，另补：`@supports not` 时受光渐变同步降透明度；**mask 描边环在极老浏览器不生效时自动退回「无描边但有 1px 高光」**，不会出现边框缺失导致的错位 | V2 形变全部由 JS 直算，reduced-motion 下直接吸附到目标、零动画、零残影 |

## V2 保留 V1 的部分（及理由）

- **单胶囊 + `position:absolute` + offset 定位**：这是需求字面要求的，且窄屏双列 grid
  下靠 `offsetLeft/offsetTop` 定位是正确解，无需改。
- **`IntersectionObserver`（`rootMargin:'-76px 0px -58% 0px'`）+ 取最靠上可见项 +
  「top ≤ 84 的最后一个 section」兜底**：滚动联动逻辑 V1 已验证可用，保留。
- **点击锁定（1.5s，滚动停止后 160ms 解锁）+ `history.replaceState` 同步 hash**：
  避免平滑滚动途中 IO 把当前项抢走，保留。
- **`aria-current="true"` + `aria-hidden="true"` 胶囊**：可访问性契约不变。
- **`@supports not (backdrop-filter)` 降级为 `--tint` 实底**：保留。
- **`.help-jump{position:relative}` 另起规则、不动 `display:flex` 锁定合同**：保留。

## 顺带修掉的两个小问题

1. **滚动监听从「每个 scroll 事件直接 `sync()`」改成 rAF 节流**：`sync()` 里有
   `getBoundingClientRect()`，裸 scroll 监听等于每事件强制布局。
2. **带 `#hash` 打开时先锁定 1.5s**：V1 只靠 `ready` 延迟 120ms 防初始 IO 回调覆盖，
   浏览器原生回跳若晚于 120ms 发生，当前项会被拽回第一项。

## 测试

`tests/test_saas_help_nav.py`（7 例，覆盖扩充）：

- 源码合同：单 `.help-pill` + `aria-hidden`、脚本经 `{% block scripts %}` 引入、
  nav 仍 7 锚点、侧栏无 `.opt`、页面 `.opt` 计数 ≤3。
- CSS 合同：`position:relative`、五层玻璃（`--pill-sheen` / `mask-composite:exclude` /
  `--pill-rim-top` / `inset 0 1px 0` / `backdrop-filter:blur(7px) saturate(1.35)`）、
  `@supports not` 降级、`aria-current` 与 `focus-visible` 与 hover、reduced-motion
  关过渡；夜间 token 含 `--pill-glow`、`--pill-rim-top`、`--pill-sheen` 与
  `155,132,216` 色相。
- Node vm 纯函数 harness：`moveParams`（角速度恒定 / 阻尼比随距离上升 / 端点钳位）、
  `springStep`（收敛、越过目标、过冲 ≤12px、大 dt 不发散）、`oscillate`（t≤0 为 0、
  先压扁后回冲、衰减到 0）、`stepResponse`（t=0 为 1、收敛、过冲）、`impactScale`
  （负值、保底、上限）、`deformScale`/`stretchScale`（符号、截断、方向无关）、
  `axisFor`、`scaleFor`（主轴形变 + 体积补偿 + 静止为 1）、`crossedTarget`、
  `transformFor`（含 2 位小数）。
- 既有约束不变：`test_saas_help_copy.py`、`test_saas_result_help.py`、
  `test_gui_saas_pages.py` 全部通过。

验证命令与结果：

```bash
uv run pytest tests/test_saas_help_nav.py tests/test_saas_help_copy.py \
  tests/test_saas_result_help.py tests/test_gui_saas_pages.py -q
# 127 passed
uv run pytest tests/ -q
# 2988 passed, 24 skipped
```

## V2 实现记录

- 修改：`src/quant_research_engine/gui/static/help-nav.js`（弹簧积分 + 速度投影形变
  + 闭式到位振荡，重写）、`src/quant_research_engine/gui/static/lab-theme.css`
  （五层玻璃 + mask 描边环 + 当前项/hover/focus 规则）、
  `src/quant_research_engine/gui/static/night-mode.css`（暗色五层 token）、
  `tests/test_saas_help_nav.py`（覆盖扩充）。
- 未改：`help.html`（V1 的胶囊元素与脚本引入原样够用）、`base.html`、其它模板、
  `night-mode.js`。
- 部署：`./deploy/saas/deploy-ecs.sh`（lab-theme.css / night-mode.css /
  help-nav.js），部署后无头浏览器自验通过，采样表与截图见 `.tmp/help-pill-v2/`。
- 未提交：等待用户在 V1 / V2 之间择优后执行 git finalization；若选 V1，按
  `docs/agent/change_requests/` 的回滚约定恢复 V1 三个静态文件即可。

## V3 形变加强（2026-10-28，Kimi，用户反馈「没看见拉长特效」后）

V2 的形变推导正确但**幅度不足以肉眼可见**：实测峰值速度约 1000px/s，而
`VEL_REF=1500` 只能吃到 2/3，`DEFORM_MAX=0.12` 又封顶在 12%——42px 胶囊只拉长
约 3.4px，采样表里能看到，页面上看不出来。

参数调整（`static/help-nav.js`）：

| 参数 | 原值 | 新值 | 理由 |
| --- | --- | --- | --- |
| `VEL_REF` | 1500 | **600** | 典型速度（相邻项 ~600、跨项 ~1000px/s）即饱和给足 |
| `DEFORM_MAX` | 0.12 | **0.28** | 42px 胶囊拉长到 53.8px（+11.8px），清晰可辨 |
| `SQUEEZE` | 0.34 | **0.26** | 原值收窄过头，抵消了拉长的视觉；保留体积感又不掩盖形变 |
| `IMPACT_MAX` | 0.10 | **0.16** | 压扁从 4.2px 提到 6.7px，与拉长匹配，回弹才看得见 |
| `IMPACT_RANGE` | 200 | **160** | 原值下相邻项只吃 0.5 下限，落地太轻 |

实测（生产无头浏览器采样 computed transform）：

| 场景 | 峰值拉伸 | 峰值压扁 |
| --- | --- | --- |
| 相邻项（46px） | scaleY **1.126** → 47.3px | 0.970 → 40.7px |
| 跨 5 项（231px） | scaleY **1.280** → 53.8px | 0.927 → 38.9px |
| 375 横向跨列 | scaleX **1.280** → 181.8px | 0.922 → 131.0px |

测试：`tests/test_saas_help_nav.py` 形变量断言同步加强（参考速度 600、上限 0.28、
真实速度区间 600–1200 必须 ≥0.20、压扁上限 0.16 且按距离比例给、保底下限改按
`IMPACT_RANGE/2` 判定）；7 passed；**全量 2988 passed, 24 skipped**。
生产已部署（MainPID 523725，回滚副本 `/tmp/qre-deploy-20261028T054823Z.bak`）。
