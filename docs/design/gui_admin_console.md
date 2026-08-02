# 统一管理台设计（QRE Admin Console）

日期：2026-07-27 ｜ 状态：P3a/P3b/REFocus/DASH/HAZARD/MANAGE DONE（2026-07-28，QRE-ADMIN-MANAGE-001，Tab 4/Tab 5 DONE，1299 tests green）｜ 作者：KIMI_CODE
关联：gui_backtest_workbench.md（P1/P2）、gui_factor_first_wizard.md（P1.5）。

## 定位（状态台哲学，2026-07-28 用户拍板）

管理台**只查询状态，不查询/修改/删除具体数据**；**查询优先，新建/入库暂缓**
（新建因子/新策略/注册操作 UI 隐藏、代码保留，标记 TODO-P3c-restore）；
写入只允许"触发已完善的项目脚本"（日更中心的立即运行按钮保留）。

- 因子管理 = 显示"数据库里存在哪些具体因子 × 是否在技术指标日更列表中"；
  新增因子 = 加入 indicators_tushare 的脚本配置（P1.5 已实现）。
- 策略管理 = catalog 清单 × 是否在 refresh 日更注册表；新策略走因子向导。
- 所有增删改通过已存在的官方脚本传递；GUI 不做数据行级查询（原 Tab 3 数据查询已撤）。

## 用户意图（原始）

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
- refresh 执行结构（QRE-REFRESH-INCREMENTAL-001）：默认 mode=incremental——
  watermark 小差（≤45 自然日≈30 交易日）只跑新增交易日并**合并**进既有结果
  （复用 7 月增量引擎 checkpoint/持仓延续/台账去重/聚合重算，分段≡全跑）；
  大差/首次自动 bootstrap 全窗；`--full-window` 保留全窗重跑兜底。
  设计细节见 docs/design/refresh_incremental.md。

### Tab 3 因子状态（REFocus 后，替代原"数据查询"）

- 三方对账（仅状态，无数据行）：库中存在的因子列（information_schema，
  剔除 ts_code/trade_date）× 日更配置展开列（indicators_tushare 自身
  factor 类 preview_columns 推导，subprocess 调其 uv 环境纯展开不触 DB）
  × 每表 watermark。
- 状态标注：在库且在日更（绿）/ 在库不在日更（黄，停滞风险）/
  配置有但库缺（红，链向新因子申请）。配置展开失败降级为配置级（指标名+参数）。
- 未纳管孤儿表保持信息段（不参与对账）。

### Tab 4 策略状态（STRAT-TAB 版）

- 策略名链接详情页（/admin/strategy/<id>：catalog 简介 + 最近结果指标卡 + 产物下载）。
- 状态表四列：回测起止、回测股票数量、策略超额收益、最大回撤（取该策略 mtime 最新的
  strategy_performance.json，无结果显示"—"）。
- 持续更新开关：绿=开启/灰=停止（registry v2 {"include","stopped"}，只改文件下次 refresh 生效；
  include 空=全量模式默认全开）；注册/移出、删除策略（连动删除本地回测产物，白名单校验）。

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
