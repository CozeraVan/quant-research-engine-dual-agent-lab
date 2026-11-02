# CR-2026-11-03 · NL 语义优化与转义项目：让中文股票语义正确落到 YAML 与真实因子

> 立项人：用户 2026-11-03 明确要求「不要再出现自然语言理解错误」，
> 并把金叉/死叉、快线/慢线、回调、支撑、N 日均线等中文股票语义的正确转义列为重点。
> 本 CR **扩展并取代** `CR-2026-11-02_nl_cross_semantics.md` 的范围（后者只覆盖穿越语义）。
> 实施者：step5review（后台），主 Agent 负责验收与部署提交。

---

## 1. 为什么现在必须做（用户原话的核心）

1. 用户每测一次 MACD 金叉死叉，得到的 YAML 不同、回测结果不同——**QRE 失去准确性**。
2. NL 把「上穿/金叉」编译成持续为真的当日状态（`>`/`<`），
   item1 的 76,511 笔、item3 的 504,183 笔交易就是这个错误的直接产物
   （见 `27_STRESS_TEST_2026-11-02.md` §8.1）。
3. 因子表名写错要等 worker 执行才报 `data_missing`（M6 实测踩到），
   用户无法在提交前发现。
4. 如果连 MACD 金叉死叉都理解错，更复杂的任务（回调、支撑、组合条件）更无从谈起。

**结论：语义正确性是 QRE 的地基，优先级高于一切新功能。**

---

## 2. 已确认的根因（代码级）

1. `gui/nl_compiler.py::_DSL_DOC` 明确写着：
   > 不支持跨周期引用（如"上穿/下穿"请改写为当周期比较，例如 `(sma_20 > sma_120)`，
   > 并明白这是当日状态而非穿越事件）
   ——**是 prompt 主动要求降级**，不是 DSL 不能表达。DSL 已支持 `.shift(1)`，
   wizard 的 `crosses_above/crosses_below` 正是编译成带 `shift(1)` 的穿越事件。
2. few-shot 只有当日状态比较，没有任何穿越示例。
3. **没有编译后语义校验层**：即使 prompt 被模型忽略，也没有任何东西拦下。
4. **没有因子存在性预检**：`validate_yaml` 只查 YAML 结构与因子配额，不查因子是否真实存在。
5. `NL_COMPILER_CACHE_VERSION` 未随语义口径变化而 bump，旧口径 YAML 可能被缓存复用。

---

## 3. 目标与验收口径（DoD）

1. **穿越语义正确**：
   - 上穿：`(A > B) and (A.shift(1) <= B.shift(1))`
   - 下穿：`(A < B) and (A.shift(1) >= B.shift(1))`
   - MACD 金叉 = DIF 上穿 DEA；死叉 = DIF 下穿 DEA（DIF=`macd_12_26_9`，DEA=`macds_12_26_9`）。
2. **中文语义正确转义**（见 §4 字典），且因子必须来自真实因子库。
3. **确定性**：同一句中文描述 → 同一份规范化 YAML（canonical 输出），
   不因重复编译而漂移；缓存版本随语义口径 bump。
4. **状态语义不被误伤**：`rsi < 20`、`sma60 > sma200` 这类水平位/持续状态描述，
   不得被加上 `.shift(1)`。
5. **因子存在性预检**：`validate` 与 NL 编译后处理都要能拦下不存在的因子表/列。
6. wizard / YAML 入口与引擎行为**零改动**。

---

## 4. 中文股票语义字典（canonical → 表达式模板）

> 原则：**先走 `configs/factor_aliases.json` 与 `factor_registry.json` 的既有别名解析**；
> 字典只补「表达式级」语义（穿越/位置/形态），不重复造一套因子命名。

| 中文说法 | 语义 | 目标表达式（示例） |
|---|---|---|
| 上穿 / 金叉 | A 本周期在 B 上方，且上一周期不在上方（穿越事件） | `(A > B) and (A.shift(1) <= B.shift(1))` |
| 下穿 / 死叉 | 上穿的镜像 | `(A < B) and (A.shift(1) >= B.shift(1))` |
| 快线（MACD 语境） | DIF（`macd_12_26_9`） | 列名直取 |
| 慢线（MACD 语境） | DEA / 信号线（`macds_12_26_9`） | 列名直取 |
| N 日均线 | 简单移动平均（`ma_N`）或指数移动平均（`ema_N`） | 按用户是否说「指数」区分；默认 MA |
| N 日指数均线 | EMA_N | 列名直取 |
| 回调 X% | 相对近 N 日高点回撤达到 X% | `close <= rolling_max(close, N) * (1 - X)` |
| 支撑 / 支撑位 | 近 N 日低点附近获得支撑（价格不低于该低点） | `close >= rolling_min(low, N)` |
| 压力 / 压力位 | 近 N 日高点附近受阻（价格不高于该高点） | `close <= rolling_max(high, N)` |
| 放量 | 成交量相对近 N 日均量放大 | `vol > rolling_mean(vol, N) * X` |
| 缩量 | 成交量相对近 N 日均量缩小 | `vol < rolling_mean(vol, N) * X` |
| 突破 | 价格上穿近 N 日高点 | `close > rolling_max(high, N).shift(1)` |

> 注：`rolling_max/rolling_min/rolling_mean` 是否在当前 DSL 安全子集内**必须先核实**
> （当前 `_DSL_DOC` 写「不支持函数调用」）。若 DSL 不支持，则这些形态用**预计算因子列**
> 表达（库内已有则引用，没有则**登记为缺因子申请**，禁止编造列名）。
> **step5 必须先做这个能力核实再动字典**，否则会写出引擎跑不了的表达式。

---

## 5. 实施方案（四个切片，TDD 先行）

### S1 穿越语义修复（最高优先）
1. 重写 `_DSL_DOC`：删除「上穿请改写为当周期比较」，改为
   「大于/小于=当日状态；上穿/下穿/金叉/死叉=穿越事件，必须用 `.shift(1)`」，
   并给出 canonical 模式。
2. few-shot 增加：SMA5 上穿 SMA200 买/下穿卖、MACD 金叉买/死叉卖。
3. **语义校验层（必须做，不能只靠 prompt）**：编译后处理若发现
   用户文本含「上穿/下穿/金叉/死叉」而 entry/exit 完全没有 `.shift(1)`，
   触发一次修复回路或明确报错——**绝不允许静默降级**。
4. bump `NL_COMPILER_CACHE_VERSION`（旧口径缓存失效）。

### S2 因子存在性预检（= M7）
1. 在 `validate` 与 NL 编译后处理里，对 `data.factor_fields` 的每个
   `schema.table.column` 做存在性校验：
   - 优先读 `configs/factor_registry.json` / `factor_catalog_llm.json`；
   - 本地可连库时再查 `information_schema`（ECS 无行情库，走元数据文件）。
2. 不存在的因子 → 明确报错并给出**最接近的合法候选**（复用别名系统的纠错层），
   不要等 worker 执行才失败。

### S3 中文语义字典与规范化输出
1. 按 §4 建 canonical 术语表（含「快线/慢线 = DIF/DEA」这类同义多名的映射）。
2. 输出规范化：canonical YAML（键序稳定、无多余注释、无 Markdown 围栏），
   同一输入重复编译产出一致；必要时对 LLM 输出做确定性后处理。
3. 建 golden dataset（`tests/fixtures/nl_semantics/*.yaml` 或内联）：
   中文描述 → 期望 YAML 结构（含/不含 `.shift(1)`、因子列名、是否穿越事件）。

### S4 真实 NL 冒烟 + 全量回归 + 部署
1. 三条真实编译（DeepSeek，非 stub）：
   SMA5 上穿 SMA200、MACD 金叉死叉、RSI 持续状态回归。
2. 一个**信号级**验证：构造一条 EMA5 只上穿 EMA200 一次的合成序列，
   确认编译出的表达式只在该日产生 1 个入场信号（不是持续满仓）。
3. 全量 `uv run pytest -q -p no:randomly` 不许变红。
4. 主 Agent 验收后部署 ECS 并 commit/push（step5 不要自行 commit/push/部署）。

---

## 6. 硬约束

- **不改引擎、不改 wizard/YAML 入口行为**；只改 NL 编译链与 validate。
- **禁止编造因子名**：一切列名必须来自真实因子库/别名系统；缺因子走申请流程。
- **状态语义不得误加 `.shift(1)`**（`rsi<20`、`sma60>sma200` 等）。
- 压测已结束，可以改业务代码，但**先做小样本，不做全量回测**。
- 每个切片前后都在 `26_WEEKLY_HANDOFF_2026-11-02.md` §7 登记计划与完成度。
- step5review 完成后**只回传结果**，由主 Agent 验收、部署、提交。

---

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| LLM 仍不遵守 `.shift(1)` 模式 | 编译后语义校验层兜底，不靠 prompt 自觉 |
| 字典里的 rolling_* 函数 DSL 不支持 | 先核实 DSL 能力；不支持就引用预计算列或登记缺因子，禁止编造 |
| 缓存复用旧口径 YAML | bump `NL_COMPILER_CACHE_VERSION` |
| 用户输入歧义（如「回调」未给幅度/周期） | 按 canonical 默认值 + 在 YAML/响应里显式 notice，不静默猜 |
| 同一描述重复编译结果漂移 | canonical 规范化 + golden dataset 合同测试锁定 |


---

## 8. 实施结果（2026-11-03，step5review 实施，主 Agent 验收部署）

**S1–S4 全部完成并上线**：
- S1：`_DSL_DOC` 重写 + few-shot + 编译后语义闸 + 修复回路 + canonical 输出 + 缓存版本 bump。
- S2：因子存在性预检已接入 `validate_yaml`（可选 lookup）、NL 后处理与 agent `/validate`。
- S3：`gui/nl_semantics.py` 术语表与确定性规范化；`rolling_*` 结论：裸函数非法，
  方法链 `close.rolling(N).max()` / `low.rolling(N).min()` / `vol.rolling(N).mean()` 可用；
  未编造任何列名。
- S4：真实 DeepSeek 三条编译（SMA5 上穿、MACD 金叉死叉、RSI 状态）；
  合成序列信号级验证：EMA5 仅上穿一次 → 恰好 1 个入场信号。
- 全量 **3437 passed, 34 skipped**；ECS MainPID 612103。

**遗留/后续**：
1. Builder 通道 `strategies/compiler.py::_compile_expression` 仍把 crosses_* 降级成 `>`/`<`，
   建议单独立项复用 `CROSS_CANONICAL`。
2. 语义闸当前为「完全无 shift 才硬拒；单边缺失且两序列互比只 warning」，如需更严可再加 per-side 硬闸。
3. 主 Agent 的 `git add -A` 曾把 step5 在制品混入 capacity/cloud 两笔提交，归属已在
   `11_AGENT_STATE.md` 澄清，不重写历史。
