# CR-2026-10-11 SaaS 生产事故修复：job 54 smoke 全市场超时 + 关联三 bug

- 状态：已实现并测试，**未 commit**（待用户批准后 commit + 部署 + 重启本机 qre-saas-worker）
- 事故现场：job 54（kind=smoke，NL「MACD金叉死叉」）23:58 起跑，10 分钟硬超时标记 expired，
  worker 子进程继续跑 25 分钟；产物目录 5533 个股票目录——smoke 跑了全市场。
  py-spy 栈：`runner.py:192 build_symbol_detail_files → lab_result.py:803 build_lab_symbol_detail
  → :372 _symbol_trade_stats → :65 _f`，逐 symbol 重复全量解析 round_trips.csv（27037 行）。
  另：job 53 曾因 `holding.max_holding_days 必须是 1..1000 的整数` 校验失败（用户语义 0=不限）。

## Bug 1：smoke 没有限定小样本（核心）

- 根因 A：`gui/engine.py apply_precheck()` 对空 codes（scope=all_a）原样返回空列表 = 全市场。
  修复：precheck 且 codes 为空时，经 `_sample_random_universe(max_codes, seed=run_id, db_url)`
  从全 A 池随机抽样（默认 PRECHECK_MAX_CODES=20 只，种子 run_id 可复现）。抽样需要本地行情库；
  DB 不可用时抛错使 run 失败——宁可失败也绝不再静默全市场。
- 根因 B：worker 侧 smoke 的后处理范围未裁剪。`worker/runner.py execute_job` 在
  `kind=smoke` 时跳过 `build_lab_tag_analysis` 与 `build_symbol_detail_files`
  （`symbol_details_meta = {"count": 0, ..., "skipped": "smoke"}`，chart_data.tag_analysis=None）；
  `build_lab_chart_data` 与 `_fill_excess_return` 保留（smoke 需要成交数/收益/费用/净值曲线
  证明链路通）。8081 lab 的 precheck→full_params 链不经过 worker 此段，行为不变。

## Bug 2：max_holding_days=0 语义

- `security/yaml_guard.py`：校验放宽为 0..1000 整数（0=不限），显式 null 合法。
- `strategies/spec.py`：键缺省保持历史默认 1 日；显式 0/null → holding_days=0。
- `strategies/compiler.py`：`rules.get(...) or experiment.get(...)` 会把 0 当 falsy 穿透，
  改为按 None 逐层回退，0 原样保留。
- 引擎执行层（0=不触发 holding_period 强平，其余退出路径不变）：
  - `portfolio/single_symbol.py`：holding_period 分支加 `holding_days > 0` 守卫；校验改 `< 0` 拒绝。
  - `portfolio/single_symbol_vectorized.py`：到期 bar 不再入堆（入场/状态恢复两处）+
    holding_period 判定守卫；校验改 `< 0` 拒绝。
  - `portfolio/shared.py`：holding_days<=0 时只认止损/止盈/exit_signal（登记 pending），
    永不到期强平；校验改 `< 0` 拒绝。`portfolio/batch.py` 校验同步放宽。
- 顺带修复同一语义的 0 值问题：`risk.stop_loss_pct/take_profit_pct/trailing_stop_pct`
  校验由 (0,1) 放宽为 [0,1)（0=不启用）；spec 新增 `_optional_pct` 把 0 归一为 None——
  否则引擎 `is not None` 判定会把 0.0 武装成立即触发止损。

## Bug 3：lease 丢失后 worker 继续执行

- `worker/daemon.py`：心跳循环加连续失败计数（`max_heartbeat_failures=3`，构造参数可配），
  成功即清零；达到阈值判定 lease 丢失（任务不存在/非运行中/leased_by 不匹配），
  置 canceled 事件——多槽子进程模式经 `slots.execute_job_subprocess(is_canceled=...)`
  terminate 子进程、释放槽位；单体模式跑完丢弃结果。结果不回传（服务端已过期，
  回传也会被拒），任务由云端按租约过期重排。单次抖动不杀任务（有专项测试）。

## Bug 4：build_symbol_detail_files 的 O(n²)

- `gui/lab_result.py build_lab_symbol_detail` 新增关键字参数 `stats=` 与
  `round_trips_by_symbol=`（缺省 None 时维持原现场计算，GUI 单股路由不受影响）。
- `worker/runner.py build_symbol_detail_files`：round_trips.csv 解析一次
  （`_symbol_trade_stats` 一次聚合 + 一次按 symbol 预分组），逐股调用传入复用。
  两处 O(n²) 点（stats 聚合 + trades 兜底分支各重读一次全量 CSV）都消除。

## 测试

- 新增/更新：
  - `tests/test_gui_workbench.py`：`test_apply_precheck_keeps_empty_codes`（断言空 codes 放行）
    改写为 `test_apply_precheck_samples_when_codes_empty`（mock 抽样、seed 可复现）。
  - `tests/test_security_sandbox.py`：`test_max_holding_days_zero_means_unlimited`
    （0/null/缺省合法，1001/1.5 拒绝）、`test_risk_zero_means_disabled`
    （0 校验通过且 spec 归一为 None）。
  - `tests/test_portfolio_single_symbol.py`：holding_days=0 持有到末尾 / 0 仍认 exit_signal /
    -1 拒绝，共 3 例。
  - `tests/test_worker.py::TestHeartbeatLeaseLoss`：连续失败 3 次终止任务不回传 /
    单次抖动正常完成，共 2 例。
  - `tests/test_saas_symbol_ux.py`：`test_round_trips_parsed_once_for_many_symbols`
    （stats 恰好 1 次、round_trips.csv 全文读取恒 2 次与股票数无关）；3 处既有
    monkeypatch lambda 补 `**kw` 适配新签名。
- 结果：`-k saas` 238 passed（基线 237+1）；`-k "saas or workbench or security or portfolio or
  compiler or worker or spec"` 全绿。

## 小样本实测证据

- `apply_precheck([], ..., max_codes=1, seed="job54-repro")` 真库抽样 → `['000333.SZ']`，
  窗口截到 180 天；同 seed 复现一致；默认 20 只。
- NL MACD YAML（dif/dea 因子、`holding.max_holding_days: 20`、`risk.stop/take: 0`）
  `validate_strategy_yaml` 通过；`max_holding_days: 0` 通过且 spec 解析
  `holding_days=0, stop_loss_pct=None, take_profit_pct=None`。

## 部署注意

- 无 DB 迁移；commit 后需重启本机 qre-saas-worker 以加载新 runner/daemon 链路。
