# Agent State

This file is the source of truth for single-agent workflow recovery.

## Current Phase

ACTIVE（2026-10-12：方案A数据重建全链收官 + 个股FRM/按需生成已上线；待小样本回测对账验收）

## Current Task

DATA-REBUILT-2026-10-11 **数据侧已全部完成**（2026-10-12 10:45 链条收官）：
- 分钟线入库 `public.stock_minute_1m` 4313 天全量（TimescaleDB 压缩已开）；WSL 侧 /home/van/mindata CSV（324G）待用户确认后删除
- stock_daily 已换名为原始价（旧表 `stock_daily_qfq_legacy` 留作回滚，验收后删）
- 因子 10 表全历史重算 5853 只零失败；alpha191 全量 191 因子 1608 万行
- 抽查通过：000001.SZ sma_20 与手工 close×adj_factor 一致；920195.BJ MACD 已修复全期无空值
- alpha149/181/182 "benchmark missing" 告警系误报（000300.SH 数据完整），实测覆盖率正常，无需补救
- **坑（已修复）**：表重建 RENAME 后 GRANT 不随迁 → qre_worker_ro 失 stock_daily SELECT 致 job 56 失败；已重新授权
- **剩余**：小样本回测对账验收（用户侧跑一次即可）→ quant_ts / indicators_tushare 两仓库 commit（代码已改完待提交）

SAAS-SYMBOL-2026-10-12（已部署 ECS，commit 93cb0eb + de3cc23）：
- 个股级 FRM 模块（risk 节随详情产物，VaR/ES/EWMA波动/状态/夏普/压力测试）
- 个股详情按需生成链路（kind=symbol_detail 轻量任务，幂等，产物落父 job 目录）
- 板块/标签榜单列头排序；FRM 修复 run 级回传（risk_report.json 登记 artifacts）
- NaN→null 序列化修复（前端 JSON.parse 卡死根因）

## Current Owner

KIMI_CODE (sole development agent; user is final approver)

## Current Task

详见上方 Current Phase（2026-10-12 已更新）。以下为历史任务存档：

**（存档）DATA-REBUILT-2026-10-11 实施步骤**：
1. **分钟线入库**（后台）：`quant_ts/import_minute_csv.py` 6 worker 把 /home/van/mindata（2009→2026，4313 天，324GB CSV，原始价）入库 `public.stock_minute_1m`（hypertable 7天chunk，量/额已换算手/千元），审计表 `stock_minute_1m_audit` 幂等断点续跑。预计 3-4 小时。
2. **方案A 日线重建**（后台）：`quant_ts/rebuild_daily_raw.py` 按 trade_date 拉 pro.daily 原始价+adj_factor 建影子表 `public.stock_daily_raw`（4372 天，含 2009 扩展段），预计约 2 小时。**验收后人工换名**（SQL 在脚本尾注释）。
3. **代码已改未生效（flag 门控，默认旧行为）**：
   - quant_ts `handlers/daily_handler.py`：fetch_data 弃 qfq 改 pro.daily 原始价（fetch_snapshot 本就是原始价——混合锚点根因）
   - indicators `core/db_manager.py`：`_adjust_prices`（IND_PRICE_BASIS=raw 激活，价格列×adj_factor）
   - indicators `alpha191/panel_loader.py`：同样 flag 门控复权
   - QRE `data/settings.py` + `data/postgres.py`：`price_basis`/QRE_PRICE_BASIS=raw 时 load_daily_bars 复权并携带 raw_open/raw_pre_close
   - QRE `portfolio/{shared,single_symbol,single_symbol_vectorized}.py`：涨跌停判定优先用 raw_open/raw_pre_close（交易所规则必须原始价）
   - QRE `gui/lab_result.py`：区间收益 ×adj_factor；K线展示锚定最新价
   - 验证：QRE 测试 2330 passed 零回归
4. **换名后待办**：systemd 各服务加 IND_PRICE_BASIS=raw / QRE_PRICE_BASIS=raw 环境变量并重启 → 因子 11 表全量重算 → 小样本回测对账 → ECS 同步。

上一任务：QRE-SAAS-SMOKE-INCIDENT (DONE 实现完成、**未 commit 待用户批准** — CR-2026-10-11 job 54 smoke
全市场超时事故四 bug：①apply_precheck 空 codes 按 run_id seed 随机抽样不再放行全市场 +
worker smoke 跳过全量后处理；②max_holding_days 0/null=不限（校验/编译/三引擎执行层全链）
顺带 risk.*_pct=0=不启用；③心跳连续失败 3 次判 lease 丢失终止子进程释放槽位；
④build_symbol_detail_files O(n²) 改一次解析逐股复用；测试 +9，`-k saas` 238 passed 零回归；
commit 批准后 push+ECS 部署+重启本机 qre-saas-worker，无 DB 迁移)

上一任务：QRE-NL-FACTOR-PIPELINE (DONE 实现完成、**未 commit 待用户批准** — CR-2026-10-09 NL 编译
因子名四层防线：真实目录快照注入 prompt（configs/factor_catalog_llm.txt + gen 脚本）/
别名字典（factor_aliases.json + auto_fix_column 第 0 层）/compile_nl 修复回路
（回喂最多 2 次，fix_attempts 透出）/兜底报错补申请新因子指引；测试 +12 全绿含
macd_signal→macds 精确案例；顺手修信号测试日期 flake；`-k saas` 237 passed 零回归；
commit 批准后再 push+ECS 部署（快照入仓库即生效，无 DB 迁移）；2026-10-10 已部署 ff0e39e + 生产实测 hotfix（平铺目录 + 快照 lookup 回退）另 commit)

上一任务：QRE-SHARED-COST-BREAKDOWN (DONE 已部署 — 交易磨损卡佣金/印花税 0 值 bug：
shared.py 四路径改 calculate_cost_breakdown + lot 级组件分摊 + _trade_row 补 6 拆分列
（键名同 vectorized）+ full_market_report shared_cash 补读聚合；存量不回填；
真库实测 fees_summary 佣金 70/印花税 32.88/过户费 1.31（修复前为 0）；
`-k saas` 237 passed + portfolio 族 482 passed 零回归；06+CR 已登记；
站立批准有效 → commit+push+ECS 部署+重启本机 qre-saas-worker)

上一任务：QRE-SAAS-RESULT-ACTIONS (DONE 已部署 — CR-2026-10-05 结果页显式入库+信号入口：
核心语义=没超额收益的策略不进策略库；jobs FK 约束下用 strategies.in_library 旗标
（提交建行不入库，显式保存/建 watch 才入库；存量一次性 backfill true）；
结果页末尾「下一步」卡（保存三态 + 信号面板三 scope）；游客整卡隐藏；
/api/results/<id>/summary 补 strategy_id（轮询走它）；测试 +2 + 断言 4，
`-k saas` 237 passed 零回归，staging 双端实测通过；站立批准有效 → commit+push+
ECS 部署+手工 apply in_library 列)

上一任务：QRE-SAAS-TIER-BETA-RELAX (DONE 已部署 — 内测期两层权限调整（用户 2026-10-05 拍板）：
游客 10 只随机补齐（云端 codes_auto_fill 标记 + worker fill_guest_codes）/近 10 年/
随机 N≤10，每日 1 次与次日清空不变；member/paid 三值全 0 不限；tier_policies 种子
不随代码更新的运维坑登记 19 号文档；测试重写+worker +4，`-k saas` 235 passed 零回归；
staging 8092（bypass=0 游客态）双端实测通过；已 push（4b1c083）+ ECS 部署 +
生产库 tier_policies 三行 UPDATE 验证 + 生产游客探针 job 43（3 自选+补齐，10 年区间）
completed、8 只不同股票成交证明补齐执行；本机 qre-saas-worker 已重启加载新 runner)

## 挂起 backlog（用户确认知悉，非进行中）

1. **深度性能优化**（用户指示"放最后"）：回测详情缓存已做过一轮；剩余为更深的
   引擎/前端性能项 + 引擎压力测试（每小时可处理多少全期全量回测/并发上限实测）。
2. **信号监控「板块」范围二级选择 UI**：当前监控范围支持 最近回测快照/全A/自定义，
   板块名单选择器未做（spec 留待细化项）。
3. **重播已验证边界**（非缺陷，首次真实场景出现时再处理）：全市场任务「同日几十只
   入场」聚合展开、orders 明细事件源路径（现走 round trips 兜底）、多因子副图页。
4. **付费体系**：信号监控 scan_enabled / max_watches 已入 tier_policies 占位；
   积分制 vs 会员制未定（用户明确暂缓）。
5. **分时策略回测**：依赖分时数据源选型（用户曾寻找稳定便宜的 A 股分时数据源，未决）。
6. **小程序/APP 端**：移动 web 适配已完成（2026-10-04）；原生端为远景项。

上一任务：QRE-SAAS-REPLAY-LAYOUT-FIX (DONE — 重播速度档换行 bug 系统性调试：根因=base.html:56
全局 select{width:100%} 使 .rp-sel 恒独占整行（五档宽度探针 width=bar 全宽实证，
与视口无关）；修复=.rp-sel 显式宽度+36px 等高 + 控制条两语义分组
（.rp-group-main 播放/单步/速度 nowrap 恒同排 / .rp-group-aux 允许折行）+
去除重复「起始日」label；同一探针五档宽度中心 y 差 0px 前后对照证明修好；
`-k saas` 235 passed；已部署 ECS，生产 asset_v 缓存破除确保用户端自动拿到新版）

上一任务：QRE-SAAS-WAIT-MASK + QRE-SAAS-REPLAY-LAYOUT (DONE — ①长等待遮罩组件 wait-mask.js
（禁 ESC/背板/全锁、z-95、护栏弹层级冲突已处理）+ new.html 生成策略与运行回测两段式
接入（「继续等待/后台运行」分流，踩坑 keepMask 短路已修）；②重播布局：倍速与播放
同排、进度条移至图表正下方（.rp-slider-row，两端生效）；staging 锁定探针/两段式
临时 worker 真执行双路径/布局断言/移动 375 全过，`-k saas` 235 passed 零回归；
awaiting git approval（站立批准有效）→ 部署 ECS)

上一任务：QRE-SAAS-REPLAY-POLISH (DONE — 重播组件两项优化（用户批准）：①接管模式——replay.js
opts.chartEl + destroy(keepDom)，symbol/job 删独立重播卡接管原 K线/收益曲线容器，
退出内存重建静态+缩放/基准条/区间卡恢复（踩坑 classList.add 链式抛错已修）；
②控制条打磨——SVG 图标+文字标签、cursor/hover/:focus-visible 紫环、transition 0.2s、
prefers-reduced-motion 降级、36px 等高 8px 网格；staging 单容器 DOM 断言/退出还原/
末帧 0.59% 强一致/UI 探针/reduced-motion 仿真/移动 375 全过，`-k saas` 235 passed；
awaiting git approval（站立批准有效）→ 部署 ECS)

上一任务：QRE-SAAS-REPLAY-S2 (DONE — CR-2026-10-04 切片2 K线级重播：replay.js 向后兼容扩展
（series type/extra 透传、ev.price 定位、initialCursor/height、yAxes pct:false 修全轴%
bug）；symbol.html #box-kreplay——K线/量/因子副图逐日推进、侧边信息卡（OHLC/因子/
持仓/浮动盈亏·毛随帧跳动/已实现累计）、默认近 2 年起播；staging 全链路实测——
浮动盈亏 −18.00==手算、末帧已实现 587.45==静态 total_pnl、切片1 回归 0.59% 不变、
移动 375 零横滚零报错；模板断言 +5，`-k saas` 235 passed 零回归；
awaiting git approval（站立批准有效）→ 部署 ECS)

上一任务：QRE-SAAS-REPLAY-S1 (DONE — CR-2026-10-04 切片1 策略级回测重播+可复用重播引擎组件：
static/replay.js（core 纯逻辑+attach UI：播放/单步/速度档/日历起始日/拖拽/空仓快进，
[0,cursor] 截断渲染+rAF 节流）+ lab-theme.css .rp-* 样式族；job.html #box-replay——
曲线逐日生长/事件流弹入聚合/8 卡指标随帧重算/「信」T 与「入出」T+1 相隔呈现；
staging 全操作链路实测 + **末帧强一致性断言（重播累计收益==静态总收益）** +
core 探针/日历联动/事件流 16 行/桌面+375 零横滚零报错；模板断言 +5，
`-k saas` 235 passed 零回归；awaiting git approval（站立批准有效）→ 部署 ECS；
切片2（symbol K线级）留待后续，组件已全参数化)

上一任务：QRE-SAAS-SIGNAL-CONSOLIDATE (DONE — 模块二 UX 收编（用户拍板：信号集成进「我的策略库」，
不做独立栏目）：顶栏「信号」项移除、未读红点改挂「个人信息」导航；策略列表 API 聚合
watch/latest_signals/signal_unread（两查无 N+1，最近信号日口径=max(trade_date) 当日
entry/exit 计数）；策略库行加监控徽标/最近信号摘要/未读红点 + 卡标题「查看全部信号 →」；
详情页加「该策略信号记录」分页区（进入即 mark-read）；/saas/signals 保留不进主导航；
测试 +2，`-k saas` 235 passed 零回归；staging 桌面+375 红点闭环与三态实测零报错；
awaiting git approval（站立批准有效）→ 部署 ECS)

上一任务：QRE-SAAS-SIGNAL-CENTER (DONE — CR-2026-10-04 模块二 策略信号监控+站内信号中心：
新表 strategy_watches/signal_events + users.signals_last_read_at + tier_policies
scan_enabled/max_watches（懒自愈+cloud_schema 同步）；用户侧 watch CRUD（默认
last_run_universe 快照/上限 403/scan 关闭 403/他人 404）+ signals 筛选分页 +
unread-count/mark-read；worker 侧 watches 下发 + signals 幂等回传；扫描脚本
deploy/saas/signal_scan.py（复用 evaluate_expression_signal，按股分组求值防 shift
跨股，挂 qre-refresh ExecStartPost=-）；strategy.html 监控卡做实 + 新页 /saas/signals
信号中心 + 顶栏「信号」红点（信号中心页跳过查询防竞态）；测试 +15，staging 全链路
实测（watch→回传→红点→mark-read 灭点）；awaiting git approval（站立批准有效）→
ECS 新表手工 apply + 生产扫描实跑)

上一任务：QRE-SAAS-STRATEGY-ASSETS (DONE — CR-2026-10-04 模块一 策略库→策略资产：strategies 加
entry_mode/wizard_state（懒自愈+存量推断+06 决策）；保存与 job 提交链路落模式与向导快照；
新页 /saas/strategies/<id> 三模式源文件还原（nl 重编译/wizard 快照+跳向导编辑/yaml 编辑）+
操作区+历史回测表+模块二占位注释；策略库行入口标签+详情链接；new.html 回填按
entry_mode/mode 还原入口并修 staging bypass 回填失效；测试 +10，`-k saas` 218 passed 零回归，
Playwright 桌面+移动截图零报错、向导回填逐键实测正确；awaiting git approval（站立批准有效）
→ 部署 ECS 需手工 apply strategies 新列)

上一任务：QRE-SAAS-MOBILE-ADAPT (DONE — 移动端 web UI 适配：Playwright 375×812 逐页审计
（records/job/symbol 三页页级横滚，根因=表格溢出/长 chip nowrap/磨损块固定宽）→
修复全集中在 base.html 新增 @media(max-width:768px) 规则块（表格块级横滚、chip 折行、
触达 44px、输入 16px/44px 防 iOS 放大、磨损块 2 列+grid 三段）；踩坑 lab-theme.css
后加载压掉同优先级覆盖 → .chart-box 前缀，登记 12 号新 §10；全页零横滚零 JS 报错 +
移动端交互冒烟（三入口/日历/提交流水线）通过 + 桌面 1280px 回归无破坏；
`-k saas` 208 passed 零回归；awaiting git approval（站立批准有效）→ 部署 ECS 后
公网 375px 复测)

上一任务：QRE-SAAS-R3-SLICE2 (DONE 已部署 — R3 切片2 资源调配封装（方案 C=A+B 混合，用户批准）：新表
worker_configs（worker_id 主键/期望四值/version+1/updated_by，懒自愈+cloud_schema 同步）；
status 响应回带 desired_config，worker _check_desired_config 比对记日志（同 version
一次/恢复一致记「已生效」）；console Worker 卡「当前 vs 期望」高亮 + 可复制
worker-tune.sh 命令 + 设为期望表单（POST /api/saas/console/worker-config admin 门禁）；
deploy/saas/worker-tune.sh sed 更新 /etc env+备份+重启 qre-saas-worker（本机 tmp 实测）；
测试 +11（saas 7 + worker 4），`-k saas` 207 passed 零回归，闭环冒烟通过；
awaiting git approval（站立批准有效）；部署：ECS 首次手工建 worker_configs 表)

上一任务：QRE-WORKER-CONSOLIDATION (DONE — worker 单例收敛：R2 调试期用户级 qre-worker(home-pc)
与系统级 qre-saas-worker(wsl-home-pc) 双跑，收敛为唯一系统级 qre-saas-worker；
/etc env 并入槽位/闸门/代理置空/QRE_MARKET_DB_URL 新密码；MemoryMax 16G→26G；
用户级 unit/env 退役 *.retired；ECS workers 表 home-pc 僵尸行已清；
收敛后 smoke job#35 completed(attempts=1) 端到端验证通过；docs 04/05/16 已同步；
awaiting git approval（本会话用户已站立批准 commit+push）)

上一任务：QRE-SAAS-R3-SLICE1 (DONE 已部署 — worker 实时状态上报 + 管理台「Worker 资源」卡)

上一任务：QRE-CALENDAR-YEAR-PICKER (DONE — 共享日历组件年→月→日钻取：点 .cal-title 标题上钻年份九宫格（12 年/页 ±12 年翻页）→月份视图→日视图，Esc 逐级返回/关闭；新增可选 opts.minDate 下界，年/月超界格子置灰禁点，maxDate 禁未来与「数据截至」页脚不变，调用方零改动兼容；.cal-cell.sel 紫底与选中日一致；仅改共享 lab-ui.js + lab-theme.css，lab/SaaS 模板零改动两端同步升级；全量 2212 passed + 4 skipped 零回归（复跑确认）；staging 8091 Playwright 三视图/禁未来/选值/Esc 实测零 JS 报错；12 号文档 §3.7+变更记录已登记；未 commit 未部署；awaiting git approval)

上一任务：QRE-SAAS-EXPOSURE-METRICS (DONE — 区间信息卡加持仓暴露度/持仓期年化两张随滑块联动卡：round trips entry/exit 展开逐日持仓掩码（同日重叠去重），暴露度=持仓日数/区间日数，持仓期年化=(1+区间收益)^(252/持仓天数)−1，无持仓显示「—」口径入 title；#range-strip 改 auto-fit minmax(130px,1fr)；job.html/symbol.html 同步，lab 侧零改动；全量 2212 passed + 4 skipped 零回归；staging 8097 宽+窄屏 Playwright 探针实测联动与数值正确、零 JS 报错；12 号文档已登记；未 commit 未部署；awaiting git approval)

上一任务：QRE-SAAS-DETAIL-CARD-UI (DONE — 公网详情页卡片 UI 四项验收修改：区间五卡 repeat(5,1fr) 整行均分、job.html 交易磨损+FRM 移到收益曲线后、symbol.html 顶部 7 卡 auto-fit 舒展布局、总结性卡片统一 --tint 淡紫底；仅改 saas/templates 的 job.html/base.html，lab 侧零改动；全量 2212 passed + 4 skipped 零回归；staging 8097 宽+窄屏 Playwright 截图验证零 JS 报错；12 号文档变更记录已登记；未 commit 未部署；awaiting git approval)

上一任务：QRE-SAAS-SYMBOL-UX-SHARED-FIX (DONE — shared 模式 per-symbol 产物缺陷修复：runner._enrich_shared_symbol_detail 从任务级产物补齐 orders/failed_orders/wear/单票净值；job 21 存量产物已重算覆盖 ECS；公网 demo01 job 23 全链路验证全模块渲染；测试 +5 全量 2212 passed + 4 skipped 零回归；已 scp 临时部署；awaiting git approval)

上一任务：QRE-AUTH-MEMBERSHIP (DONE — Authing OIDC 登录接入 A2-A6：schema 加 authing_id/avatar_url/member_*、新 authing.py 换票+JWKS 验签+自动建档+绑定旧账号、login.html 托管页主入口+邮箱密码折叠降级、测试 +22 全量 2207 passed + 4 skipped 零回归；env 已写 ECS/本地 0600、ECS venv 依赖已装；代码未部署；awaiting git approval + Authing 控制台回调白名单确认)

2026-09-27：细节见 04_TASK_HANDOFF.md 与 05_PROGRESS.md 同名条目。要点：
授权码+托管登录页流程（替代 §6 原 Guard 方案，已注记）；/saas/login/authing 302 →
/saas/login/callback 验签建档发本地 session；POST /api/saas/auth/bind 迁移旧账号。
**遗留用户操作**：Authing 控制台「登录回调 URL」白名单需含
https://www.aguhuice.com/saas/login/callback（实测报 redirect_uri_mismatch）；
部署待办：commit 批准后 ECS git pull + psql apply cloud_schema.sql + restart qre-saas。

上一任务：QRE-SAAS-FEEDBACK-FACTOR-REQ (DONE — 内测意见反馈页 + 申请新因子页 + 缺因子拦截跳转 + 全站统一侧边栏；全量 2185 passed + 4 skipped 零回归；仅本地+staging 验证未部署 ECS；awaiting git approval)

2026-09-27：细节见 04_TASK_HANDOFF.md 与 05_PROGRESS.md 同名条目。要点：
base.html 新增 .sidenav 侧边栏（意见反馈 / 申请新因子两入口，全页面自动获得）；
新表 feedback（仅登录用户提交，日 20 条上限，决策见 06）+ console「反馈」tab
（只读）；新页 /saas/factor-request（factor_requests 幂等补 formula/purpose 列）；
new.html 缺因子弹层改「当前数据库中不含此因子」+ 跳转申请页按钮（预填），
向导/YAML 提交前 unknownYamlFactors 兜底校验。测试 +21
（tests/test_saas_feedback.py）。未 commit、未部署 ECS（schema 需先 apply）。

上一任务：QRE-SAAS-LARGE-UNIVERSE-GUARD (DONE — 公网大范围板块/全市场提交耗时护栏，阈值口径同 lab 版 3000；全量测试零回归；仅本地+staging 验证未部署 ECS；awaiting git approval)

2026-09-27：细节见 04_TASK_HANDOFF.md 与 05_PROGRESS.md 同名条目。要点：
全部 A 股计数补为元数据字段 all_a_count（universe.py 新 all_a_count() =
reference.stock_basic 行数；sync_saas_metadata.py 生成逻辑更新，metadata.json
已重生成 5531 只）；/api/saas/universes 双路径透出（缺失降级 None）；
new.html 流水线第③步提交前按 LARGE_UNIVERSE_THRESHOLD=3000 判定，
超阈弹 #big-univ-modal（规范 .modal-mask 组件）说明预计股票数与耗时，
确认才提交。lab 侧零改动。测试 +3，全量零回归。未 commit。

上一任务：QRE-SAAS-SYMBOL-UX (DONE — 股票代码规范化+显示脱敏、超额收益 vs 持有不动修复、worker per-symbol 产物回传打通公网个股详情、板块弹层列补齐+点击跳转；已 rsync 临时部署 ECS 并公网验证；全量测试零回归；awaiting git approval)

2026-09-27：四项改动（细节见 04_TASK_HANDOFF.md 与 05_PROGRESS.md 同名条目）。
要点：新 gui/saas/symbol_norm.py；worker runner 新增 _fill_excess_return +
build_symbol_detail_files（_symbol_details/<ts_code>.json.gz 随 result/files 上传，
15MB 截断）；ECS api_result_symbol_detail 优先读上传 gzip；saas 模板
base/job/symbol/symbols/new 五处渲染层改动。顺手修 ECS workers 表缺授权导致的
claim 500 生产事故（已 GRANT）。测试 +31（tests/test_saas_symbol_ux.py），
test_gui_saas.py 一处断言更新。未 commit。

上一任务：QRE-SAAS-ADMIN-TUNNEL + QRE-SAAS-UI-ALIGN-FIX (DONE — 管理台撤公网改 SSH 隧道 + PG 每日备份 ECS→本地 + 公网顶栏/入口卡选中态/回测区间日历对齐 lab 版并已部署；全量 2130 零回归；awaiting git approval)

2026-09-27（方案 A，用户拍板）：nginx 对 /saas/console 与 /api/saas/console/* return 404
（仓库 deploy/landing/nginx-aguhuice.conf 同步线上）；base.html 删顶栏管理台入口注入
（断言反转，注意注释含 "/admin" 子串会撞禁链）；新增 deploy/saas/admin-tunnel.sh
（ssh -N -L 9090:127.0.0.1:8090）与 deploy/saas/pull-ecs-backup.sh；ECS cron 03:17
pg_dump 留 7 天 + 本地 cron 04:23 scp 拉取留 7 份，两端验证落地。决策入 06 日志，
运维速查入 16 号文档第 5 节。同日追加 UI-ALIGN-FIX：base.html 覆盖块对齐 lab 版
顶栏/选中态/日历（探针提取计算样式，禁用字「lab 版」代称），rsync gui/ 部署后公网
管理台入口消失、console 404 保持。未 commit。

上一任务：QRE-SAAS-ADMIN-E1E3 (DONE — SaaS 后台管理三件套：/saas/console 总览+用户/因子审核+worker 运维；users+role/status、workers 表；测试 +12 全量 2130 零回归；awaiting git approval)

2026-09-27：按 15 号文档 E 阶段落地 SaaS 管理后台（本地开发不部署）。users 加
role/status 幂等迁移、新 workers 心跳表；_require_admin 门禁；/api/saas/console/*
八端点（overview/users tier+status/factor-requests review/workers/jobs retry+cancel）；
console.html 五 tab 页面遵守 12 号设计系统；顶栏管理台入口仅 is_admin 注入。
前缀弃 /admin 改 /console（禁链纪律含注释），E3 指令下发/家里 PG 状态卡裁剪留后续，
决策入 06 日志。未 commit。
上一任务：QRE-UI-DESIGN-SYSTEM-DOC (DONE — 纯文档：12_UI_STYLE_GUIDE.md 重写为完整设计系统 25.3KB，每条规范标注源码 文件:行号；8081 lab 代码零改动；check-progress-docs.sh 通过；awaiting git approval)

2026-09-27：应用户要求把 8081 UI 设计知识从源码蒸馏进文档（根因：UI 对齐工作反复重读源码烧 token）。通读 lab-theme.css/lab-ui.js/lab.html/lab_result.html/lab_symbols.html/lab_symbol.html + SaaS base.html 复刻方式后重写 12 号文档：新增文件地图、36px 行内控件等高硬规则、ECharts 图表约定（纠正初版过时的 SVG 手绘描述）、treemap 三档显隐与 zr.off 陷阱、SaaS 复刻约定、禁链含注释教训。文档头部加「新页面开发前必读、改动规范需用户批准」。未 commit。

上一任务：QRE-LAB-UI-LANDING-R6 (DONE — OOM 限额 2G→8G + 僵尸 run 自愈 + 重提 5 年全量回测；awaiting git approval)

2026-09-08（R2 纠偏，用户驳回 R1 适配改写）：以 synthesis.html 为唯一真相源 1:1 移植——lab-theme.css=设计稿 CSS 全量+母板类映射，模板区块/类名逐段对齐，数据全走真实 API（fees_summary/symbols 路由沿用 R1 新增），echarts 图按规则 4 保留但配色/区间卡/tooltip/三级显隐对齐设计稿。测试 2067+4 绿。R1 细节（已部分被 R2 覆盖）：把已定稿设计稿 synthesis.html（docs/agent/12_UI_STYLE_GUIDE.md 为其规范）
原位落地 8081 lab 版（qre-gui-lab），8080 管理台零改动（git diff 仅 lab_* 模板 +
gui/lab_result.py + lab 两个测试文件 + 新增 lab-theme.css/lab-ui.js/lab_symbols.html）。
新建策略页：三入口并列卡 + PCB 排线（static/lab-ui.js）、预览栏（#strategy-yaml
迁入参数区之后成唯一 YAML 真相源 + 参数合并行 + 复制）、策略 ID 公共项
（param-sname，提交时 applyNameToYaml 写入 name；用户手改后不再自动覆盖）、
日历选择器（LabUI.attachCalendar，最大可选日 = /api/admin/refresh 的
state.last_data_date，禁今天及以后防未来函数）、唯一「运行回测」流水线
（①/api/validate 含 ID 校验 → ②saveToSandbox+smoke+waitForCheck → ③/api/run
沿用原参数 payload 与 >3000 只护栏；后端零改动；失败红字停留定位）。
回测记录：「股票数量」列 + 状态徽章 + 删除改二次确认弹层（API 不变）。
策略详情页：模块顺序 概述→收益曲线→交易磨损（新 box-fees，chart-data 新增
fees_summary：round_trips.csv 真实费用列聚合，缺失则整块隐藏）→FRM→归因热力图
→「查看个股回测明细 →」大入口卡；dataZoom 区间卡重算 rAF 节流；echarts 配色换
淡紫规范（策略 #6750A4 / 基准虚线 #8B7FBE / 直方图 #B7A6E8，红绿只给涨跌）。
新页 /lab/runs/<id>/symbols（lab_symbols.html + lab_result.py 新路由）：归因 A 层
聚合成全量个股表，点列头排序、搜索框模糊过滤、完整代码回车直跳个股详情。
个股详情页：顺序 概述→收益曲线（补区间卡五卡 + 滑块 rAF 重算）→交易磨损（该股
orders/trades 聚合）→K线→交易明细→下单记录；配色同步规范。
可见文案纪律：「沙箱/晋升」仍禁止；「冒烟测试：单股票 × 短期区间」为本轮用户
批准的流水线文案（test_gui_lab 去术语断言同步放行冒烟一词）。
测试：lab 两测试文件更新断言 + 3 新用例（fees 聚合、symbols 页、symbol 页结构）；
lab 65 全绿；全量 `pytest tests/ -q` → **2067 passed + 4 skipped**（2065 + 2 净增）
零回归。验证：restart qre-gui-lab 后 /、结果页、symbols、symbol、两个静态文件、
chart-data 全 200；chart-data.fees_summary 真值（18,346 笔，佣金 133.05 万 +
印花税 111.22 万 + 过户费 4.44 万 = 总磨损 248.70 万，毛收益 1,348.69 万）。
未 git commit，等用户审批（commit message 需先出示）。
上一任务：QRE-WORKER-ARTIFACT-PERSIST (DONE — 2065 tests green；awaiting git approval)

2026-09-08 QRE-UI-STYLE-GUIDE（规范文档 + 性能审计已 commit：127200b）。

2026-09-07（用户决策）：**8081 = SaaS staging（预发），ECS aguhuice.com = 生产**。
发布流程约定：改动 → 8081 验证 → 用户验收 → 部署 ECS。
8081 服务（qre-gui-lab，沿用服务名）ExecStart 已切换为 `qre saas --port 8081`
（lab*.py 代码保留在仓库，仅不再起服务；8080 qre-gui 不动）。环境变量在
`.env.saas-staging`（0600，gitignore .env.* 覆盖）：SAAS_DB_URL=本地库
aguhuice_local、SAAS_AUTH_CHANNEL=stub + SAAS_STUB_LOG + SAAS_STUB_ECHO=1
（staging 专用，生产严禁）。新系统服务 qre-saas-worker（轮询 8081，5s，
只读账号连本地大库）。新 `qre saas` CLI 子命令。端到端已验证：
dev_code 登录 → smoke job → worker done（65s）。全量 2054+4 绿。
未 git commit。
上一任务：QRE-SAAS-007 (DONE — 2052 tests green + 4 skipped；awaiting git approval)

2026-09-05: NL 编译链路因子名自动纠错层（用户直接指派；8081 gui/lab*.py
冻结页零改动，改动全在 8080/8081 共用的引擎/编译器侧）。痛点：DeepSeek
编造库中不存在的因子列名（rsi14/MACD 等），YAML 因缺因子失败、用户
只见红错。新 `gui/factor_correction.py` 纯函数层（零 DB 零 IO）：
auto_fix_column 保守三规则——归一化（小写+去下划线）等价 / 唯一候选
编辑距离 1 且次优差距 ≥3 / 唯一前缀（macd 系列多列并列则不纠正给候选）；
suggest_similar_columns Top-5；correct_factor_fields（同表候选优先、
同表空跨 8 个标准因子表兜底、列名对表写错直接换表，就地改写 target，
alias 与信号表达式不动）；COMMON_FACTOR_TARGETS 18 条常用已落库列。
compile_nl 在 missing_factors 判定前先纠错：全纠正成功重写 YAML 正常
返回（warnings 标「已自动纠正 X→Y」+ corrections 字段）；仍有未解决项
照旧入补因子队列，error 改 actionable（Top-5 候选 + 常用因子清单 +
suggestions 字段）。build_system_prompt 注入「严禁编造因子名」硬约束 +
常用已落库列。strategy_lab_routes 手工 YAML 通道（/api/strategies/create
mode=manual）同逻辑生效。测试 tests/test_gui_factor_correction.py +17。
未 git commit。
上一任务：QRE-GUI-POOL-MOM-007 (DONE — 1943 tests green + 4 skipped；awaiting git approval)

2026-09-04: 「聚类动量」页 v7 前端渲染性能（用户反馈卡顿，排查确认
瓶颈纯在前端 DOM：concept 1066 行 × 20 列 ≈ 2.1 万单元格 + 首列
sticky 重绘）。纯前端优化，API/数据/pool_momentum.py 零改动：
①默认 Top/Bottom 50 截断（MOM_EDGE_N=50 + momShowAll，.mom-gap 行
「显示全部 N 行」/「收起」按钮）；②精简列模式不再输出 mom-col-x
td/th（原 display:none 删除，展开更多列时才渲染）；③CSS 行级
content-visibility: auto + contain-intrinsic-size；④首列 sticky 仅
展开模式启用（.mom-scroll.mom-sticky）；⑤展开/收起只重渲本分区
（renderMomentumTable(poolType)），排序两表共享键仍同刷。单元格数
21,656 → 默认 ≈1,091（−95%）。改动 admin.html + style.css +
tests/test_gui_pool_momentum.py（+1，79 总；v5 断言同步删
mom-compact、加 v7 标记）。qre-gui 已重启 active；curl /admin 200
含新标记，overview API 200（988KB/0.12s）。未 git commit。
上一任务：QRE-GUI-POOL-MOM-006 (DONE — 1942 tests green + 4 skipped；awaiting git approval)

2026-09-04: 「聚类动量」页 v5 榜单可读性（用户反馈两 UI 问题）。
①concept 榜单 17+ 列横向溢出 → momTable 包 .mom-scroll 横向滚动 +
首列池名 sticky（热力行 background:inherit，行仅 heat 非空才输出
style）+ 默认精简列（池名/股票数/当前窗口 fwd/速度/加速度/共振/
⚠回避/事后×3），扩展列标 mom-col-x、.mom-compact 隐藏，
「#btn-mom-cols 展开更多列」开关切全量列。②点池名详情不再落页面
底部 → 删底部 data-section="mom-detail" 折叠区，新 #mom-detail-panel
固定于 #mom-summary 之下、榜单之上（标题 + 关闭按钮 + scrollIntoView，
点其他池原地替换）；成员明细 .mom-members-scroll 限高 420px 内部滚动
（表头 sticky 沿用全局）。改动集中 admin.html + style.css +
tests/test_gui_pool_momentum.py（+2，78 总）；pool_momentum.py 零改动。
qre-gui 已重启 active；curl /admin 200 含新标记，overview（真库
2026-09-03：concept 1066/state 14）与 detail API 200。未 git commit。
上一任务：QRE-GUI-POOL-MOM-005 (DONE — 1940 tests green + 4 skipped；awaiting git approval)

2026-09-02: 「聚类动量」页 v4 底部减速回避名单（M7 全历史结论：
fwd_ret_3 最弱 Bottom10 未来 3-5 日继续跑输约 0.2%/日，NW t=−3.86，
FDR q=0.001，20 日后消失；顶部信号全部无效）。纯函数
compute_bottom_avoid（组内最低 10 个标 avoid，None 与 n_stocks<10
剔除）+ avoid_list；overview payload 加 avoid 三键；榜单行「⚠ 回避」
徽章（白底红框区别于热力背景，title 注依据）+ 顶部 #mom-avoid 汇总卡
（点击跳详情）+ 声明卡补「顶部无选股价值，主要价值=底部回避名单」。
历史回看按选中日截面 point-in-time。测试 +11（76 总）。qre-gui 已重启
active；真库 2026-08-31 concept 回避居首「申万L3:疫苗」−5.73%，state
14 有效池取最低 10（跳空:低开 −2.35% 居首）。未 git commit。
上一任务：QRE-GUI-POOL-MOM-004 (DONE — 1929 tests green + 4 skipped；awaiting git approval)

2026-09-01: 「聚类动量」页 v3 历史回看。overview 加 trade_date 参 + fwd
可选日期下拉（249 日，point-in-time 榜单）；事后验证列 post_3/5/20
（compute_post_returns 纯函数，∏(1+fwd_ret)−1 over (T,T+w]，未满窗口→
NULL）；验证摘要条（accel_top_summary 纯函数，加速度 Top10 post_5 均值/
中位/胜率 vs 全体）；detail 加 end_date、members 传选中日期。测试 +11
（65 总）。qre-gui 已重启 active；真库 2025-09-05 concept 加速度 Top10
post_5 +0.19% vs 全体 +0.88%（该日无超额，如实呈现）。未 git commit。
上一任务：QRE-GUI-POOL-MOM-003 (DONE — 1918 tests green + 4 skipped；awaiting git approval)

2026-09-01: 「聚类动量」页升级 M7 v2 前瞻口径。速度/加速度/热力/共振全切
fwd_ret_w（compute_acceleration/compute_heat 加 metric 参、resonance 判
fwd）；回看 ret_w 降级对照列；overview 默认展示最近 fwd 已补齐日
（fwd_lag 红色提示末日 NULL=正常 T+1 滞后）；state 分区 8 个 artifact
池加事件 4 列（次日溢价/存活/胜率，对标同花顺涨停复盘）；详情主线 fwd、
回看浅色辅线；声明卡改写。测试 +9（54 总）。qre-gui 已重启 active；
真库榜单日 2026-08-31，concept fwd_ret_3 榜首「昨日打二板以上表现」。
未 git commit，等用户审批。
上一任务：QRE-GUI-POOL-MOM-002 (DONE — 1909 tests green + 4 skipped；awaiting git approval)

2026-09-01: 「聚类动量」页三项优化。①池内个股明细：新 API
/api/admin/pool-momentum/members（concept=company_tags 快照、state=当日
daily_tags；compute_member_metrics 纯函数即时算 stock_daily，口径与 M7
管线逐位一致——成员等权 ret_3 与池表值完全相等、有效成员数==n_stocks；
名称 reference.stock_basic 降级可选），详情区新增可排序成员表。②主榜单
全数值列+成员表点击表头排序（▼/▲、None 恒末位）。③行热力 compute_heat
（ret_w 截面分位 heat∈[-1,1]，红涨绿跌）随窗口重算；长弱短升改左侧绿边
+加粗。测试 +21（45 总）。qre-gui 已重启 active，curl 全 200。
未 git commit，等用户审批。
上一任务：QRE-GUI-POOL-MOM-001 (DONE — 1888 tests green + 4 skipped；awaiting git approval)

2026-09-01: 8080 管理台新增「聚类动量因子研究」tab（data-tab="mom"），
只读 cluster.pool_momentum_daily（cluster-ashare M7 产物）。新
gui/pool_momentum.py（market_risk.py 同款只读数据层 + 纯逻辑
rank_desc/compute_acceleration/resonance_flag/sort_by_acceleration）；
app.py +/api/admin/pool-momentum[/detail]；admin.html +tab（偏差声明
卡 + 窗口 3/5/20/50 切换 + concept/state 双榜单 15 列 + 长弱短升高亮 +
点击池名 250 日 inline SVG 详情）；style.css 纯追加。8081 零改动。
测试 tests/test_gui_pool_momentum.py +24。qre-gui 已重启 active，
真库 curl 三端实测 ok（2026-09-01：concept 1066 / state 14）。
未 git commit，等用户审批。
上一任务：QRE-GUI-LAB-RESULT-030 (DONE — 1840 tests green + 4 skipped；awaiting git approval)

2026-08-31: B 层关键词换代（cluster-ashare 东财+同花顺概念板块成分替换 jieba
碎片词，旧数据已删 97,838 行）+ 8080 总览「概念标签源（B 层）」卡片
（admin.py overview_concept_tags / app.py payload / admin.html 卡片）；
8081 归因端零改动实测受益（B 层真概念词：华为概念/CPO概念/PCB 等）。
cluster-ashare 204 passed。遗留：东财接口当日断连，504 板块入库 290，
网络恢复后重跑幂等补齐。未 git commit，等用户审批。
上一任务：QRE-GUI-LAB-RESULT-023~026 (DONE — 1824 tests green + 4 skipped；awaiting git approval)

2026-08-24: ①NL 示例编译失败无法复现（curl 4/4 + jsdom 点击流均成功，
疑 DeepSeek 抖动/缓存旧页）②高级选项七输入补 change+input 监听即时刷新
YAML 预览 ③向导页加「存入沙箱+冒烟测试」主按钮（saveAndSmoke 共用流程），
「去高级 YAML」降为次按钮，向导全程鼠标闭环不强制跳 tab。8080 零改动。
上一任务：QRE-GUI-LAB-ENTRY-021 (DONE — 1809 tests green；见 05/09)
两步确认显性化：晋升按钮改「正式回测（晋升）」confirm 带冒烟摘要。
selectedFactors 改由条件行使用推导（usedFactors），删除 #wz-factor-groups。
style.css 纯追加；零新前端依赖；API 契约零变化。测试 test_gui_lab.py +1。
冒烟：qre-gui-lab 重启 active，8081 / 200 含三 entry-tab 标记，8080 / 200；
node 语法自检三个 script 块全过。无 CR。未 git commit，等用户审批。
上一任务：QRE-GUI-LAB-PORT-017 (DONE — 1807 tests green + 4 skipped；见 05/09)

2026-08-23: 回测台新端口移植——「新增策略」+「回测管理（策略状态）」
两页面原样移植到独立 Flask 应用 @8081（纯移植零优化）。路由共享：
新 gui/strategy_lab_routes.py::register_strategy_lab_routes(app)，
create_app 与 create_lab_app 共用；新 create_app 路由表与 git HEAD
逐条相等（59/59）。try_acquire_run_slot/release_run_slot/run_backtest
在 app.py re-export 并经 gui.app 调用时解析（兼容既有测试 monkeypatch）。
新 gui/lab.py + templates/lab.html（两 tab 内容脚本切片组装，含排序
JS/搜索/toggle/删除/gate 徽标；附 /runs 页面）。CLI：qre gui --lab
（默认 8081）。systemd：deploy/hardened/qre-gui-lab.service 已安装
enable --now（enabled/active，SyslogIdentifier=qre-gui-lab）。
测试 tests/test_gui_lab.py +12。冒烟：8081 / 双 tab、/api/admin/refresh
stopped 118/118（8080 一致）、策略详情 200；8080 / 与 /admin 200。
两个 service 均已重启。无 CR（纯移植）。未 git commit。
上一任务：QRE-GUI-SORT-016 (DONE — 1795 tests green + 4 skipped；见 05/09)

2026-08-23: 策略状态表客户端排序（回测起止/股票数量/超额收益/最大回撤
四列可点击，升降序切换，null 恒排末位；纯模板 JS）。下游补跑链验证：
四 service 补跑 exit 0，stock_daily/factors/cluster.daily_tags/
market_risk.daily watermark 全到 2026-08-21，周五事故清零。qre-gui 已重启。
上一任务：QRE-GUI-DERIV-FRESH-015 (DONE — 1795 tests green；见 05/09)

2026-08-23: 风向标 M3 落地（CR 状态改「✅ M1–M3 已完成」）。
deploy/hardened/qre-barometer.{service,timer}（Mon..Fri 18:30、Persistent、
默认最近交易日，未 sudo）；barometer_job latest_trade_date 默认日期 +
`qre barometer` CLI；admin TIMER_UNITS/PIPELINES 登记；/admin 新「大盘
风险」tab（gui/market_risk.py 只读 market_risk.daily + 仪表盘/五序列
SVG/双口径热力表/预警详情，复用现有样式）；阈值首轮校准观察入 06
（red 11/1850=0.59% 全为已知风险事件，初值保留）。真库冒烟 ok。
1778 tests green（+14）。未 commit、未重启 qre-gui、未装 timer。
详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-BAROMETER-M2-009 (DONE — 1764 tests green；commit b0713d7)

2026-08-23: 大盘/板块风险风向标 M2 落地（CR_2026-08-23_market_risk_barometer
§5 M2 阶段；M1 = commit 64addd7）。新 risk/barometer_job.py（risk 包唯一
读写 DB 层：pct_chg/100 收益 + total_mv 市值 + industry 行业 +
daily_tags 当日簇 <5 跳过 → M1 纯函数 → 独立 schema market_risk.daily
表（PK (trade_date,scope)、ON CONFLICT 幂等 upsert）+ JSON 产物
outputs/market_risk/<date>.json；年分块 + 312 交易日 buffer）。真实回填
2019-01-02→2026-08-20：220,034 行 / 1,850 日 × 120 scope，~21min。
方向性验证全过：2020-02-03 red（突破 85.2% P100）、2024-02 微盘连续
red（总分 P99–100）、常态 green；全样本 red 11 天均为已知风险事件。
1764 tests green（+10）。未 commit、未重启 qre-gui。详见
09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-BAROMETER-M1-008 (DONE — 1754 tests green；commit 64addd7)

2026-08-23: 大盘/板块风险风向标 M1 落地（CR_2026-08-23_market_risk_barometer
§5 M1 阶段）。risk 包新增 cross_section.py（纯函数零 DB、向量化：EWMA
方差面板与 volatility 单列口径 atol 1e-15 一致、截面波动率中位/90 分位、
等权/市值加权离散度、滚动 60 日平均两两相关等权 + w_i·w_j 偶权近似、
VaR 突破计数/占比、summary 一把梭 σ shift(1) 防前视）与 barometer.py
（组合法 100% 复用 volatility/tail、252 日滚动分位分数 warmup 降级
None、红/黄/绿双判据预警、build_barometer 全市场+板块统一 dict、分组
映射调用方传入）；constants.py 加 BAROMETER_CORR_WINDOW=60/
SCORE_WINDOW=252/ALERT_CORR_LOOKBACK=20/ALERT_CORR_JUMP=0.10/
ALERT_BREACH_RATIO_MAX=0.03/BREACH_CONFIDENCE=0.99/
CROSS_SECTION_SIGMA_QUANTILE=0.90 全回显（阈值初值待 M3 校准）。
1754 tests green（+30：cross_section 17 + barometer 13）。全量首跑
test_gui_risk_report.py::test_post_conflict_409 flake，复跑全绿。
未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-PORTFOLIO-007 (DONE — 1724 tests green；awaiting git approval)

2026-08-23: FRM 风险模块 R7 落地（CR_2026-08-23_risk_derivatives_extension
R7 阶段，CR 状态改「R5–R7 已完成」；R5=5472832、R6 待审批）。新
risk/portfolio.py（纯函数零 DB，summarize_mixed_portfolio：股票腿沿用
R1–R4 收益序列法、债券/转债腿 DV01 可加 + D/C 市值加权 + 可选 KR01 按
节点加总、期权腿组合 Greeks 加权求和、config 显式给 dgv.spot_shock_sd
才计算 DGV-VaR；仅股票退化为仅 equity 节）；risk/report.py 显式传入
bond_positions/option_positions/bond_kr01 才追加 portfolio 节 +
markdown「组合与衍生品风险」渲染；GUI run_detail 有节才追加「衍生品风险
（组合层）」卡片（_risk_display + risk-card 模式）；constants.py 加
GATE_DV01_MAX/GATE_GREEKS_MAX（默认 None=不启用），evaluate_gate_risk
启用时追加组合 DV01/Greeks 限额判据、默认关闭时返回与 R4 逐键一致。
1724 tests green（+28：portfolio 14 + report 7 + gui 7）。默认 run 产物
零变化，老格式 report 向后兼容专项测试覆盖。未 commit、未重启 qre-gui。
详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-OPTIONS-006 (DONE — 1696 tests green；awaiting git approval)

2026-08-23: FRM 风险模块 R6 落地（CR_2026-08-23_risk_derivatives_extension
R6 阶段；R5=5472832）。risk 包新增 options.py（BSM 式 15.6–15.9 无股息/
q/离散股息 S₀−D、Black's 式 15.12/15.13、隐波 brentq IV_BRACKET、CRR
式 14.4–14.7 欧式+美式含 q + 第一层 delta + 可选全节点网格、美式 Greeks
数值差分（书4 Ch16）、Greeks 解析全组 Table 16.2 含 q 版与期货期权版
rho=−f·T、组合 Greeks 加权）与 derivatives_var.py（DGV 近似 P&L
式 2.3+vega 项、非中心卡方累积量解析矩、正态/Cornish-Fisher 分位 VaR、
VaR 序列对接 backtest_var_summary 复用 HIT/LR）；constants.py 加
IV_BRACKET/DEFAULT_TREE_STEPS=50/GREEK_SHOCK_*（全部 dict 回显）。
教材数值全复现：BSM 例 c=8.3069/p=7.9715+parity、隐波 7.00→25.14%、
美式 put 节点 3.058/0.494/5.699（欧式 2.838，参数 S=29,K=30,r=3%,σ=25%,
T=1 经教材原文 p193 核对）、收敛 3.082/3.067/3.059/3.055、PDE 恒等式
1e-10、纯 gamma 解析二阶矩、CF-VaR 对 MC rel 5%、VaR 序列回测违约率
≈1% 不拒绝。自审修正 Black76 theta 符号（有限差分自检发现）。
纯函数零 DB 零行情，既有 risk 模块零行为改动。1696 tests green（+39）。
未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-RATES-005 (DONE — 1657 tests green；awaiting git approval)

2026-08-23: FRM 风险模块 R5 落地（CR_2026-08-23_risk_derivatives_extension
R5 阶段；R1=96db59d / R2=f52c0f4 / R3=6852eaa，R4 待审批）。risk 包新增
rates.py（式 16.1–16.5 复利换算、PV/FV、spot↔折现因子、书4 Ch9 附息债
bootstrap 零息曲线、线性/对数线性插值、远期利率、par yield 式 16.7/10.4）
与 bonds.py（YTM brentq、actual/actual+30/360 应计利息、式 12.6 久期凸性、
effective duration/convexity、DV01 与 D↔DV01、组合聚合与对冲配比、
式 12.4 二阶近似、书4 Ch13 KR01（ΣKR01=DV01 自检）、书3 Ch16/17 转债
债底+spread duration）；constants.py 加 DEFAULT_DAY_COUNT/
CURVE_INTERPOLATION/KEY_RATE_TENORS/RATE_SHOCK_BP/YTM_BRACKET（全部
结果 dict 回显）；pyproject.toml 补 scipy 显式依赖。教材数值全复现：
bootstrap d=0.991909/0.980944/0.969406/0.956909、par yield 2.2103%、
年金解析解 P/D/C、ΣKR01=DV01、+100bp 二阶近似 rel 偏差 1.9e-5。
纯函数零 DB 零行情，既有 risk 模块零行为改动。1657 tests green（+52）。
未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-GATE-004 (DONE — 1605 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R4 落地（R1=96db59d / R2=f52c0f4 / R3=6852eaa）。
晋升全量回测闸加入风险判据：risk/constants.py 加 GATE_ES99_MAX=0.03 /
GATE_VAR_CONFIDENCE=0.99；gui/risk_report.py 加 evaluate_gate_risk（读
runs/<run_id>/risk_report.json，ES99 超阈或 99% 覆盖率 Kupiec LR 拒绝 →
risk=warning，缺失 → unavailable 不阻断）；finalize_promotion_gate 写
gate json risk 节（主判据照旧）；gate_blocks_daily 扩展 failed 或
risk=warning 非 forced 即阻止日更（force 照评估不阻断）；admin.html
闸列 warning 追加「⚠ 风险警示」徽标（tooltip ES99 + VaR 回测结论）
+ style.css .gate-risk。存量 gate json 无 risk 节行为不变。1605 tests
green（+6）。未 commit、未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-INTEGRATION-003 (DONE — 1599 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R3 落地（R1=96db59d / R2=f52c0f4）。risk 包集成进
回测报告与 GUI：risk/report.py + render_risk_markdown（汉化风险分析节，
两位小数，分布与尾部/VaR回测/波动率/压力/绩效分区，error 降级）；
新 gui/risk_report.py（组合级 equity_curve.csv daily_return 提取 +
benchmark_close 可选 + finalize 钩子写 runs/<run_id>/risk_report.json +
幂等追加 summary.md 风险节 + daily_jobs 按需 job bootstrap 开）；
engine.py:354-361 收尾钩子（try/except 兜底同 smoke/promotion_gate）；
app.py run_detail risk 视图 + POST/GET risk-report 端点（404/400/409）；
run_detail.html 风险分析六卡片 + 老 run 按需生成按钮。#4 admin badge
未加（refresh_overview 无 risk_report，硬塞超范围）。真实 E2E：mr01a
5 股×2024-2025，n=484，99% VaR 1.50%/1.79%、ES 1.72%/2.19%，JB
p<0.0001，VaR 回测两级均不拒绝，summary.md 风险节落盘。未 commit、
未重启 qre-gui。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-CORE-002 (DONE — 1578 tests green；awaiting git approval)

2026-08-22: FRM 风险模块 R2 落地（R1 = commit 96db59d）。risk 包新增
backtest_var（书2 Ch6：HIT、覆盖率 Bernoulli LR + 精确二项、独立性
Christoffersen 转移矩阵 LR——摘要未点名 Kupiec/Christoffersen 如实标注、
多重检验假阳性 1−(1−α)ⁿ）、stress（书4 Ch8：A 股四情景库、回放累计损失/
峰谷/Peak/VaR + 相关性崩溃提示、reverse stress β 穿透反查市场冲击分位/
σ 倍数）、inference（书2 Ch13：arch CBB 块长 √n 给年化收益/夏普/最大
回撤 CI + iid 对照 + MC 标准误 σ/√b）；report.py 升 R2（var_backtest
默认开用 EWMA μ=0 VaR 防前视，stress/bootstrap config 可选开启）。
46 个新测试全为已知答案核对（LR 手算 4.13085、转移计数手算、回放
−0.119179/0.05/2.5、reverse β=2、bootstrap 固定 seed CI 含真值 +
AR(1) 下 iid 低估 CBB）。未 commit、未重启 qre-gui。详见
09_CODING_HANDOFF 顶部。
上一任务：QRE-RISK-CORE-001 (DONE — 1532 tests green；commit 96db59d)。

2026-08-20: deep-validate 501 骨架落地为真功能。cluster-ashare 新增薄脚本
analysis/pool_from_conditions.py（条件 JSON→逐日池 parquet，DB 全留 cluster
侧，表达式求值复用 QRE evaluate_expression_signal；未走 factor_executor——
其分位/tag 语义与 QRE 布尔 DSL 不匹配）；QRE 新增 gui/deep_validate.py
（spec_to_conditions 纯函数转换器/locate_strategy_yaml/parse_report_summary/
start_deep_validate_job，复用 daily_jobs 基建，lock_key=deep-validate:<name>，
price/eval 缓存键含区间断点续跑）；app.py POST/GET deep-validate 真实现
（404/400×3/500/409 分层，缺因子自动入队）；index.html 沙箱行按钮+通用
入口+10s 轮询不设放弃上限。真实 E2E：mr01a 全历史 → NO-GO（gate3 净超额
-0.130% t=-10.75），报告落 cluster outputs/factor_mining/validation/。
未重启 qre-gui，GUI HTTP 链路待重启验证。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-GUI-PROMO-GATE-001。

2026-08-20: 全量回测结果成为晋升后的状态闸。晋升 mark 加 promotion_gate/
promotion_forced（线程启动前预合并）；engine 收尾新钩子 →
strategy_create.finalize_promotion_gate（写死判据：交易≥30 且超额>0 →
passed）原子写 outputs/refresh/gates/<name>.json（catalog 不动）；refresh_batch
日更跳过 gate=failed 非 forced（日志 + config.gate_skipped），refresh_overview
行加 gate 字段；admin.html 策略状态表加「全量回测闸」四态列（绿/红+tooltip/
灰/橙强制在库）；force 晋升评估照跑不阻止日更（API gate_note 注明）；新增
POST /api/strategies/<name>/deep-validate 501 骨架（策略→信号池转换器待实现）。
未重启 qre-gui，真实 E2E 待重启验证。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-GUI-CREATE-GAPS-001。

2026-08-20: GUI 新增策略/因子闭环四缺口补齐——①策略冒烟 sidecar 闭环
（engine 终态钩子 + mark 预合并消竞态 + list_sandbox 自愈 + 前端三色渲染）；
②晋升冒烟状态闸（promote/promote_factor 加 force，smoke_not_passed → 409）；
③因子冒烟同步改异步（复用 daily_jobs lock_key 机制，POST 返回 job_id +
GET 轮询端点 + 前端轮询）；④删 .p3c-hidden 死代码。未重启 qre-gui，
真实 E2E 待重启验证。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-ADMIN-FACTOR-FRESH-001。

2026-08-19: dashboard 新增「聚类分析」tab（只读展示 cluster-ashare 因子工厂
产出）：gui/cluster_admin.py（QRE_CLUSTER_REPO，分区降级+TTL 300s 缓存），
app.py +/api/admin/cluster 与 /api/admin/cluster/artifact/<path> 下载白名单，
admin.html 第 6 tab 四分区（38 因子注册表/M4 轨迹+traj13 成员/衰减监控
9-23-5/13 个产物链接）。重启 qre-gui 实测全 ok。详见 09_CODING_HANDOFF 顶部。
上一任务：QRE-M5C-MINED-FACTOR-STRAT-001。

2026-08-18: 因子工厂 Top3（cluster.mined_factors MF_001/002/003）转译为
cs07a/b/c（catalog/cross_sectional/），截面分位由 cluster-ashare 物化表
cluster.mined_factor_flags 承载（QRE 三段式寻址 cluster schema，零引擎改动）。
闭环：沙箱 3/3 → 冒烟 20 股×半年 3/3 → 晋升 → 全市场 3820 股×近 1 年
（成本/止损 8%/universe 过滤/基准 000300.SH，批次 b21f1008ec98）3/3 ok →
report-audit 6/6 ok。结论：近 1 年未复现 M3b 超额（-11.1/-11.3/-11.6% vs
基准），建议三因子转「衰减观察」（cluster 侧 status 调整待用户确认）。
详见 09_CODING_HANDOFF 顶部。上一任务：QRE-ADMIN-TIMERS-001。

2026-08-12: GUI 首页三 tab → 两 tab（新增策略一页三入口 + 新增因子路径 A/B，fc-create 迁入首页，tab-builder 删除，app.py 零改动）。详见 09_CODING_HANDOFF 顶部。上一任务：QRE-ADMIN-STRAT-INCREMENTAL-FIX-001（策略状态 tab 增量合并）。

2026-08-12: GUI 新因子创建闭环 P2（/api/factor-create/* + indicators sandbox 冒烟 + 晋升 validate→backfill job）。真实 E2E：vidya 因子 DeepSeek 生成 → 冒烟过 → 晋升 job 20260812T030850074330。详见 09_CODING_HANDOFF 顶部。上一任务：QRE-ADMIN-CONSOLE-P3A-001 + QRE-ADMIN-FACTOR-HEALTH-FIX-001 (1264 tests green)。

2026-07-28: admin console read-only slice (dashboard/timers/query) + factor-health fix (managed-table whitelist from indicators config; vortex orphan table demoted to informational). quant_ts upstream fix: normalize_reference_frame numeric coercion (daily_basic text→NUMERIC staging conflict), daily rerun completed, watermark 2026-07-27. Health: green.

Earlier 2026-07-27: GUI workbench P1 (params form/async/precheck/compare) + P1.5 (factor-first wizard + factor-admin panel) + P2 (NL→YAML compiler). Design docs: gui_backtest_workbench.md, gui_factor_first_wizard.md, gui_admin_console.md.

## Pending Decisions (user)

1. GUI acceptance on `http://localhost:8080` (+ `/admin`); NL channel needs QRE_NL_LLM_* env.
2. Optional: drop orphan empty table `factors.stock_daily_vortex_close` (destructive, needs explicit OK).
3. P3b: manual daily-trigger buttons + integration center (refresh registration) + timer log tail; P3c: maintenance tab. qre-refresh.timer install needs sudo (user runs command).
4. TimescaleDB hypertable re-registration project — unscheduled.

Then (user-directed): output-file optimization based on user inspection of `outputs/backtests/full_history_check2/ef8006cb8f4d/` (2 strategies × full market × 2010-2026).

Progress:
1. Verified canonical project `/home/van/quant-workspace/indicators_tushare` and systemd timers (quant-ts 16:30, indicators 16:40, both enabled; yaml-config factors auto-join daily updates).
2. Edits made (indicators repo, no git action): `config/factors.yaml` sma periods += 7/9/26/50/52 + `atrraw` entry; `factors/volatility_factors.py` new `ATRRawFactor` class (raw `atr_{n}` naming; same values as existing `atrr_10`).
3. Project flow: validate (success, 0 failures) → plan (all 7 target columns present; superset: other pending config columns in overlap/volatility categories also covered) → small-sample backfill of 000001.SZ → value parity vs hand-computed SMA/Wilder-ATR within storage rounding, 100% non-null.
4. Full-history backfill (`backfill --categories overlap volatility --execute --max-workers 4`) RUNNING in background.

Next when backfill completes: `factor_request_queue.py recheck` → fulfilled; small-sample re-run of the 5 shelved strategies (R-QRE-009); then user decides on full re-run.

## Standing Instructions (user)

- 2026-07-19: No full-scale backtest runs until the core engine work is mostly complete; after that, full-history (M9.4) runs start with small samples (R-QRE-009). Current slices (M10.1 analysis of existing artifacts) comply — zero backtest execution.

Parent change request: `docs/agent/change_requests/CR-0002-strategy-research-validation.md` (Milestone 9: Strategy Research Validation).

## Last Completed Step

**QRE-ANALYTICS-CONCAT-001 (DONE, finalized 2026-07-19, commit `b72b9af`):** backtest stage 25.852s — M9.1b ≤30s target MET (66.5×).

**QRE-TRAILING-STOP-BATCH-001 (DONE, finalized 2026-07-19, commit `77b8897`):** stop family complete in batch path.

**QRE-MISSING-FACTOR-QUEUE-001 (DONE, finalized 2026-07-19, commit `5c60b8b`):** queue store + shelve semantics + auto-queue + CLI + `docs/handoff.md`; 7 pending requests tracked.

**QRE-PREFLIGHT-MISSING-FACTOR-ROBUSTNESS-001 (DONE, finalized 2026-07-19, commit `6628631`).**

**QRE-BATCH-FULL-VALIDATION-001 / M9.4 pilot (DONE, finalized 2026-07-19, commit `f90567c`):** handoff emitted (7 requests); small-sample full-history pilot OK; ~3h full-scale estimate. Full-scale trigger + upstream factors remain user decisions.

**QRE-CONTINUOUS-REFRESH-001 / M10.3 (DONE, finalized 2026-07-19, commit `1345471`):**

1. `orchestration/refresh.py`: watermark query, RefreshState, rolling window, per-strategy delta computation, delta report writer with manifest.
2. `scripts/refresh_batch.py`: check-only/force/window/codes flags; idempotent vectorized re-run; state + delta persisted.
3. `deploy/qre-refresh.{service,timer}` documented (daily 18:30), NOT installed; README 7b-2 with install commands.
4. Small-sample e2e on real data: first run 106 ok/111; check-only side-effect free; same-watermark no-op; delta manifest audit ok.
5. 1118 tests green (9 new). No full-scale execution (standing instruction honored).

**QRE-STOPS-BATCH-ENGINE-001 / M10.2b (DONE, finalized 2026-07-19, commit `24c284d`):**

1. stop_loss_pct/take_profit_pct honored in both engines: close-based evaluation vs fill price, next-open execution, precedence pending retry > expiry > stop_loss > take_profit > exit_signal; dense candidates in vectorized engine when enabled.
2. Opt-in wiring: `apply_stops` + request overrides (None = spec values); shared mode passthrough incl. trailing_stop_pct; runner `--apply-stops/--stop-loss-pct/--take-profit-pct`.
3. Verification: 50 new tests (40 randomized-with-stops equality seeds); real-DB dual-engine identity (tf01a, mr04a); A/B effect + real stop_loss exit observed; default runs unchanged.
4. 1109 tests green. Trailing stop remains follow-up (shared engine already has it).

**QRE-PARAM-OVERRIDE-001 / M10.2a (DONE, finalized 2026-07-19, commit `a16d6c5`):**

1. `portfolio/universe.py`: metadata loader (stock_suspend/stock_st as-of, daily-derived list_date) + `apply_universe_filter` with complete drop accounting and honest `unavailable_rules`; `validate_profile_overrides`.
2. research_run: `profile_overrides` (dataclasses.replace + validation) and `universe_filter` (opt-in) wired for batch/shared modes; `universe_report.json` backtest artifact; manifest records overrides + flag.
3. Runner flags: `--universe-filter`, `--commission-rate/--min-commission/--stamp-tax/--transfer-fee/--slippage-buy/--slippage-sell`.
4. Small-sample verified: overrides measurably change results; unavailable rules honestly reported on real data; default runs unchanged.
5. 1059 tests green (14 new). Stops split to M10.2b (engine exit logic, dual-engine equality).

**QRE-STRATEGY-FIT-ANALYSIS-001 / M10.1 (DONE, finalized 2026-07-19, commit `d514c4c`):**

1. `analysis/strategy_fit.py`: exact binomial significance tiers (90/99/99.9%), magnitude gate (net + excess vs buy-hold), free-rider accounting, strategy meta-test vs false-positive expectation, hypergeometric enrichment, BH-FDR, deterministic outputs + manifest.
2. `scripts/strategy_fit_report.py` + `strategy_fit_report_manifest` kind registered (report-audit passes); runner `--metadata-columns` passthrough.
3. Metadata reality: `reference.stock_basic` EMPTY upstream — metadata composed from `daily_basic` snapshot + `derive_board`; `industry_group` = unknown (gap documented).
4. Real batch (2024, 106 strategies): **all below 90% meta tier** (significant-stock counts below false-positive expectation — hand-verified true result); 25 stocks at 99% tier recorded as leads in `strategy_fit_stocks.csv`.
5. 1045 tests green (11 new); R-QRE-008 screening-evidence caveat in report.

**QRE-VECTORIZED-ENGINE-001 / M9.1b (DONE, finalized 2026-07-19, commit `c86441b`):**

1. Vectorized trade-level single-symbol engine: event-level loop on candidate bars, one-pass groupby pre-split, vectorized equity reconstruction; `position_sizing` (`full_compound`/`fixed_cash`).
2. Vectorized window/rolling analytics collectors (`risk.py` untouched, used as equality oracle); shared research frame between eval and backtest stages.
3. Equality evidence: 61 synthetic + 40 randomized tests, 106/106 catalog × 50 symbols byte-identical, full-market artifacts identical to simulator baseline.
4. Benchmark: backtest stage 1,718.9s → 40.2s (**42.8×**); quick batch estimate 11.1h → ~25-30 min. Runner `--engine-impl` defaults to `vectorized` (simulator kept as fallback); 1034 tests green.

**QRE-BATCH-PERF-SLIM-001 / M9.1 (DONE, finalized 2026-07-19, commit `24699ce`):**

1. Batch runner core moved into `orchestration/batch_runner.py`; `--jobs N` process-pool parallelism; `--compact` output mode (9 files vs ~26k per strategy, metrics byte-identical).
2. Per-stage timing in research-run manifests; `PostgresDataStore.close()` engine disposal; resume scan fixed (both directory levels).
3. Profiling baseline: tf01a quick mode serial = 1742.5s (backtest stage 98.6%); data-load reuse ruled out by evidence.
4. Quick batch `f365c8a07b33` (2026-07-19 06:32 +08): **106 OK / 5 error** (known missing-factor strategies), wall time **11.1h** with 4 jobs (vs ~51h serial), per-strategy mean 1459s (-16%), **2,013 files / 2.8GB** (~99.9% fewer files, ~89% fewer bytes); `qre report-audit` on compact manifests → ok.
5. Milestone 10 planned (CR-0003): M10.1 strategy-fit clustering, M10.2 parameter overrides, M10.3 continuous refresh, M10.4 optional ML clustering; M9.2/M9.3 merged into M10.1.
6. R-QRE-009 locked (user standing instruction): small-sample validation before any full-scale run.

## Git State

- Current branch: `master`
- Last commit: `96db59d` feat(risk): FRM 风险模块 R1 核心包（R2+R3 未 commit，工作树含两者改动）
- Working tree: R2/R3 改动 + untracked `.claude/scheduled_tasks.lock` (lock file, intentionally untracked)。
- **Run outputs now live outside the repo**: `outputs` → symlink to `/home/van/qre-outputs/` (all 19GB preserved there); `QRE_OUTPUT_DIR` env var overrides the batch runner output root.
- Remote: none configured.

## Latest Validation Evidence

```
uv run pytest -q → 1960 passed, 4 skipped, 4 warnings（2026-09-05, QRE-NL-FACTOR-AUTOCORRECT-001；基线 1943 + 17 净增）
纠错演示（内存 column_lookup 桩）：编造 rsi14 + macd_x_12_26_9 → 自动纠正 rsi_14 + macd_12_26_9 并标注「已自动纠正」；
  rsi_99 无可靠匹配 → 报错附 Top-5 候选（rsi_14/rsi_6/…）+ 常用因子清单，照常入补因子队列
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest -q → 1795 passed, 4 skipped, 4 warnings（2026-08-23, QRE-DERIV-ADAPTER-013；基线 1784 + 11 净增）
带库：QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data pytest tests/test_data_derivatives.py → 15 passed
真实冒烟：scripts/derivatives_adapter_smoke.py 2026-08-21 → 曲线 8 节点 1.164%–2.110%；
  转债债底 5 只 99.14–101.74 vs bond_value 105.4–111.2（赎回溢价差异可解释）；
  50ETF 平值 K=3.0 call/put IV 13.67%（parity 标的 2.9931）
基线首跑 test_gui_admin_p3b.py::test_daily_job_lock_per_pipeline 失败，单独复跑绿（已知 flake 家族）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1778 passed, 4 warnings（2026-08-23, QRE-RISK-BAROMETER-M3-010；基线 1764 + 14 净增）
真实冒烟：market_risk_overview() 真库 ok（2026-08-20 总分 63.3 green，252 日序列，105 行业，14 簇）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1764 passed, 4 warnings（2026-08-23, QRE-RISK-BAROMETER-M2-009；基线 1754 + 10 净增）
真实回填：2019-01-02→2026-08-20，8 年块，220,034 行 / 1,850 交易日 × 120 scope，~21min
方向性验证：2020-02-03 red（breach 85.2% P100）、2024-02-05 red（score 99.4 P100）、常态 2023-06 green（P10–21）；red 11 天全为已知风险事件
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1754 passed, 4 warnings（2026-08-23, QRE-RISK-BAROMETER-M1-008；基线 1724 + 30 净增）
风险新单测 30/30 绿（cross_section 17：面板对单列一致/相关==np.corrcoef/离散度手算/突破计数；barometer 13：组合法对 tail+volatility 逐键一致/预警三态/warmup 降级/等权 vs 市值加权差异）
scripts/check-progress-docs.sh → passed
git diff --check → clean
注：全量首跑 test_gui_risk_report.py::test_post_conflict_409 失败，单独与全量复跑均绿（环境敏感 flake）
```

```
uv run pytest tests/ -x -q → 1724 passed, 4 warnings（2026-08-23, QRE-RISK-PORTFOLIO-007；基线 1696 + 28 净增）
风险新单测 28/28 绿（组合层退化/混合合并/KR01 加总/DGV 开关 + report 节开关与渲染两态 + GUI 卡片两态 + 闸默认关闭逐键一致与启用判据）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1696 passed, 4 warnings（2026-08-23, QRE-RISK-OPTIONS-006；基线 1657 + 39 净增）
风险新单测 39/39 绿（BSM/隐波/二叉树收敛/PDE/Black76/美式 Greeks/DGV 解析矩/CF/MC/回测集成全教材数值核对）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1657 passed, 4 warnings（2026-08-23, QRE-RISK-RATES-005；基线 1605 + 52 净增）
风险新单测 52/52 绿（bootstrap/par yield/年金解析解/DV01/KR01/情景/债底全教材数值核对）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1599 passed, 4 warnings（2026-08-22, QRE-RISK-INTEGRATION-003；基线 1578 + 21 净增）
scripts/check-progress-docs.sh → passed
git diff --check → clean
真实 E2E：run 20260822T114522831346（mr01a 5股×2024-2025）→ risk_report.json + summary.md 风险节
注：首跑 test_gui_factor_wizard.py::test_job_lock_conflict 失败，全量复跑 1599 全绿（已知 flake）
```

```
uv run pytest tests/ -x -q → 1578 passed, 4 warnings（2026-08-22, QRE-RISK-CORE-002；基线 1532 + 46 净增）
风险包单测 107/107 绿（R2 46 新：LR/转移计数/情景回放/reverse/bootstrap 全手算核对）
scripts/check-progress-docs.sh → passed
git diff --check → clean
注：基线首跑 test_gui_factor_wizard.py::test_job_lock_conflict 失败，单独+全量复跑均绿（环境敏感 flake，非本任务引入）
```

```
uv run pytest tests/ -x -q → 1532 passed, 4 warnings（2026-08-22, QRE-RISK-CORE-001；基线 1471 + 61 净增）
风险包单测 61/61 绿（教材例题/解析解/手算/scipy 对照全覆盖）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

```
uv run pytest tests/ -x -q → 1471 passed, 4 warnings (2026-08-20, QRE-GUI-DEEP-VALIDATE-001)
node --check index.html 三段内联 JS → OK
真实 E2E：mr01a 全历史（2015-01-01~2026-08-19）池 2826 信号日/均 3770 只；
四关验证 ~14min → NO-GO（gate1 -0.087% t=-13.12 / gate3 -0.130% t=-10.75 /
gate4 等权 -0.080% t=-18.64）；parse_report_summary 对真实报告逐关解析正确
未重启 qre-gui（用户约束）；未 commit
```

```
uv run pytest tests/ -x -q → 1454 passed, 4 warnings (2026-08-20, QRE-GUI-PROMO-GATE-001)
node --check admin.html 内联 JS → 随 test_gui_admin 通过
未重启 qre-gui（用户约束）；未 commit
```

```
uv run pytest tests/ -x -q → 1437 passed, 4 warnings (2026-08-20, QRE-GUI-CREATE-GAPS-001)
node --check index.html 三段内联 JS → OK
grep .p3c-hidden / TODO-P3c → 全仓零引用（仅剩「断言不存在」测试）
未重启 qre-gui（用户约束）
```

```
uv run pytest tests/ -x -q → 1412 passed, 4 warnings (2026-08-19, QRE-ADMIN-CLUSTER-001)
curl /admin → 200；/api/admin/cluster 四分区全 ok
下载白名单：md/json 200，parquet 404，路径穿越 404
systemctl restart qre-gui.service → active
```

```
uv run pytest -q → 1034 passed, 4 warnings (2026-07-19, M9.1b final)
scripts/check-progress-docs.sh → passed
git diff --check → clean
equality ladder: 61 synthetic + 40 randomized + 106/106 catalog × 50 + full-market artifacts identical
benchmark: backtest stage 1718.9s → 40.2s (42.8×)
```

## Pending Decisions (user)

1. ~~CR-0002/0003 slices~~ — ALL DONE through M10.3 (commits `24699ce`/`c86441b`/`d514c4c`/`a16d6c5`/`24c284d`/`1345471`).
2. **Trigger full-scale full-history batch?** (~3h estimate, `outputs/full_history_pilot/feasibility.md`) — ready when you are.
3. ~~Upstream factor computation~~ — DONE (QRE-UPSTREAM-FACTOR-DELIVERY-001): backfill 5,544 stocks/0 failed; queue 7/7 fulfilled; 5/5 strategies unblocked; daily timer covers new columns from tomorrow. Full 111-strategy re-run (incl. formerly-shelved 5) is now a user decision alongside the full-history trigger.
4. M10.4 ML clustering — needs separate dependency approval (5070 Ti noted).
5. Follow-up micro-slices (optional): groupby-aware signal evaluation; runner-level cross-strategy frame caching (frame load ~17s is now the dominant cost). ~~Preflight UndefinedColumn robustness~~ — DONE. ~~Trailing stop~~ — DONE. ~~Cross-symbol analytics (≤30s)~~ — DONE, target MET at 25.852s.

## Quick Batch In Flight

- `outputs/backtests/quick_batch_106/f365c8a07b33/`, launched 2026-07-18 ~18:40, `--jobs 4 --compact --skip-preflight --resume`.
- Per-strategy ≈ 27-30 min (CPU-bound engine loop); expected total ≈ 13h. User decided to let it finish at `--jobs 4`.
- On completion: record batch results in `09`, verify compact output size reduction, then propose commit.

## Quick Batch Final (2026-07-19 06:32 +08)

- 106 OK / 5 error (only the known missing-factor strategies); wall time 11.1h; per-strategy mean 1459s (-16% vs baseline); 2,013 files / 2.8GB (≈99.9% fewer files, ≈89% fewer bytes vs standard mode); report-audit on compact manifests → status=ok, 0 issues.
- Remaining before commit: user approval.

## Phase Vocabulary (single-agent, since 2026-07-18)

- `PLANNING`: writing/updating `08_IMPLEMENTATION_BRIEF.md`
- `IMPLEMENTING`: executing the brief; records go to `09_CODING_HANDOFF.md`
- `SELF_REVIEW`: writing `10_REVIEW_REPORT.md`; Required Fixes send the task back to `IMPLEMENTING`
- `AWAITING_GIT_APPROVAL`: review passed, commit message proposed, waiting for user approval
- `DONE`: finalized (or docs-only task completed without commit need)
- `USER_DIRECTED`: no active workflow task; user decides the next move

## Standing Approvals

None. Every git commit requires explicit user approval in the current session.

## Completion Status

Engine feature-complete (947 tests green); single-agent workflow active; batch pipeline committed. Next phase (Strategy Research Validation) planned and awaiting user go-ahead: CR-0002 + first-slice brief `QRE-BATCH-PERF-SLIM-001` are drafted in `docs/agent/`.

## Next-Week Backlog（2026-10-05 用户定稿，本周不动代码）

用户原话：下周 token 恢复后推进，本周不做任何具体任务。优先级即以下顺序。

### A. 自然语言编译入口加固与进化（下周主线）

1. **NL 输入前置校验**（防随意输入）
   - 第一层零成本规则：长度下限、必须含入场语义（买入/入场/金叉/突破等）+ 出场语义（卖出/止盈/止损/离场/死叉等）、乱码/纯数字直拒
   - 第二层轻量裁判：**首选 Jev 决策模型**（TypeSafe AI，只返回类别+置信度不生成文字；用户 2026-10-05 提议并确认方向）——低成本低延迟、输出天然结构化；置信度 <0.7 的边界输入不硬拒，弹窗提示缺失项并允许用户选择继续编译
   - Jev 动手前三项验证：①接入方式与中文交易策略文本实测效能 ②隐私口径（策略文本发第三方，需知情说明）③阈值用真实输入样本校准，勿信厂商宣传；Jev 不可用时降级 规则层+便宜 LLM，不做单点
   - 拒绝弹窗给具体缺失原因 + 合法示例
2. **生成策略按钮服务端限频**（防恶意刷 token）
   - 按 IP（游客）/账号（会员）记每日编译次数，建议初始值：游客 5 次/日、会员 20 次/日（管理台可调）
   - 超限 429；前端按钮 pending 期间禁用只是体验层，后端配额才是防线
   - 复用现有每日回测配额的同一套计数机制
3. **编译缓存 + 一致性 + 语料进化**
   - 规范化文本（空白/标点归一）哈希 → 编译缓存，命中即返回同一份 YAML（字面一致、零 token）
   - 编译时 temperature=0 + 锁定模型版本；YAML 落库前规范化（键序/空白统一）
   - 缓存表带命中计数 → 高频策略统计 → 管理台热门策略榜
   - 同 YAML + 同参数 + 数据未更新 的回测结果可缓存复用（二期，先编译缓存）
   - NL→YAML 编译对（含用户修改终版、失败案例）入库 = 策略语料库；短期做 few-shot 示例注入提升复杂策略编译成功率；长期（几千条后）评估微调小模型替代大模型
   - 诚实口径：相同 YAML 在不同时点跑结果会因数据更新而不同，展示层须区分「编译一致」与「结果随数据变化」

### B. 分时（分钟级）回测立项 —— ⏸️ 已挂起（2026-10-11 用户指示）

**挂起原因**：等用户获取到可靠的分钟级数据源后再重启。小样本试点已完成（CR-2026-10-10_minute_data_pilot.md，tests/data_test 40 文件验证 B+ 级、因子引擎零改动可用、回测引擎 gap list G1-G7 与工作量分级），重启时直接读该 CR 文档续接，不要重跑试点。

试点结论速记：数据源是第一前置（现有样本止于 2021-06、B 型缺 amount、复权锚点陈旧）；数据到位后仍需 1~2 天工程出「研究级」单标的分钟回测（G1 订单时间戳保真 + 数据接入层 bar_time + 清洗管线固化），「可信级」（T+1/日界/涨跌停拦截/年化口径）再 1~2 周；全市场分钟回测（G6 向量化重写）不做。tick 级数据已判定不需要（波段策略分钟粒度足够，tick 只对打板/微观结构有意义）。stk_mins 权限未实测（重启时第一件事）。

重启后的原路径（顺序不可跳）：
1. 分钟表结构设计与入库（分钟线体量 ≈ 日线 240 倍，存储方案先评审）
2. 分钟级因子预计算管线（少量因子起步）
3. 引擎日内模式原型：日内进出场、T+1 规则分钟级口径
4. 信号监控从「收盘后批量」向「盘中实时」演进（远期，依赖分时）
- 架构级事项，单独立项，不与 NL 优化混迭代

### 既有挂起项（不变）

深度性能优化（用户指示放最后）、信号监控板块二级选择 UI、重播三处验证边界、付费体系层级/定价（用户暂缓）、结果页操作卡 UI 精修（用户说下周做）、小程序/APP 远景。

### 2026-10-12 公网两项修复（FRM 数据链路 + 板块榜单排序）

- **FRM 风险模块上公网**：根因是 worker 端 engine 收尾钩子生成的 `risk_report.json` 写在 run 目录根部，从未登记进 `record["artifacts"]`，`collect_result_files` 不上传 → ECS `output_dir/risk_report.json` 不存在 → job 页 FRM 模块（UI 早已就位）恒 `has_report=false` 隐藏。修复：`worker/runner.py` 在 `_persist_artifacts` 后把 run 目录的 `risk_report.json` 登记进 artifacts，随 files 通道上传到云端 job 目录根。仅对新 run 生效；历史 job 如需回填可单独做。
- **板块/标签榜单排序**：saas `job.html` 的 `renderTagRank` 原来写死 total_pnl 降序；改为 TAG_COLS + tagSort 状态，列头点击切换排序（板块名/总净盈亏/交易笔数/平均每笔/胜率），null 恒排末位，行点击下钻个股不变。下钻个股表本来就有排序。
- **权限坑补记**（20 号文档踩坑节待补）：方案A 表重建 RENAME 后 PostgreSQL 表级 GRANT 不随迁，`qre_worker_ro` 失去 stock_daily SELECT 导致 job 56 冒烟失败；已重新 GRANT。今后任何表重建必须随迁授权。
- **已知缺口**：alpha191 重算日志告警 `reference.index_daily` 缺 000300.SH 基准 → alpha149/181/182 输出全 NaN；验收后需补指数行情并重算这三因子。
- 8081 lab 与公网的 FRM 均只存在于策略回测（run）层面；个股级 FRM 两侧都没有，属新开发项。

### 2026-10-12 个股 FRM + 个股详情按需生成（QRE-SAAS-SYMBOL-ONDEMAND）

- **个股级 FRM**：`build_lab_symbol_detail` 末尾嵌入 `risk` 节——基于个股区间日收盘价收益（DatetimeIndex，stress 节需要）调 `risk.report.build_risk_report`，轻量配置（var_backtest/bootstrap 关、stress 开）；批量与按需产物都带。前端 symbol.html 新增 FRM 卡片块（VaR/ES 95/99 历史法、EWMA 年化波动率、波动率状态、夏普、最好/最差单日、压力测试最差情景）。
- **按需生成链路**：ECS `POST /api/results/<id>/symbols/<ts>/generate`（幂等：产物在→ready；同父job+股票有未完结任务→复用；否则建 kind=symbol_detail / weight_class=light / priority=10 的任务，params 带 parent_job_id+run_id+ts_code）→ worker `runner._execute_symbol_detail` 从本地 RUNS_DIR/<run_id> 读 status.json，复用 build_lab_symbol_detail 生成 gzip 写回 run 目录 _symbol_details/，走既有 meta/files 通道回传 → ECS api_result_files 完成分支把 symbol_detail 产物复制到父 job 目录 → 前端轮询 `gen-status` 到 ready 后重载。产物缺失时 404 改返回 can_generate=true + 生成按钮（替换原误导性"无交易"文案）。
- **口径备忘**：历史 job 的旧详情文件无 risk 节（前端整块隐藏，不报错）；该股真实无交易时 worker 抛错、gen-status 返回 failed 并允许重试文案。

### 2026-10-12 NaN 序列化修复（symbol_detail 卡"加载中"根因）

risk 节含 NaN（如 GARCH 拟合失败/零方差 sharpe），`json.dumps` 默认把 NaN 写成裸 token = 非法 JSON → 浏览器 `resp.json()` 抛 SyntaxError，load() 中断，页面停在"详情已生成，加载中…"。修复：`worker/runner.py` 新增 `_json_sanitize`（递归 NaN/Inf→None，含 numpy 浮点），批量与按需两条 gzip 路径都应用。已用 node 严格 JSON.parse 验证。**教训：任何产出给前端 fetch 的 JSON 都必须过 _json_sanitize。**
