# Implementation Brief

## Task ID

QRE-GUI-PROMO-GATE-001（全量回测结果成为晋升后的状态闸）

## Created By

KIMI_CODE（用户 2026-08-20 直接指定的任务书；承接 76045d2「冒烟闭环+晋升闸」）

## Intended Implementer

KIMI_CODE

## Goal

让晋升触发的全量回测结果真正影响策略状态，而不是跑完就完：

1. **晋升回测打标记**：`/api/strategies/promote` 触发的全量回测 run 记录加
   `promotion_gate=True` + 策略名标记（复用 `run_backtest(mark=...)` 预合并机制，
   在线程启动前写入 record，沿用上一轮修过的竞态结论）；force 晋升加
   `promotion_forced=True`。
2. **收尾评估钩子**：`_execute_and_finalize` 尾部新增钩子，对带 `promotion_gate`
   标记的 run 完成后读取 `extract_run_summary` 指标（total_trade_count /
   strategy_total_return / excess_return_vs_buy_hold / max_drawdown），按写死判据
   **交易次数 ≥ 30 且 excess_return_vs_buy_hold > 0** → gate=passed，否则 failed
   （run failed 也记 failed）。结果原子写到 `outputs/refresh/gates/<name>.json`
   （与 registry.json/state.json 同族的状态存储，不进 git 管理的 catalog）。
3. **日更联动**：refresh 拾取策略时跳过 gate=failed 且非 forced 的策略
   （gate 缺失=未评估=正常拾取，兼容存量策略）；跳过名单记入 batch config
   （`gate_skipped`）并打印日志。GUI 侧 `list_catalog_strategies` 加
   `skip_failed_gate` 可选参数（默认 False 不动注册/开关校验语义）。
4. **dashboard 展示**：admin.html 策略状态 tab 加一列「全量回测闸」：
   passed=绿 / failed=红（title tooltip 展示交易次数与超额）/ 未评估=灰 /
   forced 晋升的策略显示「强制在库」（failed 不阻止日更，仅展示）。
5. **force 通道**：force 晋升 gate 评估照跑；API 响应注明「force 晋升：闸结果
   仅展示，不阻止日更」。
6. **预留四关验证接口**：`POST /api/strategies/<name>/deep-validate` 端点骨架，
   返回 501 + 设计说明（策略 YAML→逐日股票池转换器未实现），不写转换逻辑。

## Semantics

- gate 判据写死在 `strategy_create.py`：`GATE_MIN_TRADES = 30`，
  passed ⇔ total_trade_count ≥ 30 且 excess_return_vs_buy_hold > 0。
- gate 文件 `outputs/refresh/gates/<name>.json`：
  `{strategy, run_id, gate: passed|failed, forced, metrics, criteria, evaluated_at}`
  或 run 失败时 `{..., gate: failed, error}`。原子写（tmp + os.replace）。
- 日更跳过条件：`gate == "failed" and not forced`；forced 策略永远随日更跑。
- dashboard 三态 + forced：passed 绿 / failed 红（forced 时改显「强制在库」橙）/
  无 gate 文件灰「未评估」。

## Scope

1. `gui/strategy_create.py`：判据常量 + `finalize_promotion_gate(record)`。
2. `gui/refresh_registry.py`：gate 读写（`GATES_DIR`/`gate_path`/`load_gate`/
   `save_gate`/`load_all_gates`）；`list_catalog_strategies` 加可选 skip 参数；
   `refresh_overview` 行加 `gate` 字段。
3. `gui/engine.py`：`_execute_and_finalize` 尾部 promotion_gate 钩子（兜底 try）。
4. `gui/app.py`：promote mark 加 promotion_gate/promotion_forced；force 响应注明；
   新增 deep-validate 501 端点。
5. `scripts/refresh_batch.py`：gate=failed 非 forced 跳过 + 日志 + config 记录。
6. `gui/templates/admin.html`：策略状态表加「全量回测闸」列。
7. tests：test_gui_strategy_create.py（gate 评估判据）、test_gui_admin_p3b.py
   （list_catalog_strategies skip + refresh_overview gate 字段）、
   test_gui_admin_strat_tab.py 或新文件（dashboard 列渲染、refresh_batch 跳过）、
   test_gui_app.py（force 语义、501 端点）。
8. docs/agent 08/10/09/05/11 同步。

## Non-Goals

- 不 git commit、不重启 qre-gui.service；不改 catalog YAML；不写策略→信号池
  转换器（deep-validate 只留骨架）；不改既有 include/stopped 注册表格式。

## Expected Tests

- gate 评估：passed/failed/缺指标/run 失败/forced 标记透传。
- 日更：gate=failed 跳过、forced 不跳过、无 gate 正常拾取、refresh_batch 过滤。
- dashboard：refresh_overview 行含 gate；admin.html 含新列表头与渲染函数。
- API：promote force 响应注明；deep-validate 501 + 设计说明字段。
- `uv run pytest tests/ -x -q` 全绿（基线 1437）。
