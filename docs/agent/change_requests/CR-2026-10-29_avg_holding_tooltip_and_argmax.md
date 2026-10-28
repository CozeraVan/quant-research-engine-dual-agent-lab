# CR-2026-10-29 平均持股周期「无数据」成因提示 + 链路测试 + node -e ARG_MAX 修复

状态：已实施，未 commit/push（等用户验收）
关联：`CR-2026-10-28_holding_period_and_risk_adjusted.md`（引入平均持股周期）

## 1. 缘起（用户提问）

「为什么回测结果中的『平均持股周期』中没有数据？」

## 2. 根因（已用生产库数据实证，非猜测）

对 job 58/66/74/78 查生产库：

| job | `summary.average_bars_in_trade` | `chart_data.metrics.avg_holding_days` | `trades.total` | `trades.sampled` | `points` |
|---|---|---|---|---|---|
| 58 | 无 | 无 | 245,166 | **true** | 500 |
| 66 | 无 | 无 | 232,780 | **true** | 500 |
| 74 | 无 | 无 | 120,818 | **true** | 500 |
| 78 | 无 | 无 | 401,247 | **true** | 500 |

两个原因叠加：

1. **该字段是 2026-10-28 新增的**，这四个 job 的 `results` 行早在之前写入，快照里没有
   `average_bars_in_trade` / `avg_holding_days`；
2. **前端回退路径被正确阻断**：`_trade_points` 对 >500 笔的任务按 `|net_return|` 降序
   只留 500 笔（即**收益最大的极值样本**），用它算均值会是错的，所以
   `renderMetrics` 的回退条件写了 `!sampled`。

**没有数据源可以重算**：本地 run 产物已清空（`outputs/gui-console/runs` 0 个目录）、
SaaS 库只有 `results` 一张表（无交易表）、symbol 详情 gzip 只覆盖被查看过的个股
（有偏样本）。所以对存量 job 只能显示「—」。

**新回测不受影响**：worker 走 `lab_result.build_lab_chart_data`（本轮已把三个键加进
`metrics`），`strategy_performance.json` 本就有 `average_bars_in_trade`。

## 3. 修复

### 3.1 「—」必须说清成因（否则用户只会以为又是 bug）

- `job.html`：`holdTip` 分两种文案——有值时讲口径；无值时讲明
  「全量回测的交易散点为控体积只采样了收益最大的 500 笔，不能用来算均值；
  2026-10-28 之前完成的任务快照里也还没有这个字段。重新提交回测即可显示。」
- `symbol.html`：个股级 `trades` 全量在快照里，正常一定有值；缺了说明
  「没有已完成的买卖交易，或成交记录未提供入场/出场日期」。

### 3.2 锁死三条链路（防以后再断）

| 测试 | 锁什么 |
|---|---|
| `test_gui_lab_result.py::test_chart_data_metrics_carry_avg_holding_days` | `strategy_performance.json` → `build_lab_chart_data(metrics)` 三个键；且旧产物缺字段必须是 `None` 而非 0 |
| `test_gui_workbench.py`（扩展现费用例） | `extract_run_summary` → `SUMMARY_METRIC_FIELDS` 三项（worker `results.summary` 路径） |
| `.tmp/perf-browser/verify.py` 三路径断言 | ① 后端有值直取 45.3 天；② 后端缺 + 未采样 → 回退现算 48.7 天；③ 后端缺 + 已采样 → 「—」且 tip 含「采样」「2026-10-28」 |

### 3.3 修一个基础设施限制：`node -e` 撞 ARG_MAX

`test_saas_static_kline_tv.py::TestIndicatorSettings::test_source_contract` 把**整个
`symbol.html`**（已 107,845 字节）嵌进 `node -e <script>`，超过 Linux 单参数上限
`MAX_ARG_STRLEN`（128KB）→ `OSError: [Errno 7] Argument list too long`。

修法：该文件的 `_node()` 改为**写临时文件后 `node <file>`**（无单参数限制）。
这是模板持续增长必然撞上的坑，不是产品 bug。

## 4. 验证

- `test_perf_metrics.py` / `test_gui_lab_result.py` / `test_gui_workbench.py` /
  `test_saas_static_kline_tv.py` 全绿
- 真实浏览器三路径断言通过
- 全量 `uv run pytest tests/ -q -p no:randomly` → **3033 passed, 24 skipped**

## 5. 已知限制（如实告知用户）

存量 job 58/66/74/78 的「平均持股周期」仍显示「—」——**没有数据源可以重算**
（run 产物已清空、SaaS 库无交易表、symbol 快照是有偏样本）。
重新提交回测即可显示。已在 tooltip 里写明成因。
