# Implementation Brief

## Task ID

QRE-GUI-FACTOR-REGISTRY-001（因子语义注册表：中文展示/搜索 + NL 确定性别名解析）

## Created By

KIMI_CODE（2026-10-25；设计经用户批准，见
`docs/superpowers/specs/2026-10-25-factor-registry-design.md`，
任务书 `docs/superpowers/plans/2026-10-25-factor-registry.md`）

## 根因与目标

自选因子界面只有英文列名，中文用户无法识别常见指标；NL 编译靠 LLM 猜列名 +
子串别名兜底，中文习惯名（DEA/信号线/20日指数均线）无法映射，且常用因子清单手写
漂移。建立**单一因子语义来源**：版本化 `configs/factor_registry.json` + 只读加载层
`gui/factor_registry.py`，展示与解析共用。**数据契约完全不变**——canonical
`schema.table.column`、YAML、回测、隐藏 select、条件快照、策略还原零改动；
`/api/saas/factors` 只增 `zh`/`canonical`/`price_basis`/`aliases` 字段。

## 实施步骤

1. TDD：新建 `tests/test_factor_registry.py`（40 项）——归一化、canonical 精确命中、
   DEA/信号线/macd_signal→macds、MACD 三输出、ema_5 多候选默认 close + notice、
   显式 typical_price、非价格歧义返回 candidates、unknown→missing、坏 canonical 与
   未注册新列的校验报告、覆盖报告。
2. 实现注册表与加载层：`scripts/gen_factor_registry.py`（FAMILY_RULES 规则生成 +
   MANUAL_ENTRIES 人工维护 + CORE_TARGETS 核心示例 + EXTRA_ALIASES 跨条目别名）生成
   `configs/factor_registry.json`；`gui/factor_registry.py` 提供 `normalize_alias`、
   `FactorRegistry.resolve`、`validate_registry`、`coverage_report`、`duplicate_aliases`，
   不访问数据库。未维护条目的 `zh` 为 null，**不伪造中文名**。
3. metadata 与弹窗中文化：`factor_wizard.build_factor_groups` 每项带注册表增量字段；
   `new.html` 新增 `PRICE_BASIS_ZH`/`fpFactorLabel`/`fpBasisZh`/`fpItemText`/`fpSubLabel`/
   `fpSearchHaystack`，按钮/三栏/搜索结果中文名为主 + 口径可见 + canonical 悬停对照，
   搜索匹配中文名/别名/canonical/列名/大类子类；选择与 change 契约不改。
4. NL 接入：`factor_correction.registry_resolve_column` 在旧子串别名前调用；
   `COMMON_FACTOR_TARGETS` 由注册表 core 条目派生；notice 并入 warnings；
   Prompt 不注入全量别名。`gen_factor_catalog_llm.py`/`sync_saas_metadata.py`
   导出时跑注册表校验 + 覆盖报告。
5. 回归 + 真实 Chromium 双视口 + 长期文档同步；**未经批准不 commit、不 push、不部署 ECS**。
6. 追加 QRE-NL-HOLDING-DEFAULT-001：真实 NL 抽查发现缺 holding/模型编造天数。按用户决定，未说明期限统一 `max_holding_days: 0`，明确期限保留，缺段补齐且保持其他 YAML 原文；staging 配置真实编译后重测五类策略，不运行回测。

## Validation

- `uv run python -m pytest tests/test_factor_registry.py -q` → 40 passed。
- `uv run python -m pytest tests/test_gui_factor_wizard.py tests/test_saas_factor_picker.py
  tests/test_gui_saas_pages.py -q` → 38 + 13 + 74 passed。
- `uv run python -m pytest tests/test_gui_factor_correction.py
  tests/test_nl_factor_pipeline.py tests/test_gui_nl_compiler.py
  tests/test_factor_registry.py -q` → 95 passed。
- 全量 `uv run python -m pytest tests/ -q --ignore=tests/data_test` → 2533 passed, 5 skipped。
- `QRE_MARKET_DB_URL=... uv run python scripts/gen_factor_catalog_llm.py` → 注册表校验通过，
  覆盖 554/895（61.9%）。
- `QRE_MARKET_DB_URL=... uv run python scripts/sync_saas_metadata.py --out deploy/saas/metadata.json`
  → 校验通过，367052 bytes / 因子 902 项。
- 渲染后 new.html 内联脚本 Node 解析通过（`test_render_new_page_inline_script_parses`）。
- `bash scripts/check-progress-docs.sh && bash scripts/git-finalize-check.sh && git diff --check`。
- 真实 Chromium（8091 staging）桌面 1280×900 与移动 375×812 各 13 项通过，零 JS error、
  零页面横向溢出；证据 `.tmp/factor-registry/`。
- 不运行真实全量回测、不调用真实 LLM；不得以单元测试代替真实浏览器验收。

---

## Archive: QRE-SAAS-FACTOR-PICKER-MODAL（自选因子三栏弹窗选择器；Kimi 独立实施）

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
