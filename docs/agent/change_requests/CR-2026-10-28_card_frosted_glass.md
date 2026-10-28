# CR-2026-10-28 全站卡片磨砂玻璃 + 光标跟随光斑 + 轻微 3D 倾斜

> 用户原话需求（逐字）：
> 1. **卡片半透明磨砂玻璃**：`backdrop-filter:blur(28px)saturate(140%)`，45%–60% 透明度，
>    1px 半透明白色描边，顶部内侧一道细高光，圆角 24px，大而柔的阴影，**颜色不变**
> 2. **悬停时**：在卡片内部跟随光标显示一团柔和径向光斑；靠近光标的边框局部提亮；
>    卡片随光标位置轻微 3D 倾斜，**不超过 4 度**；移出后平滑复原

## 背景

改前全站卡片是「实色白卡 + 1px 淡紫描边 + 10px 圆角 + 一层小投影」：
`body{background:var(--paper)}` 是纯色 `#FAF9FC`，`.card` / `.chart-box` / `.panel`
`background:#fff`。两个问题：

1. **没有纵深**：整页一层平白，卡片与页面背景之间只有一道 1px 线和一层小阴影，
   重点页面（`job.html` 回测详情 / `symbol.html` 个股详情）信息密度高，视觉上糊成一片。
2. **交互反馈弱**：卡片只有 hover 变色/位移，没有「这一片是可交互玻璃面」的质感。

本次只做这一片：给全站卡片族上磨砂玻璃，并在悬停时加光标跟随光斑、边框局部提亮与
≤4° 的轻微 3D 倾斜。**不改任何颜色语义**（仍是浅紫白 + 品牌紫），不改因子/回测/K 线
渲染逻辑，不改 `night-mode.js` 主题机制。

## 目标

1. `.card` / `.chart-box` / `.panel` / `.big-link`（大卡）+ `.metric` / `.metric-card` /
   `.entry-card`（小卡）统一玻璃化：`backdrop-filter:blur(28px) saturate(140%)`、
   48% 白底、1px 半透明白描边、顶部 1px inset 高光、24px 圆角、两层大而柔的投影。
2. 悬停时卡片内出现跟随光标的柔和径向白光；1px 描边环上靠近光标的一段局部提亮。
3. 卡片随光标位置做 ≤4° 的 3D 倾斜；移出后平滑复原。
4. 夜间模式全套生效，色相不漂移；`prefers-reduced-motion` 下降级；键盘焦点环不被遮挡。
5. 零新增依赖、零新增灰色小字备注（R-UI-001）、不破坏既有测试。

## 边界

- 只改静态资源与一个模板的一行脚本引入：
  `static/lab-theme.css`、`static/night-mode.css`、新增 `static/card-fx.js`、
  `saas/templates/base.html`（加一行 `<script>`）。**未改任何业务模板结构**。
- 不改 `night-mode.js` 主题机制、因子/回测/游戏逻辑、`symbol.html` 的 K 线/LWC 渲染逻辑、
  `help.html` 的侧边栏胶囊。
- 不改 `--radius` 既有 token（`style.css` 等仍在用），新起 `--card-radius:24px`。
- 小卡（`.metric` / `.metric-card` / `.entry-card`）**沿用各自既有圆角**，不进 24px：
  60px 高的小卡用 24px 圆角会变胶囊，且改小卡圆角会连带改 `metric-strip` 的排版权重。

## 陷阱处理（逐条）

### 1. `backdrop-filter` 需要背后有内容 —— 加 `body::before` 背景装饰层

`body` 是纯色 `--paper`，在纯色上 `blur(28px)` **完全看不见**（实测：同页开关
`backdrop-filter` 的像素差 `mean_abs_diff=0.194`、`0%` 像素变化）。因此先给背景加
一层品牌紫径向渐变墙纸：

```css
body::before{
  content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;
  background:
    radial-gradient(70rem 50rem at 12% 2%,  rgba(103,80,164,.30), transparent 58%),
    radial-gradient(56rem 40rem at 90% 12%, rgba(139,127,190,.27), transparent 56%),
    radial-gradient(62rem 46rem at 78% 98%, rgba(103,80,164,.20), transparent 58%),
    radial-gradient(50rem 38rem at 2% 86%,  rgba(230,222,243,.85), transparent 56%);
}
```

- **为什么用 `z-index:-1` 而不是给 `.wrap`/`.container` 提 `z-index:1`**：负 z-index 的
  fixed 伪元素排在根层「画布背景之上、全部内容之下」，**不需要给任何内容层提层级**，
  从根上消除了「盖住文字」和「破坏 `.topbar{z-index:40}` / `.modal-mask{80}` /
  `.wm-mask{95}` / `.sidenav{60}`」两类风险。saas 模板的主容器是 `.container` /
  `.app-main`，lab 模板是 `.wrap` / `main`，逐个提层级容易漏。
- 光斑半径与位置是调过的：第一版把云团放在 `2% -12%` / `100% -4%` / `94% 104%`，
  **大部分出血到视口外**，卡片中心几乎采不到紫色（实测卡片中心开/关差 1 个色阶）。
  现在四团都压在视口内且半径足够覆盖内容区。
- 颜色仍是品牌紫（`--lav` / `--lav-ink` / `--tint-deep`），不引入新色相；透明度压在
  「浅紫白」区间，卡片中心合成后仍是 (253,252,254) 量级的白。

### 2. 图表卡不能做 3D 倾斜 —— JS 判定 `querySelector('canvas')`

含 canvas 的卡片（`#chart-main` / `#chart-tags` / `#chart-equity` / `#chart-kline` /
`#chart-risk-*` / LWC 画布 / 重播接管容器）**只加光斑，不挂 `transform`**。
判定在 `card-fx.js`：

```js
function eligibleForTilt(card){
  if (!card || !card.matches || !card.matches(TILT_SEL)) return false;
  return !card.querySelector('canvas');
}
```

`transform` 规则只挂在 JS 加的 `.fx-tilt` 类上，**没有该类 `transform` 计算值就是 `none`**
（自验实测 `#box-main` / `#chart-equity` / `#chart-kline` 的 computed `transform` 均为
`none`）。canvas 资格每次 flush 都重判，echarts 中途挂上画布也会立刻撤掉倾斜。
`.metric` / `.metric-card` / `.entry-card` 不在 `TILT_SEL` 里——它们自有
`hover{translateY}` 位移，再叠倾斜会 transform 冲突。

### 3. 性能：单个委托监听 + rAF 节流

`document` 上**只有一个** `pointermove` 监听（`passive:true`），每帧只写当前悬停卡的
四个 CSS 自定义属性；`pointerleave/pointerup/pointercancel/blur` 复位，`scroll/resize`
只作废缓存的矩形。没有逐卡监听、没有每帧多属性写入、取值不变时不写（`state.mx/my/rx/ry`
去重）。

### 4. 卡片嵌套 —— 只驱动最外层

`closest(CARD_SEL)` 命中内层卡时用 `outermost()` 向上爬到最外层玻璃卡，只驱动最外层：
内层不会重复加倾斜/光斑（否则 transform 叠加、光斑重叠）。CSS 侧点亮也由 JS 加 `.fx-on`
完成（不用 `:hover`），所以嵌套内层天然不会亮。嵌套内层小卡 additionally 恢复实色底、
不做二次 `backdrop-filter`（见下）。

### 5. 圆角 10px → 24px 的连带影响

排查了所有贴卡片边缘的子元素：`.tbl` / `.detail-table` / `.tag-rank` / `.table-wrap` /
`#tag-detail` / `#replay-events` / `#kreplay-events` 都是无底色滚动容器；`.treemap-wrap`、
`#chart-main`、`#chart-tags` 的 echarts 画布背景透明；`.wb-track` / `.zoom-track .rail`
自带圆角且在卡片内缩进。**没有露直角的个案**。仍加了一条兜底规则让贴边滚动容器继承圆角：

```css
.card>.table-wrap,.chart-box>.table-wrap,
.card>.tag-rank,.chart-box>.tag-rank,
.card>#tag-detail,.chart-box>#tag-detail,
.card>#kreplay-events,.chart-box>#kreplay-events,
.card>#replay-events,.chart-box>#replay-events{border-radius:inherit}
```

### 6. 其它硬约束

- **R-UI-001**：本次改动零新增灰字。`lab-theme.css` 里 `.opt{` 仍是原有 3 条，新增段
  （从「全站卡片：磨砂玻璃」段头到文件尾）不含 `.opt` / `--faint`；`base.html` 不新增
  `.opt`；`night-mode.css` / `card-fx.js` 不含 `.opt`。
- **禁外部依赖**：`card-fx.js` 无 http(s)/unpkg/jsdelivr/cdn，全部本地静态资源。
- **夜间模式**：`night-mode.css` 新增暗色玻璃 token（`--glass-bg:rgba(46,35,108,.48)` 等）
  与暗色装饰层，全部规则仍带 `:root[data-theme="dark"]` 作用域（既有测试
  `test_all_rules_scoped_or_button` 约束）。
- **`prefers-reduced-motion: reduce`**：CSS 侧光斑 `::before/::after{display:none}`、
  `.fx-tilt{transition:none}`；JS 侧 `prefersReduced()` 直接 return，不写任何变量
  （自验实测 `--mx` 保持初值 `50%`、`transform:none`、光斑 `opacity:0`）。
- **可访问性**：焦点环是全站既有 `:focus-visible{outline:2px solid var(--lav);
  outline-offset:2px}`，画在卡片外，不被 1px 描边环遮挡；光斑 `::before` 用
  `z-index:-1` + 父级 `isolation:isolate` **压在卡片背景之上、文字之下**，从结构上
  不影响文字对比度；光斑最大透明度 0.34（暗色 0.10）。
- **既有测试**：`test_saas_help_nav.py`（`.help-jump{position:relative}` 等）、
  `test_saas_help_copy.py`、`test_saas_result_help.py`、`test_gui_saas_pages.py`、
  `test_saas_night_mode.py` 全部通过。

## 实现

### 1. 玻璃本体（`lab-theme.css`）

```css
:root{
  --card-radius:24px;
  --glass-bg:rgba(255,255,255,.48);      /* 45%–60% 取偏下沿 */
  --glass-line:rgba(255,255,255,.5);
  --glass-hi:rgba(255,255,255,.75);
  --glass-shadow:0 1px 2px rgba(74,58,120,.06),0 18px 46px -14px rgba(74,58,120,.26);
  --glass-spot:rgba(255,255,255,.34);
  --glass-rim:rgba(103,80,164,.55);
  --glass-sheen:linear-gradient(180deg,rgba(255,255,255,.30),rgba(255,255,255,0) 45%);
  --glass-tilt:4;
}
.card,.chart-box,.panel,.big-link{
  position:relative;isolation:isolate;
  --mx:50%;--my:50%;--rx:0;--ry:0;
  border-radius:var(--card-radius);
  background-color:var(--glass-bg);
  background-image:var(--glass-sheen);   /* 顶部受光：玻璃厚度 */
  border:1px solid var(--glass-line);
  box-shadow:inset 0 1px 0 var(--glass-hi),var(--glass-shadow);
  -webkit-backdrop-filter:blur(28px) saturate(140%);
  backdrop-filter:blur(28px) saturate(140%);
}
```

`background` 拆成 `background-color` + `background-image`：`background` 简写会把
`background-image` 重置为 `none`，而 `#metric-strip .metric-card` 等既有规则用的就是
`background:var(--tint)` 简写，拆开才能让两层规则各管各的。

### 2. 光斑与边框提亮

```css
/* 光斑：跟随光标的柔和径向白光，压在卡片背景之上、文字之下 */
.card::before,...{
  content:"";position:absolute;inset:0;z-index:-1;border-radius:inherit;pointer-events:none;
  background:radial-gradient(280px circle at var(--mx) var(--my),var(--glass-spot),transparent 65%);
  opacity:0;transition:opacity .35s var(--ease);
}
/* 边框局部提亮：mask 挖空内容区，只留 1px 环 */
.card::after,...{
  content:"";position:absolute;inset:0;border-radius:inherit;padding:1px;pointer-events:none;z-index:1;
  background:radial-gradient(220px circle at var(--mx) var(--my),var(--glass-rim),transparent 70%);
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
  -webkit-mask-composite:xor;
  mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
  mask-composite:exclude;
  opacity:0;transition:opacity .35s var(--ease);
}
.fx-on::before,.fx-on::after{opacity:1}
```

`::before` 的 `z-index:-1` 需要父级是层叠上下文才落在「卡片背景之上」——所以玻璃族统一加
`isolation:isolate`（顺带也隔离了 `mix-blend-mode` 泄漏）。

### 3. 倾斜

```css
.fx-tilt{
  transform:perspective(1000px)
            rotateX(calc(clamp(calc(-1 * var(--glass-tilt)),var(--ry),var(--glass-tilt)) * 1deg))
            rotateY(calc(clamp(calc(-1 * var(--glass-tilt)),var(--rx),var(--glass-tilt)) * 1deg));
  transition:transform .38s var(--ease);
}
.fx-tilt.fx-live{transition:none}
```

- `--rx/--ry` 由 JS 写成**度**（±4），CSS 再用 `clamp()` 按 `--glass-tilt` 二次钳制兜底
  （JS 与 CSS 双向钳制，任一侧被绕过都不会超 4°）。
- **踩过的坑**：第一版写成 `rotateX(clamp(-1,var(--ry),1)*1deg)`，两处都错——
  (a) 数学函数不能裸乘 `1deg`，必须包在 `calc()` 里；(b) `clamp(-1,…)` 钳的是**度**，
  把 3.98° 钳成 1°，倾斜几乎看不见。修正后实测右缘 `rotateY=3.98°`。
- `.fx-live`（指针移动中）关掉过渡保证**跟手**；移出时移除 `.fx-live` 并把变量归零，
  同一帧的 after 样式带 `transition` → **平滑复原**。

### 4. 嵌套玻璃不二次模糊

```css
.card .metric,.card .metric-card,.chart-box .metric,.chart-box .metric-card{
  background-color:#fff;background-image:none;border-color:var(--line);
  -webkit-backdrop-filter:none;backdrop-filter:none;
}
```

两个理由：① 双层半透明叠加会发灰、光斑会重叠；② **性能**——实测 job 页指针移动帧耗时
从 39ms 降到 30ms（嵌套小卡的第二次全卡 backdrop 重采样整段消失）。

### 5. JS（`static/card-fx.js`）

```js
window.QRECardFx = { TILT_MAX:4, CARD_SEL, TILT_SEL, clamp, spot, tilt, outermost, eligibleForTilt };
```

- `spot(w,h,x,y) → {mx,my}`：指针在卡内位置 → 光斑中心百分比，越界钳 0–100，零尺寸回退 50。
- `tilt(w,h,x,y) → {rx,ry}`：`nx = clamp(x/w*2-1,-1,1)`、`ny = clamp(y/h*2-1,-1,1)`，
  `rx = nx*4`（rotateY，右缘后退）、`ry = -ny*4`（rotateX，下缘后退）。中心 0，四角 ±4。
- `outermost()` / `eligibleForTilt()` 见上。
- 纯函数在模块加载时即导出，Node vm harness 可直接跑（`typeof document === 'undefined'`
  时提前 return，不碰 DOM）。

## 测试

`tests/test_card_fx.py`（18 例，新建）：

- **源码合同**：`.card` 玻璃四件套（`backdrop-filter:blur(28px) saturate(140%)` /
  `--card-radius:24px` / `1px` 半透明白描边 / `inset 0 1px 0` 高光 + 46px 大投影）、
  `--glass-bg` 落在 45%–60% 区间、小卡不改圆角、`body::before` 装饰层
  （fixed / `pointer-events:none` / `z-index:-1` / ≥3 团品牌紫渐变）、
  `.topbar` 与浮层 z-index 未被破坏、光斑 `z-index:-1` + `isolation:isolate`、
  描边环 `mask-composite:exclude` + `-webkit-mask-composite:xor`、`.fx-on` 点亮
  （不用 `:hover`）、`--mx/--my/--rx/--ry` 声明与使用、倾斜 clamp 双向、
  canvas 卡不挂 transform、嵌套只驱动最外层、reduced-motion 降级、
  `@supports not` 兜底、焦点环规则、嵌套小卡不二次模糊。
- **夜间合同**：暗色玻璃 token 五项、卡片族 `background-color/border-color/box-shadow`
  覆盖、暗色装饰层仍是 `155,132,216` / `126,96,191` 品牌紫、所有规则仍带
  `:root[data-theme="dark"]` 作用域。
- **JS 接线与性能**：`document.addEventListener('pointermove'` 恰好 1 处、
  `{ passive: true }`、`requestAnimationFrame(flush)`、无 `forEach` 逐卡监听、
  `base.html` 在 `night-mode.js` 之后引入 `card-fx.js`、无外部依赖、无新增灰字。
- **Node vm harness**：`spot`（中心 50/50、四角 0/100、越界钳制、零尺寸回退、40 点连续
  采样不越界）、`tilt`（中心 0、四角 ±4 极值、右正左负 / 上正下负符号、任意输入含
  ±1e6 都落在 ±4 内且有限）、`outermost`（嵌套爬到最外层 / 最外层返回自身 / 无玻璃卡
  祖先返回自身）、`eligibleForTilt`（无 canvas 可倾 / 有 canvas 不倾 / 小卡与入口卡
  不倾）。

验证命令与结果：

```bash
uv run pytest tests/test_card_fx.py tests/test_saas_help_nav.py tests/test_saas_help_copy.py \
  tests/test_saas_result_help.py tests/test_gui_saas_pages.py -q     # 145 passed
uv run pytest tests/ -q                                              # 3006 passed, 24 skipped
```

（存量 1 例偶发失败与本次无关：`test_gui_saas_pages.py::TestNoAdminLinks` 禁链检查会把
`asset_v`（`int(time.time())`）里恰好含 `8081` 的时间戳判成禁链，换一秒重跑即过。）

## 验收（生产无头 Chromium 实测，脚本 `.tmp/card-fx/verify.py`，报告 `.tmp/card-fx/report.json`）

覆盖 `/saas/`、`/saas/new`、`/saas/jobs/58`、`/saas/jobs/58/symbols/920832.BJ`、
`/saas/help`、`/saas/showcase`、`/saas/console` 七页，全部零 pageerror
（3 条 console 401 来自游客态未读信号计数接口，与本次无关）。

- **玻璃真的在起作用**（纯 Python PNG 解码逐像素对比，同一卡片区域三态）：
  | 对比 | mean_abs_diff | 变化像素占比 |
  | --- | --- | --- |
  | 玻璃全开 vs 藏装饰层 | 0.97 | 18.9% |
  | 玻璃全开 vs 全关 | 0.96 | 18.3% |
  | 藏装饰层 vs 全关（纯色上开/关 blur） | 0.21 | 0.03% |

  第三行正是「必须先加装饰层」的量化证据：纯色背景上 `blur(28px)` 的像素贡献接近零。
- **悬停光斑可见度**：同一卡片「指针在卡内 30%/35%」vs「指针移出」两帧对比，
  光斑中心局部平均差 **15.4 个色阶**、全卡 12.7% 像素变化（含 1px 描边环提亮）。
- **计算样式**：`backdrop-filter:blur(28px) saturate(1.4)`、
  `background-color:rgba(255,255,255,0.48)`、`border-radius:24px`、
  `border-top:1px rgba(255,255,255,0.5)`、`box-shadow` 含 `inset 0 1px 0 rgba(255,255,255,.75)`
  与 `18px 46px -14px` 大投影、光斑 `z-index:-1`、描边环 `mask-composite:exclude`。
- **悬停跟随**：`--mx/--my` 由 25%/30% 精确变到 75%/70%；光斑与描边环 `opacity 0→1`。
- **倾斜**：右缘 `rotateY=3.980°`、`rotateX=0°`；四角 `|rx|`/`|ry|` = 3.95°/3.97°
  （≤ 4.001°）；`--rx` 钳制在 ±4。左上 = 左缘+上缘朝前、右下 = 右缘+下缘朝后，
  符号与「光标所在边向内压」一致。
- **图表卡豁免**：`#box-main` computed `transform: none`、未挂 `.fx-tilt`、仍有光斑；
  截图 `job-chart-hover.png` 中收益曲线与回撤子图清晰不发糊。
- **移出复原**：40 帧采样到 8 个不同中间值（transition 生效），终态角度 0.0000°。
- **夜间**：`background-color: rgba(46,35,108,0.48)`、`border-top: 1px rgba(241,237,248,.16)`、
  装饰层 4 团仍是品牌紫、`blur(28px)` 仍在；截图 `job-dark-full.png` /
  `symbol-dark-full.png`。
- **375 窄屏**：六页 `scrollWidth ≤ innerWidth`，无横向溢出，`symbol-375.png` 正常。
- **reduced-motion**：光斑 `opacity:0`、`transform:none`、`--mx` 保持 `50%`。
- **焦点环**：Tab 两次后 activeElement `outline: solid 2px rgb(103,80,164)`、`offset:2px`。

## 性能结论（帧率）

无头环境 **SwiftShader 软件渲染（无 GPU）**，`backdrop-filter` 的重采样由 CPU 完成。
同一指针轨迹（60 次 `mouse.move`，rAF 采样）、四组配置各跑 3 轮取中位数：

| 配置 | 平均帧耗时 |
| --- | --- |
| 静止基线 | 16.60ms（60fps） |
| A 完整实现 | 30.70ms |
| B 屏蔽 `card-fx.js` | 27.43ms |
| C JS 全跑、CSS 中和掉效果（光斑 `opacity:0` + 倾斜 `transform:none`） | 27.48ms |
| 关掉 `backdrop-filter` | 16.65ms（60fps） |

- **C − B = 0.05ms**：委托监听 + rAF 节流 + `closest`/`getBoundingClientRect` 的簿记成本
  可以忽略——这是「单个委托监听」设计的验收点，实测通过。
- **A − C = 3.22ms**：光斑重绘 + 倾斜触发 backdrop 重采样的固有成本。倾斜本身就要求
  卡片逐帧改 `transform`，在软件渲染下这会让 `backdrop-filter` 重新采样整卡。
- **关掉 `backdrop-filter` 立刻回到 16.65ms**：剩余成本 100% 来自浏览器对
  `blur(28px)` 的软件重采样，不是本次实现的缺陷。真实用户端有 GPU 硬件加速
  （`docs/agent/13_UI_PERF_NOTES.md` 亦记有同类结论）。
- 已做的减负：嵌套小卡不二次模糊（job 页 39ms → 30ms）、取值不变不写属性。

## 实现记录

- 新增：`src/quant_research_engine/gui/static/card-fx.js`、`tests/test_card_fx.py`、
  `docs/agent/change_requests/CR-2026-10-28_card_frosted_glass.md`。
- 修改：`src/quant_research_engine/gui/static/lab-theme.css`（玻璃 token + 装饰层 +
  玻璃族 + 光斑/描边环 + 倾斜 + 嵌套规则 + 降级）、
  `src/quant_research_engine/gui/static/night-mode.css`（暗色玻璃 token + 卡片族覆盖 +
  暗色装饰层）、`src/quant_research_engine/gui/saas/templates/base.html`（一行脚本引入）。
- 未改：任何业务模板结构、`night-mode.js`、`help-nav.js`、因子/回测/K 线逻辑。
- **部署**：`./deploy/saas/deploy-ecs.sh`（`lab-theme.css` / `night-mode.css` /
  `card-fx.js` / `base.html`，末次部署 MainPID 528124，回滚副本
  `/tmp/qre-deploy-20261028T073027Z.bak`），部署后无头浏览器自验通过（12/12 项 0 失败），
  截图与报告在 `.tmp/card-fx/`（`verify.py` / `report.json` / `*-full.png` /
  `*-hover.png` / `glass-on|off-*.png` / `symbol-375.png` / `job-reduced-motion.png`）。
- 未 commit / 未 push：等待用户验收后由单代理流程执行 git finalization。

## 待确认的判断（给用户）

1. **45%–60% 透明度取 48%**：区间偏下沿。理由：`--paper` 本身已接近白色，取中值 55%
   时背景光斑透过玻璃只有 1 个色阶（实测卡片中心开/关差 1），48% 把可感知差异拉到
   3–8 个色阶，同时卡片中心仍是 (253,252,254) 量级的白，「颜色不变」成立。
2. **光斑亮度 `rgba(255,255,255,.34)`（暗色 `.10`）**：压在文字之下 + 低透明度双保险，
   实测不影响文字对比度；再亮就会在深色文字上「发灰」。
3. **倾斜跟手不滞后**：移动中 `.fx-live` 关掉 `transition`，光标到哪倾斜到哪；只有
   「移出复原」这一下用 0.38s 过渡。滞后版（全程 transition）在快速划过时会明显拖影。


## 用户反馈修正（2026-10-28，Kimi）

### 1. 使用说明侧边栏不再吸附、且初始位置被下推

**根因**：`.help-side` 是 `<aside class="card help-side">`——同时带 `.card` 类。
玻璃卡族规则 `.card,.chart-box,.panel,.big-link{position:relative;...}` 与原
`.help-side{position:sticky;top:76px}`（第 620 行）**特异性相同**，而玻璃族写在
后面（第 741 行），按「后声明胜出」把 `sticky` 顶成了 `relative`。于是
`top:76px` 从「吸附阈值」变成「相对位移」，侧边栏被整体下推 76px（实测
y=281 vs 右侧 y=205），且滚动不再吸附。

**修复**：在玻璃卡族之后补一条 `.help-side{position:sticky;top:76px}`。
`isolation:isolate` 由玻璃族提供，不影响 sticky 行为。

**实测**：`position=sticky`、侧边栏 y=205 与右侧 y=205 **差 0px**；滚动 1200px
后吸附在 y=76。

### 2. 3D 倾斜不应作用于所有 div，只作用于并列小卡

**原状**：`TILT_SEL = '.card,.chart-box,.panel,.big-link'`——所有大卡都倾斜。

**修复**：`TILT_SEL` 收窄为 `'.metric-card'`（总收益率/年化收益/超额收益/夏普、
交易磨损五联卡、风险指标卡——`.wear-cards`/`.risk-cards` 内部同样是 `.metric-card`），
CSS 侧同步加 `.metric-card.fx-tilt{...translateY(-2px)}` 做双保险，并把原来的
`.metric-strip .metric-card:hover{transform:translateY(-2px)}` 的 transform 去掉
（两条 transform 规则会互相覆盖，hover 微浮合并进倾斜的同一个 transform）。

装小卡的大卡与图表卡恒为 `transform:none`——大卡内是 ECharts/LWC 画布，
`rotateX/rotateY` 会让画布发糊、文字发虚。

**实测**：
- hover 小卡 `.metric-card`（总收益率）：`fxTilt=true`、`rotateY -1.41°`、
  `rotateX 1.15°`、光斑 opacity 0.999
- hover 大卡 `.chart-box`（高 638px）：`fxTilt=false`、`transform:none`、
  光斑 opacity 0.999（玻璃与光斑仍生效，只是不倾斜）

### 测试

`tests/test_card_fx.py` 补断言：`.metric-card.fx-tilt` 存在、`TILT_SEL` 必须为
`'.metric-card'`、`.help-side{position:sticky}` 必须排在玻璃卡族之后、
`eligibleForTilt` 对大卡/图表卡/入口卡一律 false、只对 `.metric-card` true；
18 passed；相关 145 passed。


### 3. 小卡倾斜看不见（perspective 太远）

用户反馈「小卡片的div我没有检查到倾斜效果」。实测定位：**不是没生效，是几何上看不见**。
`.metric-card` 只有 170x77px，在 `perspective(1000px)` 下 4° 产生的水平位移仅 **0.4px**
（当时测得的 -2.3px 垂直位移其实来自 hover 微浮 translateY(-2px)，不是旋转）。

透视距离实测表（170x77 卡，--rx/--ry 取 0.84/0.7 倍上限）：

| perspective | 角度上限 | 左缘位移 | 上缘位移 |
| --- | --- | --- | --- |
| 1000px | 4° | -0.4px | -2.3px |
| 620px | 6° | -1.1px | -2.7px |
| 400px | 6° | -1.8px | -2.8px |
| 260px | 4° | -2.1px | -2.7px |
| 200px | 6° | -4.1px | -3.4px |

**修复**：`.metric-card.fx-tilt` 的 perspective 由 1000px 收到 **260px**——同一角度放大
6 倍位移，且**不突破用户设定的 4° 上限**。通用 `.fx-tilt`（大卡用，当前无使用者）
保持 1000px。

**实测（生产）**：右缘悬停 左缘 -2.1px / rotateY -2.39° / rotateX -1.98°；
左下悬停 左缘 +0.9px / rotateY +2.27°（方向正确跟随光标）；中心 0°（正确）；
大卡 `.chart-box` 仍 `transform:none`、光斑正常。
