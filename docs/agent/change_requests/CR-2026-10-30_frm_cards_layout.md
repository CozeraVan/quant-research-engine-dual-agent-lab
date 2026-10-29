# CR-2026-10-30 · 2.4 个股 FRM 七卡排版（6+1 → 4+3）

> 任务书：`docs/agent/change_requests/TASK-2026-10-30_deepseek_ui_round4.md` §2.4
> 实施：DeepSeek 子 agent / 复核：Kimi
> 改动文件：`src/quant_research_engine/gui/static/card-class.css`（新增两条规则块）

---

## 1. 根因

个股页 `symbol.html::renderRisk()`（`~585`）动态生成 `<div class="metric-strip">`
（7 张 `.metric-card`：VaR 95/99、ES、年化波动、最大回撤等）注入 `#risk-body`。
样式来自 `lab-theme.css:441`：

```css
.metric-strip{display:grid;grid-template-columns:repeat(6,1fr);gap:18px}
```

该规则是按 job 页「6 卡条」写的，7 卡就排成 **6+1** —— 第二排只挂一张孤卡，
右侧整片留白。注意此处是 `#risk-body .metric-strip`（class），与 job 页的
`#metric-strip`（ID）不是同一个元素，改它不影响 job 页。

## 2. 改动（`static/card-class.css`）

```css
#risk-body .metric-strip {              /* 特异性 1,1,0，压住 lab-theme 的 .metric-strip */
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 18px;
}

@media (max-width: 960px) {             /* 并入既有 960px 块的开头 */
  #risk-body .metric-strip { grid-template-columns: repeat(2, 1fr); }
  #risk-body .metric-strip .metric-card:last-child { grid-column: span 2; }
}
```

**为什么是 4+3 而不是 `auto-fit` / `repeat(auto-fit,minmax(...))`：**

1. 7 卡在任何整数列数下都不整除，4+3 是唯一「两排、排差 1、无孤立卡」的分法；
   5+2 与 3+4 会把第二排压到 1~2 张，视觉重心偏左。
2. 与 job 页 `#metric-strip` 一族的卡宽更接近（1920 下实测 444px，job 页 6 卡约 620px，
   但同属 4~6 列大卡区间），不产生「粗细两张卡」的断层。
3. `auto-fit` 在 1280/1366 等窄桌面宽度下会掉成 3 列 → 3+3+1 或 3+4，无法保证 4+3；
   显式列数在各断点行为确定，便于回归。
4. ≤960px 两列时末卡 `span 2` 消掉 2+2+2+**1** 的孤行 —— 这也是本轮唯一必须用
   「末卡跨列」而非等分的原因：7 是奇数。

`card-class.css` 里既有的 `#metric-strip/#range-strip/#replay-metrics/#kreplay-info
.metric-card{flex:1 1 100%}` 是 flex 规则，**没有**给 `#risk-body .metric-strip`
加 `display:flex`（会与 grid 冲突），故无相互覆盖。

## 3. 真实浏览器实测（`measure.py browser --tag=after2.4b`）

`riskCardBoxes` 为每张卡的 `[left, width, top]`，7 张全列：

| 视口 | gridTemplateColumns | 排布（top 分组） | 卡宽 | docW/scrollW |
|---|---|---|---|---|
| 1920 light/dark | 444px ×4 | `{1706:4, 1835:3}` | 7 张全 444 | 1920/1920 |
| 1440 light/dark | 324px ×4 | `{1733:4, 1862:3}` | 7 张全 324 | 1440/1440 |
| 375 light/dark | 137.5px ×2 | `{3981:2, 4197:2, 4353:2, 4482:1}` | 前 6 张 138，**第 7 张 293** | 375/375 |

- 1920：第 1 排 left = 45/507/969/1431；第 2 排 left = 45/507/969 —— 左对齐、与第一排同宽，**4+3** 成立。
- 375：第 7 张 left=41、width=293 = 2×137.5 + 18(gap) —— **`span 2` 生效**，末排满宽无孤卡。
- 6 组合 `docW == scrollW == bodyScrollW`，无横向溢出；`=== PAGEERRORS ===` → `(none)`。
- 截图：`.tmp/ds-round4/after2.4b-*-sym-risk.png`（`after2.4-*` 为同一 CSS 的更早一版截图）。

## 4. 回归

- `tests/test_perf_metrics.py`：`ALL_STRIPS` 不含 `#risk-body .metric-strip`，
  其正则只匹配既有相邻行（`#metric-strip .metric-card,` / `flex: 1 1 150px` 等），
  新增规则不改这些行 → 实跑通过。
- `tests/test_saas_night_mode.py::test_all_rules_scoped_or_button` 只校验 `night-mode.css`，
  不约束 `card-class.css` → 实跑 24 passed。
- 全量 `uv run pytest tests/ -q`：见 `pytest-round4.log`（本轮最终一次）。

## 5. 未动 / 遗留

- 未改 `lab-theme.css`（不属于本轮前端模板/静态目录边界，且改它会影响所有 `.metric-strip`）。
- 未加新动效、未动圆角/色板/玻璃/夜间机制，未引入灰字（卡片内文案原样）。
- 若未来 job 页或其它页面也用 7 卡 `metric-strip`，需把这两条规则提升为通用类名。