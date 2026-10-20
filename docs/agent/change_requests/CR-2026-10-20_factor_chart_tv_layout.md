# CR-2026-10-20: 因子图表 TV 风格智能布局（overlay/pane/chip 交互）

## 问题

个股回测详情（SaaS `symbol.html`、K线重播组件、8081 lab 页）中，策略因子被**机械地每个因子各占一个独立 grid、全部画成单条紫线**（`symbol.html` renderKline 约 :405-420，重播组件 :489-493）。与主流交易软件差距：

- EMA/MA 类均线未叠加到 K 线主图；
- MACD 的 DIF/DEA/HIST 三元组被拆成 2-3 个独立面板，无红绿柱；
- 用户无法切换因子显示方式。

根因：因子数据载荷只有 `{name, values}`，没有"该怎么画"的展示元数据。

## 已批准设计（2026-10-20 用户逐项确认）

### 1. 元数据层（混合模式：元数据优先 + 启发式兜底）

- 因子注册表/metadata 新增可选 display 字段：`chart_type`（`overlay`|`pane`）、`group`（同组多 series 合并同面板）、`series_style`（`line`|`bar`）、`color`。
- 元数据经 `sync_saas_metadata.py` 同步至 SaaS；详情 API factors 可选附带 display；**缺元数据时前端按名称启发式**：
  - `ema*/ma*/sma*/wma*/boll_*` → overlay 到 K 线主轴；
  - `macd + macds + macdh` 同参数后缀三元组（如 `_12_26_9`）→ 合并为一个 MACD 面板：DIF/DEA 双线 + HIST bar（正值红、负值绿，与 A 股 K 线涨跌色一致；已确认不做方向变色）；
  - `rsi*/kdj*/其余` → 独立面板。
- 首期元数据表可留空，纯启发式即可跑；后续逐因子补标注自动生效。

### 2. 前端布局算法

渲染前对 factors 分组归并：overlay 组进 grid0（与价格同量纲，共用 y 轴）；每个 pane 组一个 grid；同 group 多 series 同 grid；grid 高度按面板数自适应。

### 3. 交互

K 线标题栏加因子 chip 行（主紫 #6750A4，复用现有样式组件，遵守 12_UI_STYLE_GUIDE）：每个因子/因子组一个 chip，三态循环 **叠加K线 → 独立面板 → 隐藏**（MACD 整组切换）。状态存 localStorage，按因子名记忆。

### 4. 覆盖范围（三处全改）

- SaaS `symbol.html` renderKline（静态）；
- K 线重播组件（抽出共用分组布局函数，防两份逻辑漂移）；
- 8081 lab 版个股模板（lab_result）。

### 5. 兼容性

factors 载荷结构不变，display 字段可选；旧产物无元数据自动走启发式，无需重跑历史回测。

### 6. 验证

- job#58（MACD）个股详情：DIF/DEA/HIST 合成单面板，柱红绿正确；
- job#74（EMA5/200）：双均线叠加 K 线；
- chip 三态切换 + localStorage 记忆；
- 重播与静态布局一致；
- `test_gui_saas.py` 回归通过。

## 状态

2026-10-20 设计已获用户批准，进入实施。
