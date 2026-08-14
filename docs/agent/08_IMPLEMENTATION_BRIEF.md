# Implementation Brief

## Task ID

QRE-ALPHA191-STRAT-LOOP-001 (P6：头部 alpha191 因子新建策略闭环自测)

## Created By

KIMI_CODE (single agent; 用户 2026-08-14 直接指定的任务书)

## Intended Implementer

KIMI_CODE

## Goal

从 P5 全量 leaderboard 头部显著因子选 3 个（alpha083/alpha099/alpha042），
各设计一个最简策略并走完整「新建策略闭环」：沙箱（validate+查重）→ 小样本
冒烟 → 晋升 catalog → 全市场近 1 年回测 → 报告生成确认 → 日更登记确认。
验证引擎的因子→策略→回测→日更链路对 alpha191 面板因子开箱可用；有断点做
最小修复（带测试），无断点如实记录。

## Semantics (locked by user plan)

- 因子语义查 indicators_tushare/alpha191 formulas+errata；信号用阈值
  （alpha083/099 本身即 cs_rank 输出 ∈[-1,0]，阈值即截面分位；alpha042
  用全市场分位数标定阈值），不引入引擎不支持的算子。
- 沙箱/晋升走 gui/strategy_create.py 既有机制；回测走
  scripts/batch_backtest_runner.py（对齐 overnight 规范：vectorized、
  symbol-chunk 400、compact、workbook、apply-stops、universe-filter、
  benchmark 000300.SH）。
- 日更：refresh registry include 空 = 全量扫描 catalog，晋升即登记。
- 窗口：冒烟 20 股 × 近 6 个月；正式 2025-08-14~2026-08-14 全市场。

## Scope

1. 3 个策略 YAML（沙箱 → catalog/price_volume/pv06{a,b,c}）。
2. 回测产物 outputs/backtests/alpha191_p6/。
3. docs/agent 05/08/09/10 同步。

## Non-Goals

- 不做 git commit；不改引擎代码（预期零断点，若有则最小修复+测试）；
  不改业务数据库；不动后台无关进程；不调整因子公式。

## Expected Tests

```bash
uv run pytest tests/ -x -q   # 无代码改动时应保持 1398 绿
uv run qre report-audit <run>/<sid>/report_manifest.json
```

---

## Task ID

QRE-EVAL-ALPHA191-001 (Alpha191 赚钱效应评估管线 + GUI 路径 C 登记)

## Created By

KIMI_CODE (single agent; 用户 2026-08-14 直接指定的任务书)

## Intended Implementer

KIMI_CODE

## Goal

为 indicators_tushare 新建的 alpha191 面板因子库（factors.stock_daily_alpha191，
191 列 alpha001..alpha191）提供赚钱效应评估 CLI：逐因子装配面板（close + 单因子
列，全市场）→ EvaluationEngine.evaluate → leaderboard CSV。并在 GUI「新增因子」
tab 路径说明卡登记路径 C（Alpha191 通道，纯文案，本期不支持 GUI 内新建）。

## Semantics (locked by user plan)

- CLI：`scripts/eval_alpha191.py [--start S] [--end E] [--factors alpha001,...|all]
  [--top N] [--output PATH]`；默认窗口近 2 年（R-QRE-009 先小样本后全期）。
- 评估口径：forward_horizons=[1,3,5,10,20]，quantiles=5，成本沿用引擎默认
  （round_trip_cost_rate=None）；主排序键 mean_rank_ic(h=5)。
- leaderboard 列：factor, mean_rank_ic, icir(日频 rank IC 均值/std), ic_win_rate
  （方向一致率）, top_minus_bottom(h=5, Q5−Q1), observation_dates, significant
  （★：|rank_ic|≥0.05 且胜率≥0.55）；按 |mean_rank_ic| 降序。
- 内存：因子分批（默认每批 10 个）取数，批后 del + gc。
- 测试：合成面板 + mock evaluate 验证 CLI 输出结构与排序。

## Scope

1. 新增 `src/quant_research_engine/evaluation/alpha191.py`（口径常量 +
   daily_rank_ic/summarize_factor_result/build_leaderboard/evaluate_alpha_factors）。
2. 新增 `scripts/eval_alpha191.py`（薄 CLI）。
3. 新增 `tests/test_eval_alpha191.py`。
4. `gui/templates/index.html` 新增因子 tab 路径说明卡加路径 C 文案（h2 改
   「路径说明（A / B / C）」）。
5. 文档：docs/agent 05/08/09/10 同步。

## Non-Goals

- 不做 git commit（用户显式约束）。
- 不改 EvaluationEngine / catalog / assembler 语义；不动 alpha191 回填；
  不修复上游 alpha006 逐日常量疑点（仅登记发现）。

## Expected Tests

```bash
uv run pytest tests/ -x -q
QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' uv run python \
  scripts/eval_alpha191.py --start 2012-08-01 --end 2013-08-13 \
  --factors alpha001,alpha006,alpha012 --output /tmp/alpha_eval_smoke.csv
```

（用户指定窗口 2025-08-01~2026-08-13 因回填尚未推进到该区间（当前 2010→2013 +
日更当日），改用已覆盖窗口 2012-08-01~2013-08-13 做真实小样本；详见 09/10。）

---

> 2026-08-12 QRE-GUI-UIUX-001（GUI 全站 UI/UX 优化）为纯样式/模板 class 改动，方案由用户直接指定（设计变量 + 按钮分级 + 信息直读化），未单独写 brief；实现与验证见 09_CODING_HANDOFF.md / 10_REVIEW_REPORT.md 顶部。

## Task ID

QRE-GUI-HOME-REFACTOR-001 (GUI 首页三 tab → 两 tab 重构)

## Created By

KIMI_CODE (single agent; 用户批准的方案 2026-08-12)

## Intended Implementer

KIMI_CODE

## Goal

首页 `index.html` 三 tab（因子向导 / 策略构建器 / YAML 编辑器）合并为两 tab：
「新增策略」（默认 landing，NL / 可视化构建 / 手写 YAML 三入口同页汇入底部
YAML 预览栏）+「新增因子」（路径 A 补周期 + 路径 B 全新指标 fc-create，
fc-create 从 admin.html 因子 tab 迁入）。

## Semantics (locked by user plan)

- Tab 1 三段垂直流：顶部 NL 面板（#/api/nl_compile）→ 中部可视化构建
  （wizard step1 因子选择 + step2 条件/风控，"生成 YAML"改为同页填入预览栏，
  无 tab 跳转）→ 底部 YAML 预览栏（可编辑）+ 操作行 + 回测参数表单
  （高级参数：引擎/执行方式/DB URL/market profile/输出目录，默认折叠）+
  沙箱策略面板。运行按钮逻辑不变（预检勾选 → 小范围）。
- Tab 2：路径说明卡 → 路径 A（wizard step3 wz-admin-*，POST
  /api/factor-admin/request）→ 路径 B（fc-create 子区整体迁入，
  /api/factor-create/* 功能不变）。
- NL 缺因子错误引导改为跳「新增因子」tab（wzGotoFactorAdmin 切 tab-factor
  并预填路径 A）。
- admin.html 因子 tab 删除 fc-create 子区 HTML 与 fc JS，原地留
  「→ 新增因子请前往首页」链接；其余不动。
- 删除 tab-builder 全部 HTML 与其 JS IIFE（b-* 元素全删）；
  后端 /api/builder/* 保留不删；app.py 零改动。
- 元素 ID 尽量保留（wz-*/nl-*/param-*/fc-*/sandbox-*）；原生 JS IIFE 重组为
  tabs / strategy / factor 三个独立作用域；不引入框架/依赖。

## Scope

1. `templates/index.html` 整体重写为两 tab。
2. `templates/admin.html` 删 fc-create。
3. 测试断言更新（test_gui_factor_wizard / test_gui_app / test_gui_admin）。
4. 文档：STRATEGY_AUTHORING §3、indicators FACTOR_AUTHORING §8、docs/agent 同步。

## Non-Goals

- 不做 git commit（用户显式约束）。
- 不跑真实回测/backfill；不新增依赖；后端零改动。

## Expected Tests

```bash
uv run pytest tests/ -x -q
```

## Acceptance Criteria

- 首页两个 tab，无 tab-builder；admin 无 fc-create；全量 pytest 绿；
  临时 GUI curl 抽查 / 与 /admin 结构及 /api/factors 等 API 200。

# Implementation Brief (archive: QRE-GUI-FACTOR-CREATE-P2-001, GUI 新因子创建闭环 P2)

## Task ID

QRE-GUI-FACTOR-CREATE-P2-001 (GUI 新因子创建闭环 P2)

## Created By

KIMI_CODE (single agent; 用户批准的方案 2026-08-12)

## Intended Implementer

KIMI_CODE

## Goal

打通"GUI 新建技术指标 → indicators_tushare 入库 → 日更/因子 tab 可见"的闭环：
NL/手写 → LLM 生成因子代码草稿（用户确认）→ 查重 → 沙箱冒烟（单股只读 DB）→
用户确认晋升 → 写入 indicators 项目 + config 条目 → validate + backfill --execute。

## Semantics (locked by user plan)

- 与 `/api/factor-admin/*`（既有因子补周期/补列）区分：本通道只管**全新因子**，
  API 命名 `/api/factor-create/*`。
- 沙箱在 indicators 项目内 `sandbox/factors/`（不在 factors 包内，registry 不发现）；
  冒烟 CLI = indicators `sandbox/smoke_factor.py`（importlib 加载 → FactorBase 子类 →
  DBManager 只读单股近 N 日 → calculate() → 断言列存在/非全 NaN/列名规范，JSON 输出，
  QRE 侧 subprocess 120s 超时）。
- 生成的代码要执行，必须 AST 白名单静态检查：只允许 import pandas/pandas_ta/numpy/
  typing/core.factor_base；禁 open/eval/exec/__import__；禁危险 dunder（__class__/
  __globals__ 等；__init__ 允许）。
- 查重：factors schema 现列 + config/factors.yaml 条目；**同名指标一律拒绝**并引导
  走 factor-admin 补周期通道（registry 按 indicator_name 去重，重复类会互相覆盖——
  真实 E2E 中 roc 案例证实此闸必要）。
- 晋升：pgrep "run_factor_admin|run_factor_repair" 为空检查（过滤含 pgrep 的自匹配行）
  → 复制为 `factors/<name>_factor.py`（新独立模块，不改既有文件）→ 备份并追加
  config/factors.yaml → 后台 job（`validate --codes 600519.SH` →
  `backfill --baseline-ref HEAD --categories <cat> --max-workers 4 --execute`，
  bash -c 串联），复用 daily_jobs.start_script_job（lock_key="indicators" 与日更/补全共锁）。
- 安全闸：nl-generate 只回填不执行；smoke 同步返回；promote 二次确认。
- QRE 对业务 DB 只读；所有写库走 indicators 官方脚本。

## Scope

1. `gui/factor_nl_compiler.py`：独立系统提示词（FACTOR_AUTHORING 约束 + SMA/ATR
   few-shot）+ 两段式输出协议（`<<<CODE>>>` / `<<<META>>>`，超范围 `<<<ERROR>>>`）+
   `check_code_safety` AST 白名单。`nl_compiler.call_llm` 加可选 `system_prompt` 参数。
2. `gui/factor_create.py`：查重 / 沙箱读写 / run_smoke（subprocess 包装）/
   promote_factor（pgrep 检查 → 复制 → config 追加 → 后台 job；失败回滚）。
3. indicators `sandbox/smoke_factor.py` + `sandbox/factors/`。
4. `gui/app.py`：6 个 `/api/factor-create/*` 路由；job 状态复用
   `/api/admin/daily-jobs/<job_id>`。
5. `templates/admin.html` 因子 tab「新建因子」子区（全中文，与现有风格一致）。
6. `tests/test_gui_factor_create.py`：注入式单测 + Flask test client（不真连 DB）。
7. 文档：indicators FACTOR_AUTHORING §8 + PROJECT_GUIDE 入口表、本文件、09。

## Non-Goals

- 不做 git commit（用户显式约束）。
- 不新增 Python 依赖。
- 只支持模板型指标（pandas_ta 已有函数、单序列/HLC、单/多输出）；超范围走人工通道。

## Expected Tests

```bash
uv run pytest tests/test_gui_factor_create.py -q
uv run pytest tests/ -k gui -q
uv run pytest tests/ -x -q
```

## Acceptance Criteria

- 恶意代码（import os / open / __import__ / 危险 dunder）被安全检查拒绝。
- 查重命中库内现列与 config 同名指标；冒烟 JSON 协议可被 QRE 解析。
- 晋升有 pgrep 闸 + 文件/config 写入 + 后台 job（validate→backfill 限新类别）。
- 真实 E2E：DeepSeek 生成 vidya 因子 → 真实 DB 冒烟通过 → 真实晋升 job 起成功。
- 全量 pytest 绿。

# Implementation Brief (archive: QRE-GUI-STRATEGY-CREATE-P1-001, GUI 策略创建闭环 P1)

## Created By

KIMI_CODE (single agent; 用户批准的方案 2026-08-12)

## Intended Implementer

KIMI_CODE

## Goal

打通"GUI 创建策略 → 进 catalog → dashboard 可见"的闭环：
查重 → 沙箱 → 单股冒烟 → 用户确认晋升 → catalog → 全量回测。

## Semantics (locked by user plan)

- 沙箱目录 `outputs/sandbox/strategies/` 独立于 catalog；refresh 日更只扫
  catalog（include 为空=全量），沙箱天然隔离。
- 冒烟 = 单标的（默认 600519.SH）× 近 180 天，`run_backtest(background=True)`；
  结果以 sidecar `<name>.smoke.json` 记录，run 记录打 sandbox 标记。
- 晋升需用户确认 + 类别白名单（breakout / composite / cross_sectional /
  kline_pattern / mean_reversion / price_volume / trend_following）；
  晋升后立即触发一次全量后台回测（shared 全市场、近 2 年窗，对齐 refresh
  默认 window-years=2；refresh 为独立 CLI 管线，不复用其调用）。
- manual 通道做因子存在性检查（复用 `_default_column_lookup` +
  `find_missing_factor_columns`），缺因子入 handoff 队列且不入沙箱。

## Scope

1. `gui/strategy_create.py`：纯函数层（查重/落盘/列出/晋升/删除，目录可注入）。
2. `gui/app.py`：5 个 API（create / sandbox / smoke / promote / sandbox/delete）。
3. `templates/index.html`：存入沙箱按钮 + 沙箱面板（冒烟/晋升/删除）。
4. `tests/test_gui_strategy_create.py`：注入式单测 + Flask test client API 测试，
   run_backtest mock。
5. 文档：STRATEGY_AUTHORING §3/§4、本文件、09。

## Non-Goals

- 不做 git commit（用户显式约束）。
- 不跑真实全量回测；真实冒烟仅验证单股 6 个月链路一次。
- 不改 refresh_batch / orchestration 管线。

## Expected Tests

```bash
uv run pytest tests/test_gui_strategy_create.py -q
uv run pytest tests/ -x -q
```

## Acceptance Criteria

- 沙箱策略不出现在 catalog 与 refresh 范围；晋升后文件落在正确类别目录。
- 冒烟 run 带 sandbox 标记且可从 UI 跳转；晋升 run 带 promoted 标记。
- 全量 pytest 绿；真实冒烟链路验证通过。

# Implementation Brief (archive: QRE-STRATEGY-FIT-STABILITY-001)

## Task ID

QRE-STRATEGY-FIT-STABILITY-001 (M10.1 v1.1, deferred follow-up recorded in CR-0003)

## Created By

KIMI_CODE (single agent; user direction "请你继续推进下一步任务" 2026-07-19)

## Intended Implementer

KIMI_CODE

## Goal

Deliver the deferred v1.1: persist per-symbol monthly returns as a compact-mode artifact, and add a time-stability metric to the strategy-fit report — so a strategy's pool edge can be judged not only by significance and magnitude but by whether it repeats across months.

## Background Evidence

- M10.1 v1 explicitly deferred time stability: per-symbol monthly returns are not persisted in compact artifacts (recorded in CR-0003 and the M10.1 review).
- The concat window collector (`_collect_window_return_rows`) already produces exactly the needed intermediate: `(window, symbol, total_return)` rows from equity curves — the artifact is a materialization of that row set.
- Compact batches keep equity curves in memory at write time, so the artifact costs one vectorized pass, no re-run.

## Semantics (locked)

- Artifact `symbol_month_returns.csv` (compact mode): one row per (symbol, calendar month) with `total_return` = last/first equity − 1 within the month (identical computation to the window-summary collector; NaN when first equity ≤ 0). Manifest role `symbol_month_returns` with required columns `{window, symbol, total_return}`.
- Stability metric (strategy_fit, per strategy): for the significant pool at pool_tier, per month compare pool mean monthly return vs universe mean monthly return; `stability_ratio` = fraction of covered months where pool > universe (months with ≥1 pool stock having a return that month). Report `stability_months_covered`, `stability_ratio`, `stability_pool_month_mean_min`. Informational (no hard gate in v1.1); strategies without the artifact report blank stability fields.

## Scope

1. `write_batch_result` (compact path): write `symbol_month_returns.csv` from result equity curves via the concat collector (window="M"); register in the batch report manifest (paths + role); required-columns contract in `report_manifest.py`.
2. `analysis/strategy_fit.py`: load the artifact per strategy when present; compute stability fields; add them to `strategy_fit_summary.csv` and the markdown report.
3. Tests: artifact content vs hand-computed oracle, manifest registration/validation, stability computation with synthetic monthly data, absent-artifact blanks, full-suite green.
4. Small-sample pilot (R-QRE-009): 2 strategies × 3 codes × smoke with compact → artifact present and manifest-audited; fit report shows stability columns.

## Non-Goals

- No re-run of existing batches (artifact applies to future batches/refreshes; existing quick_batch_106 lacks it until re-run).
- No buy-hold monthly excess in v1.1 (stability uses within-strategy pool-vs-universe monthly returns — documented semantics).
- No hard stability gate; informational only.

## Expected Tests

```bash
uv run pytest -q
```

## Acceptance Criteria

- Compact batches write `symbol_month_returns.csv`, manifest-registered and passing `qre report-audit`.
- Fit report exposes stability columns for strategies with the artifact; blank otherwise.
- Full pytest suite green; pilot verified on real data.
