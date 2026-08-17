# Coding Handoff

## Task ID

QRE-ADMIN-TIMERS-001 (dashboard 日更定时任务清单补全)

## Summary

- gui/admin.py TIMER_UNITS 新增 3 条：alpha191-daily.timer、cluster-ashare-daily.timer（含 ExecStartPost 的 daily_tags 增量）、cluster-ashare-tags-weekly.timer。纯配置数组追加，无逻辑改动。
- 验证：pytest 1398 绿；systemctl restart qre-gui 后 /api/admin/timers 返回 6 条 installed+active。

## Task ID

QRE-GUI-ALPHA191-GROUP-001 (alpha191 进因子下拉 + GUI 开机自启服务)

## Written By

KIMI_CODE (single agent)

## Summary

- `gui/factor_wizard.py`：`build_factor_groups` 对 `stock_daily_alpha191`（无价格后缀，parse_factor_table_name 返回 None）单独成组 alpha191；`CATEGORY_LABELS` 加 `alpha191: Alpha191 量价因子`。验证：重启 GUI 后 `curl /api/factors` 10 组，alpha191 组 191 项。
- `deploy/hardened/qre-gui.service`（新增）：GUI 常驻 systemd 服务，EnvironmentFile 读 .env，Restart=on-failure，MemoryMax=2G，已安装并 `enable --now`（开机自启生效，实测 active + 200）。
- 测试：`uv run pytest tests/ -x -q` → 1398 passed。

## Task ID

QRE-ALPHA191-STRAT-LOOP-001 (P6：头部 alpha191 因子新建策略闭环自测)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

零代码改动任务：3 个头部 alpha191 因子各设计一个阈值策略，走通
「沙箱→冒烟→晋升→全市场回测→报告→日更登记」全闭环，**无断点、无引擎修复**。

**策略设计**（阈值标定：alpha083/099 本身即 cs_rank 输出 ∈[-1,0]，阈值即
截面分位；alpha042 阈值取自 2024-08-14 起全市场分位数 p90≈0.015/中位≈-0.24）：

| 策略 | 因子语义 | 入场 | 出场 | 持仓 |
|---|---|---|---|---|
| pv06a_alpha083_high_rank_mvp | -RANK(COV(RANK(HIGH),RANK(VOL),5)) | alpha083 > -0.2（前20%） | alpha083 < -0.5 | 10 天，止损 8% |
| pv06b_alpha099_high_rank_mvp | 同族，HIGH→CLOSE | alpha099 > -0.2 | alpha099 < -0.5 | 同上 |
| pv06c_alpha042_high_rank_mvp | (-RANK(STD(HIGH,10)))*CORR(HIGH,VOL,10) | alpha042 > 0.0（≈前12%） | alpha042 < -0.25 | 同上 |

**闭环各环节（耗时实测）**：

1. 沙箱登记（save_to_sandbox：validate+查重+落盘 outputs/sandbox/strategies/）
   3/3 ok，各 ~0.15s。
2. 冒烟（qre backtest-batch，20 大盘股 × 2026-02-14~08-14）3/3 ok：
   57.5s / 46.7s / 49.3s；round trips 129 / 124 / 100，信号正常产出；
   smoke sidecar 已记录。
3. 晋升（promote → strategies/catalog/price_volume/）3/3 ok，各 ~0.15s。
4. 全市场回测（batch_backtest_runner，5560 股 × 2025-08-14~2026-08-14，
   vectorized，chunk 400，compact+workbook，apply-stops，universe-filter，
   benchmark 000300.SH，jobs 3）3/3 ok，各 683/692/694s（eval ~14s，
   preflight ~74s）。产物 outputs/backtests/alpha191_p6/568f665c8217/。
5. 报告：每策略 backtest_report.html/xlsx + 图 + report_manifest 齐全；
   `qre report-audit` status=ok（matched 3 / missing 0 / issues 0）。
6. 日更登记：registry include 空 = 全量扫描 catalog，晋升即被
   refresh_batch 拾取；`refresh_batch.py --check-only --strategies pv06*`
   正常（watermark 2026-08-14 vs state 2026-08-11 → refresh needed）。

**回测关键指标**（batch 每股 100 万满仓复利口径；benchmark=沪深300）：

| 策略 | 总收益 | 基准收益 | 最大回撤 | 交易数 | 胜率 | Sharpe | PF |
|---|---|---|---|---|---|---|---|
| pv06a alpha083 | +1.61% | +11.76% | -1.08% | 17170（2688 股） | 48.8% | 0.77 | 1.12 |
| pv06b alpha099 | +1.03% | +11.76% | -1.11% | 17054（2689 股） | 48.8% | 0.53 | 1.10 |
| pv06c alpha042 | +1.44% | +11.76% | -1.45% | 11637（2694 股） | 49.6% | 0.72 | 1.15 |

（正收益但跑输基准——满仓复利 per-symbol 口径下正 IC 因子的截面优势被
稀释，符合"链路验证"定位；非投资建议，R-QRE-008。）

## Validation

- `uv run pytest tests/ -x -q` → **1398 passed**（无代码改动，无新增测试需求）。
- preflight 小样本（3 股）全 ok：alpha083 coverage 1.0、join 1.0；
  全市场批次 preflight=warning 为 universe 排除计数>0 的设计行为
  （check_universe excluded→warning，见 preflight.py:232），非断点。

## Findings / Follow-ups

- 无断点：alpha191 因子三段式寻址（factors.stock_daily_alpha191.<col>）在
  validate/查重/preflight/eval/backtest/refresh 全链路开箱可用。
- 策略收益口径提示：batch per-symbol 满仓复利会稀释截面选股效应；后续若要
  验证截面超额，可跑 shared-cash + score_weight 变体（未做，超出本任务）。

---

## Task ID

QRE-EVAL-ALPHA191-001 (Alpha191 赚钱效应评估管线 + GUI 路径 C 登记)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

1. **`src/quant_research_engine/evaluation/alpha191.py`**（新增）：口径常量
   （ALPHA191_TABLE / ALL_ALPHA_FACTORS / FORWARD_HORIZONS=[1,3,5,10,20] /
   PRIMARY_HORIZON=5 / QUANTILES=5 / 显著性阈值 0.05+0.55）；
   `daily_rank_ic()`（逐日 Spearman，与引擎 ic_summary 同公式，补引擎不落盘的
   std 供 ICIR）；`summarize_factor_result()`（ic_win_rate 取方向一致率：负 IC
   因子取 1−正向占比；top_minus_bottom=Q5−Q1，quantile=1 为因子最低组）；
   `build_leaderboard()`（|mean_rank_ic| 降序、NaN 垫底）；
   `evaluate_alpha_factors()`（每批 batch_size=10 个因子一次
   ResearchFrameAssembler.build(ts_codes=None, market_fields=["close"],
   factor_fields=FactorFieldRequest.from_target(f,"factors.stock_daily_alpha191.f"))，
   逐因子 evaluate(signal="close > 0" 占位, quantiles=5, 成本引擎默认 None)，
   批后 del+gc；单因子失败记 None 行不阻断）。
2. **`scripts/eval_alpha191.py`**（新增薄 CLI）：--start/--end（默认近 2 年）/
   --factors(all|逗号列)/--top(stdout 打印行数，CSV 始终全量)/--output
   （默认 outputs/alpha191/leaderboard.csv）/--batch-size/--db-url。
3. **`tests/test_eval_alpha191.py`**（新增 6 用例）：合成面板（因子驱动次日
   收益）端到端正 IC/★、排序与列结构、日频 IC、失败行不阻断、CLI main
   （monkeypatch store+evaluate）写 CSV、resolve_factors 校验。
4. **`gui/templates/index.html`**：新增因子 tab 路径说明卡 h2 改
   「路径说明（A / B / C）」并加路径 C 文案（Alpha191 通道，指向
   indicators_tushare/alpha191/README.md，本期不支持 GUI 内新建）。纯文案，
   JS/路由零改动。
5. **引擎/catalog/assembler 零改动**：stock_daily_alpha191 直接走既有
   FactorFieldRequest 三段式寻址（factors.<table>.<column>），无需 factors.yaml
   纳管适配。

## Validation

- `uv run pytest tests/ -x -q` → **1398 passed**（1392 + 6 净增，全绿）。
- 真实小样本（postgresql+psycopg:///tushare_data）：
  - 用户指定窗口 2025-08-01~2026-08-13：3 因子全 None（observation_dates=0）——
    回填当前仅完成 2010→2013 + 日更当日 2026-08-13，该窗口无因子数据，管线
    行为正确（非装配缺陷）。
  - 改用已覆盖窗口 2012-08-01~2013-08-13：alpha001 rank_ic=0.0551/胜率 0.812/
    ICIR 0.890/★；alpha006 0.0512/0.705/0.521/★（top_minus_bottom NaN）；
    alpha012 0.0204/0.624/0.327；234 个交易日。leaderboard 写 /tmp/alpha_eval_smoke.csv。

## Findings / Follow-ups

- **上游数据疑点（未处理，登记）**：alpha006 在回填段逐日仅 ~3 个 distinct 值
  （2013-01-15：2157 行仅 3 值；全窗口 53 万行仅 701 distinct），疑似
  indicators 侧 alpha006 公式把时序 corr 算成截面/常量。引擎 qcut 无法分 5 层
  → top_minus_bottom NaN 是正确表象。建议回填完成后在 indicators 侧核查
  alpha006（GTJA #6 = −corr(open, volume, 10) 应为逐股时序）。
- 回填完成前用默认近 2 年窗口跑 `--factors all` 会得到大量 None 行；待 P3c
  行数/覆盖验证通过后再跑全量 leaderboard。
- ★ 判定用方向一致率（负 IC 因子按反向计），与用户任务书「胜率≥0.55」的
  字面口径有解释性偏离，已在 alpha191.py docstring 注明。

---

## Task ID

QRE-ADMIN-ALPHA191-RECON-001 (dashboard 因子对账登记 stock_daily_alpha191)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

alpha191 面板通道表（indicators_tushare 侧 `alpha191/` 子包日更，独立于
config/factors.yaml 的 category×price 体系）登记进管理台因子对账：

1. **`gui/admin.py`**：
   - 新增 `ALPHA191_TABLE = "stock_daily_alpha191"` 常量；
     `managed_factor_tables()` 在 yaml 推导与 fallback 两条路径都并入该表。
   - `overview_factors()` 的表过滤改为「不符合 `<category>_<price>` 命名
     **且不在纳管清单**才跳过」，alpha191 由此进入对账（watermark/滞后判定）。
   - `EXPECTED_COLUMNS_SCRIPT` 追加读取 indicators 侧
     `alpha191/factors_manifest.yaml`（由 indicators
     `scripts/gen_alpha191_manifest.py` 从 FORMULAS 注册表生成，191 列），
     合成 `stock_daily_alpha191` 的期望列；manifest 缺失时静默跳过（降级不变）。
2. **不做的事**：`parse_factor_table_name` 正则未动 —— admin 的
   因子补全/删列按钮对 alpha191 返回 400（alpha191 回填走自己的
   `alpha191.runner`，不经 run_factor_admin）；factor_wizard 分组也不含它。
3. **测试**：tests/test_gui_admin.py 更新 2 个既有断言（config/fallback 清单
   含 alpha191，fallback 计数 10→11）+ 新增
   `test_factor_status_includes_alpha191`（绿/红分流）。

## Validation

- `uv run pytest tests/ -x -q` → **1392 passed**（1391 + 1 净增，全绿）。
- 真实对账（2026-08-14，`postgresql+psycopg://…/tushare_data`）：
  `factor_status()` 中 `factors.stock_daily_alpha191` watermark=2026-08-13、
  db_cols=191、green=191 / yellow=0 / red=0，`expected_available=True`；
  `overview_factors()` 含该表且不在 lagging_tables。
- 依赖前置：indicators 侧已生成 `alpha191/factors_manifest.yaml`（191 列）
  并完成当日日更点火（5560 行 upsert，alpha191-daily.timer 17:00 工作日）。

## Follow-ups

- alpha191 全历史回填进行中（indicators 侧后台任务），回填完成前列可能
  短暂显示 red（缺列）——对账语义正确，无需处理。

---

## Task ID

QRE-GUI-UIUX-001 (GUI 全站 UI/UX 优化：Data-Dense Dashboard 浅色风格)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

按 ui-ux-pro-max 数据库选定的 Data-Dense Dashboard（浅色）方案执行，不改任何
元素 id / JS 逻辑 / API / 表单字段 / 文案：

1. **`static/style.css` 全量重写**：设计变量集中 `:root`
   （--bg #F8FAFC / --card #FFF / --border #E2E8F0 / --text #1E293B /
   --muted #64748B / --primary #1E40AF / --primary-hover #1E3A8A /
   --ok #16A34A / --warn #B45309 / --err #DC2626 / --radius 6px / --mono），
   全站引用变量。按钮分级体系 .btn / .btn-primary / .btn-ghost /
   .btn-danger-outline / .btn-sm；表格斑马纹 + hover 高亮 + sticky 表头 +
   .num 右对齐 tabular-nums；tab 改下划线式（active 2px primary 指示条）；
   section-toggle 改白底 + 左侧 4px primary 竖条；health-green/yellow/red 与
   .ok/.err 颜色值换为语义色（类名不变）；字体 system-ui + PingFang SC /
   Microsoft YaHei 回退，等宽列 ui-monospace 栈。
2. **`templates/base.html`**：nav 与标题合并为紧凑顶栏 .topbar
   （左 brand「QRE 控制台」，右导航链接）。
3. **按钮分级归类（仅加 class）**：primary 实底仅 btn-run（运行回测）、
   fc-generate（生成代码）、btn-compare、btn-full-run；刷新/验证/加载文件/
   模板/编译/提交申请/查重/冒烟 → .btn-ghost；危险操作（mt-delete、fc-promote、
   sb-delete、fc 沙箱删除、wz-admin-confirm 全量回填）→ .btn-danger-outline。
4. **信息直读化**：admin 健康灯 CSS 级放大为状态条（#ov-health p 16px 半粗）；
   最新交易日 / 批次数 / 磁盘占用加 .kpi（19px 半粗）；估算行数、因子表行数、
   超额收益/最大回撤、批次体积/策略数、run_detail 摘要值、compare A/B/差异列、
   strategy_status_detail 指标值加 .num；admin.html 三处内联 `color:#a80`
   替换为 .health-yellow。
5. **未动**：所有 id、事件绑定、JS 逻辑、API、文案语言；「引擎输出，非投资建议」
   提示保留；tests 断言只引用 id（btn-nl-compile / btn-save-sandbox），无需改断言。

## Validation

- `uv run pytest tests/ -x -q` → **1391 passed**（全绿，无断言改动）。
- 临时实例 `uv run qre gui --host 127.0.0.1 --port 8123`：
  - `curl /` → 200，含 class="topbar"/brand、btn-primary ×2、btn-ghost ×8；
  - `curl /admin` → 200，含 topbar、btn-ghost ×5、btn-danger-outline；
  - `curl /static/style.css` → 含 --primary: #1E40AF。
- 实例已用 `pkill -f 'qre g[u]i'` 杀掉，8123 端口确认释放。

## Files Changed

- `src/quant_research_engine/gui/static/style.css`（全量重写）
- `src/quant_research_engine/gui/templates/base.html`（顶栏）
- `src/quant_research_engine/gui/templates/index.html`（按钮 class）
- `src/quant_research_engine/gui/templates/admin.html`（按钮 class + kpi/num/health-yellow）
- `src/quant_research_engine/gui/templates/runs.html`、`run_detail.html`、
  `compare.html`、`strategy_status_detail.html`（按钮 class / .num 列）

# Coding Handoff (archive: QRE-GUI-HOME-REFACTOR-001, GUI 首页三 tab → 两 tab 重构)

## Task ID

QRE-GUI-HOME-REFACTOR-001 (GUI 首页三 tab → 两 tab 重构)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

1. **`templates/index.html` 整体重写（1549 行 → ~1060 行）**：三 tab（wizard/builder/
   editor）合并为两 tab。「新增策略」（默认 landing）三段垂直流：顶部 NL 面板
   （nl-*，/api/nl_compile 产物填同页底部预览栏，缺因子引导跳「新增因子」tab）→
   中部可视化构建（wizard step1 因子实时枚举 + step2 条件/持仓风控，wz-fill-editor
   改为校验后同页填入 #strategy-yaml 并 scrollIntoView，不再跳 tab）→ 底部 YAML
   预览栏（可编辑）+ 操作行（验证/加载文件/模板/保存模板/存入沙箱）+ 回测参数表单
   （常显精简项 + 默认折叠「高级参数」区：引擎/执行方式/DB URL/market profile/
   输出目录）+ 沙箱策略面板。运行逻辑不变（预检勾选 → 小范围）。「新增因子」tab：
   路径说明卡 + 路径 A（wz-admin-* 新因子申请整体移入）+ 路径 B（fc-create 子区
   从 admin.html 整体移入，/api/factor-create/* 调用不变）。JS 重组为三个 IIFE
   （tabs+section toggle / strategy / factor），元素 ID 全部保留（b-* 除外，全删），
   rerun_yaml sessionStorage 回填改为同页滚动。tab-builder HTML 与其 JS IIFE 全删；
   后端 /api/builder/* 保留，app.py 零改动。
2. **`templates/admin.html`**：因子 tab 的 fc-create 子区 HTML 与 fc JS 全删，
   原地留「→ 新增因子请前往首页」链接（href="/"）；其余不动。
3. **测试**：test_gui_factor_wizard.test_index_page_contains_wizard 与
   test_gui_app.test_index_includes_builder_tab 改为新两 tab 结构断言（含
   fc-create 在首页、tab-builder/builder-layout/b-id 不存在）；
   test_gui_admin.test_admin_page_200 增加 admin 无 fc-create + 跳转链接断言。
4. **文档**：STRATEGY_AUTHORING §3 通道表重写（三入口合一页）；indicators
   FACTOR_AUTHORING §8 改为首页「新增因子」tab 路径 B（路径 A 同页）。

## Validation Output

```bash
uv run pytest tests/ -x -q → 1391 passed, 4 warnings（全绿）
node --check（index.html / admin.html 内联 JS 提取）→ 双双语法通过
scripts/check-progress-docs.sh → passed
```

临时 GUI 冒烟（127.0.0.1:8123，未跑真实回测/backfill）：`/` 含 tab-strategy /
tab-factor / fc-code / wz-factor-groups，无 tab-builder / builder-layout / b-id；
`/admin` 无 fc-create / fc-code，含「新增因子请前往首页」；
/api/factors、/api/factor-create/sandbox、/api/strategies/sandbox 均 200。
进程已清理。

# Coding Handoff (archive: QRE-ADMIN-STRAT-INCREMENTAL-FIX-001, 策略状态 tab 增量结果合并：date_end 停在全量批次的显示 bug)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

问题：策略状态 tab 数据只来自 `outputs/backtests/**/<sid>/backtest/strategy_performance.json`，
而每日增量 refresh（qre-refresh.timer 20:30）只写 `outputs/refresh/incremental/<sid>/`，
date_end 停在最近全量批次（2026-07-27），日更实际已到 2026-08-11。

1. **`gui/refresh_registry.py`**：
   - 新增 `DEFAULT_INCREMENTAL_ROOT = outputs/refresh/incremental`；
     `_load_incremental_result()` 读 `<sid>/backtest/summary_metrics.json`
     （5 键）+ 同目录 `state.json` 仅取 `data_watermark`/`last_processed_date`
     （缺字段容错，不伪造 date_end；symbols 大字段不用于展示）。
   - `latest_strategy_result(sid, backtests_dir, incremental_root=None)` 合并两源：
     增量 mtime 更新 → source="merged"，新鲜字段（date_end/symbol_count/
     traded_symbol_count/mean_total_return/total_trades/positive_return_symbol_rate）
     取增量；全量指标（excess_return_vs_buy_hold/max_drawdown/date_start/
     strategy_name 等）仍取最新批次，附 `full_metrics_as_of`（批次 date_end）与
     `full_metrics_source_file`；artifact_dir 指向增量目录（详情页下载链接随之切换）。
     批次更新 → "batch"；仅增量 → "incremental"。返回新增 `source`/`source_mtimes`，
     原键（metrics/source_file/artifact_dir/mtime）不变。缓存键纳入增量根
     （`strategy_result:<bt>:<inc>:<sid>`），`clear_strategy_result_cache` 同步。
   - `refresh_overview(..., incremental_root=None)`：策略行 date_end 用合并新鲜值，
     新增 `source` 与 `full_metrics_as_of`（仅当 < date_end 时下发，供前端标注）。
2. **`gui/app.py`**：产物下载路由白名单从仅 backtests 扩到 backtests +
   refresh/incremental 双根（root.parents 任一命中即合法）。
3. **`templates/admin.html`**：超额/回撤单元格在 `full_metrics_as_of < date_end` 时
   加小字"（全量截至 YYYY-MM-DD）"；date_start 缺失时区间列容错显示 "— ~ date_end"。
4. **`templates/strategy_status_detail.html`**：来源行标注 batch/incremental/merged；
   回测区间行附全量 as_of 小字。equity_curve.csv（133MB 级）保留下载链接，无内联预览。
5. **测试 `tests/test_gui_admin_strat_tab.py`（+7 条）**：仅增量、merged（增量更新）、
   批次更新保持 batch、缺 watermark 容错、缓存键隔离、overview 行合并值。

## Validation Output

```bash
uv run pytest tests/test_gui_admin_strat_tab.py tests/test_gui_admin_p3b.py -x -q → 39 passed
uv run pytest tests/ -x -q → 1391 passed（1385 + 6 净增，全绿）
```

真实数据验证（2026-08-12）：`latest_strategy_result("mr03a_bollinger_lower_reversion")`
→ source="merged"，date_end=2026-08-11（增量 state.json watermark），
symbol_count 3788 / traded 2261（增量），max_drawdown −0.4636 / benchmark_excess
−0.3454 / date_start 2010-01-04（全量批次），full_metrics_as_of=2026-07-27，
artifact_dir=outputs/refresh/incremental/mr03a_bollinger_lower_reversion。
`refresh_overview()` 同行字段一致（source=merged，full_metrics_as_of=2026-07-27）。

# Coding Handoff (archive: QRE-GUI-FACTOR-CREATE-P2-001, GUI 新因子创建闭环：NL/手写 → 生成草稿 → 查重 → 沙箱冒烟 → 确认晋升 → indicators 入库)

## Task ID

QRE-GUI-FACTOR-CREATE-P2-001 (GUI 新因子创建闭环：NL/手写 → 生成草稿 → 查重 → 沙箱冒烟 → 确认晋升 → indicators 入库)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

1. **`gui/factor_nl_compiler.py`**（新）：因子 NL 生成器。复用 `nl_compiler.call_llm`
   （新增可选 `system_prompt` 参数）与 `nl_config`。独立系统提示词（FactorBase
   约束 + SMA/ATR 两个 few-shot），两段式输出协议 `<<<CODE>>>` / `<<<META>>>`
   （YAML: name/category/column/periods|params），超范围输出 `<<<ERROR>>>` 转
   "请走人工通道"。`check_code_safety(code)`：AST 白名单——只允许 import
   pandas/pandas_ta/numpy/typing/core.factor_base；禁 open/eval/exec/compile/
   __import__/input/globals/locals；禁危险 dunder（__class__/__globals__/
   __subclasses__ 等 12 个；`__init__` 等常规魔术方法允许）；语法错误即拒绝。
   `generate_factor_code(description, http_post=None, env=None)` →
   {ok, code, meta} / {ok: False, code, error}。
2. **`gui/factor_create.py`**（新，纯函数层，repo/runner/job_starter 可注入）：
   - `check_factor_duplicate(name, category, column, params, tables_columns=None,
     config_path=None)`：库内现列（表 `stock_daily_<cat>_<col>`，列名
     `<name>_<suffix>` 精确/前缀匹配）+ config 条目双源查重；同名指标（任意
     类别/价格列）一律拒绝并引导走 factor-admin 通道。
   - 沙箱：`save_factor_to_sandbox`（安全检查 → `sandbox/factors/<name>_factor.py`）、
     `list_sandbox`、`discard_factor`。
   - `run_smoke`：subprocess 跑 indicators `sandbox/smoke_factor.py`（uv run，
     cwd=repo，120s 超时），解析 stdout 最后一行 JSON。
   - `check_no_admin_running`：pgrep -af "run_factor_admin|run_factor_repair"
     为空检查（过滤含 "pgrep" 的行，消除 bash -c 自匹配误报）。
   - `promote_factor(name, category, column, params, ...)`：pgrep 闸 → 复制
     `factors/<name>_factor.py`（已存在拒绝）→ 二次安全检查 → 备份 + 追加
     config（periods/params/[null] 三种风格）→ `start_script_job(lock_key=
     "indicators")` 后台跑 `validate --codes 600519.SH --sample-rows 800 &&
     backfill --baseline-ref HEAD --categories <cat> --max-workers 4 --execute`
     （bash -c 串联）；写入失败自动回滚（删文件、恢复备份）。
3. **indicators `sandbox/smoke_factor.py`**（新）：CLI 冒烟——importlib 加载文件 →
   唯一 FactorBase 子类 → DBManager.load_stock_history 只读单股近 N 日 →
   逐参数 calculate() → 断言无异常/列存在/跳过 warmup 非全 NaN/列名规范化无重复；
   stdout 末行 JSON，exit 0/1。
4. **API（`gui/app.py`，6 个 `/api/factor-create/*`）**：nl-generate（只回填不执行）
   / check（安全+查重，DB 挂降级 warning）/ smoke（同步 ≤120s）/ promote
   （409=admin_busy|duplicate_name|job_conflict）/ sandbox / sandbox/delete。
   job 状态复用 `/api/admin/daily-jobs/<job_id>`。
5. **前端 `templates/admin.html`** 因子 tab 加「新建因子」折叠子区：NL 描述框 +
   生成代码 → 代码编辑框 + name/category/column/periods 表单（meta 预填）→
   查重+安全检查 / 冒烟测试 / 晋升入库（confirm 二次确认 + job 轮询）+ 沙箱列表
   （删除）。全中文、零新框架。
6. **测试 `tests/test_gui_factor_create.py`（42 条）**：假 http_post LLM 输出、
   安全检查恶意样本、查重命中/不命中/同后缀不误判、冒烟子进程 mock、promote
   pgrep 闸/复制/yaml 追加/回滚（tmp 假 indicators 树）、API 全链路 Flask
   test client。

## Validation Output

```bash
uv run pytest tests/test_gui_factor_create.py -q → 42 passed
uv run pytest tests/ -k gui -q → 270 passed
uv run pytest tests/ -x -q → 1385 passed
```

真实 E2E（2026-08-12，真实 DeepSeek + 真实 DB）：
- `generate_factor_code("VIDYA 可变指数动态平均线，周期 20")` → VIDYAFactor
  （overlap/close，periods [20]），代码含 get_price_series + p=None/list/int 分支。
- 查重（真实 factors schema + config）：无冲突。
- 冒烟：`sandbox/smoke_factor.py --code 600519.SH --days 400 --params '[20]'` →
  ok，400 行，输出列 `vidya_20`，warmup 288 后非全 NaN，exit 0。
- 晋升（真实 GUI server :8123，POST /api/factor-create/promote）→
  `factors/vidya_factor.py` + config 追加（备份 factors.yaml.bak-20260812T030850），
  job_id `20260812T030850074330`：validate 已通过（exit 0），backfill
  （--categories overlap --execute，4 workers）进行中；backfill 前已确认
  plan noop、无 run_factor_admin 在跑，范围严格只有 vidya_20 一列。
- 查重闸实证：先生成过 roc（周期 25），发现 roc 已注册（params [null]），
  同名拒绝规则因此加入（否则会产生重复 roc 类互相覆盖）。

# Coding Handoff (archive: QRE-GUI-STRATEGY-CREATE-P1-001, GUI 策略创建闭环：查重 → 沙箱 → 冒烟 → 确认晋升 → catalog)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

1. **新模块 `gui/strategy_create.py`**（纯函数层，目录均可注入）：
   - `check_strategy_duplicate(name, catalog_dir, sandbox_dir, scan_sandbox)`：扫
     catalog（rglob `*.yaml` 读 experiment.name）+ 沙箱，命中返回中文冲突描述。
   - `save_to_sandbox(yaml_text)`：validate_yaml → 查重 → 落盘
     `outputs/sandbox/strategies/<name>.yaml`。沙箱独立于 catalog，refresh 日更
     只扫 catalog，天然隔离。
   - `list_sandbox()`：名称/文件/mtime/最近冒烟（sidecar `<name>.smoke.json`，
     由 `record_smoke()` 写入）。
   - `promote(name, category)`：类别白名单（CATALOG_CATEGORIES 7 类）→ 复制到
     `strategies/catalog/<category>/` → 删沙箱 YAML（保留 smoke sidecar）。
   - `discard(name)`：删沙箱 YAML + sidecar。
   - 常量：`SMOKE_DEFAULT_CODE="600519.SH"`、`SMOKE_WINDOW_DAYS=180`。
2. **API（`gui/app.py` create_app 内）**：
   - `POST /api/strategies/create` {mode: manual|nl, yaml_text?|description?}：
     nl 走 `compile_nl`；manual 走 validate_yaml + 因子存在性检查（复用
     `nl_compiler._default_column_lookup` + `find_missing_factor_columns`，缺因子
     入 handoff 队列并返回 code=missing_factors，DB 不可用降级 warning）→
     查重（409）→ 存沙箱。
   - `GET /api/strategies/sandbox`：列表 + 类别白名单。
   - `POST /api/strategies/smoke` {name, code?}：`run_backtest(mode="single",
     codes=[600519.SH], 近 180 天, background=True)`，run 记录打
     `sandbox_strategy`/`purpose=smoke` 标记（`_mark_run` 落盘 status.json），
     run_id 写 sidecar。
   - `POST /api/strategies/promote` {name, category}：promote() 后立即触发一次
     全量后台回测（`mode="shared"`、空 codes=全市场、近 2 年窗，对齐 refresh 默认
     window-years=2；refresh 本身是独立 CLI 管线故不复用其调用）。并发槽满时
     降级为 warning（策略随下次日更运行）。
   - `POST /api/strategies/sandbox/delete` {name}：discard。
3. **前端 `templates/index.html`**（编辑器 tab，无新框架）：编辑器操作行加
   "存入沙箱"按钮；"沙箱策略"面板（列表 + 冒烟/晋升(类别下拉)/删除按钮，
   冒烟状态链接到 /runs/<run_id>）。
4. **测试 `tests/test_gui_strategy_create.py`**（23 条）：查重命中/不命中、
   落盘与列出、缺因子分支（假 lookup + 假 enqueue）、promote 白名单/移动/查重拦截、
   API 全链路（Flask test client，run_backtest mock 掉）。

## Validation Output

```bash
uv run pytest tests/test_gui_strategy_create.py -q → 23 passed
uv run pytest tests/ -k gui -q → 228 passed
uv run pytest tests/ -x -q → 见 05_PROGRESS.md / 10_REVIEW_REPORT.md
真实冒烟：见 10_REVIEW_REPORT.md（600519.SH 近 6 个月，GUI 等价链路）
```

# Coding Handoff (archive: QRE-FACTOR-PANEL-E2E-001)

# Coding Handoff

## Task ID

QRE-FACTOR-PANEL-E2E-001 (GUI factor panel end-to-end acceptance: rsi_9 + 3 deep fixes)

## Written By

KIMI_CODE (single agent)

## Status

DONE (committed)

## Implementation Summary

1. **factor_admin.py**: PLAN/SAMPLE_BACKFILL/FULL_BACKFILL commands now pin
   `--baseline-ref HEAD`. Without it, run_factor_admin's default baseline
   (116d7cd) selects ~291 columns — a full-history recompute of everything
   including statistics semantics — instead of only the requested factor.
   Found during the first real panel run (sample stalled 20+ min).
2. **Regression test**: `test_factor_admin_backfill_commands_pin_baseline_head`.
3. **Acceptance strategy** `gui_accept_rsi14_reversal.yaml` (wizard-built):
   rsi_14 < 30 entry / > 70 exit, 8% stop; registered for the 20:30 refresh
   auto-coverage check.
4. **Panel acceptance facts**: duplicate-factor rejection works (rsi_21
   refused with config rollback); rsi_9 created, sample-verified, full
   backfill 5551 stocks / 13,363,067 rows / 0 failures; values sane
   (rsi_9 > rsi_14 in uptrend, all within [0,100]).
5. **Upstream fixes in indicators_tushare** (commit 9ffefbd): disarmed
   _ensure_hypertable auto-compression; CREATE INDEX gated to
   non-TimescaleDB mode (861-chunk lock convoy, two real stalls).

## Validation Output

```bash
uv run pytest -q → 1319+1 passed (baseline regression included)
rsi_9: 13,363,067 rows / 5,544 stocks / latest 2026-07-31 / 0 out-of-range
compression: 0 chunks, 0 policies after cleanup
```

# Coding Handoff (archive: QRE-REFRESH-INCREMENTAL-001)

# Coding Handoff

## Task ID

QRE-REFRESH-INCREMENTAL-001 (refresh 增量合并：小水印差只跑新增交易日并合并进既有结果)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1319 tests green, 7 new; real-DB equivalence PASS; awaiting commit approval)

## Implementation Summary

- **设计**：docs/design/refresh_incremental.md。核心决策——**复用 7 月增量引擎**（`orchestration/incremental.py::run_incremental`，real-DB gate 曾证分段≡全跑字节一致），不新造合并逻辑：
  - **未平仓持仓延续（最大难点）**：由 checkpoint（`incremental_state.py` per-symbol 状态机：持仓数量/入场信息/trailing 锚/待成交订单存*触发日*/现金）解决；continuation 窗口带 warmup（150 天×2）且最早回溯至最早持仓入场日 −7 天，窗口边界无缝续跑；flat symbol 现金由累计 orders 精确重放。
  - **合并**：orders/trades/failed concat+键去重(keep=last)+排序重写；equity 追加写、汇总时去重；buy-hold 锚定原窗口 first_mark_price。
  - **聚合指标**：`_recompute_summary` 每次从拼接后完整台账重算 summary.csv（总收益/超额/胜率），非增量估计。
  - **失效兜底**：config_hash 不匹配 → 自动 bootstrap；水印差 >45 自然日（≈30 交易日）→ 删 state_dir 全窗重建。
- **实现**（scripts/refresh_batch.py）：`--mode incremental|full`（默认 incremental；`--full-window` 保留旧行为）；`--incremental-threshold-days`（默认 45）；`should_full_rebuild()` / `write_incremental_summary_metrics()`（合并后 summary.csv → backtest/summary_metrics.json，供 delta 报告复用）/ `run_incremental_refresh()`（逐策略编排，单策略失败不阻塞）；增量结果存 `outputs/refresh/incremental/<sid>/`，state.json config 记 mode，last_run.json 记每策略 watermark/updated/new_rows/duration。docstring 更新。
- **测试**：tests/test_refresh_incremental.py 7 例（阈值回退/无 checkpoint/损坏 checkpoint、summary_metrics 聚合、编排 mock（小差不重建/大差删目录重建/单策略失败隔离/参数透传）、合并去重+聚合重算契约）；tests/test_refresh.py 三个旧脚本用例 argv 加 `--mode full` 保持原语义。
- 真实 outputs/refresh/state.json 已备份至 /tmp（未改动真实 outputs；验证全部走临时目录）。

## Validation Output

```bash
uv run pytest -q → 1319 passed (基线 1312 + 7 新增)
# 真实等价性（2 策略 × 200 股 × 2 年窗，临时目录）：
#   watermark=2026-07-31，D1=2026-07-17（10 交易日前）
#   tf01a_ma_cross_20_120:  bootstrap(D1) 351 trades → 增量续跑 +3 = 354
#     vs 一次性 bootstrap(D2) 354，trades_match=True
#     mean_total_return diff=3.5e-18，末日权益 max|diff|=4.7e-10
#   mr01a_rsi14_oversold_reversal: 332 + 0 = 332，match=True，
#     mean_return diff=0.0，equity diff=0.0
#   EQUIVALENCE: PASS（差异仅在浮点舍入内）
```

## Known Limitations

- continuation 不回删滚动窗口起点之前的旧台账（long-run 累积）；需要严格滚动窗口语义时用 `--full-window`。
- universe_filter 只影响新入场，既有持仓保留（7 月设计 §4.3 既定语义）。
- GUI 策略详情页的结果提取搜索 `outputs/backtests/**`，不覆盖增量存储 `outputs/refresh/incremental/`（后续可扩展 latest_strategy_result 数据源）。
- 增量模式不写 batch_summary/delta_report（delta 报告仍属 full 模式；增量每策略指标在 last_run.json 与各 state_dir/backtest/summary_metrics.json）。
- 全量 111 策略首次 bootstrap 仍需完整跑一次（之后每日增量为分钟级）；验证只用了 200 股，全量首次运行成本未实测。

---

# Coding Handoff (archive: QRE-ADMIN-STRAT-TAB-001)

## Task ID

QRE-ADMIN-STRAT-TAB-001 (策略状态 tab 四项修改：详情页链接、四列精简、开关按钮、删除连动产物)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1312 tests green, 13 new; awaiting commit approval)

## Implementation Summary

1. **策略详情页**：`/admin/strategy/<sid>`（新模板 strategy_status_detail.html）= catalog YAML 简介（`strategy_admin.strategy_catalog_info`：头部注释块 + experiment.name + 出入场条件 + 持仓天数）+ 最近结果指标卡 + 产物下载（`/api/admin/strategy/<sid>/artifact/<rel>`，双白名单：产物根在 backtests 内 + 目标在产物根内）。
2. **四列精简**：`refresh_registry.latest_strategy_result()`（`outputs/backtests/**/<sid>/backtest/strategy_performance.json` 取 mtime 最新，300s 缓存，excess 缺失时 benchmark_* 兜底）；refresh_overview 每策略输出 date_start/end、traded/total symbols、excess_return、max_drawdown，无结果 None（前端"—"）。旧列（注册/状态/变化/均值/Δ）删除。
3. **开关按钮（registry v2）**：`{"include": [...], "stopped": [...]}`，兼容纯数组与线上旧格式 `{"strategies": [...]}`（视为 include、stopped=[]）。include 空=全量模式（默认全开启）；`set_strategy_stopped` 只改文件不触发运行（提示"将于下个定时任务生效"）。`refresh_batch.load_registry_ids` 返回 `{ids, stopped}`：ids=include−空判断，主流程 discover 后过滤 stopped（--strategies 优先且不过滤）。按钮绿=开启/灰=停止；横幅文案更新（全量=默认全开启停止除外 / 注册=只跑注册未停止）。
4. **删除连动产物**：`strategy_admin.delete_strategy` 改为删 catalog YAML + 移出注册表（include+stopped 双清）+ 删除 `outputs/backtests/*/<sid>/`（白名单：resolve 后 parent.parent==backtests 根，更深嵌套不动）+ 清结果缓存，返回 deleted_files/deleted_dirs/errors。不做运行中检查（GUI 弹窗文案含"不可恢复"）。
5. 测试：`tests/test_gui_admin_strat_tab.py` 13 个（结果提取最新/benchmark 兜底/缓存/无结果、四列数据、v2 stopped 两模式、旧格式兼容、catalog 简介、删除连动白名单、toggle/详情/artifact 路由含越界）；p3b/manage 旧测试同步 v2 语义。

## Validation Output

```bash
uv run pytest -q → 1312 passed (基线 1299 + 13 新增)
# 真实只读冒烟：latest_strategy_result(mr01a) 正确选中 full_history_overnight/0e875c6a10da
# （benchmark_excess 兜底生效）；产物 25 文件；registry v2 读取线上 {"strategies": []} 正常；
# 详情页 200 含指标卡；artifact 下载 200 (5390B) → SMOKE OK
```

## Known Limitations

- 详情页数据源为"最新 mtime 的 strategy_performance.json"，refresh 滚动窗口（2 年）与全历史批次区间不同，指标卡不标注来源批次类型（source_file 可见）。
- stopped 过滤在 `discover_strategies` 之后按文件名 stem 排除；--strategies 显式指定时不应用 stopped（设计：显式优先）。
- 删除连动只清 `<backtests>/<batch>/<sid>` 一级目录；refresh delta 报告（跨策略合订本）中的该策略行不删（下次 refresh 自动刷新）。
- 后台 refresh 运行中删除策略可能出现该策略目录被重建（运行完成时）——弹窗已提示风险，未加锁。

---

# Coding Handoff (archive: QRE-ADMIN-MANAGE-001)

## Task ID

QRE-ADMIN-MANAGE-001 (管理台 Tab4/Tab5：策略删除、因子补全/删列、维护区清理)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1299 tests green, 15 new; awaiting commit approval)

## Implementation Summary

1. **恢复策略管理**：admin.html 去掉全部 .p3c-hidden（注册/移出、新建策略链接、前往新因子申请）；每行新增"删除策略"（prompt 输入策略 id 二次确认）→ `gui/strategy_admin.delete_strategy`：删 `strategies/catalog/<id>.yaml` + 自动 `unregister_strategy`；outputs 历史产物不删，返回 artifact_dirs 仅提示。
2. **因子补全**：因子状态 tab 每表"补全此表"（confirm）→ POST `/api/admin/factor-backfill` → `daily_jobs.start_script_job`（新增通用任务入口，与管线锁同一 `_active_jobs`；lock_key=indicators 与日更共用）跑 `run_factor_admin.py backfill --baseline-ref HEAD --categories <类别> --max-workers 4 --execute`；黄列文案注明补全只对配置内列生效。
3. **因子删列**：indicators 新官方脚本 `scripts/drop_factor_columns.py`（dry-run 默认；安全检查：纳管表名正则+表存在、禁删 ts_code/trade_date、列必须在库存在、在当前 config 展开集内（项目自身 factor 类纯展开）拒绝除非 --force 并告警）；GUI 黄列 chip 带 ×（绿列无按钮）→ prompt 输入列名确认 → `/api/admin/factor-columns/drop` → 同锁后台任务。
4. **Tab 5 维护区**：`gui/maintenance.py` — `list_batches`（du 体积/mtime/策略数/受保护标记，300s 缓存）+ `delete_batches`（名称正则 + resolve 后 parent==root 白名单 + PROTECTED={refresh, incremental} 拒删 + 删后清相关缓存）；UI 勾选 + 显示合计释放体积 + 输入 DELETE 二次确认。
5. 测试 `tests/test_gui_admin_manage.py` 15 个：策略删除+注册表联动+产物保留提示、通用任务与管线锁互斥、drop 脚本保护列/非法表拒绝（真实 subprocess，免 DB 路径）、批次列表保护标记、白名单删除（受保护/越界/注入名/符号链接逃逸拒绝）、6 个路由用例（命令构造断言、409、400）、页面 MANAGE UI 断言。旧 query-only 页面断言同步更新。

## Validation Output

```bash
uv run pytest -q → 1299 passed (基线 1284 + 15 新增)
# drop 脚本真实冒烟（indicators uv 环境，全程零写入）：
#   --columns rsi_14（配置列）→ 拒绝「在日更配置展开集中，拒绝删除」exit 2
#   --columns ts_code → 拒绝「关键列不可删除」exit 2
#   --table public.stock_daily → 拒绝「非法因子表名」exit 2
#   --columns rsi_14 --force → WARNING + DRY-RUN 打印 ALTER TABLE，exit 0，未执行
# 注：当前全库已无黄列（上游近期扩充了 config），黄列删除按钮暂无可作用对象，语义保留。
```

## Known Limitations

- 批次删除为路由内同步 rmtree（GB 级几秒~十几秒）；未走后台任务（rmtree 非脚本调用），大目录删除时请求会阻塞到完成。
- 补全/删列任务与日更 indicators 管线共锁：日更运行中按钮会 409（设计行为）。
- 因子补全按表类别整体 backfill（官方脚本粒度），无法只补单表中的部分列。
- 删列后 GUI 对账缓存最长 300s 才刷新（pollFsJob 完成时前端会主动重拉，已缓解）。

---

# Coding Handoff (archive: QRE-HAZARD-FIX-001)

## Task ID

QRE-HAZARD-FIX-001 (三隐患修复：注册表语义告警 + overview 冷载提速 + hardened 安装脚本)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1284 tests green, 2 new; awaiting commit approval)

## Implementation Summary

1. **注册表语义告警（隐患 #5）**：`refresh_registry.refresh_overview` 新增 `mode` 字段
   （`full_catalog` 空注册表 / `registry` 仅注册策略）；admin.html 策略状态 tab 顶部显眼横幅
   （`.mode-banner` 黄底）：全量模式显示"当前为全量模式（N 策略）；注册任意策略后将切换为
   仅注册策略模式"；注册模式显示蓝底对应文案。新增 2 测试（mode 两态 + 页面横幅断言）。
2. **overview 冷载提速（隐患 #4）**：瓶颈实测 `COUNT(DISTINCT ts_code)` on 858 chunk =
   10.34s（占首载 9.98s 的绝大部分）。改为 `pg_stats.n_distinct` 估算（0.003s；负值按占比
   × reltuples 处理），键名改 `estimated_symbol_count`，前端标签"估算股票数"，与 reltuples
   估算语义对齐；300s 缓存 + single-flight 不变。FakeStore 同步改 pg_stats 分支。
3. **安装脚本（隐患 #1 准备）**：`scripts/install_timers_hardened.sh`（bash -n 通过，未执行）：
   4 步打印（cp → daemon-reload → enable --now → list-timers 确认），全用 sudo；末尾打印
   quant_ts/indicators 两项目 hardened unit 的手动安装指引（不代装；提示先停旧 unit 防重复触发）。

## Validation Output

```bash
uv run pytest -q → 1284 passed (基线 1282 + 2 新增)
bash -n scripts/install_timers_hardened.sh → OK
# overview 冷载实测（time curl，临时 8899 端口已关停）：
#   改前首载 9.98s（COUNT DISTINCT=10.34s 单独计时确认）
#   改后首载 2.19s（剩余主要为 du -sb 4.18GB 遍历 + 10 表 MAX(trade_date)）
#   二载 0.0015s（缓存命中）
# 估算精度：pg_stats n_distinct=5209 vs 精确 5549（-6.1%，标"估算"可接受）
```

## Known Limitations

- 冷载剩余 ~2.2s 主要是 du 遍历产物目录；如需再降可放宽 du 缓存粒度或后台预热，未做。
- n_distinct 依赖 ANALYZE 统计，新大批入库后估算会滞后到下次 analyze（Autovacuum 正常周期内）。
- install 脚本未执行（按任务要求）；执行后 qre-refresh.timer 才生效。

---

# Coding Handoff (archive: QRE-ADMIN-DASH-QUERY-001)

## Task ID

QRE-ADMIN-DASH-QUERY-001 (管理台 dashboard 查询台化：加载体验 + overview 提速 + 新建/入库 UI 暂缓)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1281 tests green, 3 new; awaiting commit approval)

## Implementation Summary

- **前端加载体验（admin.html）**：新增 `fetchWithTimeout`（AbortController 30s）+ `cardError`（中文错误+重试按钮）；overview/timers/factor-status/refresh 四个 fetch 本已独立，现全部带 30s 超时与 per-card catch（超时/失败只影响该卡片，其余卡片与全部按钮不受影响）；页面骨架静态 HTML 立即渲染，按钮从不等待数据。
- **后端提速（admin.py）**：`CACHE_TTL_SECONDS` 60→300（overview_daily 的 COUNT(DISTINCT ts_code)/858-chunk watermark、overview_factors、du -sb 全部经同一 `_cached` 路径，自动对齐 300s）；`_cached` 升级 single-flight（per-key lock + 双重检查，并发同 key 共享一次计算）。
- **新建/入库 UI 暂缓（代码保留）**：新增 `.p3c-hidden{display:none!important}` + TODO-P3c-restore 注释——策略状态 tab 的注册/移出按钮（JS 生成，包 hidden span）、表头"新建策略（因子向导）"链接、因子状态红区的"前往新因子申请"链接；回测工作台首页（/）的因子向导/NL 通道不动（属回测区）；日更中心"立即运行"保留（触发已完善脚本）。
- **查询体验**：因子状态 tab 加 `fs-search`（按表名/列名客户端即时过滤 .fs-table）；策略状态 tab 加 `ob-search`（按策略 id 过滤 .ob-row）；汇总计数不变。
- 测试：TTL=300 断言、single-flight 并发共享（4 线程 1 次计算）、页面查询台模式断言（搜索框存在、p3c-hidden ≥2、TODO 标记、红区链接仅在隐藏 span 内）。

## Validation Output

```bash
uv run pytest -q → 1281 passed (基线 1278 + 3 新增)
# time curl 实测（临时 8899 端口，已关停）：
#   GET /admin                 0.004s（骨架）
#   /api/admin/overview 首载   9.98s（冷缓存：COUNT DISTINCT + du + 858 chunk）
#   /api/admin/overview 二/三载 0.0009s / 0.0010s（300s 缓存命中）
#   /api/admin/factor-status   1.70s → 0.02s；timers 0.017s；refresh 0.004s
```

## Known Limitations

- overview 冷缓存首载仍 ~10s（COUNT DISTINCT 858 chunk 为真实成本；single-flight 保证并发只算一次，前端卡片独立不阻塞其它区）。若要首载也快，需把 distinct count 换估算（pg_stats），留待用户拍板。
- 隐藏的注册/新因子/新策略功能的路由与后端逻辑全部保留可用（仅 UI 隐藏），P3c 恢复只需去掉 p3c-hidden。
- 搜索为客户端过滤（不重新请求），346 列 chip 全部渲染在折叠 details 内，未做虚拟化。

---

# Coding Handoff (archive: QRE-ADMIN-STATUS-REFocus-001)

## Task ID

QRE-ADMIN-STATUS-REFocus-001 (管理台定位修正：撤数据查询，因子状态三方对账，策略状态重组)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1278 tests green; awaiting commit approval)

## Implementation Summary

- **撤 Tab 3 数据查询**：删除 `/api/admin/query/daily`、`/api/admin/query/factor` 路由；`admin.py` 删除 `query_daily`/`query_factor`/`rows_to_csv`/`_clamp_limit`/`MAX_QUERY_LIMIT`（仅服务于此）；admin.html 查询 tab/JS 全撤；相关 11 个测试删除/改写（含路由 404 断言）。
- **新 Tab 因子状态**（`admin.factor_status` + GET `/api/admin/factor-status`）：三方对账仅状态——a) 库中列（纳管表 get_table_columns 剔除 ts_code/trade_date）；b) 日更应存在列；c) watermark。标注 green/yellow/red + 汇总计数 + 红列链向新因子申请；未纳管孤儿表保持信息段。
- **日更列展开方式（选择与理由）**：选用 subprocess 调 indicators_tushare 自身 uv 环境跑**纯展开脚本**（`FactorRegistry.discover` + `load_factor_specs` + `resolve_specs` + 每个 factor 实例 `preview_columns(params)`），不用 `run_factor_admin.py plan`/`collect_expected_columns`——后者经 `load_tasks` 会写 meta schema（ensure_supporting_schemas/register_*），违反只读定位；纯展开不实例化 DBManager、零 DB 接触，且用项目自己的 factor 类做输出列命名（权威，含 macdh/macds 等多输出与参数后缀）。实测 1.4s 展开 10 表 206 列 0 失败；300s 缓存。失败降级 `_config_level_tasks`（直接解析 yaml 为 指标名+类别+价格列+参数，标注"配置级"）。
- **Tab 4 重组为"策略状态"**：tab 改名，内容沿用（catalog × 注册表 × delta + 注册/移出 + 因子向导链接）。
- 测试：新增 4 个对账用例（展开成功/失败、三路状态标注含汇总、降级配置级）+ 3 个路由用例（查询 404、factor-status 200/503）；p3b 页面断言随改名更新。

## Validation Output

```bash
uv run pytest -q → 1278 passed (1282 − 11 查询用例 + 7 新用例)
# 真实只读冒烟（实际执行）：expected_available=True；summary green=206 yellow=138 red=0；
# 10 纳管表逐表计数合理（green 合计恰等于配置展开 206 列，0 缺列）；
# unmanaged=[stock_daily_vortex_close] → SMOKE OK
```

## Known Limitations

- 138 个 yellow（在库不在日更配置）为历史配置删减的真实状态，仅展示不处理。
- 配置展开每次缓存 300s；factors.yaml 变更后最长 5 分钟才在对账中反映（P1.5 新因子链本身写 yaml 后sample 回填，不经过此缓存路径，不受影响）。
- 黄列没有"重新纳入日更"按钮（属 P3c/配置编辑范畴）；红列仅链接到向导新因子申请。
- 策略 Tab 的每策略信息仍依赖最近一次 delta_report（refresh 机制所限）。

---

# Coding Handoff (archive: QRE-ADMIN-CONSOLE-P3B-001)

## Task ID

QRE-ADMIN-CONSOLE-P3B-001 (管理台 P3b：日更手动触发 + 接入中心/refresh 注册表)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1282 tests green, 18 new; awaiting commit approval)

## Implementation Summary

- **refresh 注册机制（选择与理由）**：refresh 原生 = 全量扫描 catalog + `--strategies` 过滤，无注册表、无 per-strategy watermark（state 仅全局 last_data_date）。最小改动方案：新增注册表文件 `outputs/refresh/registry.json`，`scripts/refresh_batch.py` 增加 `--registry`（默认该路径），文件存在且非空时自动作为策略过滤（`--strategies` 显式给定优先；文件缺失/空/损坏 → 全量扫描，与现状逐字节一致）。理由：复用既有 `discover_strategies` 过滤通道，不改 systemd unit（timer 未安装，用户安装后自动生效），不引入第二套状态。
- 新模块 `gui/daily_jobs.py`：三管线命令表（quant-ts `sync_manager.py --mode daily`、indicators `run_daily.py --max-workers 4`、qre-refresh `scripts/refresh_batch.py --jobs 4`；uv=`/home/van/.local/bin/uv`，cwd 各项目根）；每管线独立锁（重入 RuntimeError→409）；后台线程 subprocess，落盘 `outputs/gui-console/daily-jobs/<job_id>/{status.json,output.log}`；`journalctl_tail`（读不需 root，失败回退项目 logs 目录最新 .log tail）。
- 新模块 `gui/refresh_registry.py`：注册表 load/save/register/unregister（去重排序）、`list_catalog_strategies`、`refresh_overview`（state + 注册表 + 最新 delta_report.json 每策略 status/transition/收益/Δ）。
- `gui/app.py`：POST `/api/admin/daily-jobs/<pipeline>`（404/409）、GET `/api/admin/daily-jobs/<job_id>`、GET `/api/admin/daily-logs/<pipeline>`、GET `/api/admin/refresh`、POST `/api/admin/refresh/register|unregister`（catalog 校验 400）。
- `templates/admin.html`：Tab 2 改"日更中心"，每卡片"立即运行"（confirm 弹窗）+"最近日志"按钮 + 任务区 3s 轮询日志 tail；新 Tab 4"接入中心"：refresh state/delta 摘要 + 全 catalog 注册表（加入/移出按钮）+ 因子向导入口链接。
- 测试 `tests/test_gui_admin_p3b.py` 18 个：registry loader（缺/空/坏→None）、注册读写去重、catalog 列举、refresh_overview 组装、daily job 命令构造/失败/管线锁/未知管线、journalctl 正常/回退/无回退、路由 200/400/404/409 与注册全流程。另：test_gui_admin 旧断言随 tab 改名"日更中心"更新；test_gui_factor_wizard 锁测试 sleep 0.3→0.6 消抖（全量并发下曾偶发）。

## Validation Output

```bash
uv run pytest -q → 1282 passed (基线 1264 + 18 新增)
```

## Known Limitations

- 未真实触发三条管线脚本（按任务要求 mock subprocess）；首次手动触发建议盯 output.log。
- refresh 无 per-strategy watermark（机制本身是全量滚动窗口重跑）；Tab4 的"每策略"信息来自最近一次 delta_report，首次运行前为空。
- 注册表生效后，移出注册表的策略不再被日更覆盖（其历史批次仍在 outputs）；这是机制语义无误但需用户知晓。
- journalctl 回退仅覆盖 quant-ts/indicators 的 logs 目录；qre-refresh 无项目日志目录（timer 未安装）。
- Tab 5 维护区未做（P3c）。

---

# Coding Handoff (archive: QRE-ADMIN-FACTOR-HEALTH-FIX-001)

## Task ID

QRE-ADMIN-FACTOR-HEALTH-FIX-001 (管理台因子健康灯误报修复：纳管表机制)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1264 tests green, 26 admin 例；awaiting commit approval)

## Implementation Summary

- 问题：`factors.stock_daily_vortex_close`（0 行孤儿表，历史 admin 遗留）被报滞后 → 健康灯红色误报。真实链路：indicators_tushare 只写 10 张规范类别表，vortex 数据在 trend_close 内且新鲜（13,460,834 行至 2026-07-27）。
- `gui/admin.py`：新增 `managed_factor_tables()`（读 indicators_tushare config/factors.yaml 的 category+column 组合推导 `stock_daily_<category>_<column>`，已实测推出恰好 10 张表；repo 不可用回退 `MANAGED_FACTOR_TABLES_FALLBACK` 硬编码 10 表）；`overview_factors` 拆分为 `tables`（纳管，含 watermark/滞后判定；纳管但 schema 缺失的也如实列出 watermark=None）与 `unmanaged_tables`（孤儿表信息段：表名+估算行数，不参与健康灯）；`lagging_tables` 只含纳管表。
- `templates/admin.html`：因子卡片增"纳管表 N 张"计数与"未纳管表（不参与健康灯）"信息行。
- 测试：FakeStore 支持按表 watermark；新增 4 例（config 推导、repo 缺失回退、孤儿进未纳管段、孤儿不影响健康灯）；既有 overview/路由用例改为显式 monkeypatch 纳管清单（环境无关）。

## Validation Output

```bash
uv run pytest -q → 1264 passed (基线 1260 + 4 新增)
# 真实只读冒烟：managed=10，unmanaged=[stock_daily_vortex_close(-1 估算)]，
# lagging=[]，health=green「全部对齐 2026-07-27」→ SMOKE OK
```

---

# Coding Handoff (archive: QRE-ADMIN-CONSOLE-P3A-001)

## Task ID

QRE-ADMIN-CONSOLE-P3A-001 (统一管理台 P3a：只读总览 + 日更状态 + 数据查询)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1260 tests green, 22 new; awaiting commit approval)

## Implementation Summary

- 新模块 `gui/admin.py`（纯只读：SELECT + systemctl show + du）：
  - `overview_daily`：pg_class.reltuples 估算行数、MAX(trade_date)、COUNT(DISTINCT ts_code)、最近 15 个 distinct trade_date（60s TTL 缓存）。
  - `overview_factors`：11 表估算行数 + 各表 watermark + 相对日线 watermark 的滞后表清单（缓存）。
  - `overview_backtests`：批次数、策略产物目录数、du -sb 占用（outputs 符号链接先 resolve——冒烟发现 du 只量链接本身 21B，已修为 4.18GB）。
  - `parse_systemctl_show`/`timer_status`：逐管线查 timer+service（NextElapse/ActiveEnter/ExecMainStatus/Result/ActiveState/UnitFileState/LoadState）；unit 不存在 → not_installed，qre-refresh 附安装命令文本。
  - `health_status`：全对齐 green、最小滞后 ≤3 天 yellow、否则/缺数据 red。
  - `query_daily`/`query_factor`：参数化 SQL、limit 钳制 ≤1000；因子表名走 `parse_factor_table_name` 正则 + table_exists，列名走 get_table_columns 白名单（实时枚举防注入）；`rows_to_csv`。
- `gui/app.py`：GET `/admin`、`/api/admin/overview`（三域+健康灯，DB 挂 503）、`/api/admin/timers`、`/api/admin/query/daily`、`/api/admin/query/factor`（JSON + ?format=csv 下载，400 校验）。
- `templates/admin.html`（新）：三 tab 中文页面；总览三卡片+健康灯+刷新；日更三管线卡片（qre-refresh 显示未安装+安装命令文本，无按钮）；查询双表单（因子下拉 optgroup 复用 /api/factors）+ 分页 + CSV 链接。`base.html` 导航加"管理台"。`style.css` 追加卡片/健康灯样式。UI 无任何未实现的 P3b/P3c 按钮。
- 测试 `tests/test_gui_admin.py` 22 个：白名单拒非法表/列名（含注入串）、limit 钳制、CSV 格式、参数化断言（值不进 SQL 文本）、systemctl 解析（正常/未安装）、health 三色、overview（fake store）、du 缓存命中、路由 200/400/503。不连真 DB。

## Validation Output

```bash
uv run pytest -q → 1260 passed (P1.5 基线 1238 + 22 新增)
# 真实 DB 只读冒烟（实际执行）：
# daily: est_rows=13,296,204 watermark=2026-07-27 symbols=5,549 recent=[07-27,07-24,...]
# factors: 11 tables, lagging=[factors.stock_daily_vortex_close]
# backtests: batches=5 strategy_dirs=6 size=4.18GB latest=refresh
# health: red（vortex 表无数据 — 真实状态）
# timers: quant-ts installed(active, next 07-28 16:30, last exit=1 exit-code)；
#         indicators installed(active, next 16:40, success)；qre-refresh not_installed + hint
# query_daily/factor 000001.SZ 2026-07: total=19, 首行数值正确 → SMOKE OK
```

## Known Limitations (P3b/P3c)

- 手动触发日更、接入中心（refresh 注册）、维护区（产物清理）未做，UI 无对应按钮。
- quant-ts service 上次 exit=1（exit-code）为真实状态，仅展示不处理。
- vortex 表空导致健康灯红 —— 真实数据状态，留待上游补齐。
- COUNT(DISTINCT ts_code) 为精确 count（858 chunk，~2s 级），已加 60s 缓存兜底。
- timer 日志 tail 未做（P3b 随手动触发一起）。

---

# Coding Handoff (archive: QRE-GUI-FACTOR-WIZARD-001)

## Task ID

QRE-GUI-FACTOR-WIZARD-001 (GUI 因子前置三步向导 + indicators_tushare 新因子申请联动)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1238 tests green, 28 new; awaiting commit approval)

## Implementation Summary

- 新模块 `gui/factor_wizard.py`：`parse_factor_table_name`（命名规律 `stock_daily_<category>_<price_col>` 已实库确认 11 表）+ `build_factor_groups`（类别中文分组 + 行情组，剔除 ts_code/trade_date）+ `load_factor_tables_columns`（只读 information_schema 实时枚举）+ 条件/YAML 纯函数 `build_condition`/`combine_conditions`/`build_strategy_yaml`（比较+布尔，生成后过 validate_yaml）。
- 新模块 `gui/factor_admin.py`：`indicators_repo`（env `QRE_INDICATORS_REPO`，默认 `<workspace>/indicators_tushare`，已验证解析正确）；`read_indicators`/`parse_periods`（逗号正整数校验）；`append_factor_entry`（.bak-时间戳备份 + 文本追加，category 取自同名现有 entry）+ `rollback_config`；任务状态机 `start_factor_job`（单任务锁 → 备份追加 → 后台线程 validate → plan → sample backfill --execute → awaiting_execute_confirmation；失败即停并回滚 yaml）+ `confirm_execute`（人工确认 → 全量 backfill --execute）；状态/日志落盘 `outputs/gui-console/factor-admin/<job_id>/{status.json,steps.log}`；step_runner 可注入。
- `gui/app.py`：GET `/api/factors`（DB 挂 503 中文）、GET `/api/factor-admin/indicators`（配置缺失 503）、POST `/api/factor-admin/request`（400 校验/409 锁）、GET `/api/factor-admin/jobs/<id>`、POST `/api/factor-admin/<id>/execute`（状态闸 409）。
- `templates/index.html`：新首屏"因子向导" tab（YAML 编辑器改标"高级"）：Step1 分组 checkbox + factor_fields 预览；Step2 四段式条件行（左下拉/运算符/右类型切换/右操作数）+ 出入场组 AND/OR + 持仓/stops + 实时 YAML 预览 + "校验并填入编辑器"（安全闸不变）；Step3 指标/价格下拉 + 周期校验 + 任务卡片（3s 轮询、日志 tail、awaiting 时显示"确认全量回填"按钮）；NL 缺因子错误加"前往新因子申请"链接（预填指标名/周期猜测）。`style.css` 追加向导样式。
- 测试 `tests/test_gui_factor_wizard.py` 28 个：表名解析、分组/标签/剔列、条件各运算符与右值类型、AND/OR、YAML 生成（出入场/stops/校验失败）、periods 校验、yaml 追加/备份/回滚（临时目录副本，未碰真实 repo）、任务状态机成功链+确认执行、失败回滚、锁冲突、错误状态确认、路由 200/400/404/409/503。

## Validation Output

```bash
uv run pytest -q → 1238 passed (P2 基线 1210 + 28 新增)
# 真实环境只读冒烟：load_factor_tables_columns() → 9 因子组 346 列 + 行情组 7；
# read_indicators(真实 repo) → 69 指标名 / 3 价格列。SMOKE OK
```

## Known Limitations

- 全量回填链路未真实执行（按任务要求 mock subprocess）；首次真实跑建议先小样本观察 steps.log。
- factors.yaml 追加为文本块（不保注释往返，但不动既有内容；pyyaml 可正常解析，已验证）。
- Step2 仅比较+布尔；算术组合（如 close/ma-1）留 P3。跨周期（上穿/下穿）同 P2 限制。
- params 型指标（如 kama [10,2,30]）暂只支持 periods 输入；params 申请留待后续。
- 向导 alias 冲突时前端加 `_2` 后缀；极长列名列表（346 列）在折叠 details 内渲染，未做搜索过滤。

---

# Coding Handoff (archive: QRE-GUI-WORKBENCH-P2-001)

## Task ID

QRE-GUI-WORKBENCH-P2-001 (GUI 回测工作台 P2：自然语言 → 策略 YAML 编译器，通道 C)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1210 tests green, 16 new; awaiting commit approval)

## Implementation Summary

- 新模块 `gui/nl_compiler.py`：配置全走 env（`QRE_NL_LLM_BASE_URL/API_KEY/MODEL`，OpenAI 兼容 chat completions，stdlib urllib，60s 超时，无新增依赖）；`build_system_prompt` 注入真实 DSL 说明（StrategySpec 字段 + 信号表达式安全子集，crosses_above 按 compiler 现状降级为当周期比较并如实告知模型）+ `_INDICATOR_CATALOG` 因子目录 + 2 个精简 few-shot（取自 catalog mr01a 与 GUI 默认 bollinger）；`strip_yaml_fence` 剥围栏 → 复用 `engine.validate_yaml` → 复用 `factor_request_queue`（`find_missing_factor_columns`/`build_requests_for_strategy`/`upsert_requests`）做因子存在性检查，缺因子写队列并返回中文"已搁置"；DB 不可用时跳过检查并带 warning。返回 `{"ok", "yaml"|"error"+code+草稿}`。安全闸：编译结果只填编辑器，前端无任何自动执行路径。
- `gui/app.py`：POST `/api/nl_compile`（空描述 400，未配置 503，其余 200）。
- `templates/index.html`：编辑器页顶部"自然语言描述策略"文本框 + "编译为 YAML"按钮 + 状态区；成功填入 YAML 编辑器并提示"请检查确认后再提交回测"，失败显示中文错误与可编辑草稿；`static/style.css` 追加 `.nl-panel`。
- 测试 `tests/test_gui_nl_compiler.py` 16 个：配置缺失/完整、prompt 内容、围栏剥离、正常往返（含围栏）、LLM HTTP 异常、非法 YAML 回传草稿、非 YAML 输出、缺因子入队（校验队列文件内容）、DB 不可用跳过检查、路由 400/503/200（urlopen 全 mock）、首页含通道 C UI。

## Validation Output

```bash
uv run pytest -q → 1210 passed (P1 基线 1194 + 16 新增)
```

## Known Limitations

- 因子目录注入为指标目录（名称:类别）+ 命名约定，非全量列清单（控制 token）；模型可能生成不存在的列名 → 由因子存在性检查兜底（需 DB 可用）。
- 无 DB 时跳过因子检查（带 warning），缺因子要待提交回测时才暴露。
- "上穿/下穿"语义降级为当日比较（与现有 compiler 一致），非真正的穿越事件检测。
- 未对真实 LLM 做端到端验证（无配置凭据）；提示词质量需真实环境调优。

---

# Coding Handoff (archive: QRE-GUI-WORKBENCH-P1-001)

## Task ID

QRE-GUI-WORKBENCH-P1-001 (GUI 回测工作台 P1：参数表单 + 异步限流 + 出口强化 + run 对比)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1194 tests green, 22 new; awaiting commit approval)

## Implementation Summary

- `gui/engine.py`：`run_backtest` 扩展签名（profile_overrides / engine_impl / stop_loss/take_profit/trailing_stop / precheck / background，全部带向后兼容默认值）；`background=True` 时 daemon 线程执行、立即返回 status=running，结束回写 status.json（含 artifacts）；模块级锁 + 计数实现全局 2 并发槽位（`try_acquire_run_slot`/`release_run_slot`）；`apply_precheck` 截断前 20 只 × 近 180 天；`build_market_profile` 用 dataclasses.replace 覆盖 AShareMarketProfile 成本字段；`_execute_engine` batch/shared 传入 stops 与 engine_impl；codes 为空 → ts_codes/symbols=None 走全市场。新增 `extract_run_summary`（rglob 找 strategy_performance.json，回退解析 stdout key=value，含键别名映射）、`compare_run_summaries`（diff=B-A）、`equity_curve_svg`（inline SVG 折线，无 JS 依赖）、`SUMMARY_METRIC_FIELDS`（中文标签+百分比标记）。
- `gui/app.py`：`/api/run` 接收新表单字段；all_market 校验（single 模式拒绝）；非 cli 执行先取槽位，满了返回 409"已有 2 个回测在运行，请稍后再提交"；新增 `/compare?a=&b=` 页面路由；run_detail 传入摘要行 + 权益 SVG；注册 `fmtval` Jinja 过滤器（两位小数/百分比）。
- 模板：`index.html` 参数面板中文化全表单（标的/区间快捷键/摩擦/规则/引擎/预检默认勾选），提交后跳转提示；`run_detail.html` 预检横幅 + "放大到完整范围"按钮（用 request.json 的 full_params 重提）、摘要卡、artifact 按 xlsx/csv/json/其他分组、权益 SVG、running 时 3 秒 meta refresh；`runs.html` 对比复选框（限选 2 个）+ running 自动刷新；新增 `compare.html`（并排表 + 差异列红绿着色）；`base.html` 加 head block；`style.css` 追加 P1 样式。
- CLI executor 路径未动。
- 测试：`tests/test_gui_workbench.py` 22 个新用例（成本覆盖、预检截断、槽位限流、409、预检 full_params 记录、参数透传、摘要提取两路、对比差值、SVG、页面路由）；`tests/test_gui_app.py::test_api_run_success` 适配异步语义（先 running 后轮询 completed）。

## Validation Output

```bash
uv run pytest -q → 1194 passed (基线 1172 + 22 新增)
```

## Known Limitations (留给 P2/P3)

- 预检仅截断代码清单与区间，全市场预检仍是全 universe 拉数据（区间截断控制体量）。
- run 对比为摘要指标级；无曲线叠加图（P3）。
- 无任务取消按钮；NL→YAML 编译器属 P2。
- 全市场模式依赖 assembler ts_codes=None 全量加载，内存风险由 2 并发限流 + 预检缓解。

---

# Coding Handoff (archive: QRE-FULLHISTORY-BATCH-001)

## Task ID

QRE-FULLHISTORY-BATCH-001 (111-strategy full-history overnight batch)

## Written By

KIMI_CODE (single agent)

## Status

DONE (111/111 OK; docs synced; awaiting commit approval)

## Implementation Summary

- Ran `scripts/run_full_history_overnight.sh` twice (agent-launched): batch `7a7091245d87` 22 ok / 89 error (281min), then after DB fix resume batch `0e875c6a10da` 89/89 ok (1381min). Range 2010-01-04→2026-07-27, 5,547 symbols.
- Root cause of 89 errors: TimescaleDB catalog empty (all hypertable registrations lost), orphan chunks under inheritance (stock_daily: 858). Plan-time locks × jobs 4 exhausted lock table (64×100). Fix: user ran `ALTER SYSTEM SET max_locks_per_transaction = 512` + postgres restart. Timescale re-registration still open.
- Aggregated `outputs/backtests/full_history_overnight/aggregate_summary.csv` (111 rows). Headline: mean strategy_total_return -3.11% vs buy-hold +93.58%; 0/111 beat buy-hold; mean benchmark excess -36.31%; mean DD -48.24%; win rate 43.52%; best tf01a +2.17%, worst pt03a -51.37%. Per-symbol excess columns present for M10.4 clustering.

# Coding Handoff (archive: QRE-OVERNIGHT-FULLHISTORY-PREP-001)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting commit approval)

## Implementation Summary

1. `scripts/run_full_history_overnight.sh`: manual overnight full-history batch — all 111 catalog strategies, `2010-01-04` → run day, vectorized engine, `--jobs 4 --symbol-chunk-size 400 --compact --workbook --apply-stops --universe-filter --metadata-columns board industry_group market_cap_bucket liquidity_bucket --benchmark-table reference.index_daily --benchmark-code 000300.SH --skip-preflight --skip-eval --resume`, output `outputs/backtests/full_history_overnight`, tee log `outputs/backtests/full_history_overnight_<ts>.log`. Usage: `bash scripts/run_full_history_overnight.sh`.
2. Outputs cleanup: `~/qre-outputs/backtests/` 19G → 2.9G. Deleted `full_batch_106` (15G, superseded by quick_batch_106), `profile_baseline`, `full_history_check2`, hash dirs `199494f22100 1de849b37935 47b7a9906d90 b87003a71839 dd5b0e5037d4`. Archived `full_batch_106/61e67b53b644/batch_summary.json` → `~/qre-outputs/_archive/full_batch_106_summaries/`. Kept: `quick_batch_106`, `full_history_cn`, `blank_check`, `refresh`.
3. `.venv-ml` via `uv venv` (host lacks python3.12-venv/ensurepip) + scikit-learn/pandas/numpy; `.gitignore` += `.venv-ml/`; README Quick Start += overnight script line.

## Validation Output

```bash
bash -n scripts/run_full_history_overnight.sh → OK
du -sh ~/qre-outputs/backtests/ → 2.9G (was 19G)
.venv-ml python -c "import sklearn" → (see 05_PROGRESS for recorded versions)
```

# Coding Handoff (archive: QRE-REPORT-BENCHMARK-001)

## Task ID

QRE-REPORT-BENCHMARK-001 (report blank columns + benchmark data/wiring)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + verification; awaiting docs sync and commit approval)

## Implementation Summary

1. **Report blank columns (user policy: fill or delete)**:
   - Filled from engine results: `open_trade_count` (position held at window end), `win_count/loss_count/gross_profit/gross_loss/profit_factor` (from trades), `sortino` (downside-deviation ratio), `information_ratio_vs_buy_hold` (active-return mean/std × √252, enabled by new `buy_hold_equity` column in both engines' equity curves), `turnover` (traded notional ÷ mean equity), MFE/MAE in round_trips (equity-segment excursions, None-safe guards), `run_id` (resolved run id threaded through research_run → both backtest paths).
   - Deleted: `industry` column (100% blank, no source until upstream stock_basic; `industry_group` kept as placeholder). `board` now falls back to `derive_board(symbol)` when frame metadata is NaN.
   - Incremental-mode buy-hold anchor fix: continuation windows re-anchor `buy_hold_equity` to the ORIGINAL window's first mark price (engine's frame-local anchor broke split-run equality — caught by `test_incremental.py`, fixed via summary_inputs `first_mark_price`).
2. **Benchmark data (B1)**: root cause of `reference.index_daily` staleness found — TimescaleDB catalog lost all hypertable registrations while orphan `_hyper_79_*` chunks persisted under `reference.index_daily` (inheritance), making `create_hypertable` fail and silently killing the daily sync task. Fixed in `quant_ts/handlers/reference_data_handler.py`: hypertable activation moved to its own transaction with try/except WARN (plain table is fine; sync never blocked). Resynced all 5 indexes to 2026-07-24 (matches stock_daily watermark). 399006.SZ starts 2010-06-01 (source coverage, documented).
3. **Benchmark wiring (B2)**: research_run batch paths (unchunked + chunked) compute benchmark-relative metrics when `benchmark_table`+`benchmark_code` are set (alpha/beta/IR/tracking error/up-down capture/excess, merged into summary_metrics as `benchmark_*`); runner `--benchmark-table/--benchmark-code/--benchmark-value-column` flags with paired-arg guard; verification: alpha −0.0003, beta 0.0092, IR −2.0884 vs 000300.SH on real data.

## Validation Output

```bash
uv run pytest -q → 1172 passed
index_daily: all 5 indexes fresh to 2026-07-24 (4020/4020/4020/4020/3921 rows)
symbol_performance: only board had 1 blank (now derive_board fallback)
round_trips: run_id/MFE/MAE all filled
benchmark summary_metrics: benchmark_alpha/beta/IR/tracking_error/up_capture/down_capture/excess present
```

# Coding Handoff (archive: QRE-INCREMENTAL-BACKTEST-001)

## Task ID

QRE-INCREMENTAL-BACKTEST-001 (P1 incremental backtest + daily update)

## Written By

KIMI_CODE (single agent, with coder subagent for implementation)

## Status

DONE (implementation + real-DB acceptance gate PASS; awaiting commit approval)

## Implementation Summary (per approved design docs/design/incremental_backtest.md)

1. **State store** (`orchestration/incremental_state.py`): `SymbolState` (cash/quantity/entry info/cost parts/trailing anchor/pending dates) + `StrategyCheckpoint` (schema_version, strategy_id, config_hash — spec YAML + engine impl + profile/stops/universe sha1[:12], last_processed_date, watermark). Hash mismatch or corruption → rebuild.
2. **Incremental engine** (`orchestration/incremental.py`): watermark detection, no-op when W ≤ D, warmup-window frame load (chunked 400), per-symbol continuation via `run_working_incremental` (shared `_run_loop` with `run_working` — no logic fork), checkpoint-symbol exemption from universe re-filtering, cash reconstruction by replaying accumulated orders (bit-exact for full_compound).
3. **Ledgers**: orders/trades/failed (read+concat+dedup keep-last) + equity_curve (append, dedup at summary time) + `summary.csv` recomputed from accumulated ledgers (aligned with batch `_summary_row`). Ledgers written before checkpoint.
4. **CLI + timer**: `scripts/incremental_update.py --strategy <id|all>` (per-strategy try/except, summary table, --dry-run); `deploy/qre-incremental.{service,timer}` (daily 18:30, delivered not installed).
5. **Engine refactor**: vectorized engine's event loop extracted to `_run_loop` shared by `run_working` and the new incremental entry (start_index + initial state + schedule-beyond-frame); public API unchanged (127 related tests green).

## Acceptance Gate (design §5, non-negotiable)

- Synthetic: bootstrap ≡ full batch; incremental(T1)+incremental(T2) ≡ full run byte-identical including rolling-expression warmup, cross-boundary pending orders, trailing anchors, new symbols, idempotent no-op.
- **Real-DB gate: PASS** — mr04a × 50 codes: full [2024-01-01→06-30] vs bootstrap [→03-31] + incremental [→06-30]: orders 70 rows, trades 35, equity_curve 5,849, summary 50 — **all IDENTICAL**. Incremental update runtime **0.3-0.5s** (vs minutes for any replay).

## Files Changed

- New: `orchestration/incremental_state.py`, `orchestration/incremental.py`, `scripts/incremental_update.py`, `deploy/qre-incremental.{service,timer}`, `tests/test_incremental.py` (9)
- Modified: `portfolio/single_symbol_vectorized.py` (shared `_run_loop` extraction)
- `uv run pytest -q` → **1172 passed** (1163 + 9 new)

## Known Limits (documented)

- `summary.csv` does not yet include `metadata_columns` composition (board/cap/liquidity) — follow-up.
- Watermark-day signals schedule pending into tomorrow (by design — matches next-day replay semantics).
- fixed_cash checkpoint cash uses override semantics (tested only implicitly).

# Coding Handoff (archive: QRE-COST-BREAKDOWN-001)

## Task ID

QRE-COST-BREAKDOWN-001 (commission/stamp tax/transfer fee columns)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + real-data verification; awaiting docs sync and commit approval)

## Root Cause (user question: "为什么佣金、印花税列仍然为空")

The MT5-style schema columns (`commission`/`stamp_tax`/`transfer_fee`/`slippage_amount`) existed in the report builders but were **hardcoded to None** — the engine only tracked a combined `cost` (single number from `calculate_cost`), so the components were never computed per order.

## Implementation Summary

1. `AShareMarketProfile.calculate_cost_breakdown(side, notional)`: per-component breakdown (commission with ¥5 minimum, transfer fee, stamp tax on sells only); `total` matches `calculate_cost` exactly (test-locked).
2. Both batch engines (simulator + vectorized, identical columns): order rows gain `price_raw` (pre-slippage), `commission`, `stamp_tax`, `transfer_fee`; trade rows gain `entry_commission/stamp_tax/transfer_fee` + `exit_*` counterparts.
3. Report builders: `build_trades_ledger` now maps real components and computes `slippage_amount = |price_executed − price_raw| × quantity`; `build_round_trips` gains `commission`/`stamp_tax`/`transfer_fee` (entry+exit sums) — components sum exactly to the existing `total_cost`.
4. Tests (2 new): breakdown math (¥5 minimum, sell-only stamp, zero notional, total==calculate_cost), orders/trades carry components with exact sums; the existing dual-engine randomized equality suite covers column identity automatically.

## Validation Output

```bash
uv run pytest -q → 1162 passed (1160 + 2 new)
real sample (mr04a × 3 codes):
  buy: commission 299.85 + transfer 10.00 = cost 309.85 ✓
  sell: commission 289.91 + stamp 483.19 + transfer 9.66 = cost 782.76 ✓
  round trip: commission 589.77 + stamp 483.19 + transfer 19.66 = total_cost 1092.61 ✓
```

# Coding Handoff (archive: QRE-REPORT-CN-001)

## Task ID

QRE-REPORT-CN-001 (report layer: localization, strategy intro, blank filling, 2dp)

## Written By

KIMI_CODE (single agent, with coder subagent for the mechanical layer)

## Status

DONE (implementation; full-market rerun with latest data in flight)

## Implementation Summary (user's 4 requirements)

1. **全面汉化** (display layer): `COLUMN_LABELS`/`KEY_LABELS` maps in `full_market_report.py`; xlsx column headers + Key sheets + Artifacts descriptions + full HTML (sections, metric cards, tables) in Chinese. Sheet names and file names stay English (manifest contracts); CSV headers and values untouched (machine contracts for downstream pandas analysis).
2. **策略说明块**: `_build_strategy_intro()` renders strategy name/id/family, entry/exit conditions, holding days, stop params, universe rules, initial cash, execution mode at the top of the Overview sheet and HTML. Payload threading (`_strategy_identity` + `_run_request_payload` in research_run) now carries strategy_id/name/family/date_start/date_end — the fields the user reported blank.
3. **填空白格**: new shared `data/metadata_compose.py::compose_symbol_metadata` (board via derive_board, industry_group unknown while stock_basic is empty, cap/liquidity buckets from daily_basic) + `merge_symbol_metadata` (fillna, no column duplication); merged into frames in `_run_backtest` and per chunk in `_run_batch_chunked` when metadata_columns requested; `scripts/strategy_fit_report.py` deduped to the shared helper. NaN/None render as `-`.
4. **两位小数**: xlsx cell number_format — ratio columns (return/rate/pct/win/excess/drawdown tokens, count/duration excluded) `0.00%`, others `0.00`; HTML same policy (x.xx%); CSV keeps raw precision (documented decision).
5. **Performance date fix** (self-review catch): date_start/date_end in the Performance sheet were still `-` (engine summary doesn't carry them); added run_request backfill in both batch and shared branches.
6. **Latest data rerun**: watermark 2026-07-24 (daily timers healthy); same 2 strategies × full market × 2010-2026 in flight.

## Files Changed

- `src/quant_research_engine/data/metadata_compose.py` (new)
- `src/quant_research_engine/orchestration/research_run.py` (payload + metadata merge)
- `src/quant_research_engine/portfolio/full_market_report.py` (localization, intro, formatting, date backfill)
- `scripts/strategy_fit_report.py` (shared helper)
- `tests/test_report_cn_localization.py` (new, 19), `tests/test_full_market_report.py` (label updates)

## Validation Output

```bash
uv run pytest -q → 1160 passed (1141 baseline + 19 new)
small-sample xlsx inspection: 汉化表头 ✓ 策略说明块 ✓ Overview 日期/名称 ✓ 元数据列 ✓ 0.00/0.00% 格式 ✓ NaN→'-' ✓
data watermark: 2026-07-24 (fresh)
full rerun: outputs/backtests/full_history_cn/ (in flight)
```

# Coding Handoff (archive: QRE-CHUNKED-BATCH-001)

## Task ID

QRE-CHUNKED-BATCH-001 (full-history OOM fix + universe list_date fix)

## Written By

KIMI_CODE (single agent)

## Status

IN_PROGRESS (chunked path + fixes verified; final 2-strategy validation run in flight)

## Implementation Summary

1. **OOM root cause (WSL2 ×3 crashes)**: a full-market 16-year research frame (~21M rows × ~15 cols incl. strings) is ~3-4GB per worker; two workers + pandas transient copies killed WSL2's memory ceiling.
2. **Symbol-chunked backtest path** (`research_run._run_batch_chunked` + `--symbol-chunk-size N`): per-chunk frame slice load → engine → accumulate → gc; results are byte-identical to unchunked (batch engines are per-symbol independent; equality test `tests/test_chunked.py`). Progress lines per chunk. Universe filter applies per chunk with globally-loaded metadata and a merged `universe_report.json`.
3. **Universe `min_listing_days` bug fix**: `load_universe_metadata` derived `list_date` from each symbol's first bar in `stock_daily`, which starts 2010-01-04 — so every pre-2010 stock had `list_date` ≥ 2010-01-04 and was dropped when the run start minus N days preceded the data history (observed: `min_listing_days` dropped ALL 5,544 symbols, 0 trades). Fix: symbols whose first bar equals the table's data start now get `list_date = NaT` (unknown → kept); only symbols with first bar AFTER the data start are treated as genuinely dated. Regression test added.
4. **--workbook flag** (earlier slice, commit `ea05895`): compact mode can also emit `backtest_report.xlsx` + HTML + charts from in-memory results (no per-symbol trees).

## Validation So Far

```bash
uv run pytest -q → 1141 passed (chunked equality + universe regression)
run 1 (before list_date fix): universe dropped ALL 5544 symbols → caught by zero-trade metrics
run 2 (after fix): in flight — verify trades > 0, charts present, metrics sane
```

# Coding Handoff (archive: QRE-UPSTREAM-FACTOR-DELIVERY-001)

## Task ID

QRE-UPSTREAM-FACTOR-DELIVERY-001

## Written By

KIMI_CODE (single agent)

## Status

DONE (upstream delivery complete; 5/5 strategies unblocked)

## Implementation Summary

1. **Investigation**: canonical project `/home/van/quant-workspace/indicators_tushare` (git main; `/home/van/indicators_tushare` is a stray .venv). systemd timers confirmed: `quant-ts-daily` 16:30 (data sync) → `indicators-tushare-daily` 16:40 (factor update), both enabled — yaml-config factors auto-join the daily schedule with zero scheduler changes.
2. **Edits (indicators repo, no git action)**: `config/factors.yaml` sma periods += 7/9/26/50/52 + `atrraw` entry; `factors/volatility_factors.py` new `ATRRawFactor` class (raw `atr_{n}` naming; identical formula to existing `atrr_10` — pandas_ta RMA/Wilder, discovered and documented).
3. **Project flow**: validate (success/0 failures) → plan (7 target columns confirmed; superset = other pending config columns in overlap/volatility also covered per project config-parity behavior) → small-sample backfill (000001.SZ) → **value parity verified** vs hand-computed SMA/Wilder-ATR (storage-rounding diffs only, 100% non-null) → full-history backfill: **processed 5,544 stocks, failed_count 0**.
4. **Final coverage**: sma_7 13.28M rows/5,541 stocks, sma_9 13.27M/5,539, sma_26 13.17M/5,531, sma_50 13.04M/5,416, sma_52 13.03M/5,415, atr_10 13.26M/5,539.
5. **QRE side**: `factor_request_queue.py recheck` → **7 newly fulfilled, 0 pending**. Small-sample re-run of the 5 shelved strategies: 4 OK + tf07e failed with a NEW root cause — signal expression precedence bug `(sma_7 / sma_65 - 1).abs() > 0.03 & (close > sma_20)` (Python parses `> (0.03 & ...)`). Fixed with parens in BOTH the YAML and `scripts/generate_strategy_yamls.py`; tf07e now OK. **All 5/5 strategies unblocked.**
6. Daily updates: from the next 16:40 trigger, `run_daily.py` covers the new columns automatically (yaml-driven).

## Validation Output

```bash
indicators validate → success, failure_count 0
small-sample parity: sma_7/9/26/50/52 + atr_10 within storage rounding, 100% non-null
full backfill: processed 5544, failed_count 0
queue recheck: 7 newly fulfilled, 0 pending
unblock batch (5 strategies × 3 codes × smoke): 5/5 OK after tf07e expression fix
uv run pytest -q → 1137 passed
```

## Notes

- The full backfill also covered other pending config columns in the overlap/volatility categories (project config-parity behavior) — disclosed and accepted.
- tf07e's precedence bug only surfaced now because the strategy was shelved before ever reaching expression evaluation; the paren fix is in the YAML and the generator (regeneration-safe).
- indicators repo working tree left untouched (their pre-existing uncommitted changes not mine to resolve).

# Coding Handoff (archive: QRE-STRATEGY-FIT-STABILITY-001)

## Task ID

QRE-STRATEGY-FIT-STABILITY-001 (M10.1 v1.1)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + pilot; awaiting self-review and user-approved commit)

## Implementation Summary

1. **Artifact** `symbol_month_returns.csv`: per-(symbol, calendar month) `total_return` (last/first equity − 1, NaN when first ≤ 0) via the concat window collector, written by `write_batch_result` in BOTH modes — scope adjusted from "compact only" to both modes to preserve the M9.1 contract that compact outputs are a strict subset of standard outputs (the committed parity test caught it). Manifest role `symbol_month_returns` with required columns `{window, symbol, total_return}`; passes `qre report-audit`.
2. **Stability metric** (`analysis/strategy_fit.py`): `load_batch` picks up the artifact when present; per strategy at pool_tier — `stability_months_covered` (months with ≥1 pool stock reporting), `stability_ratio` (fraction of covered months where pool mean monthly return > universe mean), `stability_pool_month_mean_min`. Blank when the artifact is absent (older batches). Surfaced in `strategy_fit_summary.csv` and the markdown ranking table (`ratio/months` format). Informational only, no hard gate.
3. **Tests** (3 new): artifact content vs hand-computed oracle + manifest entry + ReportManifest validation; stability computation (pool wins one of two months → ratio 0.5, covered=2, min locked); blanks without artifact. Existing compact-parity test updated via the both-modes decision.
4. **Pilot**: 2 strategies × 3 codes × smoke — artifact written per strategy, audit clean, fit report shows stability columns.

## Validation Output

```bash
uv run pytest -q → 1137 passed, 4 warnings (1134 baseline + 3 new)
pilot: artifact OK; qre report-audit → 0 issues; fit summary stability columns present
```

## Note for Existing Batches

Older batches (incl. quick_batch_106) lack `symbol_month_returns.csv`; the fit report shows blank stability for them. Future batches and refresh runs include it automatically. If stability on the 2024 catalog is wanted before the next scheduled run, a `--resume`-compatible re-run is needed (user decision).

# Coding Handoff (archive: QRE-ANALYTICS-CONCAT-001)

## Task ID

QRE-ANALYTICS-CONCAT-001 (M9.1b ≤30s target completion)

## Written By

KIMI_CODE (single agent)

## Status

DONE — **≤30s acceptance target MET** (backtest stage 25.9s)

## Implementation Summary

1. **Concat window collector** (`_collect_window_return_rows`): one concatenated frame across symbols (per-symbol stable sort preserved for contract equality), one datetime conversion, ONE `groupby([window, symbol], sort=False)` aggregation for first/last — replacing ~5,292 per-symbol pandas groupby objects. Row order contract (dict order, windows ascending) preserved via sort=False first-occurrence semantics.
2. **Concat rolling collector** (`_collect_rolling_return_rows`): output assembled from concatenated numpy arrays into ONE final DataFrame — eliminating per-symbol DataFrame construction + the expensive 5,292-frame `pd.concat`.
3. **Equality gate**: `tests/test_analytics_vectorized.py` (risk.py oracle) passes unchanged; real-DB benchmark diff vs baseline is byte-identical for all six artifacts.
4. **Final benchmark (BENCH4)**: backtest stage **25.852s** (vs 40.172s before this slice, vs 1,718.9s original simulator baseline → **66.5×**); eval 18.4s. New decomposition: frame load ~17s (now dominant), engine ~6s, analytics ~2-3s. The M9.1b ≤30s acceptance line is now MET.

## Validation Output

```bash
uv run pytest tests/test_analytics_vectorized.py -q → 6 passed (oracle unchanged)
uv run pytest -q → 1134 passed
BENCH4 stage_durations_s: {'backtest': 25.852, 'eval': 18.419}
artifacts vs baseline: summary.csv/metrics/window M/Q/Y/rolling_20 ALL IDENTICAL
```

# Coding Handoff (archive: QRE-TRAILING-STOP-BATCH-001)

## Task ID

QRE-TRAILING-STOP-BATCH-001 (M10.2b follow-up)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + verification; awaiting self-review and user-approved commit)

## Current Owner

KIMI_CODE

## Implementation Summary

1. **Semantics (locked, batch-path model)**: anchor starts at actual fill `entry_price`, updates every bar while holding with the bar's `high` (fallback to `mark_price_column` when `high` unavailable); trigger when `close <= anchor × (1 - trailing_stop_pct)` → sell next bar open, reason `trailing_stop`. Precedence: pending retry > holding expiry > stop_loss > take_profit > trailing_stop > exit_signal. Deliberate difference from the shared engine (intraday low/high touch + same-day fill) — documented.
2. **Simulator** (`single_symbol.py`): `trailing_stop_pct` field; `trailing_anchor` state (set on fill, updated per bar, reset on exit); trigger branch at locked precedence.
3. **Vectorized engine**: identical anchor/branch; dense candidate set when ANY stop type enabled (fixed or trailing); `high` column array with close fallback.
4. **Wiring**: `BatchBacktestRequest.trailing_stop_pct` + validation (>0); both batch paths thread it; `ResearchRunRequest.trailing_stop_pct` override (None = spec value when `apply_stops`); runner `--trailing-stop-pct`; batch_summary config echo. Shared-mode passthrough was already wired in M10.2b and now uses the hoisted value.
5. **Tests** (5 new deterministic + randomized suite extended with trailing params): trigger with hand-computed anchor/exit, anchor reset between trades, high-column fallback, precedence vs exit_signal (reconstructed after the first data design let exit_signal preempt — documented), batch validation.

## Files Changed

- `src/quant_research_engine/portfolio/single_symbol.py`, `single_symbol_vectorized.py` (anchor + branch)
- `src/quant_research_engine/portfolio/batch.py` (field + validation + threading)
- `src/quant_research_engine/orchestration/research_run.py`, `batch_runner.py`, `scripts/batch_backtest_runner.py` (override + flag)
- `tests/test_single_symbol_vectorized.py` (+5 deterministic, randomized suite now includes trailing)

## Validation Output

```bash
uv run pytest -q → 1134 passed, 4 warnings (1129 baseline + 5 new)

# R-QRE-009 real-DB small-sample:
#   mr04a × 3 codes × smoke, --apply-stops --trailing-stop-pct 0.05:
#     simulator vs vectorized → summary.csv IDENTICAL
#   A/B (1% trailing vs off): summaries differ — trailing measurably honored
#   real trailing_stop exit observed (000001.SZ)
```
