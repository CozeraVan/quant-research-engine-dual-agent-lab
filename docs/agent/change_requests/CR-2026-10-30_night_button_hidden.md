# CR-2026-10-30 · 2.1 顶栏夜间模式按钮隐藏

> 任务书：`docs/agent/change_requests/TASK-2026-10-30_deepseek_ui_round4.md` §2.1
> 实施：DeepSeek 子 agent / 复核：Kimi
> 改动文件：`src/quant_research_engine/gui/saas/templates/base.html`（内联 `<style>` 一条规则）

---

## 1. 改动

在 `base.html` 内联样式 `header.topbar .mainnav a.active` 之后插入一条（带注释说明恢复方式）：

```css
/* 夜间模式按钮暂不启用（R4-2.1）：功能全部保留…恢复只需删下面这一条。
   DOM 必须保留——night-mode.js 见页面无 .tt-btn 时会注入 .tt-btn.tt-float 悬浮钮。 */
header.topbar .tt-btn{display:none}
```

- `<button class="tt-btn">` 的 **DOM 未删**（`base.html` 顶栏内），只是不可见。
- `static/night-mode.js`、`static/night-mode.css` **一行未改**：`qre-theme` 持久化、
  系统偏好跟随、防 FOUC（`<html>` 早期设 `data-theme`）、ECharts 主题联动、`qre:themechange`
  事件全部保留，行为不变。
- 选择器带 `header.topbar` 前缀（特异性 0,2,1），高于 `night-mode.css` 的 `.tt-btn`；
  且只作用于 SaaS 顶栏，**不会影响** `login_callback.html` 里的 `.tt-btn.tt-float` 悬浮钮。

## 2. 关键风险点与实测结论

`static/night-mode.js` 的逻辑是「页面里找不到 `.tt-btn` 就注入悬浮钮」。若用
`display:none` 隐藏，DOM 仍存在 → 不注入。若误删 DOM，会冒出 `.tt-btn.tt-float`。
实测（`.tmp/ds-round4/measure.py browser --tag=after2.1`：

| 视口 × 主题 | `header.topbar .tt-btn` display | `.tt-btn.tt-float` 存在 | `themeAttr` |
|---|---|---|---|
| 1920 light | `none` | 无（`null`） | light |
| 1440 light | `none` | 无 | light |
| 375 light | `none` | 无 | light |
| 1920 dark | `none` | 无 | **dark** |
| 1440 dark | `none` | 无 | **dark** |
| 375 dark | `none` | 无 | **dark** |

- dark 组 `themeAttr == "dark"` 证明「localStorage 里存 dark 时页面仍按 dark 渲染」——
  持久化链路完整，不会因为按钮不见了就弹回浅色。
- `docW == scrollW == bodyScrollW`：1920/1920、1440/1440、375/375，**无横向溢出**。
- `=== PAGEERRORS ===` → `(none)`（6 组合均无 pageerror / console.error）。
- 截图：`.tmp/ds-round4/after2.1-{1920,1440,375}-{light,dark}-{job,sym}-{top,risk}.png`。

## 3. 验证

- `node --check`：`base.html` 4 个内联 script 全通过（`.tmp/ds-round4/nodecheck.py`）。
- `uv run pytest tests/ -q`：见 `.tmp/ds-round4/pytest-2.1.log`（全量）。
  `tests/test_saas_night_mode.py::test_toggle_button_in_nav` 只断言 HTML 中仍有该按钮，
  DOM 保留 → 通过。
- 顶栏 padding（2.2 的改动）在本项下未回归：1920/1440 仍为 16px、375 为 12px。

## 4. 遗留

- 按钮 DOM 与 `night-mode.js` 的 `.tt-btn` 绑定保留为「休眠」状态。后续若要重新启用，
  删掉这一条 CSS 即可，注释里已写明。
- `login_callback.html` 内的 `.tt-btn.tt-float`（夜间悬浮钮）仍显示 —— 不在本轮 2.1 范围内，
  已记入遗留清单。