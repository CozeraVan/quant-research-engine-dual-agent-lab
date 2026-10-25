# 因子语义注册表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一个版本化注册表统一自选因子的中文展示/搜索与 NL 的确定性别名解析，canonical 和回测行为保持不变。

**Architecture:** `factor_registry.json` 保存语义，`gui/factor_registry.py` 提供只读归一化索引、校验与消歧。metadata 和弹窗消费展示字段；NL 在现有纠错/编译边界调用解析器，Prompt 不承载全量别名。

**Tech Stack:** JSON、Python、Jinja/JavaScript、pytest、Node VM、现有 Playwright/Chromium。

## Global Constraints

- 权威设计：`docs/superpowers/specs/2026-10-25-factor-registry-design.md`。
- canonical `schema.table.column`、YAML、快照、隐藏 select、回测结果不变。
- 同名未说明价格口径时默认 close 并提示；其他歧义返回候选，不猜。
- 不全量注入别名到 Prompt，不新增 API/依赖，不运行真实全量回测。
- 每阶段 TDD；提交、push、ECS 部署分别按用户当时授权执行。

---

### Task 1: 注册表、加载器与防漂移校验

**Files:**
- Create: `configs/factor_registry.json`
- Create: `src/quant_research_engine/gui/factor_registry.py`
- Create: `tests/test_factor_registry.py`
- Modify: `src/quant_research_engine/gui/factor_catalog_llm.py`

**Interfaces:**
- Produces: `normalize_alias(text)->str`、`FactorRegistry.resolve(text, price_basis=None)->Resolution`、`validate_registry(snapshot)->list[str]`。
- `Resolution` 包含 `status: unique|ambiguous|missing`、`canonical: str|None`、`candidates: list[str]`、`price_basis: str|None`、`notice: str|None`。

- [ ] **Step 1: 写失败测试。** 覆盖中英文/全角/空格归一化，canonical 精确命中，DEA/信号线→macds，MACD 三输出，ema_5 多候选默认 close 并 notice，typical_price 显式选择，非价格歧义返回 candidates，unknown 返回 missing，坏 canonical 和未注册新列产生校验报告。
- [ ] **Step 2: 验证 RED。** Run: `/home/van/.local/bin/uv run python -m pytest tests/test_factor_registry.py -q`。Expected: 模块或函数不存在。
- [ ] **Step 3: 最小实现。** JSON 包含 market_fields、tables、factors；常用行情、EMA/MACD/RSI/布林及现有类别骨架先行，规则生成中文名，特殊项人工补全。加载器建立 canonical 与 alias 反索引，兼容目录快照校验；不访问数据库。
- [ ] **Step 4: 验证 GREEN。** Run: `/home/van/.local/bin/uv run python -m pytest tests/test_factor_registry.py -q`。Expected: 全部 PASS；校验当前快照无失效 canonical。

### Task 2: metadata 与弹窗中文化

**Files:**
- Modify: `scripts/sync_saas_metadata.py`
- Modify: `src/quant_research_engine/gui/factor_wizard.py`
- Modify: `src/quant_research_engine/gui/saas/templates/new.html`
- Test: `tests/test_gui_factor_wizard.py`
- Test: `tests/test_gui_saas.py`
- Test: `tests/test_saas_factor_picker.py`

**Interfaces:**
- Consumes: Task 1 注册表与现有 `build_factor_groups()`。
- Produces: metadata item 增量 `zh/canonical/price_basis/aliases`；前端原 value 不变，缺字段回退旧 label。

- [ ] **Step 1: 写失败测试。** 断言 metadata 新字段透传；弹窗按钮/三栏/搜索显示中文与口径、canonical 辅助可对照，中文和英文别名均可命中；同名 close/typical_price 可区分；隐藏 select/YAML 不变。
- [ ] **Step 2: 验证 RED。** Run: `/home/van/.local/bin/uv run python -m pytest tests/test_gui_factor_wizard.py tests/test_gui_saas.py tests/test_saas_factor_picker.py -q -k 'registry or chinese or alias'`。Expected: 新断言 FAIL。
- [ ] **Step 3: 实现展示链路。** metadata 仅增字段；`FACTOR_OPTIONS` 读取 zh/canonical/basis/aliases，按钮与列表中文优先，搜索拼接中文、别名、族与 canonical，不修改选择/change 契约。
- [ ] **Step 4: 验证 GREEN 与真实浏览器。** Run 同上全部 PASS；用 8091 staging + 现有 Chromium 验证桌面 1280/移动 375 的搜索、三级选择、同名口径和 YAML，截图 `.tmp/factor-registry/`。

### Task 3: NL 确定性别名接入

**Files:**
- Modify: `src/quant_research_engine/gui/factor_correction.py`
- Modify: `src/quant_research_engine/gui/nl_compiler.py`
- Modify: `src/quant_research_engine/gui/factor_catalog_llm.py`
- Modify: `scripts/gen_factor_catalog_llm.py`
- Test: `tests/test_gui_factor_correction.py`
- Test: `tests/test_nl_factor_pipeline.py`

**Interfaces:**
- Consumes: `FactorRegistry.resolve` 和现有 `auto_fix_column/correct_factor_fields`。
- Produces: 注册表精确别名优先、价格口径 notice、候选列表；`COMMON_FACTOR_TARGETS` 由注册表派生，旧子串 aliases 仅作 legacy 兜底。

- [ ] **Step 1: 写失败测试。** 验证 DEA/信号线/macd_signal→macds，中文“20日指数均线”→对应 ema，MACD 三输出不混淆，ema_5 默认 close 有提示，显式典型价正确，其他歧义给候选；Prompt 不包含全量 aliases。
- [ ] **Step 2: 验证 RED。** Run: `/home/van/.local/bin/uv run python -m pytest tests/test_gui_factor_correction.py tests/test_nl_factor_pipeline.py -q -k 'registry or alias or dea or chinese'`。Expected: 新断言 FAIL。
- [ ] **Step 3: 接入纠错边界。** 在现有子串替换前调用注册表；唯一命中走 canonical，歧义保留候选，notice 并入 warnings；缺少参数用已批准默认值并提示。不要改变 DSL、回测或旧 YAML。
- [ ] **Step 4: 验证 GREEN 和小样本。** 同上 PASS；以固定 NL 样本调用 stub LLM/纠错路径，不消耗真实模型额度，不运行全量回测。

### Task 4: 全量回归、长期文档与发布门禁

**Files:**
- Modify: `docs/agent/04_TASK_HANDOFF.md`
- Modify: `docs/agent/05_PROGRESS.md`
- Modify: `docs/agent/06_DECISION_LOG.md`
- Modify: `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- Modify: `docs/agent/09_CODING_HANDOFF.md`
- Modify: `docs/agent/10_REVIEW_REPORT.md`
- Modify: `docs/agent/11_AGENT_STATE.md`
- Modify: `docs/agent/12_UI_STYLE_GUIDE.md`
- Modify: `docs/agent/21_FACTOR_LIBRARY_PLAN.md`

**Interfaces:**
- Consumes: Tasks 1–3 的实际实现和证据。
- Produces: 可接续的注册表维护/同步纪律和发布状态。

- [ ] **Step 1: 全量验证。** Run: `/home/van/.local/bin/uv run python -m pytest tests/ -q --ignore=tests/data_test`，再跑模板 Node 解析和 `bash scripts/check-progress-docs.sh && bash scripts/git-finalize-check.sh && git diff --check`。Expected: 0 failed。
- [ ] **Step 2: 记录维护流程。** 新因子必须补注册条目、重新生成 NL 快照和 SaaS metadata；校验缺失不得静默。记录默认价格口径、别名 Prompt 限制和未覆盖回退。
- [ ] **Step 3: 发布。** 仅在用户明确批准后 commit/push；ECS 先备份并同步 metadata、配置和相关生产文件，重启 `qre-saas`，校验中文目录和公网弹窗。不得重启 worker 或运行全量回测。
