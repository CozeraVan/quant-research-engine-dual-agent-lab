# CR-2026-10-28 详情页小卡条统一紫底 + flex 自适应均分整行

状态：已实施，未 commit/push（等用户验收）
关联：`CR-2026-10-28_holding_period_and_risk_adjusted.md`（引入 `#ra-strip`）、
`CR-2026-10-28_card_frosted_glass.md`（磨砂玻璃卡族）

## 1. 现象（用户验收 α/β/IR 时发现）

1. α/β/IR 所占 div 与该位置风格不符；
2. 同类小 div **部分是白底、部分是紫底**；
3. 个股回测详情前面的小 div 数据集合**第一排 5 个、第二排 3 个、第三排 3 个**，不美观。

## 2. 根因

`#ra-strip`（α/β/IR）与两个重播条（`#replay-metrics` / `#kreplay-info`）**不在原有的紫底名单里**，
于是一路落到底层规则：

- 背景：`base.html` 的 `.metric-card{background:#fff}` → **白底**
- 布局：`lab-theme.css` 的 `.metric-strip{display:grid;grid-template-columns:repeat(6,1fr)}`
  → 3 张卡各占 1/6 宽，**剩 3 个空轨道**（半行）

而 `#sum-strip`（8 卡）走 `repeat(auto-fit,minmax(200px,1fr))` → 实测 5 列 → **5+3**。

三者叠加正是用户看到的「5 / 3 / 3，白紫混杂」。

**实测基线**（Chromium，symbol 页，内容宽 1216px）：

| 条 | display | 列 | 卡数/每行 | 背景 |
|---|---|---|---|---|
| `#sum-strip` | grid | auto-fit 200px ×5 | 8 → **5+3** | 紫 |
| `#ra-strip` | grid | 6×194px | 3 → **3（半行）** | **白** |
| `#range-strip` | grid | auto-fit 130px ×7 | 7 → 7 | 紫 |

## 3. 修复（`saas/templates/base.html`，只改 CSS）

把六条小卡条收敛到**同一套 flex 规则**：

```css
#metric-strip,#sum-strip,#range-strip,#ra-strip,#replay-metrics,#kreplay-info
  {display:flex;flex-wrap:wrap;gap:10px}
<六条> .metric-card{background:var(--tint);border-color:var(--tint-deep)}   /* 统一紫底 */
#metric-strip/#range-strip/#replay-metrics/#kreplay-info .metric-card{flex:1 1 130px}
#sum-strip/#ra-strip .metric-card{flex:1 1 250px;padding:10px 14px}
#sum-strip/#ra-strip .metric-card .m-value{font-size:15px}
```

设计要点：

- **flex-wrap + flex-grow**：每行必然填满（末行拉宽），不会再有半空行；
  窄屏自然换行，不需要为每个断点写列数。
- **两档 min**：密集条（指标/区间/重播，7 卡左右）130px → 一行并排；
  简介条与风险调整收益条（卡少、字号大）250px → 8 卡呈 **4+4**、3 卡**撑满整行**。
- **130px 是实测值**：job 页 `.container` 约 1000px，`7×150+6×10=1110` 放不下 → 退化成
  **6+1 孤行**（第一版就踩了）；`7×130+6×10=970` 放得下 → 一行并排。
- 删掉旧的 `grid-template-columns` 死代码（flex 容器上不生效，留着误导后来者）。
- `.metric-card` **不在**磨砂玻璃卡族（`.card`/`.chart-box`/`.big-link`）内，所以紫底平坦卡
  是既有设计，本次只是把漏网的条并进来。

## 4. 测试

新增 `tests/test_perf_metrics.py::TestMetricStripStyleContract` 4 例（源码合同）：

- `test_all_strips_share_flex_and_purple`：六条必须同在一个 flex 规则和一个紫底规则里
- `test_dense_strips_fit_seven_in_one_row`：密集条 min ≤130px（防 6+1 孤行回归）
- `test_summary_and_ra_strips_use_wider_basis`：简介/ra 条 min 250px + 15px 字号
- `test_no_leftover_grid_rules_for_these_strips`：不得残留 grid 死代码

**RED 验证**：把 `#ra-strip` 移出名单 + 密集条改回 150px → 2 例立即红；恢复后 14 passed。

## 5. 真实浏览器验证（Chromium，`.tmp/perf-browser/verify.py`）

对 job/symbol 两页 × 1440/1024/375 三个视口，断言「背景统一 + 行内等宽 + 非末行填满 + 无溢出」：

| 页面/视口 | `#metric-strip` | `#sum-strip` | `#ra-strip` |
|---|---|---|---|
| job 1440 | **7（一行）** | — | 3（撑满） |
| job 1024 | **7（一行）** | — | 3（撑满） |
| job 375 | 2+2+2+1 | — | 2+1 |
| symbol 1440 | — | **4+4** | 3（撑满） |
| symbol 1024 | — | 3+3+2（末行拉宽） | 3（撑满） |
| symbol 375 | — | 2+2+2+2 | 2+1 |

全部背景 `rgb(241,237,248)`（统一紫底）；同一行内卡片等宽；`scrollWidth ≤ innerWidth`。

同时复验了上两轮成果未被 CSS 改动破坏：α=12.00% / β=0.89 / IR=0.78（与 Python
`performance_summary` 一致）、平均持股周期 45.3 天 / 48.7 天、job 指标卡 7 张、
LWC 图例 5 pill 且成交量/EMA5/MACD 往返全通。**零 pageerror / console error。**

截图：`.tmp/perf-browser/symbol-cards.png`（可见 4+4+3 全紫底）。

## 6. 影响面

只改 `base.html` 的一段 CSS。lab（8081）页面不用这些 ID，不受影响；
`.metric-card` 的玻璃/夜间规则未动。
