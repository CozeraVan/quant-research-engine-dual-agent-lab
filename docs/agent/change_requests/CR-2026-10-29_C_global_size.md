# CR-2026-10-29 C：全局尺寸调整（宽屏铺满 / 字号加大 / 间距放松 / 图表加高）

状态：已实施，未 commit/push，等用户验收
上游任务书：`TASK-2026-10-29_deepseek_uiux.md` §C（顺序 A → C → B，本 CR 是 C）

## 1. 用户诉求（28 寸 + MacBook 主观反馈）

「字小、密度大、主题窄」三条对应任务书 C2 的 ①②③。C 项同时要求幂等覆盖 SaaS 与
8081 lab 两套页面（`lab-theme.css` 是共用文件），且 `.wrap` 与 `.topbar-inner` 的
max-width/padding 必须严格一致，否则顶栏与内容左右对不齐。

## 2. 改动

### 2.1 宽度（C2-①）

| 选择器 | 现 → 新 |
| --- | --- |
| `.wrap` | `max-width:1280px; padding:32px 32px 80px` → `max-width:1600px; padding:20px 20px 80px` |
| `.topbar-inner` | `max-width:1280px; padding:0 32px` → `max-width:1600px; padding:0 20px` |
| `main`（8081 lab 的 style.css 遗留纠偏） | `1280px/32px` → `1600px/20px` |
| `.topbar`（8081 无 inner 包裹层，顶栏直接作用于 header） | `padding:0 32px` → `padding:0 max(20px,calc((100% - 1600px)/2 + 20px))` |
| `.panel`（8081） | `padding:20px 22px; margin-bottom:20px` → `26px 28px / 28px` |
| SaaS `base.html .container` | `max-width:1100px; padding:16px` → `max-width:1600px; padding:20px` |
| `body`（lab-theme） | 追加 `max-width:none`，压掉 `style.css` 遗留的 `body{max-width:1200px}` |

8081 的 `.topbar` 用 `max(...)` 而不是固定 padding：没有 `-inner` 包裹层时，只有把
左右 padding 做成「随内容列居中」才能让品牌左缘 = 居中内容左边界（实测 1920 下
`brandL=180`、`boxL=160`，差值即 `.wrap` 的 20px padding）。

**窄屏对齐**：SaaS `base.html` 的 `@media(max-width:400px)` 把 `header.topbar`
从 `padding:0 10px` 改为 `0 12px`；`lab-theme.css` 新增
`@media(max-width:768px){.app-shell .wrap{padding:20px 12px 60px}}`。
原因是窄屏 `.container`/内容列都是 12px，顶栏 10px 会让品牌与内容错开 2px；
lab 页（非 `.app-shell`）顶栏是 20px，`.wrap` 保持 20px 不动。

### 2.2 字号（C2-②，只放大不放小）

| 选择器 | 现 → 新 |
| --- | --- |
| `body` | `15px` → `16px` |
| `.page-head p` | `14.5px` → `15.5px` |
| `.chart-title` | `14.5px` → `15.5px`（模板内联的 `13px` → `14px`，按任务书） |
| `.chart-title .opt` / `.opt` | 不放大（保持弱化层级；均 ≥12px） |
| `.metric .m-label` / `.metric-card .m-label` | `12px` → `13px` |
| `.metric-card .m-value` | `18px` → `20px`；`#sum-strip/#ra-strip` `15px` → `16.5px` |
| `table.tbl` | `13.5px` → `14.5px`；`.tbl th` `12.5px` → `13.5px` |
| `.detail-table` | `12.5px` → `13.5px`；`.detail-table th` `12px` → `13px` |
| `.bench-bar` | `13px` → `14px`；`.seg-btn` `12.5px` → `13.5px` |
| `job/lab_result` 的 `.chart-title` 内联 | `13px` → `14px` |

`font-family` / `font-weight` / `line-height` 一律未动；除 `#sum-strip/#ra-strip`
的 `m-value`（任务书点名 `16.5px`）外全部为整 px 的 +1。

### 2.3 间距与内边距（C2-③）

| 选择器 | 现 → 新 |
| --- | --- |
| `.card` | `padding:20px 22px; margin-bottom:20px` → `26px 28px / 28px` |
| `.chart-box` | `padding:16px 18px; margin-bottom:20px` → `22px 24px / 28px` |
| `.metric-card`（`card-class.css`） | `padding:12px 14px` → `16px 18px` |
| `#sum-strip/#ra-strip .metric-card` | `padding:10px 14px` → `16px 18px` |
| `.metric-strip` | `gap:10px; margin-bottom:16px` → `14px / 22px` |
| `.metric-strip`/`.metric-card` 圆角 | 未动（24px 玻璃规格） |
| `.wear-cards` / `.risk-cards` / `#kreplay-info` gap | `10px` → `14px` |
| `#sum-strip/#ra-strip .metric-card` min-width | `250px` → `280px` |
| `@media(max-width:960px)` 卡片 flex | `1 1 45%` → `1 1 100%` |

### 2.4 图表高度（C3-1/2，统一 +60px）

| 元素 | 现 → 新 |
| --- | --- |
| `#chart-main`（job / lab_result） | `420px` → `480px` |
| `#chart-tags`（job / lab_result） | `420px` → `480px` |
| `#chart-equity`（symbol / lab_symbol） | `260px` → `320px` |
| `#chart-risk-dist` | `240px` → `300px` |
| `#chart-risk-vol` | `240px` → `300px` |
| `#chart-risk-stress` | `220px` → `280px` |
| `#chart-kline`（symbol / lab_symbol 静态） | `460px` → `520px` |
| `klineHeightForPanes()`（`replay.js`） | 无副图 `460` → `520`；有副图 `420+n*160` → `480+n*160` |
| `QRELwcAdapter.klineHeight()`（`kline-lwc.js`） | 同上（两处必须同源） |

重播/静态共用同一公式，`klineHeightForPanes(0)=520 / (1)=640 / (3)=960`，
已写进 `tests/test_saas_replay_tv.py` 等断言，避免两处再次漂移。

### 2.5 ECharts grid（C3-4）

| 图 | 现 → 新 |
| --- | --- |
| `#chart-main` 收益曲线 | `left:55` → `68`（`right:20` 不动） |
| `#chart-equity` 收益曲线（symbol） | 统一后由 `equity-chart.js` 出图，`left:68`（原为 `left:70,right:60` 的双轴布局，B 项删双轴时取消） |
| 回撤图 | `top:'70%'; height:'16%'`（原 symbol 是 `58%/14%`、`74%`） |
| symbol 因子副图（T1 重构后） | `factor-layout.klineGridSpec` 的 `left:16`（副图与主图共用左边界，由 T1 定） |
| `#chart-equity` dataZoom slider | 高度 `18` → `22`（字号变大后 18 太薄） |

## 3. 与任务书不符 / 需要知会的地方

1. **C1 的「现值」不完整**：除 `.wrap`/`.topbar-inner` 的 1280 之外，还有
   ①`style.css` 遗留 `main{max-width:1200px}`、`body{max-width:1200px}`；
   ②SaaS `base.html .container{max-width:1100px}`；③`.topbar`（8081）的固定 32px padding。
   只改 `lab-theme.css` 的 1280 两项，8081 lab 页与 SaaS 仍会有两种内容宽度 —— 已一并改。
2. **`.chart-title` 的实际值不是 13px 而是 14.5px**（lab-theme.css），13px 只存在于
   模板内联。两者都改了：CSS 用相对 +1 → `15.5px`，内联按任务书写 `14px`。
3. **C3-3 的 `flex:1 1 45%` 只在 `card-class.css`** 的 `@media(max-width:640px)` 里，
   `lab-theme.css` 里没有同名规则；已按 C3 要求改成 `1 1 100%`（两处 `#sum-strip`/密集条）。
4. **C3-4 的 `#chart-equity left:70,right:60` 已随 B 项消失**：B 删除双 y 轴后
   由 `equity-chart.js` 统一 `left:68/right:20`。
5. **`.topbar-inner` 是死代码**：lab 页顶栏没有 `.topbar-inner` 包裹层（`.topbar` 直接
   作用在 header 上），改它只对仍用 inner 的页面生效；8081 的 `.topbar` 规则已同步改。
6. **C3-1 里 `#chart-risk-*` / `#chart-tags` 的高度**部分由 JS 在运行时写
   （`el.style.height`、内联模板字符串），只改 HTML 的 `style` 会漏；已同时改 JS。
7. **`#tag-note` 的 12px 未放大**：它是提示类弱化文本，C2 明确「`.opt`/提示类不放大，
   但不得小于 12px」，保持原值。

## 4. 验收（C4）

脚本 `.tmp/size-browser/`：`prepare.py`（无参，用 `uv run python` 生成真实页面快照与
`c_verify.py` 的输入）、`c_verify.py`（Playwright，四视口 × 浅/夜间 × 七页）。

```
uv run python .tmp/size-browser/prepare.py
.tmp/browser-venv/bin/python .tmp/size-browser/c_verify.py
```

结果（`.tmp/size-browser/run_c3.log`）：

```
ERRORS: 无
FAILS: 0
ALL OK 60 runs
```

- 对齐：375px `boxL=0 brandL=12`、1440px `0/20`、1920px `160/180`、2560px `480/500`
  （差值恒等于内容列 padding，符合「brand 左缘 = 内容左边界」的设计）。
- 无横向溢出：四视口 `scrollWidth <= innerWidth`。
- 图表高度实测：`chart-main:h480/L68`、`chart-risk-vol:h300/L55`、
  `chart-risk-stress:h280/L60`。
- 截图：`.tmp/size-browser/screenshots/{path}__{vw}__{theme}.png`，七页 × 四视口 × 两主题。

**踩坑记录（避免复现假验收）**：`prepare.py` 必须用 `uv run python` 跑。用
`.tmp/browser-venv/bin/python` 跑它会缺少项目依赖、静默沿用旧快照，导致
`c_verify.py` 验的是改动前的页面（第一次就是这样「通过」的，页面里还是旧字号）。

**工具限制**：本 agent 没有图像读取能力（无 ReadMediaFile），截图已生成但**未做
人工视觉复核**；C4-3 的「无重叠/无裁切」目前只有自动化断言（溢出、对齐、元素可见性、
高度）+ 轴标签边界框检查支撑，**请验收时人工看一眼截图**。

## 5. 测试

- 全量 `uv run pytest tests/ -q` → 见下方「全量结果」。
- 受影响的既有 JS 沙箱用例（`test_gui_saas_pages.py` / `test_saas_replay_tv.py`）
  已随高度公式更新，无放宽断言。