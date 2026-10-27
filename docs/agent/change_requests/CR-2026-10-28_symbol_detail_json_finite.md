# CR-2026-10-28 个股详情加载失败：JSON 出口非有限浮点硬化

## 背景

线上反馈「打开个股回测详情显示加载失败，请稍后重试」。复现与定位结论：

- 已知页面 job58/920832.BJ 正常；`/saas/jobs/58/symbols/301308` 稳定复现失败，
  HTTP 200、无 console/pageerror 报错，说明异常被 `load()` 的 catch 吞掉。
- 页面内直接 `fetch` 该 API：`SyntaxError: Unexpected token 'N' ... "values":[NaN,NaN,Na"`。
- 根因：`job_58/_symbol_details/301308.SZ.json.gz` 的 `factors[].values` 含裸
  `NaN`（MACD warm-up 段在 PG 里存的是 `double precision NaN` 而非 NULL）。
  Flask 底层 `json.dumps` 默认 `allow_nan=True`，把 NaN 原样写进响应体——
  这不是合法 JSON（ECMA-404），浏览器 `resp.json()` 抛 `SyntaxError`，
  `symbol.html` 走 catch 显示「加载失败，请稍后重试」。
- 同类问题 2026-10-12 已在 worker 侧修过（`_json_sanitize`），但只覆盖
  「写产物」一刻：**云端读取出口不过滤**，历史产物（job_58 产物写于
  2026-10-12 02:08，早于修复上线）继续带毒。
- 影响面：job58 抽样 40 只中 8 只失败，全部为 301xxx.SZ / 001309.SZ
  （上市晚、K 线窗口短，warm-up NaN 占比高）；job66 同源策略同样命中。

## 目标

1. JSON 出口统一硬化：非有限浮点（NaN/±Inf）一律降级 `null`，与缺口同语义，
   前端按既有断线逻辑渲染。
2. 根因同步修：因子查询不再把 DB NaN 放进行列，新产物自身干净。
3. 三处出口（lab 路由 / SaaS `_jsonable` / worker 写产物）共用同一实现，
   不再各写一份后漂移。
4. 不重写历史产物、不动 schema、不动引擎、不改前端交互。

## 边界

- 只改 `lab_result.py`、`saas/app.py`、`worker/runner.py` 及必要测试。
- 不重跑回测、不批量回填历史 gzip 产物（读取出口已覆盖）、不改前端。
- 不新增灰色小字备注。

## 实现（2026-10-28，TDD：先 RED 3 例后 GREEN）

### 改动文件

- `src/quant_research_engine/gui/lab_result.py`
  - 新增 `json_safe(value)`：递归归一化——`datetime/date` → ISO 串，
    非有限浮点 → `None`，dict/list/tuple 递归。三处出口的唯一实现。
  - `_fetch_factor_panels()`：两处因子查询的 `r[1] is not None` 过滤加
    `math.isfinite(float(r[1]))`，DB NaN 按缺口处理，不再进 `raw`。
  - lab 路由 `/api/lab/runs/<run_id>/symbol/<ts_code>/detail`：
    `jsonify(json_safe(data))`。
- `src/quant_research_engine/gui/saas/app.py`
  - `_jsonable()` 改为委托 `lab_result.json_safe`（保留函数名与全部调用点），
    覆盖 SaaS 全部 JSON 响应，含 `/api/results/<job>/symbols/<code>`。
- `src/quant_research_engine/worker/runner.py`
  - `_json_sanitize()` 委托 `lab_result.json_safe`（原递归实现删除），
    写产物与读出口同源。

### 测试

- 新增 `tests/test_json_finite_contract.py`：
  - `test_jsonable_drops_non_finite_floats`：NaN/±Inf → None，日期口径不变；
  - `test_fetch_factor_panels_skips_non_finite_db_values`：DB NaN → None。
- `tests/test_gui_saas.py::TestSymbolDetailJsonFinite`：带 NaN 的历史 gzip
  产物 → 响应体无裸 `NaN` token、可按 ECMA-404 严格解析、NaN 降级为 `null`。
- `tests/test_gui_lab_result.py::test_lab_symbol_detail_response_is_strict_json`。

### 验证

- 单测：`uv run pytest tests/test_json_finite_contract.py "tests/test_gui_saas.py::TestSymbolDetailJsonFinite" tests/test_gui_lab_result.py::test_lab_symbol_detail_response_is_strict_json -q` → 4 passed。
- 相关套件：`tests/test_gui_saas.py tests/test_gui_lab_result.py tests/test_factor_display_contract.py tests/test_json_finite_contract.py` → 152 passed。
- 全量：`uv run pytest tests/ -q` → 2960 passed, 24 skipped。
  另 2 例 `test_saas_public_beta_ops.py::TestConsoleOps` 失败为**存量问题**
  （已在 pristine HEAD worktree 复现，与本次改动无关，window=today 口径相关）。
- 生产（ECS `qre-saas`，部署 `app.py` + `lab_result.py`）：
  - 原始 API `301308` 的 `NaN` token 数 0；
  - 无头 Chromium 打开 job58 的 301308 / 001309 / 301018 / 920832.BJ：
    全部 200、`load_fail=false`、K 线 canvas 正常、console 干净；
  - job58 + job66 各 80 只严格 JSON 扫描：bad=0。

## 发布

- 已按长期指令直接部署 ECS（`deploy/saas/deploy-ecs.sh app.py lab_result.py`），
  回滚副本 `deploy@47.119.127.40:/tmp/qre-deploy-20261027T163118Z.bak`。
- 未 commit / 未 push，待用户验收。
