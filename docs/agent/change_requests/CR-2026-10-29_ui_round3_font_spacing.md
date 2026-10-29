# CR-2026-10-29 · DeepSeek UI 第三轮：全站字号 +2px 与间距系统放大

> 任务书：`docs/agent/change_requests/TASK-2026-10-29_deepseek_ui_round3.md`
> 实施：DeepSeek 子 agent / 复核：Kimi
> **说明**：本轮 CR 由 Kimi 补写——DeepSeek 完成了代码与浏览器验收，但未按任务书
> §5.11 落 CR 文档。证据全部来自它在 `.tmp/ui-round3/` 留下的产物，Kimi 逐项核过。

---

## 1. 任务 A：全站字号 +2px（用户原话「所有字号再大2PX」）

### 1.1 改前改后（Kimi 线上实测复核）

| 目标 | 改前（线上） | 改后（工作区） |
|---|---|---|
| `body` | 17px | **19px** |
| `.page-head h1` | 30px | **32px** |
| `.page-head p` | 15.5px | **17.5px** |
| `table` | 14px | **16px** |
| `.tbl th` / `.detail-table(-th)` | 14px | **16px** |
| `.chart-title` | 16.5px | **18.5px** |
| `.metric-card .m-label` | 14px | **16px** |
| `.entry-card p` | 13px | **15px** |
| `pre.yaml` | 12.5px | **14.5px** |
| `.chart-tip` | 12px | **14px** |

### 1.2 硬约束核对：`line-height` 一律未动

Kimi 用 `git diff` 逐行核了 `lab-theme.css` 的 `line-height`——
**所有命中的行都是字号变了、`line-height` 原值保留**：

```diff
-body{...font-size:17px;line-height:1.65;...}
+body{...font-size:19px;line-height:1.65;...}      ← 倍数 1.65 未动

-.page-head h1{...font-size:30px;line-height:1.3}
+.page-head h1{...font-size:32px;line-height:1.3}  ← 倍数 1.3 未动

-.entry-card p{font-size:13px;...line-height:1.55}
+.entry-card p{font-size:15px;...line-height:1.55} ← 倍数 1.55 未动
```

符合用户「行间距暂不推进」的要求。`tests/test_ui_dense_font_scale.py` 的 docstring
也明确写了「本轮不推进 line-height：本文件不对任何 line-height 作断言」。

---

## 2. 任务 B：间距系统放大

### 2.1 用户点名的第一现场已修

使用说明页头部，改前实测（`.tmp/ui-round3/gaps_before.json`）：

```json
"headGap": {"next": "div.card", "gap": 0, "headMarginB": 0}
```

即 `.page-head` 与主体 DIV 之间**间距 0**、`.page-head` 自身 `margin-bottom` 也是 0。

改后实测（`.tmp/ui-round3/gaps_after.json`）：

```json
"headGap": {"next": "div.card", "gap": 28, "headMarginB": 28}
```

对应改动 `lab-theme.css:55`：`.page-head{margin-bottom:28px}`（与 `.chart-box` 的
28px 同族），`.page-head p{margin-top:12px}`。

### 2.2 其余间距（按 DeepSeek 的对照产物）

`.tmp/ui-round3/` 下有改前改后两份 gap JSON + 两份 diff 逐对文本
（`diff_pairs.txt` 77KB / `diff_pairs_key.txt` 78KB），覆盖九页相邻 DIV 的
`getBoundingClientRect().top - prev.bottom` 全量对比。Kimi 抽核了首页/使用说明/
回测详情/个股详情四页的 headGap 与 chart-box 间距，均从 0 或极小值抬到 14–28px 区间。

---

## 3. 验收（DeepSeek 产物，Kimi 复核）

`.tmp/ui-round3/verify_result.json`：**54 组合全绿**

- 9 页 × 3 视口（1920/1440/375）× 2 主题（light/dark）= **54**
- 每组合 `body=19px`、`scrollWidth == innerWidth`（**零横向溢出**）、`fails=0`
- `.tmp/ui-round3/lineheight_check.py` 专项校验 line-height 未被改

Kimi 独立复跑全量测试：**3205 passed, 34 skipped, 0 failed**。

---

## 4. 测试

`tests/test_ui_dense_font_scale.py` 从 11 例改写为覆盖第三轮目标值
（table 16px / .tbl th 16px / .detail-table 16px / 密集控件 15.5px /
`.opt` 随全站 +2 但不得低于 14px），并显式声明不对 line-height 断言。
另同步更新 `tests/test_perf_metrics.py`、`tests/test_saas_help_nav.py`、
`tests/test_saas_result_help.py` 里受影响的字号/间距断言。

---

## 5. 未做 / 遗留

| 项 | 状态 |
|---|---|
| CR 文档 | **DeepSeek 漏写，本文件由 Kimi 补**（任务书 §5.11 要求每项落 CR） |
| `05_PROGRESS.md` / `09_CODING_HANDOFF.md` 追加 | 同样漏写；已在 `11_AGENT_STATE.md` 有记录 |
| 浏览器证据进 CI | 未做（依赖本地服务 + Playwright，与上轮同样处理） |
| ECS 部署 | **未部署**——本轮改动未 commit，按派单约束等 Kimi 复核后统一提交 |

未 commit / 未 push / 未部署 ECS。
