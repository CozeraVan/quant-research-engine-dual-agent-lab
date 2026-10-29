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
| `04` / `05` / `09` / `10` / `11` 追加 | 已全部补写（04 交接、05 进度、09 编码交接、10 复核报告、11 状态） |
| 浏览器证据进 CI | 未做（依赖本地服务 + Playwright，与上轮同样处理） |
| ECS 部署 | **未部署**——本轮改动已被并行 TV R4 的收尾提交 `8789a15`（2026-10-29 13:04）一并提交并推到 `origin/master` |

提交状态更新：本 agent 未执行 commit / push / 部署 ECS；`8789a15` 由并行 TV R4
任务发出（标题为「TV_ROUND4 R4-1~R4-4 + UI 第三轮」），把本轮 18 文件一并带走。
本地与 `origin/master` 无差，**ECS 仍为旧版本**。

---

## 6. 复核补充：改动明细、判断要点与证据（Kimi 子 agent）

### 6.1 逐文件改动（18 文件，+314 / −286）

| 文件 | 改动 |
|---|---|
| `gui/static/lab-theme.css` | 主体：body/表格/标题/m-label/m-value/page-head 字号 +2；`.card` 30/32、`.chart-box` 26/28、`.metric-card` 20/22、`.metric-strip` gap 18 / mb 28、`.page-head{margin-bottom:28px}`、`.tbl td` 14/14。所有 `line-height` 行原值保留 |
| `gui/static/card-class.css` | 卡片类字号族 +2 |
| `gui/static/night-mode.css` | 暗色对应字号同步（1 行） |
| `gui/saas/templates/base.html` | 内联字号族 +2；裸 `th,td{padding:8px}`→`13px 14px`；新增 `@media(max-width:400px)` 导航横滚 6 行 |
| `_records_body.html` / `_records_scripts.html` | 记录表字号/内联尺寸 +2 |
| `dashboard.html` / `showcase.html` | 页头字号 +2 |
| `help.html` | 侧栏与正文段落字号、间距 +2/放大 |
| `job.html` | brief-line margin 12/18→16/20 + 字号族 +2 |
| `new.html` | 表单/卡片间距放大、字号 +2 |
| `profile.html` | 分享卡字号 +2（R-UI-001 的 `tip-trigger` 结构保持不变） |
| `strategy.html` / `symbol.html` | 参数区与详情字号 +2、间距放大 |
| `tests/test_ui_dense_font_scale.py` | 11 例改写为第三轮目标值（table 16 / `.tbl th` 16 / `.detail-table` 16 / `.m-label` 16 / `.m-value` 21 / `.opt`≥14），并显式声明不断言 line-height |
| `tests/test_perf_metrics.py` / `test_saas_help_nav.py` / `test_saas_result_help.py` | 同步受影响的字号/间距断言 |

### 6.2 五个判断（复核时逐一核过，均已在代码中体现）

1. **`.m-value` 21 而非 22**：任务书 A1 写 19→21；`.page-head h1` 才是 30→32。
2. **`.page-head{margin-bottom:28px}` 与「删 pMB 断言」**：加 margin 后
   `.page-head p` 自身的 margin-bottom 属段落内距，不是「页头→主体」间距，
   把它纳入 `>=12` 断言属口径错误，故删除该断言而非改 CSS。
3. **375 视口导航改横滚而不是缩字号**：6 个导航项在 375 下任何合规字号都放不下；
   缩字号会破坏「全站字号 +2px」的硬要求，故改为单行可横滚（隐藏滚动条）。
4. **job 页不包 `.page-head`**：`.page-head` 的 margin 修不到 job 的 h1+副标题，
   故直接给 brief-line 加 margin（16/20），实测 `headGap=16`，满足 >=16。
5. **line-height 等价性用分布比对而非「看着没改」**：`lineheight_check.py` 与
   commit diff 两侧 11 档值分布逐档相同 → `EQUIVALENT` / `DISTRIBUTION_IDENTICAL`。

### 6.3 证据（原始输出）

```text
uv run --with playwright python .tmp/ui-round3/verify.py
  → combos=54 failures=0 elapsed=158.0s / PASS (exit 0)
python .tmp/ui-round3/lineheight_check.py → EQUIVALENT (removed 22 / added 22)
python .tmp/ui-round3/nodecheck.py → checked 7 script blocks, 0 failed
git show 8789a15 -U0 -- '*.css' '*.html' | grep -E '^[+-].*line-height' | wc -l → 44
uv run pytest tests/ -q → 3205 passed, 34 skipped, 6 warnings in 164.09s (exit 0)
```

### 6.4 发现但未改

- `symbol.html` 用 `/api/results/1/symbols/000001.SZ` 的 404 作控制流，建议改
  200 + `ok:false`（API 契约变更，不在本轮范围），本轮只在 `verify.py`
  `CONSOLE_ALLOW_4XX` 显式登记。
- `.help-side{padding:14px}` 低于本轮 `.card` 的 30/32 族值，属既有设计。
- `profile.html` 的 metric-strip 在 `.card` 内且 inline `margin-bottom:0`，
  页面级无 strip 可量（`verify.py` 记 `metricStripSkipped`）。
- `12_UI_STYLE_GUIDE.md` 基线过期，按任务书边界只提示不改。
- `deploy/saas/*`、`TV_ROUND4_*`、`tests/test_no_silent_failure_patterns.py`、
  `tests/test_template_inline_js_syntax.py`、`AGENTS.md`、
  `20_DATA_DICTIONARY_DAILY_MINUTE.md` 属并行任务，不计入本轮。
