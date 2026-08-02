# 新策略写作规范（STRATEGY AUTHORING）

面向：人类与 AI agent。目标：写出能被 QRE 校验、编译、回测、纳入日更的策略。
日期：2026-07-28 ｜ 本文为**现行规范的权威整合版**；细则与示例以链接文档为准：

- 高层录入标准（strategy_card / factor_requirements / experiment_plan 三段式）：
  `docs/strategy_entry/README.md`、`factor_requirements.md`、`examples.md`、`strategy_card.md`
- 目录组织与快速开始：`strategies/README.md`
- 完整低层实例（带逐行注释）：`strategies/catalog/`（111 个，7 大类）、
  `strategies/low_level/bollinger_mean_reversion.yaml`
- 缺因子申请协议：`docs/strategy_entry/missing_factor_request.md`

## 0. 一句话模型

策略 = **入场条件组** + （可选）**出场条件组** + **持仓/风控参数** +
**因子需求映射**。所有条件必须可分解为
`(行情字段或因子别名, 比较运算符, 阈值或另一别名)` 的三元组，
组内用 AND 或 OR 连接。不能分解成这个形式的策略描述，当前引擎不支持（见 §5 限制）。

## 1. 低层 StrategySpec YAML 全字段规范

这是引擎直接执行的格式（GUI 向导/Builder/NL 最终都编译成它）：

```yaml
experiment:                  # 必填
  name: my_strategy_id       # 必填，snake_case，全库唯一
  market_profile: ashare_daily_default
  frequency: daily

data:
  market_fields: [open, high, low, close, pre_close, vol, amount]  # 内置行情别名，默认即此
  factor_fields:             # 策略用到的技术指标，别名 -> 库内真实列
    rsi_14: factors.stock_daily_momentum_close.rsi_14
    bb_lower: factors.stock_daily_volatility_close.bbl_20_2_0_2_0

universe:                    # 可选，默认不排除
  exclude_st: true
  exclude_suspended: true
  exclude_risk_warning: true
  min_listing_days: 120

signal:                      # 必填
  entry: (close <= bb_lower) and (rsi_14 < 30)   # 必填，见 §2 表达式子集
  exit: (close >= bb_middle)                     # 可选

holding:
  max_holding_days: 20       # 必填，整数 ≥1

risk:                        # 可选；null 或省略即不启用
  stop_loss_pct: 0.08
  take_profit_pct: null
  trailing_stop_pct: null

evaluation:
  forward_return_horizons: [1, 3, 5, 10, 20]
  quantiles: 5
```

### factor_fields 映射规则

- 目标格式 `factors.<table>.<column>`（`schema.table.column` 三段；
  `factors.xxx.col` 两段是非法的，校验会直接拒绝）。
- 表名规律：`stock_daily_<category>_<price_col>`（纳管 10 表，如
  `stock_daily_momentum_close`）；列名用 information_schema 实时枚举
  （GUI 因子状态 tab 或 `GET /api/factors` 可查当前全部可用列）。
- 别名是表达式里的操作数名；不得与内置行情别名
  （open/high/low/close/pre_close/vol/amount）重名（Builder 编译会报 shadow 错误）。

## 2. signal 表达式安全子集（硬性边界）

- **支持**：别名与数值字面量；比较 `< > <= >= == !=`；布尔 `and or not`；
  算术 `+ - * /`；括号。
- **不支持**：函数调用、索引/切片、属性访问、跨周期引用、字符串。
- 表达式必须能对每根 K 线求值为布尔序列。
- 执行语义：T 日信号，T+1 开盘价成交（catalog 惯例 execution 段注释说明；
  低层引擎固定 t_plus_1_open）。

## 3. 三条录入通道及其边界

| 通道 | 输入 | 边界 |
|---|---|---|
| 因子向导（GUI 首屏） | 下拉选因子 + 条件行 | 仅"比较 + 布尔"（AND/OR 组内统一）；不支持算术组合右值；产物填入编辑器由用户确认（安全闸，不自动执行） |
| 高层 Builder / entry YAML | strategy/rules/factor_requirements/experiment 四段 | 见 `docs/strategy_entry/README.md`；`crosses_above/below` 会**降级为当周期比较**并给出 warning，不是真正的穿越事件 |
| NL 自然语言 | 中文描述 | LLM 编译为低层 YAML，经 validate + 因子存在性检查；缺因子自动入 handoff 队列；同样只填编辑器待确认 |

## 4. 策略验收 checklist（提交前逐项过）

- [ ] `validate_yaml` 通过（GUI"验证"按钮或 `validate_yaml()`；StrategySpec 解析无错）。
- [ ] 引用的每个 `factor_fields` 目标列在 DB 中存在（preflight / 因子状态 tab 对账无红色）。
- [ ] 条件可分解为 §0 三元组形式；没有穿越/多周期/函数语义。
- [ ] 小样本预检跑通（R-QRE-009：GUI 默认前 20 只 × 近 6 个月；确认有订单、无异常报错后再放大）。
- [ ] universe/风控参数与策略意图一致（stops 是否启用影响引擎分支，batch 引擎 stops 需 `--apply-stops` 或 GUI 交易规则字段）。
- [ ] 需要日更时：把策略 YAML 放入 `strategies/catalog/<category>/`（遵循现有命名
      `<类别前缀><序号><变体>_<名称>.yaml` 与头部注释块），管理台"策略状态"可见；
      refresh 注册表生效期间需注册（当前注册表为空 = 全量，机制见
      `docs/agent/09_CODING_HANDOFF.md` P3B 段）。
- [ ] 结果页保留"引擎输出，非投资建议"认知（R-QRE-008）。

## 5. 明确不支持的语义（自然语言 → 标准策略的约束）

以下意图**无法**被当前 DSL 表达，NL/向导通道会降级或拒绝，写作时不要依赖：

| 意图 | 状态 | 说明 |
|---|---|---|
| 上穿/下穿（穿越事件） | 降级 | 只能写当周期比较 `(a > b)`；编译器对 crosses_* 出 warning 后降级 |
| 多周期/引用历史值（如"昨日收盘"） | 不支持 | 表达式无 lag/shift |
| 算术组合因子（如 `close/ma20 - 1 > 0.05`） | 部分支持 | 低层表达式手写可用算术；向导/Builder 不支持，留 P3 候选 |
| 分钟/Tick/基本面/选股打分排序 | 不支持 | v1 范围：日线技术指标、信号驱动（strategy_entry README Scope） |
| 做空、多空对冲 | 引擎字段存在（direction）但 catalog 与报告链路按 long_only 验证 | 慎用 |

违反约束的 NL 描述会得到校验错误或降级 warning——这是设计行为，不是 bug。

## 6. AI agent 写作流程建议

1. 把自然语言策略先改写成 §0 的条件组清单（逐条列出三元组）。
2. 每条因子查 `GET /api/factors` 或因子状态 tab 确认列存在；不存在 →
   走缺因子路径（P1.5 新因子申请 / handoff 队列），不要编造列名。
3. 生成低层 YAML → validate → 小样本预检 → 用户确认 → 正式回测。
4. 全程遵守 R-QRE-005/008/009（见 `docs/PROJECT_GUIDE.md` §2）。
