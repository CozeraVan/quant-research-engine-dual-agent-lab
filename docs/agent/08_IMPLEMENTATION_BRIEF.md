# Implementation Brief

## Task ID

QRE-SAAS-FACTOR-PICKER-MODAL（自选因子三栏弹窗选择器；Kimi 独立实施）

## Created By

KIMI_CODE（2026-10-25；设计经用户批准，见
`docs/superpowers/specs/2026-10-25-factor-picker-modal-design.md`，
任务书 `docs/superpowers/plans/2026-10-25-factor-picker-modal.md`）

## 根因与目标

自选因子（入口 2）条件行原在一行内堆叠「大类 / 子类 / 因子」三个下拉，因子库有
数百项时长下拉难以浏览定位。改为：每个因子位置一个「当前因子选择按钮」+ 三栏联动
弹窗 + 名称/字段搜索。**数据契约完全不变**——`.wz-left`/`.wz-rfield` 的 select 仍是
唯一值来源，`readGroup()`、`snapshotWzArea()`、`usedFactors()`、YAML 预览、固定值切换、
策略还原、price basis 归一逻辑零改动。

## 实施步骤

1. TDD：新建 `tests/test_saas_factor_picker.py`。静态断言弹窗结构（三栏 / 搜索 / 关闭 /
   ARIA）；Node VM 验证打开 → 父子联动 → 最终因子写回隐藏 select、按钮文本更新、
   派发一次 change、关闭并归还焦点；连续打开不重复创建；Esc / 遮罩 / 关闭按钮只关不改值；
   搜索过滤 / 清空恢复 / 空态 / 搜索选中；向导既有回归（条件增删、AND/OR、固定值、
   快照与还原）。
2. 实现：`makeFactorSelect` 保留三个 select 为隐藏数据字段并新增 `.factor-select-btn`；
   `syncFactorSelect` 末尾同步按钮；新增 `openFactorPicker`/`closeFactorPicker`/
   `syncFactorPickerButton`/`fpRender`/`fpPick`/`fpList`，复用 `FACTOR_OPTIONS`、
   `factorGroups()`、`factorSubs()` 与既有目录加载结果，**不新增 API、不加依赖**。
3. 样式全部落在 `static/lab-theme.css`：复用 `.modal-mask`/`.modal` 组件与紫色
   主题变量，无新色相、无循环动效；移动端（768px）接近全宽 + 视口限高 + 三栏降单列堆叠、
   各自内部滚动，禁止页面横向溢出。
4. 真实 Chromium 验收：本地 staging 8091，桌面 1280×900 与移动 375×812 分别完成左右
   因子三级选择、搜索与清空、连续三次开关、Esc / 遮罩 / 关闭按钮、焦点返回与 Tab 焦点锁、
   按钮与 YAML 值一致、固定值切换、条件增删与 AND/OR；截图存 `.tmp/factor-picker-modal/`。
5. 回归 + 静态检查 + 长期文档同步；部署 ECS 供用户验收；未经批准不 commit、不 push。

## Validation

- `uv run python -m pytest tests/test_saas_factor_picker.py -q` → 10 passed。
- `uv run python -m pytest tests/test_gui_saas_pages.py tests/test_saas_factor_picker.py -q` → 83 passed。
- `uv run python -m pytest tests/test_gui_saas.py tests/test_gui_saas_pages.py
  tests/test_saas_authing.py tests/test_gui_lab.py tests/test_saas_symbol_ux.py
  tests/test_saas_help_copy.py tests/test_saas_factor_picker.py -q` → 242 passed。
- 全量 `uv run python -m pytest tests/ -q --ignore=tests/data_test` → 2474 passed, 5 skipped。
- 渲染后 new.html 内联脚本 Node 解析通过（`test_render_new_page_inline_script_parses`）。
- `bash scripts/check-progress-docs.sh`、`bash scripts/git-finalize-check.sh`、`git diff --check`。
- 真实 Chromium 64/64 项检查通过（桌面 + 移动两视口合计），无 JS error、无页面横向溢出。
- 不运行真实全量回测；不得以单元测试代替真实浏览器验收。
