# CR-2026-10-28 个股详情刷新入口 HTMLCollection 误用修复

## 背景

job#78（私人全期任务）个股回测详情持续「加载失败，请稍后重试」。上一轮
`CR-2026-10-28_symbol_detail_json_finite` 修掉非法 JSON 后仍复现，说明是另一条
独立根因。

定位过程：

- job#78 产物（`_symbol_details/600330.SH.json.gz`）写于 2026-10-21，**NaN token 为 0**，
  因子/K线/交易/风险结构完整，`resp.json()` 不会炸。
- 用真实 job#78 产物在浏览器里逐段跑 `renderSummary/renderEquity/renderWear/
  renderRisk/renderKline/initKlineReplay/table(...)`：**全部 OK，零 pageerror**。
- 补跑 `showSymbolDetailRefresh()`：抛
  `TypeError: (host.children || []).some is not a function`。

**根因**：`symbol.html` 的 `showSymbolDetailRefresh()` 用
`(host.children || []).some(...)` 做去重。真实 DOM 的 `Element.children` 是
`HTMLCollection`——有 `length`/索引/`item`，**没有 Array 的 `some`/`find`**，
浏览器里必抛 `TypeError`，被 `load()` 的 catch 吞掉 → 整页「加载失败，请稍后重试」。

**触发条件**：`d.factor_basis !== 'qfq_anchor_v1' && !d.readonly`。即
**非只读（私人 job）+ 旧口径产物（缺 `factor_basis`，2026-10-27 前写入）**。
经典策略 58/66/74 是 showcase 只读（`readonly=true`），入口被跳过，所以上一轮
只验证只读页面全部通过，没暴露这条路径。

**为什么测试没抓到**：`tests/test_gui_saas_pages.py` 的 `_SYMBOL_JS_HARNESS` 用
普通数组冒充 `element.children`（数组有 `some`/`find`），把线上必抛的写法测成绿灯。

## 目标

1. 修掉 `showSymbolDetailRefresh()` 的 HTMLCollection 误用。
2. 让测试 harness 的 `children` 按真实 DOM 语义（HTMLCollection）模拟，使这类
   「数组方法当 DOM 用」的 bug 以后能被测出来。
3. 显式断言非只读旧详情不得走整页失败分支。

## 边界

- 只改 `symbol.html` 与 `tests/test_gui_saas_pages.py`。
- 不动 worker、引擎、schema、因子注册表、游戏、其它模板。
- 不重跑回测、不重写历史产物、不新增灰色小字备注。

## 实现（2026-10-28，TDD：harness 先 RED，源码修复后 GREEN）

### 改动文件

- `src/quant_research_engine/gui/saas/templates/symbol.html`
  - `showSymbolDetailRefresh()` 去重改为
    `Array.prototype.some.call(host.children || [], fn)`，并注释说明
    HTMLCollection 无 Array 方法、抛错会被 catch 吞成整页失败。
- `tests/test_gui_saas_pages.py`
  - `symbolEl()` 的 `children` 由普通数组改为 `htmlCollectionView()` 生成的
    HTMLCollection 形态（`length` + 索引 + `item`，无数组方法）；内部改用
    `_children` 维护，`appendChild`/`replaceChildren`/`textContent` setter 同步。
  - 新增 `childById(host, id)`（`Array.prototype.find.call`）供
    `generateButton()`/`refreshButton()` 使用。
  - `test_symbol_detail_refresh_entry_for_legacy_payload` 增加
    `assert.equal(h.calls.failure, 0, '旧口径非只读详情不得整页加载失败')`。

### 测试

- TDD：先改 harness → `test_symbol_detail_refresh_entry_for_legacy_payload` RED
  （复现线上：刷新入口不出现）；再修源码 → GREEN。
- 命令与结果：
  - `uv run pytest tests/test_gui_saas_pages.py -q` → 94 passed
  - `uv run pytest tests/ -q --deselect tests/test_saas_public_beta_ops.py::TestConsoleOps`
    → 2960 passed, 24 skipped（2 例 ConsoleOps 为存量失败，pristine HEAD 已复现）

### 生产验证（真实浏览器，ECS SSH 隧道）

- 部署 `symbol.html`，新 MainPID 510277，回滚副本
  `/tmp/qre-deploy-20261027T165032Z.bak`。
- 真实 DOM 断言：`#sym-note` 的 `children` 为 `[object HTMLCollection]`、
  `children.some === undefined`；调用 `showSymbolDetailRefresh()` 不再抛错，
  按钮文案「刷新详情」，重复调用幂等（count=1），零 pageerror。
- 端到端：把真实 job#78 产物（缺 `factor_basis`、`readonly=false`）灌进
  `apiFetch` 后跑 `load()` → `showSymbolLoadFailure` 调用 0 次、
  K 线 canvas 渲染、`sym-note` = 「数据截止 2026-10-20 全量 3945 个交易日」+
  刷新入口、页面无「加载失败」文案。
- 回归：job58/920832.BJ、job58/301308、job66/300308.SZ 均 200 正常渲染。

## 发布

- 已按长期指令直接部署 ECS；未 commit / 未 push，待用户验收。
