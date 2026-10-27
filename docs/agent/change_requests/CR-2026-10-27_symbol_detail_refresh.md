# CR-2026-10-27 历史旧个股详情按需刷新

## 背景

价格型因子已改为在 GUI 呈现层按 K 线前复权锚点换算，但历史任务回传的 `_symbol_details/*.json.gz` 仍是旧口径。当前按需生成接口只要产物存在就直接 `ready`，用户无法刷新旧详情。

本 CR 做一个最小可用切片：给详情加口径标记，旧产物可一键按需刷新。

## 目标

1. `build_lab_symbol_detail()` 输出新增 `factor_basis` 标记，例如 `qfq_anchor_v1`，用于区分新口径详情。
2. `POST /api/results/<job_id>/symbols/<ts_code>/generate` 支持 `refresh=1`：即使详情产物已存在，也允许重新生成；未完结同标的任务继续复用。
3. 前端个股详情页在检测到旧产物（缺 `factor_basis` 或值过期）时显示“刷新详情”入口；点击后调用刷新接口，轮询 `gen-status`，完成后重载详情。
4. 新产物刷新后价格型因子与 K 线同尺度；旧产物不被批量回填，只按需刷新。

## 边界

- 只改 `lab_result.py`、`saas/app.py`、`saas/templates/symbol.html` 及必要测试。
- 不改 worker（已支持幂等覆盖）、引擎、schema、游戏、因子注册表。
- 不跑回测、不批量刷新历史产物、不部署 ECS（主 Agent 复核后部署）、未 commit/push。
- 不新增灰色小字备注；刷新入口用既有按钮/tip 机制。

## 测试与验收

- TDD：先 RED 后 GREEN。
- 覆盖：
  - `build_lab_symbol_detail` 新产物带 `factor_basis`；
  - generate 接口 `refresh=1` 绕过 ready 并建任务；无 refresh 时保持幂等 ready；
  - 前端在缺 `factor_basis` 时显示刷新入口，点击调用 `?refresh=1` 并轮询重载；
  - 现有 symbol detail/on-demand 测试不回归。
- 命令：
```bash
uv run pytest tests/test_gui_lab_result.py tests/test_gui_saas.py tests/test_saas_symbol_ux.py tests/test_gui_saas_pages.py -q
uv run pytest tests/ -q
```

## 发布

- 测试通过后由主 Agent 部署 ECS，仅同步实际改动文件并重启 qre-saas；用户验收前不 commit/push。

## 实现记录（2026-10-27，TDD：先 RED 3 例后 GREEN）

### 改动文件

- `src/quant_research_engine/gui/lab_result.py`：新增模块常量
  `FACTOR_BASIS_QFQ_ANCHOR_V1 = "qfq_anchor_v1"`；`build_lab_symbol_detail()`
  输出新增 `data["factor_basis"]` 标记（价格型因子已按 K 线前复权锚点换算）。
  worker `_execute_symbol_detail` 经同一函数生成 gzip，新产物自动携带；
  历史旧产物无该字段。
- `src/quant_research_engine/gui/saas/app.py`：`api_symbol_detail_generate`
  支持 `refresh=1`（兼容 `true`/`yes`）：即使 `_symbol_detail_ready()` 为真
  也继续创建刷新任务；未完结同标 `symbol_detail` 任务继续复用（逻辑不变）；
  `refresh` 缺省时保持既有幂等 `ready` 行为。只读分享/经典策略 403 前置不变。
- `src/quant_research_engine/gui/saas/templates/symbol.html`：`load()` 渲染成功后
  判断 `d.factor_basis !== 'qfq_anchor_v1'`（缺字段或值过期）即调
  `showSymbolDetailRefresh()`：在头部「数据截止」旁追加既有 `btn-sm` 样式按钮
  `#btn-refresh-detail`（文案「刷新详情」，`dataset.tip` 走 LabUI.helpTips 既有
  机制，无新增灰字备注）；点击 POST `generate?refresh=1`，`ready`/活跃态复用
  既有 `pollGen()` 轮询 `gen-status`，完成后 `load()` 重载；分享只读视图
  （SHARE_TOKEN）不出入口；新口径产物不显示入口。
- 测试：
  - `tests/test_gui_lab_result.py`：`test_symbol_detail_factor_basis_marker`。
  - `tests/test_gui_saas.py`：新增 `TestSymbolDetailRefresh` 3 例（refresh=1
    绕过 ready 并建任务、未完结复用不重复建、无产物时 refresh/缺省均建任务），
    autouse fixture 把 `SAAS_UPLOAD_DIR` 指到 tmp_path。
  - `tests/test_gui_saas_pages.py`：harness 增 `refreshButton()`；2 例前端行为
    （旧产物出现入口→点击调 `?refresh=1`→轮询→ready 重载→入口消失；
    新产物无入口且零请求）。

### 验证结果

- RED：3 个核心新测试先失败（无 factor_basis / refresh 被 ready 拦掉 / 无入口）。
- `uv run pytest tests/test_gui_lab_result.py tests/test_gui_saas.py tests/test_saas_symbol_ux.py tests/test_gui_saas_pages.py -q`
  → 261 passed。
- 相关回归：`uv run pytest tests/test_worker.py tests/test_saas_result_contract.py tests/test_saas_access_hardening.py -q`
  → 119 passed。
- `uv run pytest tests/ -q` → 见交付说明（全量结果）。

### 已知限制 / 遗留

- 刷新入口对 showcase 经典策略（匿名只读）仍会显示，点击后 403 仅静默恢复按钮
  （详情 GET 200 通道不返回 readonly 标记，未扩大 payload 合同）；分享链接视图
  已用 SHARE_TOKEN 屏蔽。如需彻底屏蔽可在后续切片给详情 200 响应加 readonly 标记。
- `data-tip` 文案提到「不改变回测结果」为口径说明；刷新只重算详情展示层因子口径。
- 未批量刷新任何历史产物；仅提供按需入口。
