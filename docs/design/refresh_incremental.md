# Refresh 增量合并设计（QRE-REFRESH-INCREMENTAL-001）

日期：2026-07-28 ｜ 状态：DESIGN（实现随本文件同批落地）｜ 作者：KIMI_CODE
关联：gui_admin_console.md 日更一节、docs/design/incremental_backtest.md（7 月 P1 增量引擎）。

## 0. 问题

现状 refresh：watermark 前进 1 天也按滚动 2 年窗口**全窗重跑** 111 策略。
用户决策：小水印差只跑新增交易日并**合并**进既有结果；全窗重跑保留为兜底。

## 1. 复用而非新造：7 月增量引擎

`orchestration/incremental.py::run_incremental(store, spec, IncrementalRequest)`
已具备全部所需语义（real-DB gate：分段 ≡ 全跑 字节一致）：

- **检查点**（`incremental_state.py`，per-strategy `state.json`）：每个 symbol 的
  可恢复状态机——持仓数量/入场信息/trailing 锚、待成交订单（存*触发日*而非执行日）、
  现金。**未平仓持仓延续**由此解决：continuation 窗口带 warmup（默认 150 天 ×2）
  且最早回溯到最早持仓入场日前 7 天，持仓与挂单在窗口边界无缝续跑。
- **合并**：orders/trades/failed 台账 concat + 键去重（keep=last）+ 排序重写；
  equity 追加写、汇总时去重。
- **锚定**：buy-hold 锚定原窗口 first_mark_price（summary_inputs.json），
  不因 warmup 起点漂移；flat symbol 现金由累计 orders 精确重放（`_replay_cash`）。
- **聚合重算**：`_recompute_summary` 每次从**拼接后的完整台账**重建 summary.csv
  （总收益/胜率/成本/买入持有/超额），不是增量估计。
- **失效**：config_hash（spec 字节 + 引擎 + profile/stops/universe）不匹配 → 自动
  无检查点 → bootstrap 全跑。

## 2. refresh 编排（mode="incremental"，默认）

```
data_date = 数据 watermark
start, end = 滚动窗口（沿用 window_years=2，bootstrap 用）
对注册表过滤后的每个策略：
  state_dir = outputs/refresh/incremental/<strategy_id>/
  若 checkpoint 存在且 (data_date − last_processed) > 阈值(45 自然日≈30 交易日)
      → 删除 state_dir（大差回退全窗 bootstrap）
  run_incremental(store, spec, IncrementalRequest(
      strategy_path, start, end, output_root=outputs/refresh/incremental,
      apply_stops/universe_filter/codes 与 CLI 参数一致))
  由合并后 summary.csv 写 backtest/summary_metrics.json
  （mean_total_return/total_trades/positive_return_symbol_rate）供 delta 报告复用
state.json 记录 mode=incremental；outputs/refresh/incremental/last_run.json
  记录每策略 watermark/updated/new_rows/duration。
```

- 新策略首次：无 checkpoint → 自动 bootstrap（等价全窗）。
- 水印差 ≤ 阈值：continuation，只加载 warmup + 新增日的 bars（ chunked 400）。
- mode="full"（`--full-window` 或 `--mode full`）：现状行为一字不动。

## 3. 与全窗的等价性边界

- 交易/订单/权益：7 月 gate 已证分段 ≡ 全跑字节一致（同一引擎入口
  `run_working_incremental`，无语义分叉）。
- 聚合指标：由合并后完整台账重算 → 与全跑一致（浮点路径相同）。
- 不等价情形（按全窗语义可接受）：universe_filter 只影响新入场（既有持仓
  保留，incremental_backtest.md §4.3 既定语义）；策略 YAML 变更 → config_hash
  失效 → 自动 bootstrap。
- window 起点随时间前移：滚动窗口 bootstrap 会丢弃起点之前的旧交易——
  这是滚动窗口本身语义；continuation 不会回删旧台账行（long-run 累积）。
  需要严格滚动窗口时跑 `--full-window`。

## 4. 验证

两个真实策略（tf01a_ma_cross_20_120、mr01a_rsi14_oversold_reversal）、
200 只股票、2 年窗：bootstrap 到 D1（watermark−10 交易日）→ 增量续跑到
watermark，对比直接 bootstrap 到 watermark 的合并结果（trades 数、
summary mean total_return、末日权益），差异应只在浮点舍入内。
输出全部到临时目录，不动真实 outputs。
