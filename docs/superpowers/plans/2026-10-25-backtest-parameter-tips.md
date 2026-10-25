# 回测参数口径提示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为全部回测参数提供准确的悬停/点击口径、单位和默认值说明。

**Architecture:** 复用 `LabUI.helpTips()` 的事件委托，仅在参数 label 上增加 `data-tip` 与必要键盘焦点；不增加可见灰字，不改参数值或 YAML。

**Tech Stack:** Jinja、原生 JavaScript、pytest、现有 Playwright/Chromium。

## Global Constraints

- 权威设计：`docs/superpowers/specs/2026-10-25-backtest-parameter-tips-design.md`。
- 不改默认值、API、编译、YAML 或回测结果；Kimi 内联实施。
- 金额元、比例小数、0/留空规则必须准确。
- 真实桌面和移动浏览器验收，不运行回测。

### Task 1: 参数提示与静态回归

**Files:**
- Modify: `src/quant_research_engine/gui/saas/templates/new.html`
- Test: `tests/test_saas_parameter_tips.py`

- [ ] **Step 1: 新建失败测试。** 遍历参数 label 对应 data-tip；断言共享/批量、元、0 不限、次日价格、小数百分比、佣金和滑点说明。Run: `/home/van/.local/bin/uv run python -m pytest tests/test_saas_parameter_tips.py -q`。Expected: FAIL（提示不存在）。
- [ ] **Step 2: 实现。** 为策略 ID、区间、范围、板块、随机、代码、模式、资金、持仓、价格、止损止盈、移动止损、佣金、最低佣金、印花税和滑点添加 data-tip；label 可键盘聚焦。
- [ ] **Step 3: 验证 GREEN。** 同上全部 PASS；渲染 new 后内联脚本 Node 解析 exit 0。

### Task 2: 浏览器与长期文档

**Files:**
- Modify: `docs/agent/04_TASK_HANDOFF.md`
- Modify: `docs/agent/05_PROGRESS.md`
- Modify: `docs/agent/06_DECISION_LOG.md`
- Modify: `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- Modify: `docs/agent/09_CODING_HANDOFF.md`
- Modify: `docs/agent/10_REVIEW_REPORT.md`
- Modify: `docs/agent/11_AGENT_STATE.md`
- Modify: `docs/agent/12_UI_STYLE_GUIDE.md`

- [ ] **Step 1: 浏览器验收。** 8091 桌面 1280/移动 375 展开回测参数，逐个检查 label 提示；重点验证模式/资金/持仓/价格/比例/费用，重复三次和移动 tap 正文可见，零 JS error、零横滚。截图 `.tmp/parameter-tips/`。
- [ ] **Step 2: 全量验证。** Run: `/home/van/.local/bin/uv run python -m pytest tests/ -q --ignore=tests/data_test` 和 `bash scripts/check-progress-docs.sh && bash scripts/git-finalize-check.sh && git diff --check`。Expected: 全过。
- [ ] **Step 3: 文档与发布门禁。** 更新实际结果。未经用户明确批准不 commit/push/部署；获批后备份并同步 new.html 到 ECS，重启 qre-saas，校验公网提示。
