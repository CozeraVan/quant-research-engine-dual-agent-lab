# Implementation Brief

## Task ID

QRE-GUI-DEEP-VALIDATE-001（deep-validate 501 骨架落地：策略 YAML → 逐日信号池 → 四关验证）

## Created By

KIMI_CODE（用户 2026-08-20 直接指定的任务书；承接 cfb860d 的 501 骨架）

## Intended Implementer

KIMI_CODE

## Goal

让 GUI 对任意 catalog/沙箱策略一键跑 cluster-ashare 的四关重型验证
（`analysis/validate_factor.py`）。核心缺口是「策略 YAML → 逐日信号池」
转换器。本轮落地：

1. **cluster-ashare 侧薄脚本** `analysis/pool_from_conditions.py`：输入条件
   JSON（QRE 转换器产出）+ 区间，输出逐日池 parquet（trade_date, ts_code）。
   DB 访问与因子口径全部留在 cluster-ashare（QRE 只读业务库传统不破）。
   条件求值**不重写**：脚本把 QRE 的 `src/` 插入 sys.path，直接 import
   `quant_research_engine.evaluation.signals.evaluate_expression_signal`
   （纯 ast/pandas 模块，无重依赖），框架构造对齐 QRE evaluation engine
   （sort ts_code/trade_date 后整表面板求值）。
2. **QRE 转换器**（纯函数，新模块 `gui/deep_validate.py`）：
   `spec_to_conditions(spec, d0, d1)` → 条件 JSON（name / expression /
   factor_fields / market_fields / used_fields / d0 / d1）。used_fields 用
   ast 走 expression 的 Name 节点，cluster 脚本只拉取被引用的列（控内存）。
   `locate_strategy_yaml(name)`：沙箱优先，其次 catalog rglob 按
   experiment.name / 文件 stem 匹配。`parse_report_summary(md_text)`：
   解析四关报告 markdown 的「## 0. 结论」（GO/NO-GO + reasons）与
   「## 3. 四关结果」表（各关平均超额/t），纯函数可单测。
3. **异步 job**：`start_deep_validate_job` 复用 `daily_jobs.start_script_job`
   （lock_key=`deep-validate:<name>`，同名串行；runner 可注入便于测试）。
   runner 顺序跑两个 subprocess（cluster `.venv/bin/python`）：
   ① pool_from_conditions.py → ② validate_factor.py --pool-parquet
   （--price-cache / --eval-cache 按区间落 cluster outputs 实现断点续跑；
   daily_basic 缓存存在则加 --basic-cache 启用 gate4）。终态解析报告写
   job_dir/result.json（verdict/reasons/gates 摘要/报告路径/池统计）。
4. **API**：`POST /api/strategies/<name>/deep-validate`（可带 d0/d1 覆盖，
   默认 2015-01-01 ~ 当天）→ 定位 YAML → StrategySpec 解析 → 无入场表达式
   400 → cluster venv/脚本缺失 500 → 因子存在性检查（复用
   `_default_column_lookup` + `find_missing_factor_columns`，缺失则入
   factor_request_queue 并 400）→ 提交 job 返回 job_id；同名在途 409。
   新增 `GET /api/strategies/<name>/deep-validate/<job_id>` 轮询（终态附
   result.json）。
5. **前端**：index.html 沙箱列表每行加「深度验证」按钮；提交后轮询（10s
   间隔，不设放弃上限）；终态行内渲染 GO 绿 / NO-GO 红 + 四关净超额摘要
   + 报告路径，失败显示错误。

## Semantics

- 信号池口径：T 日收盘满足**入场条件**的股票集合；出场/止盈止损/持仓参数
  不进池（四关验证的是信号本身的选股能力），报告/结果注明该口径。
- 默认区间 2015-01-01 ~ 今天；请求参数 d0/d1 可覆盖（YYYY-MM-DD 校验）。
- 表达式求值语义与 QRE evaluation engine 一致（同一函数，整表面板
  sort(ts_code, trade_date) 后求值；含 shift() 的表达式按此口径）。
- 区间缓存键：price/eval 缓存文件名含 d0/d1，换区间不命中旧缓存
  （load_price_panel 对已有缓存路径不做范围校验，必须靠文件名隔离）。
- 验证 name 用 `qre_<safe_name>`，报告落 cluster 侧
  `outputs/factor_mining/validation/qre_<name>_四关验证报告.md`（不改
  cluster 代码，只用其输出目录）。

## Scope

1. cluster-ashare（邻居项目新增一个脚本，不改既有代码）：
   `analysis/pool_from_conditions.py`。
2. QRE：`src/quant_research_engine/gui/deep_validate.py`（新模块：转换器 +
   job 启动 + 报告解析）。
3. `gui/app.py`：501 骨架替换为真实现 + GET 轮询端点。
4. `gui/templates/index.html`：沙箱行加按钮 + 轮询渲染。
5. tests：新 `tests/test_gui_deep_validate.py`（转换器纯函数 / 报告解析 /
   API mock subprocess / 409 / 400 / 500 路径）；删除/改写旧 501 测试。
6. docs/agent 08/10/09/05/11 同步。

## Non-Goals

- 不 git commit、不重启 qre-gui.service；不改 cluster-ashare 既有代码
  （只新增一个 analysis 脚本）；QRE 侧不直连业务库取数（DB 全走 cluster
  脚本）；不改 validate_factor.py / factor_validation 任何文件；不动
  出场/风控参数语义。

## Expected Tests

- 转换器：catalog YAML → 条件 JSON（expression/factor_fields/used_fields/
  区间默认与覆盖）；无 signal.entry → 明确错误；locate 沙箱优先于 catalog。
- 报告解析：样例 md → verdict/reasons/gate 摘要；GO 与 NO-GO 两种。
- API：404 未知策略；400 无入场表达式/缺因子（入队）；500 cluster 脚本缺失；
  409 同名在途；happy path（注入 fake starter+runner）返回 job_id 且轮询
  终态含 verdict 与报告路径。
- `uv run pytest tests/ -x -q` 全绿（基线 1454）。

## Validation

1. `uv run pytest tests/ -x -q`
2. `node --check` index.html 内联 JS（随既有 GUI 测试或手工抽取）
3. 真实端到端冒烟：挑 catalog 策略 mr01a（rsi_14 单因子）跑一次完整
   deep-validate 流程（直接命令行调转换器+两个 cluster 脚本），核对
   `qre_mr01a_rsi14_oversold_reversal_四关验证报告.md` 结论段。
