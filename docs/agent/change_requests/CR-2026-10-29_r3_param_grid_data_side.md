# CR-2026-10-29 · R3-3 T5 参数网格：数据侧已完工（前提纠正）+ 离线重算闭环

> 任务书：`docs/agent/TV_ROUND3_TASKS_2026-10-29.md` §4
> 优先级 P1，1–2 人日。实施：Kimi。
> **结论先说**：任务书的前提「数据侧未开工」**只对了一半**。数据侧早就完工，
> 真正缺的是**产物侧**；而产物侧的改动与用户「稳定性第一」的既定约束冲突，
> 因此本轮只做能安全做闭环的部分，把取舍摊开给用户。

---

## 1. 事实核对（推翻了任务书的一半前提）

### 1.1 数据侧：**已完工**，不是"未开工"

`configs/factors.yaml`（indicators_tushare，日更管线配置）里：

```yaml
- name: macd
  category: momentum
  column: close
  params: [[12,26,9], [6,13,5], [15,35,10], [24,52,18]]   # 4 组
- name: rsi
  category: momentum
  column: close
  periods: [2, 6, 7, 9, 12, 14, 21, 24, 28]               # 9 个周期
```

实测库里（`information_schema`）确实都在：

```
macd_12_26_9  macd_15_35_10  macd_24_52_18  macd_6_13_5
macdh_12_26_9 macdh_15_35_10 macdh_24_52_18 macdh_6_13_5
macds_12_26_9 macds_15_35_10 macds_24_52_18 macds_6_13_5
rsi_2 rsi_6 rsi_7 rsi_9 rsi_12 rsi_14 rsi_21 rsi_24 rsi_28
```

**任务书要求"日更时对 MACD/RSI/MA/BOLL 各算 3–4 组参数变体宽表列入库"——
MACD/RSI 这条已经满足，不需要新做工。**（MA/BOLL 未逐项核，见 §4。）

### 1.2 产物侧：这才是真正的缺口

`_strategy_factor_specs()`（`gui/lab_result.py:798`）只读 `strategy.yaml` 的
`data.factor_fields`——**只拿策略自己那一组参数**。所以 per-symbol 产物里
MACD 只有一个参数组，前端 `applyParamChoices` 没有可切的东西。

实测证据：生产 job 78 的 symbol 产物 factors 只有 `ema_5` / `ema_20`
（策略自己那两个），没有任何第二组参数。

### 1.3 为什么本轮**不动**产物侧（摊开给用户决定）

`SYMBOL_DETAILS_MAX_BYTES = 15 MiB`（`worker/runner.py:357`），而
**这个上限已经打满**：

| job | `_symbol_details/` 体积 | 文件数 |
|---|---|---|
| 78 | **17 M** | 184 |

即 job 78 的个股详情产物**已经被截断**（`truncated=True`）。在此之上再加参数变体：

- 每个变体 ≈ 一条 4000 点序列，gzip 后约 10–12 KB/股；
- 3 组 MACD 变体 × 3 列 = 9 条 → 每股 +~100 KB，**产物体积约翻倍**；
- 15 MiB 上限下，能下发的个股数**直接减半**。

这与用户两条既定约束正面冲突：
1. 「稳定性第一，暂不追求回测速度」；
2. 项目刚因 OOM 修过一轮，用户明确要求"留出阈值空间"。

**所以：产物侧是否加变体，是"个股覆盖数 ↔ 参数灵活性"的取舍，应由用户定，
不该由 agent 单方面改产物格式。** 已列入 `11_AGENT_STATE.md` 待决。

---

## 2. 本轮实际做的：离线重算闭环（ROUND2 T5 验收第 2 条）

ROUND2 时因"无数据可验"搁置的验收第 2 条——**"同一产物切 3 组参数，因子值与离线
重算逐一一致"**——本轮在**数据层**闭环。

新建 `tests/test_factor_param_variants_data.py`（2 例）：

1. `test_macd_variant_columns_exist`：4 组 MACD 参数变体 × 3 列必须都在库里
   （数据侧"已完工"的硬证据，缺列即红）。
2. `test_macd_param_variants_match_offline_recompute`：用**纯 numpy 独立实现**
   （**不 import pandas_ta**，避免与管线共用同一份代码而失去交叉验证意义）
   对全量历史重算 4 组参数，与库里逐值比对。

### 2.1 三个口径坑（实测踩过，写进测试注释防复发）

| 坑 | 错法给出的结果 | 正确口径 |
|---|---|---|
| 复权口径 | 用 raw close 重算，`dif` max_abs_diff=**39.1** | 因子表是 **hfq**（close × adj_factor），必须同口径 |
| warm-up 窗口 | 只取 2024 年窗口重算，diff 大到几十 | 必须用**全量历史**（4244 根） |
| EMA 定义 | `Series.ewm(span, adjust=False)`（从首个值就递归），max=**15.5** | TA-Lib / pandas-ta 口径：前 n 个有效值 **SMA 播种**后递归 |
| HIST 公式 | `(dif - dea) * 2`，max=**52.0** | `dif - dea`（A 股软件的 ×2 是显示口径，不是库里口径） |
| 精度上界 | 按 0.005 断言，24/52/18 组 0.0069 假阳性 | MACD 三列都是**导出量**（两个 EMA 相减），最坏两次舍入 → 上界 **0.01** |

### 2.2 实测结果（000001.SZ，2009-01-05 → 2026-10-28，4244 根）

```
macd_12_26_9.{dif,dea,hist}  max ≈ 0.005
macd_6_13_5.{dif,dea,hist}   max ≈ 0.005
macd_15_35_10.{dif,dea,hist} max ≈ 0.005
macd_24_52_18.{dif,dea,hist} max ≈ 0.005（dif 0.0069，界内）
```

即 4 组参数 × 3 列 × 4244 个交易日全部落在 DB 2 位小数舍入界内。
**数据质量这一半闭环。**

无数据库环境自动 skip（CI 不阻塞）。

---

## 3. 前端侧：本来就是好的，补一条说明

`symbol.html` 的参数面板在"本产物只有一组参数"时已经明确显示
「该策略的指标只有一组参数」（`symbol.html:1604`），不会静默无反应。
`applyParamChoices` 在只有一个参数组时**逐字节原样返回**（`test_kline_param_grid.py`
覆盖），存量产物零行为变化。

**所以 T5 前端片没有残留工作**；缺的只有产物数据，而归属于上面那个取舍。

---

## 4. 未做 / 待决

| 项 | 状态 |
|---|---|
| MA / BOLL 的参数变体是否也已入库 | **未逐项核**（只核了 MACD/RSI）。要核的话查 `information_schema` 里 `stock_daily_overlap_close` 的 `ma_*`/`sma_*` 与 `stock_daily_volatility_close` 的 `bb*`/`boll*` |
| 产物侧下发参数变体 | **待用户决定**（见 §1.3：15 MiB 上限已打满，加变体会让个股覆盖数减半） |
| 「切参数 < 100ms」真实浏览器验收 | 前端只做 filter + 一次 setOption、无网络往返，单测覆盖；真实浏览器验收要等产物侧有数据才有意义 |
| 锚点纪律对新列生效 | 新列与主参数同表同口径同锚点，无独立锚点；`factor_basis` 由产物统一带，不因参数组而变 |

## 5. 测试

- 新增 `tests/test_factor_param_variants_data.py` 2 passed
- `tests/test_kline_param_grid.py` / `tests/test_factor_registry.py` 全绿
- 未跑全量（本轮只加测试文件，无产品代码改动）

未 commit / 未 push / 未部署 ECS（按派单约束）。
