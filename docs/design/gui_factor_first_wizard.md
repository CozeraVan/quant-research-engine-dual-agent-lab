# GUI 因子前置录入改造设计（P1.5 增补）

日期：2026-07-27 ｜ 状态：DONE（2026-07-28，QRE-GUI-FACTOR-WIZARD-001，1238 tests green）｜ 作者：KIMI_CODE
关联：gui_backtest_workbench.md（P1/P2 DONE）；本文件为用户验收意见的重构增补。

## 用户意见（原文三点）

1. 因子需求前置：第一步选因子库中存在的因子，第二步设对比条件决定出入场。
2. 减少手填单元格，尽量下拉菜单，防止填错产生 bug。
3. 联动 indicators_tushare：新因子/新周期的计算入库与更新接口接入 GUI。

## 已核实的事实

- QRE 侧可实时枚举因子库：`information_schema` 查 `factors.*` 表列
  （`strategies/factor_request_queue.py` 的 column_lookup 已有此能力，只读）。
- indicators_tushare 管理入口：`run_factor_admin.py validate / plan / backfill
  [--execute]`（严格流程，backfill 默认 dry-run）；配置在 `config/factors.yaml`，
  日更 timer（16:40）自动把 yaml 中配置纳入每日更新。
- indicators_tushare 已配置 71 类指标（sma/ema/macd/rsi/kdj/bbands/…）。
- 信号表达式安全子集：比较 + 布尔 + 算术 + 括号，无函数调用。

## 设计：策略录入三步向导（替代/包裹现有 YAML 首屏）

### Step 1 选因子（下拉多选，零手填）

- 数据源：实时查 DB `factors.*` 表列 + 基础行情字段
  （open/high/low/close/pre_close/vol/amount）。
- 按类别分组展示（overlap/momentum/volatility/volume/trend/candle/derived/
  statistics/performance + 行情），每项显示列名 + 类别标签。
- DB 不可用 → 中文提示并禁用向导（回退手写 YAML 通道）。
- 选中即生成 `data.factor_fields` 映射预览。

### Step 2 条件构建器（决定入场/出场）

- 条件行四段式：[左操作数下拉：已选因子+行情字段] [运算符下拉：> ≥ < ≤ = ≠]
  [右类型切换：因子 | 数值] [右操作数：下拉或数值框]。
- 行间关系：AND/OR 下拉；分"入场条件组"与"出场条件组"两组。
- 附加项：holding_days（数值）、止盈/止损/trailing（可空，沿用 P1 表单）。
- 实时预览：生成的表达式 + 完整 YAML；提交前过 validate_yaml。

### Step 3 缺因子与新因子申请（联动 indicators_tushare）

- 由于 Step 1 下拉来自实时库，向导路径天然不会缺因子；此步服务 NL 通道/
  手写 YAML 引入的缺因子，以及用户主动想要的新指标/新周期。
- "新因子申请"面板：指标名（下拉，71 类）+ 价格类型（下拉）+ 周期/参数
  （数值框，带格式校验）→ 后端写入 indicators_tushare `config/factors.yaml`
  （repo 路径由 `QRE_INDICATORS_REPO` 配置，默认 `../indicators_tushare`）→
  后台自动执行 `validate → plan → sample backfill` 链 → 展示结果 →
  **用户人工确认后才 `--execute` 全量回填**（重操作闸）。
- 任务化：后台线程 + 日志轮询；同时只允许一个因子任务（保护 DB）。
- 日更接入零成本：yaml 配置一旦生效，16:40 的 indicators timer 自动纳入。

## 与现有通道的关系

- 向导成为默认首屏；手写 YAML 与 NL 通道保留为"高级"折叠区。
- NL 编译产物若缺因子，一键跳转新因子申请面板（预填指标名/周期）。

## 风险与对策

- 跨项目写 factors.yaml → 写入前备份原文件；格式用 ruamel/pyyaml 保注释
  往返（若 indicators 项目用 pyyaml 则跟随其实现）；写后必须 validate 通过
  才允许 backfill。
- execute 全量回填耗时长 → 人工确认闸 + 单任务锁 + 日志可视。
- 表达式能力边界 → 本版只做比较+布尔；算术组合（如 close/ma-1）列 P3 候选。
