# 自选因子三栏弹窗 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将自选因子条件行的三级下拉替换为可搜索的三栏弹窗，同时保持所有策略数据契约不变。

**Architecture:** 原 `.wz-left/.wz-rfield` select 作为隐藏数据字段，新增按钮负责显示与打开弹窗。弹窗复用 `FACTOR_OPTIONS` 和既有目录函数，选择后写回 select 并触发原 change 事件；不新增 API。

**Tech Stack:** Jinja、原生 JavaScript、共享 CSS、pytest、Node VM、隔离 Playwright/Chromium。

## Global Constraints

- 权威设计：`docs/superpowers/specs/2026-10-25-factor-picker-modal-design.md`。
- 不改 YAML、条件快照、固定值切换、策略还原、price-basis、API、数据库或回测引擎。
- 复用现有 modal/按钮/表单/紫色主题，不新增依赖。
- 桌面和 375px 真实 Chromium 验收；不运行真实全量回测。
- 先部署 ECS；未经用户另行批准不 commit、不 push。

---

### Task 1: 弹窗与数据字段桥接

**Files:**
- Modify: `src/quant_research_engine/gui/saas/templates/new.html`
- Modify: `src/quant_research_engine/gui/static/lab-theme.css`
- Test: `tests/test_saas_factor_picker.py`

**Interfaces:**
- Consumes: `FACTOR_OPTIONS`、`factorGroups()`、`factorSubs()`、`makeFactorSelect(cls)`、`setFactorSelectValue(wrap,v)`、`refreshWizard()`。
- Produces: `openFactorPicker(wrap)`、`closeFactorPicker()`、`syncFactorPickerButton(wrap)`；原 `.wz-left/.wz-rfield` 继续保存最终值。

- [ ] **Step 1: 编写失败测试。** 新建 `tests/test_saas_factor_picker.py`，静态断言弹窗三栏、搜索、关闭按钮存在；Node VM 验证打开→父子联动→最终选择写回原 select、按钮文本更新并派发一次 change；连续打开不重复创建弹窗，Esc/遮罩关闭且焦点返回。

```python
def test_picker_preserves_value_contract():
    page = (ROOT / "src/quant_research_engine/gui/saas/templates/new.html").read_text()
    assert 'id="factor-picker-modal"' in page
    assert 'id="factor-picker-search"' in page
    assert "wrap.querySelector('.wz-left')" in page or "cls" in page
```

- [ ] **Step 2: 验证 RED。** Run: `/home/van/.local/bin/uv run python -m pytest tests/test_saas_factor_picker.py -q`。Expected: FAIL，因为弹窗和桥接函数不存在。
- [ ] **Step 3: 最小实现。** `makeFactorSelect` 保留 select 为隐藏数据字段并新增 `.factor-select-btn`；`syncFactorSelect` 继续填充隐藏值且同步按钮。弹窗每次打开根据当前值渲染三栏；最终项点击后设 `select.value`、同步按钮并 `dispatchEvent(new Event('change',{bubbles:true}))`，再关闭并返回焦点。Esc、关闭按钮和遮罩只关闭，不改值。
- [ ] **Step 4: 样式与可访问性。** 使用 `.modal-mask/.modal` 结构；三栏列表内部滚动、选中态紫底、搜索 autofocus、按钮 aria-label、dialog aria-modal/label。移动端宽度 `calc(100vw - 24px)`、高度受视口限制、三栏可降为单列或横向小栏，禁止页面横滚。
- [ ] **Step 5: 验证 GREEN。** Run: `/home/van/.local/bin/uv run python -m pytest tests/test_saas_factor_picker.py -q`。Expected: 全部 PASS；渲染 new 后内联脚本 Node 解析 exit 0。

### Task 2: 搜索及既有向导回归

**Files:**
- Modify: `src/quant_research_engine/gui/saas/templates/new.html`
- Test: `tests/test_saas_factor_picker.py`
- Test: `tests/test_gui_saas_pages.py`

**Interfaces:**
- Consumes: Task 1 的 `openFactorPicker/closeFactorPicker` 和隐藏 select。
- Produces: 搜索仅过滤当前弹窗显示，不改变 `FACTOR_OPTIONS`；还原仍调用 `setFactorSelectValue`。

- [ ] **Step 1: 编写失败测试。** 验证搜索同时匹配 label/value/group/sub、清空恢复、无结果空态；搜索结果选中后三栏与按钮一致。验证固定值切换、条件增删、AND/OR 和 `snapshotWzArea` 值不变。
- [ ] **Step 2: 验证 RED。** Run: `/home/van/.local/bin/uv run python -m pytest tests/test_saas_factor_picker.py -q -k 'search or snapshot'`。Expected: 新搜索断言 FAIL。
- [ ] **Step 3: 实现搜索。** 对 `FACTOR_OPTIONS` 做只读过滤，组合 `label/value/group/sub` 小写匹配；结果显示完整层级，点击复用 Task 1 的选择函数，清空输入恢复三栏。
- [ ] **Step 4: 验证 GREEN。** Run: `/home/van/.local/bin/uv run python -m pytest tests/test_saas_factor_picker.py tests/test_gui_saas_pages.py -q`。Expected: 全部 PASS。

### Task 3: 真实浏览器、回归、文档与部署

**Files:**
- Modify: `docs/agent/04_TASK_HANDOFF.md`
- Modify: `docs/agent/05_PROGRESS.md`
- Modify: `docs/agent/06_DECISION_LOG.md`
- Modify: `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- Modify: `docs/agent/09_CODING_HANDOFF.md`
- Modify: `docs/agent/10_REVIEW_REPORT.md`
- Modify: `docs/agent/11_AGENT_STATE.md`
- Modify: `docs/agent/12_UI_STYLE_GUIDE.md`

**Interfaces:**
- Consumes: Tasks 1–2 的最终实现及现有 8091 staging、`.tmp/browser-venv`。
- Produces: 可复核的浏览器证据、长期交接和 ECS 验收版本。

- [ ] **Step 1: 真实 Chromium 验收。** 启动/复用 8091 staging；桌面 1280px 和移动 375px 分别完成左因子选择、右因子选择、搜索、清空、Esc、遮罩、焦点返回和连续三次打开关闭。检查按钮与 YAML 一致、固定值与策略还原不回归、无 JS error、无横向溢出。截图保存 `.tmp/factor-picker-modal/`。
- [ ] **Step 2: 完整回归。** Run: `/home/van/.local/bin/uv run python -m pytest tests/test_gui_saas.py tests/test_gui_saas_pages.py tests/test_saas_authing.py tests/test_gui_lab.py tests/test_saas_symbol_ux.py tests/test_saas_help_copy.py tests/test_saas_factor_picker.py -q`，随后 `uv run python -m pytest tests/ -q --ignore=tests/data_test`。Expected: 0 failed。
- [ ] **Step 3: 静态检查和文档。** 更新 08/12 及交接文档，记录真实结果和未验证项；Run: `bash scripts/check-progress-docs.sh && bash scripts/git-finalize-check.sh && git diff --check`。Expected: 全过。
- [ ] **Step 4: 部署 ECS 验收。** 备份线上 `new.html` 与 `lab-theme.css`，只同步这两个生产文件并重启 `qre-saas`；不部署测试/文档，不重启 worker。校验 SHA256、公网 200 和弹窗标记。返回服务状态、备份路径和验收链接；不 commit、不 push。
