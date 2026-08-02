# QRE 项目运维指南（PROJECT GUIDE）

面向：人类运维者与 AI agent 的快速接手文档。README 是功能全集，本文是
"系统是什么、边界在哪、怎么跑、坏了怎么办"。
日期：2026-07-28 ｜ 测试基线：`uv run pytest -q` = **1282 passed**

## 1. 这是什么

quant-research-engine（QRE）：A 股日线量化策略的**回测执行与报告引擎**。
输入策略 YAML（低层 StrategySpec）→ 从 DB 组装研究帧 → 三模式回测
（single/batch/shared）→ 全市场报告产物（xlsx/html/csv/json）→ GUI 工作台与管理台。

## 2. 职责边界（红线，先读）

| 边界 | 内容 |
|---|---|
| **R-QRE-005 DB 只读** | QRE 对 `tushare_data` 只发 SELECT。指标计算、日线同步、DB 写/删一律走各项目官方脚本（quant_ts / indicators_tushare）。 |
| **QRE 不算指标** | 技术因子由 indicators_tushare 计算入库（`factors.*`）；QRE 只做存在性检查与缺因子申请（handoff 队列）。 |
| **R-QRE-008 结果非研究结论** | 回测/冒烟输出是筛选证据，不是投资建议或研究结论；界面与报告必须保留此标注。 |
| **R-QRE-009 先小样本后全量** | 任何全市场运行前先小样本验证（GUI 默认勾选"小样本预检"）。 |

## 3. 在三项目数据流中的位置

```
quant_ts (16:30 timer)          indicators_tushare (16:40 timer)        QRE
日线 K 线同步 ──→ public.stock_daily ──→ 因子计算入库 factors.*(10 纳管表) ──→ 策略回测/报告
                                                                      └─→ refresh 日更(18:30, 未安装)
部署机：单机 ubuntu，23G 内存，PostgreSQL+TimescaleDB（tushare_data，858 继承 chunk）。
```

管理台 `/admin` 是**纯只读状态查询台**（dashboard）：总览/日更中心/因子状态/策略状态；
新建因子、新策略、注册操作的 UI 已暂缓隐藏（`TODO-P3c-restore`，代码保留）；
唯一写动作是"触发已完善的项目脚本"（日更中心立即运行、回测执行）。

## 4. 核心入口

| 入口 | 命令/路径 | 用途 |
|---|---|---|
| CLI | `uv run qre --help` | backtest-single/batch/shared、compile、gui 等 |
| GUI 工作台 | `uv run qre gui` → `http://127.0.0.1:8080/` | 因子向导(默认首屏)/Builder/YAML 编辑器(含 NL 通道)；异步执行限 2 并发；run 对比 |
| 管理台 | `/admin` | 只读状态 + 日更手动触发 |
| 全量批跑 | `scripts/batch_backtest_runner.py` | 111 catalog 策略批量（过夜脚本 `scripts/run_full_history_overnight.sh`） |
| 增量日更 | `scripts/refresh_batch.py` | watermark 检测 + 滚动 2 年窗重跑 + delta 报告；注册表 `outputs/refresh/registry.json` 存在且非空时按表过滤，缺省全量 |
| 增量(检查点) | `scripts/incremental_update.py` | checkpoint 续跑（deploy/qre-incremental.*） |

## 5. 测试纪律

- 全量：`uv run pytest -q`，当前基线 **1282 passed**，提交前必须全绿。
- 不连真实 DB（mock store/subprocess）；真实冒烟单独跑、只读优先。
- GUI 模板内联 JS 有 node --check 回归测试（见"故障案例 3"）——改模板 JS 后必须保证通过。

## 6. 稳定运行冻结清单（QRE-STABILIZE-DOCS-001）

以下组件已进入"稳定运行"状态：**只修 bug，不做架构性改动**；改动须全量测试 + 真实冒烟双验证。

| 组件 | 文件 | 角色 |
|---|---|---|
| 三引擎 | `portfolio/single_symbol.py`、`single_symbol_vectorized.py`、`batch.py`、`shared.py` | bar 仿真/向量化、批量、共享资金回测 |
| 引擎支撑 | `portfolio/analytics.py`、`risk.py`、`risk_controls.py`、`weights.py`、`universe.py`、`benchmark.py` | 汇总指标/风控/权重/universe 过滤/基准 |
| 报告 | `portfolio/full_market_report.py`、`io.py`、`report_manifest.py` | 全市场报告产物（汉化、xlsx/html） |
| 数据层 | `data/`（postgres/settings/assembler/catalog/interfaces/metadata_compose/tushare_security） | 只读 store、研究帧组装 |
| 策略层 | `strategies/spec.py`、`compiler.py`、`factor_request_queue.py`、`missing_factor.py`、`smoke_runner.py` | StrategySpec、高层 entry 编译、缺因子队列 |
| 编排 | `orchestration/batch_runner.py`、`research_run.py`、`refresh.py`、`incremental*.py` | 批跑/单次/日更刷新/增量 |
| 脚本 | `scripts/batch_backtest_runner.py`、`refresh_batch.py`、`incremental_update.py`、`run_full_history_overnight.sh` | 生产入口 |
| GUI | `gui/`（app/engine/factor_wizard/factor_admin/nl_compiler/admin/daily_jobs/refresh_registry + templates/static） | 工作台 + 管理台 |
| 部署 | `deploy/`（原版 + `deploy/hardened/` 自愈版，均未安装） | systemd unit |

依赖锁定：`uv.lock` 与 `pyproject.toml` 一致（2026-07-28 `uv lock --check` 通过）。

### qre-refresh 安装（hardened 版，未安装）

```bash
sudo cp deploy/hardened/qre-refresh.service deploy/hardened/qre-refresh.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qre-refresh.timer
```

hardened 差异：`Restart=on-failure`（StartLimit 600s/3 次）、`TimeoutStartSec=7200`、
`MemoryMax=18G`、Nice/IO 降级、timer 随机延迟 300s。建议 18:30（错开上游 16:30/16:40）。

## 7. 常见故障案例（已发生过的，按此排查）

1. **Timescale 锁耗尽**：全历史批跑（jobs=4 × 858 chunk 计划锁）撑爆
   `max_locks_per_transaction`（默认 64×100）。症状：大量策略报 lock 错误。
   处置：`ALTER SYSTEM SET max_locks_per_transaction = 512` + 重启 postgres（已实施）。
   相关：Timescale catalog 曾整体丢失、orphan chunk 挂在继承树下（stock_daily 858 个），
   重注册 hypertable 时 Guard 住激活路径（quant_ts 侧已修）。
2. **858 继承 chunk 的查询成本**：`COUNT(DISTINCT ts_code)` / 全表 count 是秒级~10 秒级。
   管理台一律用 `pg_class.reltuples` 估算 + 300s 缓存 + single-flight；
   精确 distinct count 也走缓存，别在热路径加未缓存的全表聚合。
3. **GUI 内联 JS 语法错误整页失能**：模板 `<script>` 一处语法错误会导致整页
   事件绑定静默失效（"卡片全在加载中、按钮不可点"的典型原因之一）。
   防线：`tests/test_gui_admin.py::test_admin_template_script_parses_with_node`
   用 `node --check` 校验内联 JS；改模板后必须全量 pytest。
4. **du 对符号链接只量链接本身**：`outputs` 是指向 `~/qre-outputs` 的 symlink，
   `du -sb` 前必须 `resolve()`（曾误报 21 字节）。
5. **孤儿因子表误报**：`factors.stock_daily_vortex_close`（0 行历史遗留）不是
   日更管线成员；健康灯/对账只评估"纳管表"（由 indicators config/factors.yaml
   的 category+column 推导的 10 张表），vortex 数据实际在 trend_close 表内。
6. **全市场内存风险**：GUI 回测限 2 并发 + 默认小样本预检；批跑用
   `--symbol-chunk-size 400`（OOM 修复方案，chunked 与整跑结果字节一致）。

## 8. 相关文档

- 功能全集：`README.md`
- 新策略写作规范：`docs/STRATEGY_AUTHORING.md`
- 策略录入标准（高层 entry）：`docs/strategy_entry/README.md` 及同目录其余文件
- 工作流记录：`docs/agent/05_PROGRESS.md`（Latest Verified State）、`docs/agent/09_CODING_HANDOFF.md`
