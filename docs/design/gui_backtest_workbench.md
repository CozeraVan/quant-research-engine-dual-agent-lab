# GUI 回测工作台设计（QRE Backtest Workbench）

日期：2026-07-27 ｜ 状态：P1/P2 DONE（2026-07-28，1210 tests green；P3 待启动）｜ 作者：KIMI_CODE

## 0. 背景与可行性结论

用户目标：把回测引擎的入口（标的、区间、资金、费率等参数）与出口（报告文件）
做成 GUI 可视化，并支持自然语言描述策略 → 提交 → 得到回测结果。

可行性：**可行，约 80% 组件已存在**。

- 已有 Flask 控制台（`src/quant_research_engine/gui/app.py`）：策略 YAML 编辑、
  校验、提交运行、run 历史、artifact 下载、模板库、高层 builder 编译。
- 所有入口参数已存在为 CLI flags（batch_backtest_runner / research_run）：
  区间、universe-filter、jobs、chunk、stops、benchmark、资金/费率在策略/引擎配置内。
- 缺的三块：① 参数表单化（把 CLI flags 映射为表单）；② 自然语言→YAML 编译器；
  ③ 出口报告的 GUI 呈现与对比。

## 1. 架构（四层）

```
┌─ 入口层  参数表单 + 策略三通道（选文件 / builder / 自然语言）
├─ 策略层  NL→YAML 编译器（LLM，schema 约束）→ 校验 → preflight 因子检查
├─ 执行层  后台任务队列（限流）→ 小样本预检 → 正式回测
└─ 出口层  汉化摘要卡 + Excel/CSV 下载 + 权益/回撤图 + run 对比 + 一键加入日更
```

## 2. 入口层：参数表单

| 分组 | 字段 | 映射 |
|---|---|---|
| 标的范围 | 全市场 / 板块 / 行业 / 自定义代码列表 / 股票池文件 | `--universe-filter` + symbol list |
| 回测区间 | 起止日期；快捷键：近1年/2年/5年/全期 | `--start --end` |
| 资金与摩擦 | 初始资金、佣金率、印花税、滑点、最低佣金 | 引擎 cost 配置 |
| 交易规则 | 止盈/止损/trailing 开关与数值、T+1、涨跌停限制 | `--apply-stops` + 策略 risk 段 |
| 引擎选项 | vectorized/bar 仿真、并发 jobs、benchmark 指数 | `--engine-impl --jobs --benchmark-code` |
| 输出 | compact/workbook、输出目录 | `--compact --workbook --output-dir` |

默认值 = 当前过夜脚本配置（已验证稳定）。表单带"小样本预检"勾选项，默认勾选
（对应 R-QRE-009：先小样本后全量）。

## 3. 策略层：三通道

- **通道 A 选已有策略**：catalog 111 + 用户模板库，下拉选择，附带策略说明
  （开仓/平仓条件从 YAML 提取展示）。
- **通道 B 可视化 builder**：沿用现有 high-level entry compile。
- **通道 C 自然语言**（新组件，核心增量）：
  1. 用户输入自然语言（如"20 日均线上穿 120 日均线买入，跌破 60 日线卖出，
     止损 -8%"）。
  2. 后端调用可配置 LLM（env：`QRE_NL_LLM_BASE_URL/API_KEY/MODEL`，不内置任何
     特定 provider；无配置时通道 C 显示"未配置"并回退提示用通道 A/B）。
  3. Prompt 受策略 DSL schema 约束（把 JSON schema + 可用因子清单注入），
     输出只允许 YAML。
  4. 输出经现有 `validate_yaml` + preflight 因子检查；缺因子 → 走现有 handoff
     队列，界面明确提示"该策略已搁置，缺因子 xxx，已通知 indicators_tushare"。
  5. **安全闸**：LLM 输出绝不直接执行——必须展示 YAML 给用户确认后才可提交。

## 4. 执行层

- 提交 → 后台任务（复用 `run_backtest` 基建），进度轮询、可取消。
- 限流：最多 2 个并发回测任务（保护 23G 内存 + DB 锁；锁参数虽已调 512，
  仍避免 GUI 场景失控）。
- 小样本预检通过 → 用户一键"放大到全量"。

## 5. 出口层

- Run 详情页：汉化摘要卡（总收益/超额/回撤/胜率/交易数 vs 买入持有 vs 基准）。
- 文件下载：Excel workbook、trades/round_trips/symbol_performance CSV、manifest。
- 图表：权益曲线、回撤曲线（复用现有 chart 基建；CJK 字体问题顺带修复）。
- **Run 对比**：选两个 run 并排对比摘要指标（用户核心诉求：参数调整后看差异）。
- **一键加入日更**：把该策略注册进 refresh 集合（M10.3 增量刷新基建）。

## 6. 分期

- **P1（纯工程，无 LLM）**：参数表单 + 出口强化（摘要卡、下载、对比）。
  风险低，1~2 天量级。
- **P2**：NL→YAML 编译器（schema 约束 prompt + 校验回路 + 安全闸）。
- **P3**：run 对比深化、日更注册按钮、聚类分析入口（接 M10.4）。

## 7. 风险与对策

- LLM 编译不准 → schema 约束 + 校验回路 + 用户确认闸；失败时给可编辑 YAML。
- LLM 成本/依赖 → provider 完全可配置，不进入项目主依赖；无配置时降级。
- GUI 并发压垮 DB/内存 → 任务队列限流 2 并发 + 默认小样本预检。
- 结果误读 → 界面标注"引擎输出，非投资建议"（R-QRE-008）。

## 8. 与日更的关系（回答用户疑问 1）

当前日更链：quant-ts（16:30 K线）→ indicators（16:40 因子）已安装；
QRE 增量刷新（M10.3，`scripts/refresh_batch.py`，watermark 增量）已建成并
小样本验证，但 `deploy/qre-refresh.timer` **未安装**。
收尾动作：安装 timer（建议 18:30，错开上游）+ 注册 111 策略 refresh 集合。
增量只算新增交易日，成本为分钟级。
