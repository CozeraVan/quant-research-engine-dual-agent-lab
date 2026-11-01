# CR-2026-11-01 · P2-14 参数网格唤醒：TOP-N 与截断序叠加语义

> 任务：P2-14 参数网格唤醒。背景：前端 `applyParamChoices` 早已就绪，数据侧 MACD/RSI 多变体已入库；产物侧因 `SYMBOL_DETAILS_MAX_BYTES=15MiB` 已打满而休眠（用户裁决 A）。本轮用户要求推进，先定义可执行语义与安全落地步骤，不未审先改产物格式。

---

## 1. 目标

让用户在个股回测详情里切换指标的参数组（如 MACD 12/26/9 ↔ 6/13/5 ↔ 15/35/10 ↔ 24/52/18），且不突破现有产物体积上限、不让存量产物行为变化。

---

## 2. 现状事实

- 前端：`symbol.html` 参数面板 + `applyParamChoices` 已就绪；单参数组时逐字节原样返回（`tests/test_kline_param_grid.py` 覆盖）。
- 数据侧：`configs/factors.yaml` 中 MACD 4 组、RSI 9 周期已入库；MA/BOLL 变体未逐项核。
- 产物侧：`_strategy_factor_specs()` 只读策略 YAML 的 `data.factor_fields`，per-symbol 产物只有策略自己那一组参数。
- 预算：`SYMBOL_DETAILS_MAX_BYTES = 15 MiB`；job 78 实测 `_symbol_details/` 17M 已截断，加变体会使个股覆盖数下降。

---

## 3. 建议语义（本 CR 的核心）

### 3.1 变体来源

只对**因子库中同族存在多参数组**的字段生成变体，来源以 `configs/factors.yaml` 与数据库实际列名为准，不凭空造参数。

### 3.2 注入范围：只给 TOP-N 保留股

采用既有讨论中的 C 方案：

- 先按现有截断序选出最终保留的个股集合；
- 参数变体**只注入这些保留股**，不为了变体扩大个股集合；
- 默认 `TOP-N = 20`（可配置），避免全市场变体把 15MiB 预算打爆。

### 3.3 截断序与变体叠加顺序（硬规则）

1. **先截断个股，后插变体**：现有 `_symbol_details` 截断序（`abs(total_pnl)` 降序保头部）保持不变；
2. **变体不得挤占个股**：任何一个本应保留的个股，其主参数组必须完整保留；
3. **超预算时先砍变体，再砍个股**：如果注入变体后超过 `SYMBOL_DETAILS_MAX_BYTES`，按保留股优先级从低到高删除变体，直到回落到预算内；仍不够才按现有规则减少个股；
4. **股内优先级**：主参数组 > `configs/factors.yaml` 中的族内顺序；
5. **禁止静默超限**：manifest 必须显式记录 `param_variants_included` 与 `param_variants_truncated`。

### 3.4 兼容性

- 存量产物没有变体时，前端继续显示“该策略的指标只有一组参数”，行为零变化；
- 新产物若因预算砍掉变体，也必须在 manifest/前端可观测，不能伪装成“只有一组参数”。

---

## 4. 实施步骤（未做，待本 CR 批准）

1. **数据核对**：确认 MA/BOLL 变体是否已入库；未入库则列入 indicators 侧 backlog，不阻塞 MACD/RSI 首批。
2. **产物侧实现**：在 worker/lab_result 侧按 `TOP-N` 选择保留股，注入同族多参数组；实现 3.3 的预算保护与 manifest 计数。
3. **测试**：
   - 单测：截断序不变、变体不挤占个股、超预算先砍变体、manifest 计数正确；
   - 小样本：1 个策略 × TOP-N 股，实测 `_symbol_details` 体积与变体覆盖；
   - 真实浏览器：切换参数组 <100ms、无 JS error、旧产物降级文案不变。
4. **全量前必须报预算**：按小样本实测体积 × 全市场保留股数，向用户报告增量与覆盖数影响。

---

## 7. 2026-11-01 实施状态（首版，未 commit）

**已实现**：

- `lab_result.py` 新增纯函数 `_param_family_params()` / `_select_param_variant_columns()`：同族最多 4 组参数，主组优先，MACD 三元组完整；单组不扩展；非数字参数后缀（如 `macd_cn_*`）不识别为参数变体。
- `_fetch_factor_panels()` / `build_lab_symbol_detail()` 新增 `include_param_variants` 开关，默认 False；开启时按 information_schema 发现的同族列额外下发变体 panel，并按 `(table,column)` 去重，避免 MACD 主列/信号列/自动补柱重复。
- `worker/runner.py::build_symbol_detail_files()` 按现有截断序的前 `SYMBOL_DETAIL_PARAM_VARIANT_TOP_N=20` 只注入变体；超预算时先砍变体再砍个股；manifest 增加 `param_variants_included` / `param_variants_truncated` / `param_variant_top_n`。
- 新增 `tests/test_param_variants.py` 4 例；`tests/test_saas_symbol_ux.py` 新增 2 例（TOP-N 注入、超预算先砍变体）。

**小样本实测（2026-11-01，5 只策略样本中 3 只实际交易）**：

- baseline（无变体）：294,684 bytes；
- variants（TOP-N=20，实际 3 只）：509,809 bytes；
- 增量：+215,125 bytes，**ratio 1.73**，约 **+71.7KB/股**；
- 变体 panel 12 列，无重复列，`macd_cn_*` 已正确排除；
- 预算提示：15MiB 上限在存量全量任务已打满，TOP-N=20 理论增量约 **1.4MB**，会挤占约 14 只普通个股详情；超预算时先砍变体。

**真实浏览器参数切换验收（2026-11-01）**：

- 用实测变体产物加载 `factor-layout.js`：`paramVariants` 识别 `macd` 4 组；
- 切换到 `6_13_5` 后，因子集合 12 → 3，只剩 `macd_6_13_5/macdh_6_13_5/macds_6_13_5`；
- 零 pageerror。

**未做/待办**：

- MA/BOLL 变体入库核对；
- 全量预算报告与用户批准（建议先在小样本任务上开启默认 TOP-N，再全量）。

---

## 5. 风险与待用户确认

| 项 | 建议默认 | 说明 |
|---|---|---|
| TOP-N | 20 | 首用保守值；可在 manifest 观测后调整 |
| 变体族 | MACD/RSI 首批 | MA/BOLL 待核对 |
| 超预算策略 | 先砍变体后砍个股 | 保证主参数组与个股覆盖优先 |
| 是否默认开启 | 小样本验证后默认开 TOP-N | 全量前需用户批准预算 |

---

## 6. 验证清单

- [ ] MA/BOLL 变体入库核对
- [ ] 截断序与预算保护单测
- [ ] 小样本产物体积与覆盖数实测
- [ ] 真实浏览器参数切换验收
- [ ] 全量预算报告与用户批准
