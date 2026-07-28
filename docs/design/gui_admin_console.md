# 统一管理台设计（QRE Admin Console）

日期：2026-07-27 ｜ 状态：P3a DONE（2026-07-28，QRE-ADMIN-CONSOLE-P3A-001，1260 tests green；P3b/P3c 待启动）｜ 作者：KIMI_CODE
关联：gui_backtest_workbench.md（P1/P2）、gui_factor_first_wizard.md（P1.5）。
用户意图：把 ubuntu 内多个项目（日线数据 quant_ts、因子库 indicators_tushare、
回测引擎与产物 QRE）的数据查询、日更管理、新因子/新策略接入集中到同一 GUI，
类比"管理台"。

## 已核实的系统现状

| 管线 | 入口 | 日更 timer | 状态 |
|---|---|---|---|
| 日线数据 quant_ts | `uv run python sync_manager.py --mode daily`（cwd=quant_ts） | quant-ts-daily.timer 16:30 | 已安装运行中 |
| 因子库 indicators_tushare | `uv run python run_daily.py --max-workers 4`；新因子 `run_factor_admin.py` | indicators-tushare-daily.timer 16:40 | 已安装运行中 |
| 回测增量 QRE | `scripts/refresh_batch.py`（watermark 增量） | deploy/qre-refresh.timer | **未安装** |
| DB | tushare_data：public.stock_daily / factors.*(11表346列) / reference.* | — | QRE 只读红线 |

## 设计：GUI 增加"管理台"顶层区（五个 tab）

### Tab 1 总览 Dashboard（只读）

三域卡片，一键刷新：
- 日线：行数、最新交易日（watermark）、股票数、最近 10 个交易日缺口检测。
- 因子库：11 表行数/最新日期、配置指标数、相对日线 watermark 的滞后表清单。
- 回测：批次数、策略产物数、`~/qre-outputs` 磁盘占用、最近批次状态。
- 健康灯：三域 watermark 是否对齐（同日=绿，滞后=黄/红）。

### Tab 2 日更中心

- 三条管线卡片：timer 状态（`systemctl show` 读取 last/next/result，读不需要
  root）、最近运行日志 tail、当前 watermark。
- 手动触发按钮：后台任务调用**各项目自己的入口脚本**（不经 sudo、不经
  systemctl），单任务锁 + 中文确认闸 + 日志轮询（复用 factor-admin 任务基建）。
- qre-refresh：显示"未安装"与安装命令（sudo cp ... 由用户手动执行）；
  同时提供"手动增量刷新"按钮（直接调 refresh_batch.py，无需 sudo）。

### Tab 3 数据查询（只读）

- 日线查询：代码 + 区间 → 分页表格 + CSV 下载。
- 因子查询：代码 + 因子下拉（复用 /api/factors）+ 区间。
- 回测产物浏览：批次 → 策略 → 摘要指标 + 文件下载（复用现有 artifact 体系）。

### Tab 4 接入中心

- 新因子申请（P1.5 面板迁入，含 validate→plan→sample→确认 execute 链）。
- 新策略（因子向导/NL 通道入口）+ 创建后"加入持续更新"：注册进 refresh
  策略集合（写 QRE 自己的 refresh state，不碰上游）。
- 持续更新状态：每个已注册策略的 watermark、最近 delta、下次刷新时间。

### Tab 5 维护（危险区，二次确认）

- 仅清理 QRE 自己的 outputs 产物（旧批次目录，先预览体积，确认后删）。
- **不删/不改 DB 数据**：QRE 对上游 DB 只读是既有红线；DB 写操作一律通过
  各项目官方脚本触发，GUI 不直接执行 SQL 写。

## 边界与红线

1. GUI 对 DB 只读；"删查填改"中的写/删仅覆盖 QRE 自有产物与配置文件
   （factors.yaml 走 P1.5 的备份+回滚机制）。
2. 所有长耗时/重操作：后台任务 + 单任务锁 + 人工确认闸 + 日志可视。
3. 不动 systemd（安装 timer 给命令让用户自己 sudo）。

## 分期建议

- P3a：Tab 1 总览 + Tab 2 日更状态（只读部分）+ Tab 3 查询 —— 纯只读，风险最低。
- P3b：Tab 2 手动触发 + Tab 4 接入中心（含 refresh 注册）。
- P3c：Tab 5 维护 + 健康灯告警细化。
