# 12_UI_STYLE_GUIDE.md — QRE UI 设计系统（8081 lab 冻结版为基准）

> **使用说明（必读）**
> 1. 做**任何**新页面或改页面（8081 lab 侧 / SaaS aguhuice.com 侧）之前，先读完本文档；读完后**不需要再重读源码**去猜风格——本文档是自包含的设计系统蒸馏，所有色值/像素/类名都在此。
> 2. **改动设计规范本身需用户批准**。若发现源码与本文档不一致，以 8081 lab 侧源码为准并修订本文档（同时告诉用户）；SaaS 侧必须与 8081 保持一致。
> 3. 每条规范后括号内标注了对应源码位置（`文件:行号`），供核查，非必读。
> 4. 基准源：`src/quant_research_engine/gui/static/lab-theme.css`（1:1 提取自用户验收定稿 `/home/van/qre-outputs/ui-drafts/synthesis.html`，2026-09-08 定稿冻结）。8080 管理台（style.css + admin.html 等）**不适用**本规范，也绝不可改。
> 5. 性能约束另见 `13_UI_PERF_NOTES.md`（rAF 节流、contain、降采样等约定）。

---

## 0. 文件地图（这套 UI 由哪些文件构成）

| 文件 | 角色 |
|---|---|
| `static/lab-theme.css`（442 行） | 唯一主题文件。设计 tokens + 全部组件样式 + 对 style.css 遗留规则的纠偏 |
| `static/lab-ui.js`（139 行） | 共享交互：PCB 排线、日历弹层、运行流水线步骤态、UTC→本地时间格式化。暴露 `window.LabUI` |
| `static/echarts.min.js` | 本地 ECharts（禁止 CDN），仅图表页引用 |
| `static/style.css` | 8080 管理台旧样式，lab 页面会连带加载，lab-theme.css 尾部（`lab-theme.css:376-442`）负责逐项纠偏 |
| `templates/base.html`（25 行） | 母板：`<header class="topbar">` + `<main>`，lab 各页 extends 它 |
| `templates/lab.html` | 新建策略 + 回测记录（两 tab 同页） |
| `templates/lab_result.html` | 回测结果详情页 |
| `templates/lab_symbols.html` | 个股明细列表页 |
| `templates/lab_symbol.html` | 个股回测详情页 |
| SaaS 侧 `gui/saas/templates/*.html` | 复刻版：base.html 内嵌一份精简 tokens 后**同样引入 `/static/lab-theme.css` + `lab-ui.js`**（`saas/templates/base.html:73`），视觉以 lab-theme 为准 |

**重要现状**：lab_result/lab_symbol 模板头部有一段页面级 `<style>`（如 `lab_result.html:5-58`），是落地早期残留的灰蓝色硬编码（`#2563eb` 蓝、`#e5e7eb` 灰等），其中大部分被 lab-theme.css 后加载覆盖/纠偏。**新代码一律用 lab-theme 的类与变量，禁止再写页面级硬编码颜色**；残留蓝（如 tag-rank 的 `#2563eb` 链接色、`lab_result.html:42-44`）属于已存在瑕疵，不是规范。

---

## 1. 设计 Tokens

### 1.1 色板（`lab-theme.css:5-18`，CSS 变量名即落地名，直接用 var()）

| Token | 色值 | 用途 |
|---|---|---|
| `--paper` | `#FAF9FC` | 页面底色（极淡紫白） |
| `--panel` | `#FFFFFF` | 卡片/表面 |
| `--tint` | `#F1EDF8` | 淡紫区块底（折叠头、chip、区间卡底、行 hover） |
| `--tint-deep` | `#E6DEF3` | 深一档淡紫（滑轨、hover 底） |
| `--lav` | `#6750A4` | **主紫**：主按钮、激活态、选中边框、策略主曲线 |
| `--lav-deep` | `#4A3A78` | 深紫：hover/按下加深、磨损数值、PCB 脉冲、结论强调 |
| `--lav-ink` | `#8B7FBE` | 次级紫：基准虚线、阈值线、内链下划线 |
| `--ink` | `#241F2E` | 正文近黑（带紫相）、toast 底 |
| `--grey` | `#6F6879` | 次要文字、label、表头 |
| `--faint` | `#9A93A6` | 弱化文字、坐标轴、占位、页脚说明 |
| `--line` | `#E4DFEE` | 分隔线/边框 |
| `--up` | `#C93A3A` | **红涨**（A 股惯例：涨/赚/买入 = 红） |
| `--up-soft` | `#FBEFEF` | 红浅底（fail 徽章、危险 hover） |
| `--up-deep` | `#8B1A1A` | 深红（err 文字） |
| `--down` | `#1E8E5A` | **绿跌**（跌/亏/卖出 = 绿）；同时作 ok/成功态文字 |
| `--down-soft` | `#EBF6F0` | 绿浅底（ok 徽章/成功提示） |

图表内补充色（JS 内直接使用，非 CSS 变量）：
- 直方图柱 / 成交量柱 `#B7A6E8`（浅紫）；VaR95 虚线 `#d43030`、VaR99 `#8b0000`；回撤面积 `#d43030`；正态拟合线 `#241F2E`；波动率非当前档 `#D9D2EA`。
- 买卖点：买 `#d43030` ▲、卖 `#1a9e4b` ▼；K 线阳线 `#C93A3A` / 阴线 `#1E8E5A`（`lab_symbol.html:188`）。
- treemap 插值：浅基底 `rgb(245,244,250)` → 深档红 `[201,58,58]` / 绿 `[30,142,90]`，系数 `0.25 + 0.75·(|pnl|/maxAbs)`（`lab_result.html:165-171`）。
- YAML 代码块：底 `#221D2E`、字 `#DCD4F0`、键 `#B7A6E8`、注释 `#7E7595`、值 `#EDE8F8`、行号 `#6E6591`（`lab-theme.css:134,270-275`）。
- 成功/失败提示框边框：ok `#BFE3D0`、err `#F0CACA`（`lab-theme.css:136-137`）。

**语义色纪律（硬规则）**：
- 红绿**只表达涨跌/盈亏/亏损风险**，禁止作装饰、品牌色或普通状态色。运行中状态用紫色呼吸点，不用第三色。
- 交易磨损等中性财务量用 `--lav-deep` 数字 + 双紫横条，不占红绿。
- 全页配色集合 = 淡紫系 + 红绿语义 + 黑白灰，**不得引入第四种色相**（禁橙/蓝；例外是上述已存在的页面级残留，新代码不得效仿）。

### 1.2 形状 / 阴影 / 边框（`lab-theme.css:11,16-17`）

- 圆角阶梯：卡片/普通按钮/输入框 `8~10px`（`--radius:10px`）、入口卡与弹层 `12px`、小按钮 `6px`、徽章/chip/导航胶囊 `999px`。
- 阴影两级，**阴影色一律带紫相**（`rgba(74,58,120,...)`），不用纯黑透明：
  - `--shadow-1: 0 1px 3px rgba(74,58,120,.08)` 静态卡
  - `--shadow-2: 0 8px 28px rgba(74,58,120,.14)` hover/弹层
- 边框 `1px solid var(--line)`；选中态 `inset 0 0 0 1.5px var(--lav)`；focus 环 `:focus-visible{outline:2px solid var(--lav);outline-offset:2px}`。

### 1.3 字体排印（`lab-theme.css:12-14,20,45`）

- 全部系统字体栈，**离线可用，禁止 webfont CDN**：
  - 正文 `--sans`: `"Noto Sans SC",-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif`
  - 标题/大数字 `--serif`: `"Noto Serif SC","Songti SC","STSong","SimSun",serif`
  - 代码 `--mono`: `"SF Mono","JetBrains Mono",Consolas,"Courier New",monospace`
- 用法：品牌名、页面 H1、指标卡大数字用衬线 700/900；正文表格用无衬线；YAML 用等宽。
- 字号阶梯：H1 30px（详情页 22px）/ 区块标题 h2 16px、chart-title 14.5px / 正文 15px / 表格 13.5px（detail-table 12.5px）/ 辅助 `.opt` 12.5px / 坐标轴 10–11px / 指标卡数值 20px（个股页 15px）。
- 数字一律 `font-variant-numeric:tabular-nums`；正文行高 1.65、标题 1.3。
- 全站 reset：`*{box-sizing:border-box;margin:0;padding:0}`——**间距一律由容器控制，不给 h/p 写 margin**（`lab-theme.css:19,387`）。

---

## 2. 布局体系

### 2.1 页面骨架

- `base.html`：sticky 顶栏（60px 高、毛玻璃 `rgba(250,249,252,.92)` + blur(8px)、底边框，`lab-theme.css:26`）+ `<main>` 内容区。顶栏左侧 brand（30px 紫方块 logo + 衬线 18px 品牌名 + 12px 副标），右侧 `.mainnav` 胶囊导航（active = 紫底白字，`lab-theme.css:34-37`）。
- 内容容器 `max-width:1280px; margin:0 auto; padding:32px 32px 80px`（lab 页因无 `.wrap` 包裹层，纠偏直接作用于 `main`，`lab-theme.css:378`）。
- 页面头 `.page-head`：衬线 H1 + 灰字说明段（14.5px、`--grey`、max-width 46em，`lab-theme.css:45-46`）；详情页 H1 降 22px。
- 卡片 `.card` / `.panel`：白底、1px `--line` 边框、圆角 10px、`padding:20px 22px`、`--shadow-1`、卡片间距 20px（`lab-theme.css:47,384`）。
- 图表卡 `.chart-box`：同卡片规范，`padding:16px 18px`（`lab-theme.css:192`）。
- 响应式断点 960px：多列 grid 降为 2 列 / 1 列（`lab-theme.css:310-316`）。
- 使用说明页（2026-10-26 用户批准方向）：桌面 `.help-layout` = 190px 侧栏 + 自适应内容，`.help-side` sticky top 76px；卡片 h2=20px。≤760px 侧栏转静态顶部双列导航，禁止横向溢出。结果页不重复堆「问号 + 说明链接」，仅保留问号悬停提示；结果合同与新旧口径标签不向用户展示。

### 2.2 栅格

- 三入口卡 `.entry-grid`: `repeat(3,1fr)` gap 16px。
- 指标卡 `.metric-strip`: `repeat(6,1fr)` gap 10px。
- 区间信息卡 `.range-strip`: `repeat(5,1fr)` gap 10px。
- 磨损卡 `.wear-cards`: `repeat(5,1fr)`；风险卡 `.risk-cards`: `repeat(4,1fr)`；风险双图 `.risk-grid`: `1fr 1fr` gap 16px。
- 表单 `.form-grid`: `150px 1fr`（label 列固定 150px），`gap:12px 16px`，`align-items:center`（`lab-theme.css:68-69`）。

### 2.3 行内控件等高对齐规范（修过同类 bug，硬规则）

同一行混排的输入框/下拉/按钮必须**同高 36px 且垂直居中**（`lab-theme.css:430-438`）：
```css
.form-grid input[type=text],.form-grid input[type=number],.form-grid select{height:36px;line-height:normal;padding-top:0;padding-bottom:0}
.form-grid .btn-sm{height:36px;display:inline-flex;align-items:center}
```
工具行（`.editor-actions` 等）同理：`height:36px; display:inline-flex; align-items:center; padding-top/bottom:0`。预览栏头部小按钮 30px。**新增行内控件时先查所在行是否已有 36px 约束，没有就加上**。

---

## 3. 组件库

### 3.1 按钮（`lab-theme.css:49-61`）

| 类 | 形态 | 交互 |
|---|---|---|
| `.btn.btn-primary` | 紫底白字，圆角 8px，padding 9px 22px，14px/500 | hover：深紫底 + 浮起 -1px + 紫光阴影 + **斜向高光扫过 0.55s**（仅主按钮有此光泽）；:active scale(.97) |
| `.btn.btn-ghost` | 白底、深紫字、`--line` 边 | hover：紫边 + `--tint` 底 |
| `.btn.btn-danger` | 白底红字浅红边（`#F0CACA`） | hover：`--up-soft` 底 + 红边 |
| `.btn-sm` | 12.5px，padding 4px 12px，圆角 6px，白底灰字 | hover 紫边淡紫底；`.on` = 紫底白字（切换态） |
| `.btn-run-main` | 主按钮加大：宽 100%、16px、padding 14px 22px、圆角 10px | 运行中 `disabled + opacity:.65` |
| `.view-link` | 淡紫描边胶囊链接（次按钮级，"查看结果 →"） | hover 紫底白字浮起（`lab-theme.css:416-417`） |
| `.seg-btn` | 胶囊切换按钮（基准切换、tag tabs） | `.active` 紫底白字（`lab-theme.css:196-198`） |
| `.inl` | 行内链接：紫字 + `--lav-ink` 虚线下划线 | hover 深紫（`lab-theme.css:138-139`） |

所有按钮 `white-space:nowrap`（防窄容器文字竖排，2026-09-26 修过的 bug）。

### 3.2 表单控件（`lab-theme.css:63-72`）

- `input/textarea/select`：1px `--line` 边、圆角 8px、padding 8px 12px、14px；hover 边变 `--lav-ink`；focus 紫边 + `box-shadow:0 0 0 3px rgba(103,80,164,.15)`（不用 outline）。
- 必填星号 `.req` 红色常规字重（400，不加粗）；辅助说明 `.opt` 12.5px `--faint`（**仅为既有遗留定义**）。
- **新 UI 备注硬规则（2026-10-26 用户长期指令）**：新页面或 UI 改动不得新增任何形式的灰色小字号备注，包括 `.opt`、muted/faint 段落与灰色小字行内说明；必要解释统一使用 `tip-trigger` + `data-tip` + `LabUI.helpTips`，支持悬停、键盘聚焦与触摸，不在页面常驻重复说明。
- 单选 `.radio-inline` / `.label-inline`：inline-flex、nowrap、`accent-color:var(--lav)`（原生 radio/checkbox 染紫）。

### 3.3 折叠区（`lab-theme.css:74-81,323-329`）

- `.section-toggle`（或 `.sec-toggle`）：整宽 `--tint` 底按钮 + 紫色小箭头（CSS border 三角，展开 rotate(-45°)→(45°)）。
- 展开动画用 `grid-template-rows: 0fr→1fr`（0.35s），内容包一层 `overflow:hidden` div。**不用 max-height 动画**。
- 规则：可选/高级内容默认折叠，必选直接露出。

### 3.4 三入口卡 + PCB 排线（新建策略页独有）

- `.entry-card`：12px 圆角、padding 20px、flex 纵向、`entry-fit`（适合人群）`margin-top:auto` 贴底保证三卡等高（`lab-theme.css:84-98,423-424`）。hover 浮起 -4px + 阴影升档；选中 = 紫边 + inset 1.5px 紫环 + 右上角对勾圆圈（对勾 scale .3→1 回弹）。
- 三张卡标注适合人群：① 人人可用（自然语言）② 懂指标（快速向导）③ 有经验（YAML）；详情区**单面板随选切换，禁止三面板堆叠**。
- PCB 排线层（`lab-ui.js:9-41`、`lab-theme.css:141-158`）：语义 = "数据从入口流向面板"，**只此一处，禁止蔓延到其他模块**。
  - 形态：直角折线（垂直→水平→45° 斜段→垂直，禁止曲线），线宽 2px；卡出口焊盘 r=4，面板入口共享焊盘 r=6 + 芯点 r=2.4。
  - 状态：未选中 = `#DCD5EA` 虚线（5 5）；选中 = `--lav` 实线 + `--lav-deep` 脉冲段（`pathLength=300`、`dasharray 14 286`、`dashoffset 300→0` 1.5s 线性循环，方向必须卡片→面板）。
  - 切换瞬间一次性 0.5s「通电」紫光闪烁（drop-shadow），随后稳定点亮；旧线熄灭新线点亮。
  - 端点用 `getBoundingClientRect` 实测，resize/load 时重算。

### 3.5 状态徽章与提示框

- `.badge`（`lab-theme.css:173-178`）：12px 胶囊，`.ok` 绿（`--down-soft` 底/`--down` 字/`#BFE3D0` 边）、`.fail` 红（`--up-soft`/`--up`/`#F0CACA`）、`.run` 紫（`--tint`/`--lav-deep`/`--tint-deep` 边）+ **紫点呼吸动画 breathe 1.6s 无限**（opacity .35↔1 + scale .8↔1.15）。
- `.risk-light`：VaR 回测状态灯，`.ok` / `.bad` 两态（同徽章配色，`lab-theme.css:231-234`）。
- `.result-box.ok/.err`：绿/红浅底提示条（编译结果、运行结果，`lab-theme.css:135-137`）。
- `.chart-empty`：空态文案，`--faint` 居中 padding 34~40px。
- `#toast`：底部居中黑底（`--ink`）胶囊，opacity+translate 进场，约 2.2s 自动消失（`lab-theme.css:255-256`）。
- 弹层 `.modal-mask` + `.modal`：半透明紫黑罩 `rgba(36,31,46,.42)`、白卡 12px 圆角 max-width 400px；删除确认的主按钮改红底（`lab-theme.css:248-253`；用法见 `lab.html:299-309`）。删除等不可逆操作**必须二次确认弹层，不用原生 confirm 蒙混**（其他场景 confirm 可接受）。

### 3.6 表格（`lab-theme.css:160-172,352,369-373`）

- `table.tbl`：13.5px、无竖框无斑马纹；表头 `--grey` 12.5px、下边框 2px `--line`；行下边框 1px `#F2EFF7`；行 hover `--tint` 底。
- 数值列右对齐 + tabular-nums（`td.num`/`th.num`）；首列左对齐。
- 涨跌类名 `.pos`（红）/`.neg`（绿）/`.flat`（ink）。
- 可排序列：`th.sortable`，hover 变紫，当前列显示 ▲▼；排序约定 **null 恒排最后、与方向无关**（`lab.html:1674-1685`）。文本列首点升序、数值列首点降序。
- 整行点击跳详情用 `tr.row-link`（行内按钮/链接 stopPropagation，`lab.html:1738-1744`）。
- 明细小表 `.detail-table` 12.5px 全数值右对齐（首列除外）；`.table-wrap{max-height:360px;overflow:auto}` 滚动容器。

### 3.7 日历弹层（`lab-ui.js:47-175`、`lab-theme.css:279-304`）

- 自绘日历（零依赖）：`.cal-pop` 288px 宽白卡弹层；`.cal-day.sel` 紫底白字、`.in-range` 淡紫底、超出 maxDate 的天 `:disabled` 灰 `#D5CFE3`。
- **年→月→日钻取**（QRE-CALENDAR-YEAR-PICKER）：点头部标题 `.cal-title`（年/月/年范围文案随视图切换）逐级上钻——日视图→年份视图（12 年/页九宫格 `.cal-grid-ym` 4 列，前后翻页 ±12 年，标题显示「YYYY – YYYY 年」）→选年进入月份视图（当年 12 个月）→选月回日视图。Esc 逐级返回（年→月→日→关闭弹层），年视图下再点标题直接回日视图；年/月格子用 `.cal-cell`（与 `.cal-day` 同族视觉），选中起/止日所在的年/月 `.sel` 紫底高亮，与选中日一致。头部翻页箭头各视图复用 `.cal-nav`。
- **禁未来函数**：最大可选日 = 数据最近交易日（`/api/admin/refresh` 的 `state.last_data_date`），之后含今天全禁；输入框 readonly，只能点选。可选下界 `minDate`（可选 opts）同样生效：年视图整年超界、月视图整月超界的格子 `:disabled` 置灰禁点，翻页箭头在无可翻内容时禁用。
- 页脚必须注明「数据截至 X（最近交易日），之后日期不可选」；年/月视图追加「Esc 或点标题返回上级」提示。

### 3.8 运行流水线（`lab-theme.css:296-308`、`lab-ui.js:110-126`）

- `.pipe-step` 竖排步骤：圆点 doing = 紫圈呼吸（breathe 1.2s）、done = 实紫点、skip = 灰点、fail = 红点；右侧 `.pipe-st` 小字状态；doing/done 步骤显示进度条 `.pipe-bar`（`--tint-deep` 轨 + `--lav` 填充）。
- 失败时红字 `.pipe-err` 停留定位，不自动消失。

### 3.9 指标卡 / chips / 大入口 / 磨损条

- `.metric`（或母板类 `.metric-card`，已纠偏对齐，`:400-407`）：白卡居中，`.m-label` 12px faint + `.m-value` 衬线 20px 700 + tabular-nums；hover 浮起 -2px；SaaS 可带 `data-tip` 解释口径，由统一提示组件展示。风险区卡片改淡红边 `#F0CACA` + `#FFFBFB` 底。
- `.meta-chips .chip2`：白底 12px 参数 chip（`<b>` 强调值）。
- `.range-strip .metric`：区间卡改 `--tint` 底 + `--tint-deep` 边，与普通指标卡区分。
- `.big-link`：详情页→子页大入口卡（主标题 + 灰字副标 + 右侧 → 箭头，hover 紫边浮起箭头右移 4px，`lab-theme.css:240-245`）。
- 交易磨损条 `.wb-*`：毛收益条 `#8B7FBE` / 净收益条 `#6750A4`，`--tint` 轨 18px 高，宽度按 |值|/max 归一，0.6s 生长动画；结论行「磨损吃掉毛收益 X（Y%）」用 `--lav-deep` 强调（`lab-theme.css:258-267`，渲染见 `lab_result.html:395-428`）。

### 3.10 YAML 预览栏（`lab-theme.css:269-275`）

`pre.compiled-yaml.pv`：深色代码块 + CSS counter 行号 + 简语法高亮（`.yk` 键紫 / `.yc` 注释灰 / `.yv` 值浅紫），max-height 340px 滚动。它是页面**唯一 YAML 真相源**，三个入口产出都汇聚到这里。

### 3.13 说明提示（QRE-SAAS-HELP-COPY-002）

- `LabUI.helpTips()` 在 base 初始化一次，document 事件委托读取 `[data-tip]`，单例 `#qre-help-tip.tip-pop` 用 `textContent` 展示；动态重绘无需 refresh 或逐节点监听。
- 桌面 mouseover 每次均显示、mouseout 关闭；focusin/out 支持键盘；touch/pen pointerup 切换。触摸后 700ms 内忽略兼容鼠标事件，滚动时重新定位而非误关；Esc/外部触摸关闭并清理 ARIA。
- 模块标题使用 `.tip-trigger` 问号按钮；指标卡整卡使用 `data-tip` + `tabindex=0`，不再为每卡额外画问号。提示层 fixed 定位、视口防溢出、`pointer-events:none`，颜色只用既有主题变量。
- 必要权限、错误、动态状态、截断和免责声明保持可见，不得为精简而藏入提示。真实 Chromium 连续悬停与移动 tap 是此类改动的验收硬门槛。
- 回测参数 label 使用 `data-tip` + `tabindex=0` 提供口径/单位/默认值：金额元、比例小数、0/留空规则、共享与批量资金差异；不增加可见灰字，不以 placeholder 替代默认值参数的说明。

### 3.14 自选因子三栏弹窗选择器（QRE-SAAS-FACTOR-PICKER-MODAL，2026-10-25）

- 用途：入口 2（自选因子交易）条件行的因子选择。原一行三个堆叠下拉（大类/子类/因子）
  改为「当前因子选择按钮 + 三栏联动弹窗 + 搜索」，只改 `gui/saas/templates/new.html`；
  8081 lab 侧 `lab.html` 的自有向导副本冻结不动。
- **数据契约（硬规则）**：`.wz-left` / `.wz-rfield` select **不删除、不改类名、不改
  change 监听**，仅追加 `.factor-picker-field` 类并由 lab-theme.css
  `.factor-picker-field select{display:none}` 隐藏，继续作为唯一数据字段。`readGroup()`、
  `snapshotWzArea()`、`usedFactors()`、YAML 预览、固定值切换、策略还原、price basis
  归一一律不因本组件改动。按钮（`.factor-select-btn`）只显示当前「大类 / 子类 / 因子」
  （未选显示「选择因子」）并打开弹窗，**不承载任何策略状态**。最终因子选中后走
  `syncFactorSelect` 写回隐藏 select，再 `dispatchEvent(new Event('change',{bubbles:true}))`
  复用原 change 契约，禁止直接调用刷新函数绕过事件链。
- 结构：`#factor-picker-modal` 复用 `.modal-mask` + `.modal.factor-picker`
  （`role="dialog"`/`aria-modal`/`aria-label="选择因子"`），含 `#factor-picker-close`、
  `#factor-picker-search`、三栏 `#fp-list-group`/`#fp-list-sub`/`#fp-list-factor`、
  搜索结果 `#factor-picker-results`、空态 `#factor-picker-empty`。弹窗复用
  `FACTOR_OPTIONS`/`factorGroups()`/`factorSubs()` 与既有 `/api/saas/factors` 目录加载
  结果，**不新增 API、不加依赖**；目录未就绪（`catalogReady` false）不弹窗，只在
  `#wz-factor-status` 沿用既有错误提示。
- 交互硬规则：点父级只更新下级不改值；Esc、关闭按钮、点遮罩**只关不改值**；打开后焦点
  进搜索框，关闭后焦点回到打开它的那个按钮（直接持有按钮元素，不用
  `document.activeElement`——Safari 点击按钮不自动聚焦）；Tab 焦点锁在弹窗内循环并过滤
  `[hidden]` 容器节点；搜索匹配 label/value/group/sub 并展示完整层级，清空恢复三栏，
  切回三栏必须清空搜索结果容器（否则隐藏残留节点会劫持 Tab 焦点链末位）。
- 视觉：`.fp-item` 选中态 `--lav` 底白字（与 `.cal-day.sel` 同调），列表 `--tint` hover，
  三栏表头 `--tint` 底 + `--grey` 12px；弹层阴影 `--shadow-2`；`:focus-visible` 紫环；
  无新色相、无循环动效。桌面 `max-width:780px`、`max-height:min(600px,calc(100vh - 48px))`。
- 移动端（768px）：`width:calc(100vw - 24px)`、`max-height:calc(100vh - 40px)`、三栏
  `grid-template-columns:1fr` 单列堆叠、`.fp-list{max-height:30vh}` 各自内部滚动；
  按钮 `min-height:44px`（命中 §10 点击目标）且允许折行（`white-space:normal`）。
  真实 Chromium 375px 硬门槛：无页面横向溢出、无 JS error。

### 3.15 因子呈现属性统一协议（QRE-FACTOR-DISPLAY-CONTRACT，2026-10-27）

- `configs/factor_registry.json` 是因子呈现的唯一权威：除中文名/别名外，每个 canonical 必须有 `display.chart_type/panel_id/role/series_type/axis/precision/color/price_basis/render_order`；`gen_factor_registry.py` 负责生成与校验，页面不得各自猜指标类型。
- EMA/均线/BOLL/轨道类一律 overlay K 线主图；MACD/PPO/PVO 同参数 DIF+DEA+HIST 同副图；KDJ/STOCH 等家族同副图；RSI、风险、流动性与 Alpha 默认独立副图。`panel_id` 必须含价格口径，同列不同口径不得共用键。
- `factor-layout.js` 优先消费显式 display；只有旧注册表/旧产物缺 display 时才使用启发式回退。SaaS 因子目录、symbol 静态图与重播必须同源，禁止把 EMA 错放到独立指标 DIV。
- 呈现协议与夜间模式正交：主题切换只改颜色，不改 panel/role/series 或数据。修改图表时必须回归 EMA overlay、MACD 同面板、不同口径不串键与 375 无横溢。

---

## 4. 图表规范（ECharts）

- **选型**：ECharts（本地 `static/echarts.min.js`，禁 CDN）。仅结果页/个股页引用；lab.html（新建+记录页）无图表不引。
- **通用约定**：`animation:false`（所有图，入场无描画动画）；`tooltip.trigger:'axis'`；多 grid 时 `axisPointer.link` 联动所有 x 轴；缩放 = `dataZoom:[{type:'inside'},{type:'slider',bottom:6,height:22}]`；容器显式高度（主图 420px、风险子图 220–240px、K线 460px 起）；`resize` 监听调 `chart.resize()`；销毁用 `chart.dispose()`（重渲染前 dispose 旧实例，见 `lab_result.html:510-511`）。
- **系列配色（硬规则）**：
  - 策略净值/主曲线：`#6750A4` 实线 2px（`lab_result.html:663`）
  - 基准：`#8B7FBE` 虚线 1.5px（`:749`）；个股页的「持有到期」对比线 `#9A93A6` 虚线（`lab_symbol.html:294`）
  - 回撤子图：`#d43030` 面积 0.35 透明（`lab_result.html:669`）
  - 直方图 `#B7A6E8`、正态拟合 `#241F2E` 虚线、VaR95/99 markLine `#d43030`/`#8b0000` 虚线
  - 波动率状态柱：当前档 `#6750A4`、其余 `#D9D2EA`
  - 压力测试：区间累计损失 `#d43030`、窗口最大回撤 `#8B7FBE`
  - K线：阳 `#C93A3A` / 阴 `#1E8E5A`；买 ▲ `#d43030` 贴最低价×0.99，卖 ▼ `#1a9e4b` 贴最高价×1.01（triangle / triangle+180°，size 10，hover tooltip 显示下单明细）
  - 因子副图线 `#6750A4` 1.2px，阈值 markLine `#8B7FBE` 虚线
- **策略结果主图结构**：双 grid（净值 52% + 回撤 16%，无回撤数据时单 grid 72%）+ 基准切换 seg 按钮组（纯前端切换 + "无基准"选项）+ **区间信息卡五卡**（区间策略收益/区间基准收益/区间超额/区间最大回撤/交易日数），监听 `datazoom` 事件用 **rAF 节流**重算（`lab_result.html:732-737,755-795`；区间收益口径 = 首末净值比 `(1+r₁)/(1+r₀)−1`）。信号散点不画在主图（交易多时糊住曲线，已决策，`lab_result.html:665`）。
- **treemap 归因热力图**：`type:'treemap'`，`roam:false, nodeClick:false, breadcrumb.show:false`，白边 2px + gap 2px；面积 ∝ |总净盈亏|，颜色红赚绿亏按 `pnlColor()` 插值；**面积三级显隐**：>4% 名称+数值 / >1.1% 仅名称 / 其余纯块 hover 看 tooltip；只铺前 20 个（超出在 note 注明"完整见下表"）；点击矩块或排行表行下钻个股贡献表，再点收起；点空白处收起（用 `getZr().on('click')` 且**绝不能 `zr.off('click')`**——会拆掉 echarts 内部事件桥，`lab_result.html:215-217`）。
- **K 线图结构**：grid 数 = 2（K线 58%/42% + 量 14%/10%）+ 每因子一副图；摆动指标（RSI 等）**不做价格叠加**（量纲不同，已决策，`lab_symbol.html:216-218`）。

---

## 5. 动效规范

统一缓动 `--ease: cubic-bezier(.22,1,.36,1)`；回弹缓动 `cubic-bezier(.34,1.56,.64,1)`（brand mark、对勾、徽章入场）。

| 场景 | 参数（出处） |
|---|---|
| 视图切换 | `viewIn` opacity 0→1 + translateY 10px→0，0.45s（`:41-42`） |
| 面板/区块切换 | `panelIn` 同上幅度 8px，0.3–0.35s（`:100-101`） |
| hover 浮起 | translateY(-1~-4px) + 阴影升档，0.2–0.25s |
| 按压 | `:active` scale(.97~.985) 瞬时 |
| 主按钮光泽 | 斜向高光扫过 0.55s（仅 `.btn-primary`） |
| 运行中呼吸点 | `breathe` 1.6s（徽章）/ 1.2s（流水线点）无限 |
| 折叠区 | grid-template-rows 0fr↔1fr，0.35s |
| PCB 脉冲 | dashoffset 300→0 1.5s 线性无限；切换通电闪 0.5s 一次 |
| 磨损条生长 | width 0.6s |

**硬规则**：
- `prefers-reduced-motion` 下所有 animation/transition 压到 0.01ms；PCB 脉冲与通电闪烁单独关闭，但**保留点亮/熄灭的静态区分**（`lab-theme.css:43,158`）。
- 克制原则：纯展示区块（静态表格、说明文字、空态）不加循环动画；除呼吸点、PCB 脉冲外**不允许无限循环动效**；ECharts 图 `animation:false`。
- ECharts 以外的 DOM 高频更新（滑块/缩放联动）一律 rAF 节流。

---

## 6. 降级语义与数据真实性（硬规则）

1. **数据缺失 → 模块整块隐藏，不留空壳**：无 fees 数据 → 交易磨损卡 `display:none`（`lab_result.html:398`、`lab_symbol.html:132`）；无风险报告 → FRM 区显示「生成风险报告」按钮或跳过说明，不放假数据。
2. **序列缺失 → 图例/卡片同步隐藏**；图容器空态用 `.chart-empty` 文案（如「暂无分布数据」）。
3. **样本截断 → 明确标注口径**：「热力图仅显示前 20 个，共 N 个」「已过滤 X 个无效关键词」「带 ·通用 后缀的为通用行业」（`lab_result.html:196-207`）。
4. **禁止编数、禁止占位假图**：页面所有数值必须来自真实 API；mock 仅限流程交互且必须文案明示；接口给不出的总量不许推算冒充。
5. **情景未覆盖 → 显示跳过说明**：压力测试 note「以下情景回测区间未覆盖，未参与：…」（`lab_result.html:617-619`）。
6. **报错友好化**：fetch 失败/超时显示中文错误 + 重试按钮（`lab.html:1648-1652`）；JSON 解析失败显示 HTTP 状态码而非原始报错。
7. 时间戳：后端存 UTC，前端一律 `LabUI.fmtLocalTime()` 转本地时区显示（`lab-ui.js:130-136`）。

---

## 7. 禁链与文案纪律（硬规则）

- **SaaS 页面禁止出现指向内网/管理端的任何链接或字样**：`/admin`、`factor-admin`、`factor-create`、`8080`、`8081` 均不得出现在 SaaS 页面 HTML 中——**包括 HTML/JS 注释**（断言测试 `tests/test_gui_saas_pages.py:211-218` `TestNoAdminLinks` 逐页扫描）。曾在注释里写「8081」撞线两次，写注释时用「lab 版」代称。
- 可见文案禁用内部术语「沙箱/晋升」，面向用户说「小范围验证/正式回测」；「冒烟测试」一词已获用户批准可出现在流水线文案。
- 日期截止相关的所有选择控件必须对齐数据最近交易日（禁未来函数），见 §3.7。
- 路由/交互完整性：所有按钮链接必须有真实响应，禁止死按钮；未实现的能力给 toast 或文案说明。

---

## 8. 页面级固定结构

- **新建策略页**（lab.html）：page-head → 三入口卡 → PCB 排线 → 单详情面板 → 共用回测参数区（必选只露 策略 ID/回测区间/标的范围，其余收「高级参数」折叠区；内部工程参数 hidden）→ 策略代码预览栏（唯一 YAML 真相源）→ 唯一「运行回测」流水线卡（校验→冒烟→全量）。「我的策略」面板 hidden 保留。
- **回测结果页**（lab_result.html）固定模块顺序：结果概述（简介可折叠 + meta chips + 6 指标卡）→ 收益曲线（基准切换 + 缩放 + 区间五卡）→ 交易磨损（无数据整块隐藏）→ FRM 风险 → 归因热力图（行业/关键词/动态标签三层 tab + 最好/最差切换 + 排行表 + 下钻）→ 「查看个股回测明细 →」大入口卡 → 底部辅助链接行。
- **个股明细列表页**（lab_symbols.html）：page-head → 单卡片（工具行：搜索框 + 计数提示；全列可排序大表；点行进个股详情；完整代码回车直跳）。
- **个股详情页**（lab_symbol.html）：概述 7 指标卡 → 收益曲线（净值 vs 持有到期 vs 基准 + 区间五卡）→ 交易磨损 → K线+买卖点（+因子副图）→ 交易明细 → 下单记录 → 失败订单。页头顶部与底部均有返回链接。

---

## 9. SaaS 侧复刻约定

- SaaS 模板（`gui/saas/templates/`）**不复制主题代码**：base.html 内嵌一份极简 tokens 兜底后，直接 `<link href="/static/lab-theme.css">` + `<script src="/static/lab-ui.js">`（与 lab 同源，静态文件由同包 static 目录伺服）。视觉类名与 lab 完全一致（`.card` `.btn-primary` `.badge.ok/run/fail` `.metric-strip` `.page-head` 等）。
- SaaS 特有元素复用既有类：游客提示条 `.guest-strip`（`lab-theme.css:441-442`）、job 状态徽章映射 queued/running→`.run`、completed→`.ok`、failed/canceled→`.fail`。
- 对齐方法（历次 UI 对齐任务的做法）：8081 截图作基准 → SaaS 对应页截图 → 逐项 diff → 只改 SaaS 侧模板呈现层，数据接口零改动。**8081 lab 侧代码冻结，绝不许为了迁就 SaaS 改它。**

### 3.11 回测重播组件（`replay.js` + `lab-theme.css` .rp-* 族，2026-10-04，2026-10-04 接管模式修订）

- 共享组件：`static/replay.js`（saas/lab 同源），切片1 job.html 策略级重播首发，
  切片2 symbol.html K线级复用。API：`QREReplay.core`（纯逻辑：binEvents/
  positionCounts/nextEventfulCursor/frameMetrics）+ `QREReplay.attach(mountEl, opts)`。
- **接管模式（2026-10-04 用户拍板，替代独立重播卡）**：点「重播」后接管原图表容器
  渲染重播帧——`opts.chartEl` 传原容器（组件先销毁静态实例防 dataZoom/legend 残留），
  控制条插在卡片内插槽 div；「退出重播」调 `destroy(keepDom=true)`（只撤控制条/日历、
  dispose 图表）后由页面用内存数据重建静态全量渲染。**禁止再新建第二个同内容图表模块。**
  接管期间隐藏冲突的静态交互（job 页隐藏基准切换与区间卡；退出恢复）。
- 渲染红线（不可违反）：全量数据内存持有，每帧只把 `[0, cursor]` 截断喂 ECharts
  （未来数据天然不可见）；setOption 走 rAF 节流（~16ms 帧预算）；主轴=净值/行情序列
  交易日，事件按日归箱对齐。
- 时序红线：信号日 T（成交日前一交易日，淡紫小点「信」）与成交日 T+1（实心
  「入」红/「出」绿 pin）相隔呈现，不得神化策略时序；控制区固定口径文案与免责声明。
- 控制条族：`.rp-bar`（播放/暂停 `.rp-play` 主紫、单步、速度 1/2/5/10 `.rp-sel`、
  起始日 `.rp-date` 复用 LabUI.attachCalendar、可拖进度 `.rp-slider` accent 主紫、
  空仓快进）；事件流 `.rp-ev-day`/`.rp-ev-chip`（同日同类 >5 聚合可展开）；
  指标面板 `.rp-metrics`（auto-fit minmax(110px) 卡族），峰值刷新
  `.rp-peak-flash`（淡紫边+晕，无新色相）。
- **交互打磨硬规则（2026-10-04）**：图标一律内联 SVG + 可见文字标签（禁 emoji、
  禁无标签纯图标钮，辅助控件补 title/aria-label）；可点元素 cursor:pointer +
  hover 淡紫反馈；`:focus-visible` 紫环不许去；transition 150–300ms（本组件 0.2s）；
  `prefers-reduced-motion: reduce` 下弹入动画/峰值闪烁/按钮过渡全关；
  按钮 36px 等高（§1 行内控件规则）、8px 间距网格。
- **布局规则（2026-10-04 布局调整 + 根因修复）**：控制排分两个语义分组——
  `.rp-group-main`（播放/暂停、单步、速度档，`flex-wrap:nowrap` **恒同排**，不靠
  flex-wrap 宽度运气）与 `.rp-group-aux`（起始日、空仓快进、帧计数，允许折行）；
  **进度条不放控制排**，经 `.rp-slider-row` 置图表容器正下方一行（视觉从属于图表；
  接管模式 insertAfter chartEl，自建模式紧随 chartEl）。移动端辅助组可折行，
  主控组始终同排。⚠️ 组件内 `<select>` 必须显式宽度（`.rp-sel{width:auto}`）——
  base.html 有全局 `input,select,textarea{width:100%}`，不显式豁免就独占整行
  （2026-10-04 换行 bug 根因）；行内控件 36px 等高同样适用于 select。

### 3.12 长等待模态遮罩（`wait-mask.js` + `lab-theme.css` .wm-* 族，2026-10-04）

- 用途：NL 编译 / 运行回测等长等待期间锁页面防误点与重复提交。API：
  `LabUI.waitMask.show/update/hide/isOpen`（base.html 全站引入，任意页面可复用）。
- 结构：半透明深色背板（rgba(36,31,46,.48)）+ 居中淡紫卡片（`.wm-card`，
  spinner `.wm-spin` + 标题 `.wm-title` + 副文案 `.wm-sub` + 按钮排 `.wm-btns`）。
- 硬规则：显示期间**禁 ESC 关闭、禁背板点击关闭、页面交互全锁**（`.wm-lock`
  禁滚动 + 背板物理拦截）；z-index **95**（高于 `.modal-mask` 80 / cal-pop 60，
  低于 toast 99）——与其他弹层并存时必须显式管理（如大范围耗时护栏：先关遮罩
  再弹护栏，确认后重开）；分流按钮出现时 spinner 停转（等待语义交还用户）；
  触发按钮同步 disabled 防重复提交。
- 两段式范式（运行回测）：等待段「冒烟校验中…」→ 提交成功「已提交，排队执行中」
  +「后台运行 / 继续等待」分流按钮；`keepMask` 按钮只保持遮罩，onClick 必先执行。
- 打磨：focus-visible 紫环、0.2s 过渡、prefers-reduced-motion 下 spinner 动画关闭
  （静态降级）、768px 卡片自适应 + 按钮堆叠 44px。
- 扩展选项（切片2 引入，向后兼容）：series `type`/`extra` 透传任意 ECharts 序列
  （candlestick/bar/scatter）；事件可带 `ev.price` 真实成交价定位；`opts.initialCursor`
  （窗口起播，如近 2 年）；`opts.height`；yAxes `pct:false`（价格/量/因子轴不加 %，
  收益率轴默认 %）。侧边信息卡经 `onFrame(cursor)` 钩子渲染（如 K线页 OHLC/因子值/
  持仓浮动盈亏），组件不感知业务口径。
- 移动端：768px 断点 `.rp-chart` 320→260px、控制条折行、事件日期列收窄。
- 一致性要求：播放到最后一帧的指标值必须等于页面静态报告值（Playwright 断言校验，
  见 04 号 QRE-SAAS-REPLAY-S1 条目）。

---

## 10. 移动端适配规则（QRE-SAAS-MOBILE-ADAPT，2026-10-04）

适用范围：SaaS 公网页面（new/records/job/symbol/login/profile/feedback/factor-request）；
console 管理台为本地桌面工具，不做移动端。改动全部集中在 `saas/templates/base.html`
内嵌样式块末尾的 `@media (max-width:768px)` 移动端规则块，桌面端渲染零改动
（1280px 回归截图对比确认）。

落地规则（手机视口 375×812 实测口径）：

- **断点**：移动端主断点 **768px**（新规则块）；既有 960px 断点（lab-theme.css:318-325
  多列降 2 列、base.html 顶栏缩小、sidenav 移左下）保留不变。960 管「窄桌面/平板」，
  768 管「手机」。
- **横向滚动红线**：页面级 `scrollWidth > clientWidth` 视为 bug；审计脚本逐页探针
  （`.tmp/mobile-audit/audit.js`，Playwright 375×812 + isMobile/hasTouch）。
- **表格**：`.tbl` / `.detail-table` 移动端 `display:block; overflow-x:auto`（块级横滚，
  表头随内容横向滑动，页面不整体横滚）；不做卡片化改写。
- **长文本 chip**：`.meta-chips .chip` 取消 `white-space:nowrap` 允许折行（费率/区间
  长 chip 在 375px 下原样溢出）。
- **点击目标 ≥44px**：`.mainnav a` / `.sidenav` / `.tab` / `.btn` / `.btn-sm` / `button` /
  `.bench-bar button` / `.tag-tabs button` 统一 `min-height:44px`；日历格子
  `.cal-pop .cal-day/.cal-cell` `min-height:40px`、翻页钮 `.cal-nav` 40×40
  （弹层内密度优先，40px 妥协值）。例外：logo 链接、纯文本行内链接不强制。
- **输入控件**：`input/select/textarea` `font-size:16px; min-height:44px`——16px 是
  iOS Safari 聚焦不自动放大的阈值；桌面端 36px 等高规则（§1）不变，移动端 44px 优先。
  checkbox/radio 例外。
- **交易磨损块**（job/symbol）：`.wear-cards` 5 列降 2 列；`.wb-row` 改
  `grid-template-columns:96px 1fr auto`（`.wb-label`/`.wb-val` 取消固定 170/190px，
  val 11px 上限 140px）。⚠️ lab-theme.css 在 base.html 内嵌样式**之后**加载，同优先级
  规则会被覆盖——移动端覆盖必须用更高优先级选择器（`.chart-box` 前缀）或 ID 选择器
  （同 §9 既有约定；本次初版用裸类名被静默压掉，探针复核才发现）。
- **指标卡**：`.metric-card` min-width 110→96px；`.page-head h1` 降 22px。
- **图表**：ECharts 容器宽度自适应既有实现（chart-box 100% 宽）已达标，未改。
- **顶栏**：960px 断点既有单行精简（logo 30px + 导航 12.5px）实测 375px 单行不折行，未加汉堡。

审计结论（修复前 → 修复后，375px）：records/profile/login 页级横滚（记录表 712px）→
表内横滚；job 页横滚 625px（费率长 chip + 磨损 5 列卡 + 磨损条固定宽）→ 零横滚；
symbol 页 571px（同上 + 交易明细表 517px）→ 表内横滚；new/feedback/factor-request
原本无横滚（YAML 预览行内滚动属容器内行为）。全部页面 JS 零报错。

---

## 11. 夜间模式（QRE-SAAS-NIGHT-MODE，2026-10-27）

适用范围：全部 SaaS 公网页面（new/records/job/symbol/login/login_callback/help/profile/feedback/factor-request）与 9090 console 管理台，共用同一套开关。**浅色主题的 tokens、配色、字体、排版、间距、布局、组件形状、动效、文案、数据一律不变**；lab 侧 8080/8081 页面不引入本机制。

### 11.1 夜间 tokens（`static/night-mode.css:6-23`，`[data-theme="dark"]` 覆盖）

| Token（任务名） | 色值 | 落地变量名 | 用途 |
|---|---|---|---|
| bg | `#17153B` | `--bg` / `--paper` | 页面底色、顶栏、滚动条轨道 |
| card | `#2E236C` | `--card` / `--panel` | 卡片/面板/图表容器 |
| line | `#433D8B` | `--line` / `--tint-deep` | 边框、分隔线、滚动条滑块 |
| text | `#F1EDF8` | `--text` / `--ink` | 正文、标题 |
| muted | `#C8ACD6` | `--muted` / `--grey` / `--faint` | 次要文字、坐标轴、占位 |
| accent | `#7E60BF` | `--accent` | 夜间交互主色（次按钮 hover/focus 辅助） |
| accent-deep | `#C8ACD6` | `--accent-deep` / `--lav-deep` | 链接、强调文字、可读性优先的强调色 |
| accent-soft | `#2E236C` | `--accent-soft` | 淡紫底替代（与 card 同值，夜间不再叠加第三层紫） |

派生覆盖（同样只在夜间生效）：`--lav:#9B84D8`（主紫按钮/主曲线在深底上提亮）、`--lav-ink:#A99BD8`；`--tint:#3A3170`（折叠头/chip/行 hover 底，比 card 亮一档）；`--field:#241E52`（输入框/`option`/代码块底，比 card 暗一档）；`--up:#FF7A7A` / `--up-soft:#3A2030` / `--up-deep:#FF9B9B` 与 `--down:#4FD69A` / `--down-soft:#17342A`（红涨绿跌**只提亮不改色相**，见 §11.3）；`--shadow-1/--shadow-2` 改纯黑半透明（深底上紫相阴影不可见）。

### 11.2 生效机制

- **浅色不动原则**：`night-mode.css` 所有规则都带 `:root[data-theme="dark"]` 前缀，浅色下零命中；`night-mode.js` 在浅色下除写 `data-theme="light"` 外不改任何既有配置。base.html 的浅色 `:root` token 块未改一行（`git diff` 复核）。
- **优先级**：模板内联 `<style>` 在 `lab-theme.css` 之前、`night-mode.css` 在两者之后加载，且夜间规则带属性前缀，天然压过同族裸类名规则——不需要给既有选择器加 `!important`（`#guest-note` 是唯一例外，见 §11.5）。
- **防首帧闪白（FOUC）**：`base.html` / `login_callback.html` 在 `<head>` 的 `theme-color` meta 之后放内联脚本，同步读 `localStorage('qre-theme')`（非法值忽略）→ 无存储值时读 `prefers-color-scheme` → 立即写 `documentElement.dataset.theme`，早于样式表渲染首帧。
- **持久化与系统偏好**：键名 `qre-theme`，值仅 `dark` / `light`。用户未点过开关时**不写** localStorage，跟随系统偏好（`matchMedia('(prefers-color-scheme: dark)')` 的 `change` 事件也跟随）；点过之后以存储值为准。
- **meta theme-color**：浅色 `#4A3C78`、夜间 `#17153B`，随主题切换同步改 `content`（移动端浏览器地址栏/状态栏一致）。
- **切换按钮**：`.tt-btn`（顶栏 `</nav>` 前，`type="button"`，带可见文字「夜间模式/日间模式」+ `aria-pressed` + `aria-label="…（切换配色）"`）；login_callback 等无顶栏页面用 `.tt-btn.tt-float`（右下角浮动，≤768px 收 12px）。JS API：`window.QRETheme = {current, set, toggle, themeChart}`，切换时派发 `qre:themechange` 事件。
- **移动端**：开关不额外占行，375px 无横溢（审计脚本逐页验）；按钮点击目标与 §10 的 44px 规则一致。

### 11.3 红涨绿跌（夜间）

红绿语义不变、**色相不变，仅提亮保证深底可读**：涨/赚/买 `#C93A3A → #FF7A7A`，跌/亏/卖 `#1E8E5A → #4FD69A`（浅底/徽章底同步改 `#3A2030` / `#17342A`）。图表内散点、K 线阴阳、treemap 红绿插值、回撤面积等由 `themeChart` 的浅色 patch 只做**中性色替换**，红绿系列色不动（见 §11.4）。禁止在夜间引入第四种色相或把红绿对调。

### 11.4 ECharts 接入约定（`night-mode.js` `themeChart`）

- 接入方式：图表 `echarts.init(el)` 后包一层 `QRETheme.themeChart(chart)`——它把实例的 `setOption` 记在 `__qreOrigSetOption` 上并替换为「每次调用先注入主题 patch、再调原方法」，因此**每次重绘（含重播逐帧 setOption）都自动带上夜间配色**，页面无需在每次渲染时判断主题。现有接入点：job.html 主图/标签 treemap/风险子图、symbol.html 两图、`replay.js` 重播实例。
- patch 范围（`applyNeutral`）：`backgroundColor` 恒设；仅深合并**已存在**的 `textStyle` / `legend` / `tooltip` / `xAxis` / `yAxis`（缺省字段不凭空造，避免改变浅色布局）。夜间取值：背景 `#17153B`（透明容器则保持 `transparent`）、轴线与轴线 `#C8ACD6`、轴标签/图例 `#C8ACD6`、tooltip 底 `#2E236C` + 边 `#433D8B` + 字 `#F1EDF8`。
- **只改色不重算**：不碰 `series` 的坐标、数值、轴区间、grid 尺寸、`dataZoom`——主题切换不得引起布局抖动或数据变化；切回浅色时恢复 ECharts 默认轴色 `#6E7079`。
- treemap 无坐标轴（`axis` 恒空），审计判据按「含笛卡尔系序列才断言轴色」处理。

### 11.5 已知刻意保留项

- `#guest-note`（游客提示条）：夜间保留深色告警样式（边 `#B4761F`、底 `#3D3118`），属「提醒」语义色，不并入紫系；这是唯一带 `!important` 的夜间规则（`night-mode.css:265`）。

---

## 变更记录

- 2026-10-27（QRE-SAAS-NIGHT-MODE）新增 §11 夜间模式规范：SaaS 全部页面（含 9090 管理台）追加可切换深色主题，**浅色 token/配色/视觉/排版/文案/数据零改动**，唯一新增交互是顶栏 `.tt-btn` 主题切换按钮。实现为三个新/改文件：`static/night-mode.css`（深色 token 覆盖 + 组件族深色规则，仅 `[data-theme="dark"]` 作用域）、`static/night-mode.js`（`QRETheme`：浅色不写 storage、`prefers-color-scheme` 跟随、手动选择落 `localStorage('qre-theme')`、`meta[name=theme-color]` 同步、`themeChart` 图表配色注入）、`saas/templates/base.html` 4 处挂载（防 FOUC 内联脚本 + css + js + 按钮）。夜间色板固定 8 token（bg `#17153B`/card `#2E236C`/line `#433D8B`/text `#F1EDF8`/muted `#C8ACD6`/accent `#7E60BF`/accent-deep `#C8ACD6`/accent-soft `#2E236C`）；红涨绿跌只提亮不断语义；ECharts 每次 `setOption` 前注入背景/轴/文字/tooltip/品牌紫，不重算布局与数据；375px 零横溢、按钮带文字与 `aria-pressed`。`#guest-note` 深色告警（`#B4761F` 字 / `#3D3118` 底）刻意保留。
- 2026-10-26（QRE-SAAS-CLASSIC-ACTIONS-UI）新增结果操作卡与经典策略 CTA 两条局部规则族（无新色相/组件/动效，仅追加于 `lab-theme.css` 末尾）：**结果操作卡**——job「下一步」与「分享结果」合并为 `#result-actions-card`（标题「结果操作」+ 问号提示），内部两组 `.result-action-group`；按钮行 `.result-action-buttons`（flex、gap 10px、wrap、居中，`.btn` min-height 44px）；保存/确认信号=`btn btn-primary`、提示信号/分享=`btn btn-ghost`；`#action-status`/`#share-status` 类改 `.result-action-status`（13px `--ink` 正常可读状态文本，不用 `.opt` 灰字）；信号面板「T+1 参考/风险提示」移入「扫描范围」标签旁 `.tip-trigger`（`.result-action-scope`），radio/select/ID/scope 值不变；新增空安全 `syncResultActionCard()`（任一组非 hidden 才显示外层，游客/showcase/分享只读整体隐藏），init 两函数全分支同步、不重复绑定。**经典策略 CTA**——showcase 底部卡 `.showcase-cta`（flex wrap、h2 右推、主按钮 min-height 44px），页头备注移入 H1 旁问号提示。≤768px：CTA 纵排全宽、操作按钮 `flex:1 1 auto` 居中；375px 零横溢经真实 Chromium 验证。
- 2026-10-25（QRE-SAAS-RESULT-UNDERSTANDING）新增 `static/lab-theme.css` 两条帮助页专用规则（无新色相/组件/动效）：`.help-sec{scroll-margin-top:76px}`（`/saas/help` 锚点小节避开 60px sticky 顶栏）与 `.help-jump`（页首锚点跳转胶囊，`--tint` 底 + `--tint-deep` 边 + hover 主紫反白，复用既有 token）。帮助页本体 `gui/saas/templates/help.html` 只用既有 `.page-head`/`.card`/`.tbl`/`.inl` 类；结果页各模块「说明 →」为 `.inl` 行内链接；SaaS 顶栏导航增至 5 项，`base.html` ≤400px 断点补 `header.topbar .mainnav{gap:0}`（lab-theme `.mainnav{gap:4px}` 后加载，须 `header.topbar` 前缀提优先级）+ logo 24px + 链接 11.5px，保证 375px 单行不折行。
- 2026-10-25（QRE-SAAS-FACTOR-PICKER-MODAL）新增 §3.14 自选因子三栏弹窗选择器：入口 2 条件行三个堆叠下拉改为「按钮 + 三栏弹窗 + 搜索」；`.wz-left`/`.wz-rfield` select 降级为隐藏数据字段（`.factor-picker-field select{display:none}`）但仍是唯一值来源，YAML/快照/固定值/策略还原/price basis 零改动；弹窗复用 `FACTOR_OPTIONS` 与既有目录加载，不新增 API 与依赖；Esc/遮罩/关闭按钮只关不改值、焦点进搜索并归还原按钮、Tab 焦点锁；样式复用既有 modal 与紫色主题变量，768px 三栏降单列 + 视口限高。改动集中在 `gui/saas/templates/new.html` 与 `static/lab-theme.css`（移动端规则随组件放 lab-theme.css，因 base.html 无同族竞争规则），8081 lab 侧零改动。
- 2026-10-25（QRE-GUI-FACTOR-REGISTRY-001）§3.14 自选因子三栏弹窗选择器补充**中文优先展示规则**：因子按钮、三栏列表与搜索结果一律以注册表中文名（`zh`）为主文案，价格口径（收盘价/典型价/均价）以「（口径）」后缀同屏显示，canonical `schema.table.column` 放进按钮 `title` 作悬停辅助对照（不占主文案、不进列表正文）；注册表未维护中文名的条目 `zh` 为 null，前端回退既有 `label`，**不得显示空文案**。子类栏在原有表名/分段键之上显示「大类(口径)」（数据键不变，仅换展示文本），因此同名列的不同价格口径在按钮、子类栏与搜索结果中都可区分。搜索匹配范围扩展到中文名、canonical、列名、全部别名与大类/子类（小写包含匹配），空态与「切回三栏即清空搜索结果」的既有规则不变。样式零新增（无新色相、无新组件），仅 `gui/saas/templates/new.html` 与 `gui/factor_wizard.py` 的目录数据结构；8081 lab 侧零改动。
- 2026-10-04（QRE-SAAS-WAIT-MASK + REPLAY-LAYOUT）新增 §3.12 长等待模态遮罩组件规则（禁 ESC/背板/全锁、z-95、两段式分流范式、keepMask 语义）；§3.11 补布局规则（倍速与播放同排、进度条置图表正下方 .rp-slider-row）。
- 2026-10-04（QRE-SAAS-REPLAY-POLISH）§3.11 修订：重播改**接管模式**（接管原图表容器，禁第二模块，退出内存重建静态）+ 交互打磨硬规则（SVG 图标+文字标签、hover/focus-visible、150-300ms、prefers-reduced-motion 降级、36px 等高 8px 网格）。
- 2026-10-04（QRE-SAAS-REPLAY-S1）新增 §3.11 回测重播组件规则：static/replay.js 共享组件（core 纯逻辑 + attach UI），[0,cursor] 截断渲染/rAF 节流/时序 T 与 T+1 相隔三条红线，.rp-* 控制条与事件流族（淡紫 tokens 无新色相），768px 断点折行，末帧指标=静态报告强一致性（Playwright 断言）。
- 2026-10-04（QRE-SAAS-MOBILE-ADAPT）新增 §10 移动端适配规则：768px 主断点、表格块级横滚、长 chip 折行、点击目标 ≥44px（日历格子 40px 妥协）、输入控件 16px/44px、磨损块 2 列+grid 三段、lab-theme 后加载需高优先级选择器覆盖的踩坑。改动全部在 saas/templates/base.html 内嵌样式块；本条为「记录实际落地规则」，经用户任务书批准。
- 2026-09-28（QRE-CALENDAR-YEAR-PICKER）共享日历组件（`lab-ui.js` attachCalendar，8081 lab 与 SaaS 同源）新增**年→月→日钻取**：点头部年月标题（新 `.cal-title` 按钮）进入年份视图（12 年/页九宫格 `.cal-grid-ym` 4 列 + `.cal-cell` 格子，翻页 ±12 年），选年进月份视图（12 个月），选月回日视图；Esc 逐级返回（年→月→日→关闭），年视图再点标题回日视图。年/月格子超 [minDate,maxDate] 范围 `:disabled` 置灰禁点（minDate 为新增可选 opts，未传则仅 maxDate 约束，调用方零改动）；选中起/止日所在年/月 `.sel` 紫底高亮与选中日一致（`.cal-cell.sel` 复用 `--lav`）；页脚数据截至提示不变，年/月视图追加「Esc 或点标题返回上级」。样式全部落在 `lab-theme.css` cal-pop 组件族（新增 `.cal-title`/`.cal-grid-ym`/`.cal-cell` 三条规则，无新色相、无循环动效）。lab/SaaS 模板零改动。
- 2026-09-28（QRE-SAAS-EXPOSURE-METRICS）SaaS 详情页区间信息卡新增 2 张随滑块联动指标卡（第 6/7 张，job.html 与 symbol.html 同步）：**持仓暴露度**（有持仓交易日数 ÷ 区间交易日数，同日多笔按 1 天去重；数据源 = 结果已有 round trips 的 entry/exit 日期展开成逐日持仓掩码，job 级用 chart_data.trades.points，>500 笔 sampled 时悬停提示「按前 500 笔估算」，symbol 级用 d.trades 全量）与**持仓期年化收益**（(1+区间策略收益)^(252/持仓天数)−1，252=年交易日数）；区间内无持仓两卡均显示「—」，口径写在 title 悬停提示。`#range-strip` 网格由 `repeat(5,1fr)` 改 `repeat(auto-fit,minmax(130px,1fr))` 按卡数自适应（≤960px 仍降 2 列）。
- 2026-09-28（QRE-SAAS-DETAIL-CARD-UI）SaaS 详情页卡片修正（saas/templates 侧，lab 侧零改动）：①区间五卡末尾留白根因——lab-theme.css 把 `.metric-strip` 纠偏为 `repeat(6,1fr)` 网格，五卡只占 5/6；saas base.html 加 `#range-strip{grid-template-columns:repeat(5,1fr)}`（≤960px 降 2 列）。②job.html 模块顺序对齐 §8：交易磨损 + FRM 移到收益曲线之后、归因之前。③symbol.html 顶部 7 简介卡（6 列网格装 7 卡导致 6+1 且窄高臃肿）改 `#sum-strip{grid-template-columns:repeat(auto-fit,minmax(200px,1fr))}` + 卡 padding 10px 14px + 数值 15px（对齐 §1.3「个股页 15px」）。④总结性卡片淡紫底：`#metric-strip/#sum-strip/#range-strip 的 .metric-card` 用 `--tint` 底 + `--tint-deep` 边（区间卡即 §3.9 `.range-strip .metric` 既有规范推广到概述/简介卡）。均用 ID 选择器压过 lab-theme 后加载的同族规则；Jinja 模板内 CSS 选择器 `{#id` 连写会被当注释，需 `{ #id` 留空格（本次踩过）。
- 2026-09-08 初版：从 synthesis.html 定稿提取（用户验收通过）。
- 2026-09-27（QRE-UI-DESIGN-SYSTEM-DOC）重写为完整设计系统：补文件地图、行内控件 36px 等高规范、ECharts 图表配置约定（此前文档写的是设计稿期 SVG 手绘方案，落地已改 ECharts）、SaaS 复刻约定、禁链含注释的教训；每条规范标注源码文件+行号。
- 2026-09-27（QRE-SAAS-FEEDBACK-FACTOR-REQ）SaaS 侧新增统一侧边栏组件 `.sidenav`（saas/templates/base.html）：左列固定 150px、≤960px 降级顶部横排；链接态复用既有 tokens（默认 --muted 字、hover/active = `--tint` 底 + 主紫字），无新色相、无循环动效。此前 SaaS 页面无侧边栏，本条为新增组件登记（lab 侧不涉及）。
