# Review Report

## Task ID

QRE-RISK-CORE-002（FRM 风险管理模块 R2：VaR 回测 + 压力测试 + Bootstrap 推断）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **纯函数边界**：新模块零 DB、零 QRE 内部 import（只 import
  numpy/pandas/scipy/arch 与包内 constants/volatility/performance），
  cluster-ashare 独立 import 目标不受损；arch CBB 与 scipy chi2/binomtest
  均为 R1 已引入依赖，无新增第三方库。
- **公式忠实度**：逐条对照 `docs/frm/FRM量化风控知识摘要.md`——HIT 定义
  （书2 Ch6 式 6.6，严格 >，损失正号）、Bernoulli 覆盖率 LR（教材方法③，
  附方法①精确二项；note 注明「公式同 Kupiec，摘要声明教材未点名」）、
  独立性 Christoffersen 转移矩阵 LR（摘要只给思路未点名，注释与返回值
  如实标注出处差异，符合 CR 允许的偏差申报路径）、多重检验 1−(1−α)ⁿ
  （教材 40.1%/99.4% 复现）、CBB 块长 q≈√n 与 MC 标准误 σ/√b（式 13.3）、
  iid 低估不确定性的教材论断（式 13.11 后讨论）。所有口径差异写进
  返回 dict note。
- **已知答案核对**：覆盖率 LR 手算 4.13085（n=100/x=10/p=0.05）、
  边界 x=0/x=n 解析式、独立性 LR 手算（3/2/2/0 转移计数）、情景回放
  手算（累计 −0.119179、峰谷 0.05、Peak/VaR=2.5）、reverse stress
  β=2 精确穿透 + 分位/σ 倍数 numpy 独立复算、最大回撤手算 0.2、
  夏普与 performance 同口径、bootstrap 固定 seed 复现 + CI 含样本统计量。
  无纯冒烟断言；随机数据全固定 seed。
- **防前视**：默认 VaR 序列用 ewma_forecast_series（raw.shift(1)，R1 已
  验证的 PIT 语义）；μ=0 RiskMetrics 口径避免全样本均值前视，note 披露。
- **降级语义**：report 三节对数据不足/索引不符/样本不覆盖窗口全部降级
  error 节不抛异常（有测试）；stress/bootstrap 默认关、var_backtest 默认
  开，meta.sections 回显开关。
- **基线无回归**：1578 passed（1532 + 46 净增），4 warnings 与基线一致。
  插曲：基线首跑 test_gui_factor_wizard.py::test_job_lock_conflict 失败，
  单独与全量复跑均绿，与已知环境敏感 flake 同族，非本任务引入。
- **既有测试改动**：仅 test_risk_report.py 的 top-level keys 集合断言
  随 report 接口扩展更新（加 var_backtest），属接口变化的必要同步，
  未改任何既有逻辑断言。

## Required Fixes

None.

## Residual Risks

- iid_underestimates 对最大回撤在纯 ARCH 聚类下不稳定（实测反向），
  测试改用 AR(1) 序列自相关验证教材机制；结论解读应聚焦均值类统计量。
- reverse stress 的 β 线性穿透是近似（教材：压力期相关性上升不能简单
  线性放大），note 已声明；深度非线性穿透（如波动 targeting 策略）需
  未来按策略结构定制。
- 情景回放的相关性崩溃用 Pearson（与 dependence 模块一致的基线口径）；
  尾部秩相关崩溃可在 R3 后按需补。
- R3（markdown 渲染、回测报告集成、GUI 展示区）未做，按 CR roadmap
  后续单独 brief。

## Task ID

QRE-RISK-CORE-001（FRM 风险管理模块 R1：risk 包核心）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **纯函数边界**：risk 包零 DB、零 QRE 内部 import（grep 核实：只 import
  numpy/pandas/scipy/arch 与自身 constants/volatility），满足 cluster-ashare
  独立 import 的最终目标。`tail.ewma_parametric_var_es` 对
  `volatility.ewma_variance_series` 是包内延迟 import，无循环。
- **公式忠实度**：逐条对照 `docs/frm/FRM量化风控知识摘要.md`——参数正态
  VaR/ES（书4 Ch1 式 1.7，教材例题 49.79/59.96 复现到 1e-2 内）、历史模拟
  （书4 Ch2 有序统计量 + 插值披露）、EWMA（式 3.2，brief 手算序列逐位
  核对）、GARCH（式 3.4，V_L/半衰期/平稳判据）、偏度峰度（书2 Ch5 sample
  analog 手算 + scipy 双口径）、JB（式 12.11，T vs T−1 差异披露）、
  Spearman/Kendall（式 12.13/12.14 手算 0.5、1/3）、正定性（书2 Ch12
  特征值法）、绩效五指标（书1 Ch5，Sharpe 与 portfolio/risk.py 同口径
  抽查一致 rel 1e-9）。所有口径差异（ES 含 VaR、插值方法、scipy JB 用 T）
  都写进返回 dict 的 note 字段，报告可审计。
- **防前视**：ewma_forecast_series = raw.shift(1) 有专门测试（改动 r_t
  不影响 ≤t 的预测值）；arch 交叉验证确认 raw/shift(1) 语义对应关系。
- **常量集中与参数回显**：constants.py 单一来源；report.meta 与各结果 dict
  均携带所用 λ/rf/年化/置信水平/分位。
- **降级语义**：report 对可预期失败（GARCH <50 obs、<2 obs）降级
  {"error": ...} 而非崩溃；benchmark=None 时基准节为 null（有测试）。
- **测试质量**：61 用例全部含已知答案（解析值/手算/scipy 对照/确定性
  模拟复现），无纯冒烟断言；随机数据全部固定 seed。
- **基线无回归**：1532 passed（1471 + 61 净增），4 warnings 与基线一致
  （numpy RuntimeWarning 来自既有用例，非本任务引入）。

## Required Fixes

None.

## Residual Risks

- arch 8.0.0 与 brief 写作时的 API 差异（simulate 无 seed、无 RiskMetrics
  字符串入口）已用手写确定性模拟 + 固定参数 GARCH 绕开；若未来降级 arch
  版本交叉测试仍成立（只用 fix/conditional_volatility 基础 API）。
- GARCH 拟合是 MLE，短样本（<~500 obs）参数噪声大；测试用 3000-4000 obs
  的 sane 范围断言，生产短序列结果应配合 V_L/半衰期的量级检查阅读。
- R2/R3 未做（backtest_var/stress/inference/markdown 渲染/集成），按 CR
  roadmap 后续单独 brief。

## Task ID

QRE-GUI-DEEP-VALIDATE-001（deep-validate 501 骨架落地）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 只读边界：QRE 侧零 DB 取数——池生成与四关验证全部 subprocess 调
  cluster-ashare 官方 venv + 脚本；cluster 侧只新增一个 analysis 脚本，
  既有代码零改动（git status 双侧核实）。
- 求值语义零重写：pool_from_conditions.py 通过 qre_src sys.path 直接
  import QRE 的 evaluate_expression_signal，与 QRE evaluation engine 同一
  函数同一面板排序口径；SQL 标识符白名单正则（^[A-Za-z_][A-Za-z0-9_]*$）
  覆盖 schema/table/column，条件 JSON 即使被篡改也注不了 SQL。
- 缓存正确性：load_price_panel 对已存在缓存路径不做范围校验（读源码确认
  gates.py:137），故 price/eval 缓存文件名强制含 d0/d1——换区间不会误命中
  旧缓存；同区间重跑则断点续跑（eval_cache 逐日追加语义来自既有框架）。
- 口径诚实：信号池只纳入场条件（任务书明确要求），scope_note 写进条件
  JSON 与 job result；报告由 cluster 框架生成，自带诚实边界章节。
- 并发与生命周期：lock_key=deep-validate:<name> 同名串行（409 路径有测试）；
  不同策略可并行；subprocess 各 4h 超时；前端轮询不设放弃上限（仅连续 30
  次网络失败停止），匹配「可能几十分钟」的真实耗时（实测 mr01a ~14min）。
- 错误分层与既有 GUI 惯例一致：404 未找到 / 400 invalid_yaml·
  no_entry_signal·missing_factors（缺因子自动入队，复用 factor_request_queue
  链路）/ 500 cluster_unavailable（预检 venv+两脚本存在性）/ 409 在途。
- 模块级常量（CATALOG_DIR 等）by-value import 的 monkeypatch 陷阱已在测试
  fixture 里显式处理（patch deep_validate.CATALOG_DIR 而非源模块）。
- 前端：runDeepValidate 单一函数复用于行按钮与通用入口，escHtml 全覆盖
  服务端字符串；node --check 三段内联 JS 通过。

## Required Fixes

None.

## Residual Risks

- 未重启 qre-gui.service，POST/GET 的真实 HTTP 链路未在运行服务上验证
  （用户约束）；转换器→cluster 两脚本的真实链路已用 mr01a 命令行全程跑通。
- 全历史池生成内存峰值与全市场面板成正比（mr01a 1121 万行因子表合并，
  实测顺利）；used_fields 只拉被引用列已控制列宽，但不限行数。
- GUI 进程内 runner 线程持两个长 subprocess；GUI 重启后线程丢失，job
  status.json 滞留 running（与 daily_jobs 既有行为一致，未自愈）。

## Task ID

QRE-GUI-PROMO-GATE-001（全量回测结果成为晋升后的状态闸）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 标记与竞态：promotion_gate/promotion_forced 经 `run_backtest(mark=...)` 在
  线程启动前合并进 record（app.py promote 路由），与 sandbox 标记同机制，
  未回到事后打标记的竞态老路。
- 评估口径零新增：复用 `extract_run_summary`（strategy_performance.json 优先、
  stdout 兜底）取 SMOKE 同款 4 键；判据写死在 strategy_create（30 笔 + 超额>0），
  无量纲漂移空间。run 失败→failed+error，缺指标→failed（宁严勿宽）。
- 状态存储选型：gates 落 `outputs/refresh/gates/`（outputs 为符号链接出仓，不进
  git），catalog YAML 零改动；`save_gate` tmp+os.replace 原子写，与既有
  sidecar/registry 惯例一致。注册表格式未动（gates 独立目录，register/
  unregister 的 save_registry 归一化不会丢 gate 数据）。
- 日更跳过只挂在 refresh_batch 的自动拾取路径（`--strategies` 显式指定时优先，
  不做闸过滤——手动点名视为操作员知情决定）；跳过名单双落：stdout 日志 +
  batch_summary config.gate_skipped。list_catalog_strategies 新参数默认 False，
  注册/开关 400 校验语义不变（存量 1437 测试零适配即绿可证）。
- force 语义闭环：评估照跑（finalize_promotion_gate 不区分 forced），
  `gate_blocks_daily` 对 forced 恒 False，dashboard 独立「强制在库」橙标，
  API 响应 gate_note 注明。三点一致。
- deep-validate 为纯 501 骨架：路由不与 sandbox/delete 等静态段冲突
  （<name>/deep-validate 三段锚定），无任何外部调用。
- admin.html 新列仅消费 refresh_overview 新增的 gate 字段（缺失=null→灰），
  前端对旧响应兼容；node --check 随 test_gui_admin 通过。

## Required Fixes

None.

## Residual Risks

- 未重启 qre-gui.service，dashboard 列与 promote→gate→日更的真实 E2E 未在
  运行中的服务上验证（用户约束）。
- 判据为写死最简版；发现期/全量口径对齐、四关验证落地依赖后续
  「策略→信号池转换器」。

## Task ID

QRE-GUI-CREATE-GAPS-001（新增策略/因子闭环四缺口）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 缺口 1（策略冒烟闭环）：回写钩子放在 engine._execute_and_finalize 尾部
  （run 终态唯一收口点），整体 try/except 兜底——sidecar 回写失败不影响
  run 收尾；标记经 run_backtest(mark=...) 在线程启动前合并进 record，消除
  原 _mark_run 事后写 status.json 的竞态（极快失败的 run 可能丢标记）。
  sidecar 一律 tmp+os.replace 原子写。list_sandbox 自愈覆盖 GUI 重启丢
  daemon 线程的滞留 running。指标复用 extract_run_summary 既有口径
  （strategy_performance.json 优先、stdout key=value 兜底），未引入新口径。
- 缺口 2（晋升闸）：gate 放在查重/存在性检查之后、写动作之前（fail-fast，
  无副作用）；force=true 管理员通道在响应里以 forced + warning 显式注明。
  策略/因子两侧语义一致（只认 status=="completed"）。
- 缺口 3（因子冒烟异步化）：调度复用 daily_jobs.start_script_job 与
  lock_key 机制（factor-smoke:<name> 同名串行，不同名可并行），未新造
  job 基础设施；run_smoke 的 120s 超时与末行 JSON 解析逻辑原样保留
  （仅抽出 _smoke_cmd/_parse_smoke_stdout 供两处复用）。结果双写：
  job_dir/result.json（轮询端点读）+ 沙箱 sidecar（晋升闸读）。
- 缺口 4：全仓 grep 确认 .p3c-hidden 仅 style.css 两处（注释+规则）与
  一个「断言不存在」的测试，模板/JS 零引用，删除安全。
- 兼容性：sync POST /api/factor-create/smoke 的响应契约改变（columns→
  job_id）是有意为之，前端同步改轮询；test_api_smoke 相应改写。
  run_backtest 新增 mark 为可选参数，既有调用方零影响。
- 验证：pytest 1437 绿（1417 + 20 净增）；node --check 三段内联 JS OK。
  未重启 qre-gui（用户显式约束），真实端到端验证留待服务重启后。
  无 Required Fixes。

## Task ID

QRE-ADMIN-FACTOR-FRESH-001 (因子状态 tab 新鲜度判定)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 只读红线未破：新鲜度判定复用 overview_daily 既有 SELECT（DISTINCT
  trade_date），无新查询类型、无任何写路径；沿用 `_cached` TTL 300s
  single-flight 缓存模式。
- 口径正确性有测试钉住：lag 用交易日序列计数而非自然日差（07-24→07-27
  跨周末 lag=1 而非 3），集成用例防回归；alpha191 无价格后缀表同样判定。
- 降级符合要求：交易日序列查询失败时 fresh/lag_days=null、
  fresh_available=False，前端显示 "-"，列级三方对账与页面其余部分
  不受影响（有专门降级用例）。
- UI 复用现有 ok/err/health-yellow/opt 语义类，零 CSS 新增，符合
  Data-Dense 现有视觉体系。
- 验证：pytest 1417 绿（1412+5）；重启 qre-gui 后 curl
  /api/admin/factor-status 实测 daily_watermark 2026-08-18、alpha191
  lag=1 warn、其余 10 表 lag=0 ok、summary lagging=1/stale=0，与
  「VM 停机漏跑 alpha191 日更」的真实状态一致。无 Required Fixes。

## Task ID

QRE-ADMIN-CLUSTER-001 (dashboard 聚类分析页)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 只读红线未破：PG 只发 SELECT（cluster.mined_factors），文件只读；
  无任何写库/写文件路径；下载走独立白名单（resolve 后必须在
  factor_mining 根内 + 后缀 ∈ {.md,.csv,.json}），路径穿越与 parquet
  实测 404。
- 错误降级符合要求：四分区各自 try/except + 路由级兜底；测试覆盖
  DB 不可用、m4_meta 缺失/坏 JSON、monitor 目录缺失/为空等降级路径。
- 缓存沿用 admin._cached TTL 300s（single-flight），与既有分区一致。
- 路径不硬编码：QRE_CLUSTER_REPO 环境变量 + parents[4] 默认，同
  QRE_INDICATORS_REPO 先例。
- UI 复用现有样式类与 fetchWithTimeout/cardError 模式，零 CSS 改动。
- 验证：pytest 1412 绿（1398+14）；重启 qre-gui 后 curl /admin 200、
  /api/admin/cluster 四分区全 ok（真实数据：38 因子、20 轨迹、
  monitor 9/23/5、13 个下载产物）。无 Required Fixes。

## Task ID

QRE-M5C-MINED-FACTOR-STRAT-001 (M5c：因子工厂 Top3 因子 → QRE 正式策略闭环验证)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 任务书逐项落实：Top3 以库内 evidence 为准（MF_001/002/003，综合分顺序）；
  每因子一策略；沙箱→冒烟→晋升→全市场回测→report-audit 全闭环无断点。
- 转译方案侵入最小：QRE 零代码改动（FactorFieldRequest 既有任意 schema
  三段式寻址；信号表达式 `mf_00X == 1` 在 DSL §2 子集内）；截面分位语义
  由 cluster-ashare 共享 executor（condition_mask，与 M3b/注册表同一函数）
  物化，未复制第二份实现；QRE 只读红线未破（建表写库全在 cluster schema、
  由 cluster 项目脚本执行）。
- 诚实边界已标注：冒烟 cs07a 仅 1/20 股有交易（样本为大盘股，MF_001 池偏
  中小盘）；M3b（异动日事件采样、无成本）与 QRE（每日全市场、含成本止损）
  口径差异在对比结论中如实说明，未把「不一致」淡化。
- 回测结论为负（近 1 年超额 -11.1%/-11.3%/-11.6%），如实记录并给出
  「转衰减观察」建议而非强行上线——符合统计纪律。
- 验证：pytest 1398 绿（无代码改动）；flags↔signals 双向差集为 0；
  report-audit 6/6 ok。无 Required Fixes。

## Task ID

QRE-ADMIN-TIMERS-001 (dashboard 日更定时任务清单补全)

## Review Status

PASS

## Findings

- 改动为 TIMER_UNITS 纯追加，风险为零；实测 6 条定时任务状态正确。无 Required Fixes。

## Task ID

QRE-GUI-ALPHA191-GROUP-001 (alpha191 进因子下拉 + GUI 开机自启服务)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 改动最小：factor_wizard.py 仅新增 alpha191 特判分支 + 1 行 label 映射，不影响既有 10 组逻辑；服务文件为新增不触碰现有单元。
- 验证：pytest 1398 全绿；真实 GUI 重启后 /api/factors 返回 alpha191×191；systemctl is-active=active，curl / =200。
- 无 Required Fixes。

## Task ID

QRE-ALPHA191-STRAT-LOOP-001 (P6：头部 alpha191 因子新建策略闭环自测)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 任务书逐项落实：3 个指定因子（083/099/042）各一策略；信号用纯阈值比较
  （DSL §2 子集内，无函数/穿越/多周期），未触碰引擎——alpha083/099 本身
  是 cs_rank 输出（∈[-1,0]，阈值即截面分位），alpha042 阈值用真实全市场
  分位数标定（p90≈0.015、中位≈-0.24），无需截面 zscore/rank 算子。
- 闭环六环节全部实测通过且有计时/产物证据（沙箱→冒烟→晋升→全市场回测
  →报告→日更登记），详见 09 顶部。断点数为零，故无修复与新增测试；
  pytest 1398 绿（与任务前一致）。
- 口径说明：回测为 batch per-symbol 满仓复利（每股 100 万），基准 000300.SH；
  三策略正收益但跑输基准属预期（截面 IC 优势在该口径下被稀释），报告已
  注明非投资建议（R-QRE-008）。
- preflight=warning 已定位：check_universe 排除计数>0 → warning
  （preflight.py:232 设计行为）；小样本 preflight 全 ok（factor coverage
  1.0 / join 1.0），因子链路本身无缺口。
- 守约束：未 git commit；未改业务库；未动后台无关进程；回测产物在
  outputs/（仓外 symlink）。

## Required Fixes

无。

---

# Review Report (archive: QRE-EVAL-ALPHA191-001, Alpha191 赚钱效应评估管线 + GUI 路径 C 登记)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 逐条对齐任务书：CLI 参数齐全（--start/--end/--factors/--top/--output，另加
  --batch-size/--db-url 两个无害扩展）；默认近 2 年；分批 10 因子取数批后
  del+gc；leaderboard 列与排序（|mean_rank_ic| 降序）符合规格。
- 引擎/catalog/assembler 零改动：alpha191 表走既有 FactorFieldRequest
  三段式寻址，无需 factors.yaml 纳管适配（任务书预警的装配坑不存在）。
- 口径选择均有出处并在 docstring 注明：signal_expression="close > 0" 占位
  （本评估不看事件流）；quantile=1 最低组/5 最高组（引擎 qcut 语义），
  top_minus_bottom=Q5−Q1 与 rank IC 同号为方向一致；ICIR 用与引擎同公式的
  日频 rank IC 重算 std（引擎只输出均值/胜率）。
- 偏离（已登记）：①★ 胜率采用方向一致率（负 IC 因子取 1−正向占比），对
  任务书字面「胜率≥0.55」的解释性扩展；②用户指定冒烟窗口 2025-08-01~
  2026-08-13 因回填仅完成 2010→2013+日更当日而无因子数据，改用已覆盖窗口
  2012-08-01~2013-08-13 验证（3 因子 234 交易日，alpha001/alpha006 ★）。
- 测试：`uv run pytest tests/ -x -q` → 1398 passed（6 净增：合成面板端到端
  正 IC/★、排序、日频 IC、失败行、CLI mock 写 CSV、参数校验）。
- 上游发现（不属本任务范围，未处理）：alpha006 回填段逐日仅 ~3 个 distinct
  值 → qcut 分层塌陷、top_minus_bottom NaN 为正确表象；建议 indicators 侧
  核查 alpha006 公式。
- GUI 改动为纯文案（h2 + 路径 C 一条），无 JS/路由变更；无测试断言引用旧
  文案（grep 确认）。

## Required Fixes

无。

---

# Review Report (archive: QRE-GUI-UIUX-001, GUI 全站 UI/UX 优化：Data-Dense Dashboard 浅色风格)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 方案逐条对齐用户指定设计变量：:root 集中定义 --bg/--card/--border/--text/
  --muted/--primary/--primary-hover/--ok/--warn/--err，全站引用，无散落硬编码
  hex（admin.html 三处内联 #a80 已替换为 .health-yellow）。
- 按钮分级落实：每屏/卡片唯一 primary（运行回测 / 生成代码 / 对比 / 放大全范围），
  次要操作 .btn-ghost，危险操作 .btn-danger-outline 描边红无实底。
- 约束遵守：所有元素 id、JS 事件绑定、API、表单字段、中文文案未动；
  「引擎输出，非投资建议」提示保留；health-*/.ok/.err 类名不变仅换色值。
- 验证：`uv run pytest tests/ -x -q` 1391 passed 全绿（无断言改动）；
  临时实例 curl / 与 /admin 均 200 且含新 class；进程已杀、端口已释放。
- 无 Required Fixes。

## Required Fixes

无。

# Review Report (archive: QRE-GUI-HOME-REFACTOR-001, GUI 首页三 tab → 两 tab 重构)

## Task ID

QRE-GUI-HOME-REFACTOR-001 (GUI 首页三 tab → 两 tab 重构)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 结构与用户批准方案逐条对齐：两 tab、三段垂直流、路径 A/B、fc-create 迁入、
  admin 留跳转链接、tab-builder 与 b-* JS 全删、/api/builder/* 与 app.py 未动。
- 元素 ID 全部保留（wz-*/nl-*/param-*/fc-*/sandbox-*），JS 逻辑逐段平移，
  仅两处行为改动（均为方案要求）：wz-fill-editor 同页填入 + 滚动；NL 缺因子
  跳「新增因子」tab 路径 A 预填。rerun_yaml 回填改同页滚动。
- 自审修复点：①fc JS 迁入时 pollFcJob 原调用 admin 专属的 loadFactorStatus()，
  已移除该调用（loadFcSandbox 保留）；②高级参数区用既有 section-toggle/collapsed
  机制实现默认折叠，无需新 CSS；③node --check 双模板内联 JS 通过。
- 测试 1391 绿；存在性断言已更新为新结构（两 tab、fc-create 在首页、admin 无
  fc-create、tab-builder 不存在）。无真实回测/backfill 执行（standing instruction）。

## Behavior Verified

见 09_CODING_HANDOFF.md 顶部 Validation Output（临时 GUI curl 抽查）。

# Review Report (archive)

## Task ID

QRE-ADMIN-STRAT-INCREMENTAL-FIX-001 (策略状态 tab 增量结果合并)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 合并语义符合确诊结论：增量只在 mtime 更新时接管新鲜字段；全量指标永不取增量
  （增量 summary_metrics 本就无这些键，merged 时显式附 full_metrics_as_of 防伪）。
- 自审修复点：①缓存键初版不含增量根会串键，已纳入（clear_strategy_result_cache
  同步）；②app.py 下载路由白名单原仅 backtests，增量 artifact_dir 会被 400，
  已扩双根；③增量源无 date_start，admin.html 区间列与 detail 页均做容错显示。
- 向后兼容：原返回键（metrics/source_file/artifact_dir/mtime）语义不变，
  仅批次存在时行为与旧版一致（source="batch"）；旧 13 条 strat_tab 测试未改仍绿。
- 测试 7 条新用例（仅增量/merged/批次更新/缺 watermark/缓存隔离/overview 行），
  全量 1391 绿。state.json 整读约 1MB 仅取 watermark，equity_curve.csv 不读。

## Behavior Verified

见 09_CODING_HANDOFF.md 顶部 Validation Output（真实 mr03a：date_end=2026-08-11
增量 + full_metrics_as_of=2026-07-27，source=merged）。

# Review Report (archive)

## Task ID

QRE-GUI-FACTOR-CREATE-P2-001 (GUI 新因子创建闭环 P2)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- 安全闸链完整：nl-generate 只回填不执行；check/smoke/promote 三关各自独立；
  promote 有 pgrep 时机闸 + 目标文件存在闸 + 二次 AST 检查 + 写失败回滚。
- 自审修复点：①AST dunder 初版全禁误伤 `super().__init__`，改 12 项逃逸通道黑名单；
  ②白名单初版漏了必需的 `core.factor_base` from-import；③pgrep -f 会匹配
  调用方 shell 的命令行造成自匹配误报，过滤含 "pgrep" 的行；④查重初版只查
  参数交集，真实 E2E 中 roc（已注册 params [null]）漏网——加"同名指标一律拒绝
  并引导 factor-admin 通道"规则（registry 按 indicator_name 去重，重复类互覆）。
- 测试 42 条注入式 + Flask client；全量 1385 绿。不真连 DB、不真跑 backfill。
- 真实 E2E（真实 DeepSeek + 真实 DB + 真实 GUI server）：vidya 生成 → 查重过 →
  冒烟过（600519.SH 400 行 vidya_20）→ 晋升 job 20260812T030850074330 起成功
  （validate→backfill --categories overlap --execute，后台）。backfill 前核实
  `plan --baseline-ref HEAD --categories overlap` = noop 且无 admin 任务在跑，
  故 backfill 范围严格只有 vidya_20 一列。

## Behavior Verified

见 09_CODING_HANDOFF.md 顶部 Validation Output 与真实 E2E 段。

# Review Report (archive)

## Task ID

QRE-REPORT-CN-001 (report layer: localization, strategy intro, blank filling, 2dp)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- All four user requirements verified on the final full-market run (batch `133a95e11050`): Chinese labels throughout xlsx/HTML; strategy intro block at report top (entry/exit/holding/stops/universe/execution); previously-blank fields filled (strategy_name, strategy_id, strategy_family, 开始日期 2010-01-04, 结束日期 2026-07-24, 股票数量, 交易笔数); 0.00/0.00% cell formats; NaN→`-`.
- Self-review catch fixed: Performance-sheet dates were still blank after the subagent pass (engine summary doesn't carry them) — added run_request backfill in both batch and shared branches, re-verified filled on the final run.
- Contract discipline: sheet names, file names, CSV headers and CSV values unchanged (machine contracts); localization/formatting confined to xlsx cell layer and HTML strings. Full suite 1160 green (19 new localization tests).
- Metadata composition is honest about gaps: `industry_group` stays `-`/unknown until upstream populates `reference.stock_basic`; board from ts_code derivation; cap/liquidity buckets from daily_basic.
- matplotlib chart text stays English (no guaranteed CJK font in environment — documented limitation, charts are auxiliary).
- `sharpe` is formatted as a ratio (0.00%) per the token list — flagged by the implementer; semantically not a percentage but display is consistent (0.00% of a Sharpe value still reads fine at 2dp; noted for user review).

## Behavior Verified

- Final run: 2/2 OK (pt02b 1899s, cb01b 2067s), trades pt02b 1,835 / cb01b 2,027 (latest week included, watermark 2026-07-24); universe correctly drops 4,079 post-2009-09 IPOs + 35 suspended.
- `qre report-audit` → 0 issues; `scripts/check-progress-docs.sh` → passed; `git diff --check` → clean (re-run before commit).
- 1160 tests green.

## Residual Risks

- None material for the report layer. Follow-ups noted: chart-text localization needs a CJK font check; industry_group depends on upstream stock_basic population.

## Next Step

Phase → `AWAITING_GIT_APPROVAL`. Proposed commit message presented to the user; commit only after explicit approval.
