# Task Handoff

## Task ID

QRE-SAAS-EXPOSURE-METRICS (区间信息卡新增持仓暴露度/持仓期年化收益两张联动卡)

## Current Status

DONE (implementation; full test suite green (2212 passed + 4 skipped); 仅本地 staging 验证、未部署 ECS；awaiting user-approved git finalization)

## Task Note

- 范围：saas/templates 的 job.html、symbol.html、base.html；lab 侧零改动。
- 数据口径：持仓暴露度 = 有持仓交易日数 ÷ 区间交易日数。数据源用结果已有
  round trips（job 级 chart_data.trades.points entry/exit 日期；symbol 级
  d.trades 全量），每笔 [entry,exit] 展开到交易日轴成逐日持仓布尔掩码，
  同日多笔重叠按 1 天去重；产物无逐日仓位序列，此为最准口径。
  持仓期年化 = (1+区间策略收益)^(252/持仓天数)−1（252=年交易日数）。
  区间无持仓 → 两卡均显示「—」；口径写 title 悬停提示；job 级 >500 笔
  sampled 时提示「按前 500 笔估算」。
- 联动：掩码在 renderMain/renderEquity 构建一次，updateRangeStrip（rAF 节流）
  切片求和，随滑块重算，与既有区间卡同链路。
- 样式：base.html #range-strip 由 repeat(5,1fr) 改
  repeat(auto-fit,minmax(130px,1fr)) 按卡数自适应（≤960px 仍降 2 列），
  卡片沿用淡紫底 metric-card 族（QRE-SAAS-DETAIL-CARD-UI）。
- 测试：零新增零修改；全量 2212 passed + 4 skipped 零回归。
- 验证：staging 8097 job 26，Playwright 宽+窄屏截图
  /tmp/qre-shots/expo-{job,symbol}-{wide,narrow}.png；探针实测 7 卡、缩放联动
  （80.00%/1.33% → 89.47%/4.41%）、无持仓区间「—」、数值抽查
  1.0059^(252/112)−1≈1.33% 正确、零 JS 报错。
- 12 号文档变更记录已登记（QRE-SAAS-EXPOSURE-METRICS）。未 commit、未部署。

---

## Archive: QRE-SAAS-DETAIL-CARD-UI (公网回测详情页/个股详情页卡片 UI 四项验收修改)

## Current Status

DONE (implementation; full test suite green (2212 passed + 4 skipped); 仅本地 staging 验证、未部署 ECS；awaiting user-approved git finalization)

## Task Note

- 范围：只改 SaaS 侧 src/quant_research_engine/gui/saas/templates/
  （job.html、base.html），8081 lab 侧零改动。
- ① 区间信息卡末尾留白：根因是 lab-theme.css 把 .metric-strip 纠偏成
  repeat(6,1fr) 六列网格，五卡只占 5/6。base.html 加
  `#range-strip{grid-template-columns:repeat(5,1fr)}` 整行均分；≤960px 降 2 列。
- ② job.html 模块顺序对齐 12 号文档 §8：box-fees（交易磨损）+ box-risk（FRM）
  DOM 移到 box-main（收益曲线）之后、box-tags（归因）之前。
- ③ symbol.html 顶部 7 简介卡：`#sum-strip` 改
  `repeat(auto-fit,minmax(200px,1fr))` + padding 10px 14px + 数值 15px
  （对齐 §1.3 个股页口径），宽屏 5+2 舒展布局、宽高比约 3.4:1，窄屏自动降列。
- ④ 总结性卡片淡紫底：#metric-strip/#sum-strip/#range-strip 的 .metric-card
  统一 var(--tint) 底 + var(--tint-deep) 边（既有 token，无新色相）。
  均用 ID 选择器压过 lab-theme.css 后加载的同族规则。
- 踩坑（已记入 12 号文档变更记录）：Jinja 模板内联 CSS 中 `{#id` 连写会被当
  Jinja 注释起始 → 500 TemplateSyntaxError，须写 `{ #id` 留空格。
- 测试：零新增零修改（既有模板断言不含模块顺序，全绿）；全量
  2212 passed + 4 skipped 零回归。
- 验证：本地 staging（8097 + aguhuice_local + job 26；为截图把本地 run
  20260927T040759327205 的 per-symbol 产物复制到 outputs/saas_uploads/job_26/
  _symbol_details/ 并手工补 equity 字段——纯本地 staging fixture，不入库）。
  Playwright 宽屏 1440 + 窄屏 390 截图 /tmp/qre-shots/cardui-{job,symbol}-{wide,narrow}.png；
  DOM 探针：range-strip trailingGap=0、卡底 rgb(241,237,248)=--tint、模块顺序正确、
  零 JS 报错。
- 12 号文档变更记录已登记（QRE-SAAS-DETAIL-CARD-UI）。未 commit、未部署。

---

## Archive: QRE-SAAS-SYMBOL-UX-SHARED-FIX (per-symbol 产物回传 shared 模式数据缺陷修复)

## Current Status

DONE (implementation; deployed to ECS via scp 临时部署（最终 git pull 对齐由用户做）; full test suite green (2212 passed + 4 skipped); awaiting user-approved git finalization)

## Task Note

- 根因：shared（共享资金）模式引擎不产出 per-symbol 目录（`<output_dir>/<ts_code>/`
  仅 batch 有），build_lab_symbol_detail 的 equity/orders/failed_orders 全 None；
  此前验证的 job 19 恰为 batch 模式所以漏测。job 21（真实用户 shared 单票）线上
  收益曲线/买卖点缺失即此因。job 20 无产物属正常（smoke 0 笔交易）。
- 修法（worker/runner.py，SaaS 链路专属，lab 版零改动）：新
  `_enrich_shared_symbol_detail`——orders/failed_orders 从任务级 CSV 按 symbol
  过滤；wear 聚合块从 round_trips 真实费用列算出；equity 仅单票 shared run 取
  任务级 equity_curve.csv（口径正确），多股保持 None 不编数；回填
  summary.total_ret_pct。symbol.html：renderWear 优先消费 d.wear；round_trips
  口径交易明细补「费用」列。
- 存量修复：job 21 用本地 run 目录重跑 builder 生成修正 gz（10.9KB，equity
  480/kline 480/orders 19）scp 覆盖 ECS uploads/job_21/_symbol_details/。
- 验证：公网 demo01 新 shared 单票 job 23 全链路（裸代码 603970 → 新 worker →
  回传）API 与页面全模块渲染，截图 /tmp/qre-shots/pub-fix-symbol23.png 零 JS 报错。
- 部署：scp symbol.html + restart qre-saas；runner.py 本地 restart
  qre-saas-worker。临时部署，最终 git pull 对齐由用户做。
- 测试：tests/test_saas_symbol_ux.py +5；全量 2212 passed + 4 skipped 零回归。
- 未 commit。

---

## Archive: QRE-AUTH-MEMBERSHIP (Authing 身份层登录接入，A2-A6；18 号设计文档)

## Current Status

DONE (implementation; full test suite green (2207 passed + 4 skipped); 仅本地+staging 验证、代码未部署 ECS；awaiting user-approved git finalization + Authing 控制台回调白名单确认)

## Task Note

- 实施流程与设计文档 §6 的 Guard 方案不同：OIDC 授权码 + Authing 托管登录页跳转
  （与控制台已配置的回调 URL 匹配，零前端 SDK）。18 号文档已注记。
- A2：deploy/saas/cloud_schema.sql 幂等追加 users.authing_id（部分唯一索引）/
  avatar_url/member_since/member_expire_at；aguhuice_local 已 apply。
  **ECS 部署前须先 psql apply cloud_schema.sql**。
- A3：新模块 src/quant_research_engine/gui/saas/authing.py（换票/JWKS 缓存/验签，
  requests+pyjwt 惰性导入）；app.py 新增 GET /saas/login/authing（302+state）、
  GET /saas/login/callback（验签→按 sub 建档/关联→本地 session→
  login_callback.html 落 localStorage 跳工作台）、POST /api/saas/auth/authing
  （JSON 版）、POST /api/saas/auth/bind（绑定旧邮箱账号，迁移 authing_id）。
- 依赖：pyproject 加 pyjwt[crypto]>=2.8 + requests>=2.31（uv.lock 已更新）；
  ECS 精简 venv 已 pip install 完成。
- A4：login.html——Authing 主按钮 + 邮箱密码/绑定旧账号两个 details 折叠区；
  已登录不再自动跳工作台（保证绑定入口可达）。新模板 login_callback.html。
- A5：tests/test_saas_authing.py +22（本地 RSA mock JWKS 正反例/建档幂等/绑定四态）；
  全量 2207 passed + 4 skipped 零回归。
- A6：AUTHING_* 四键已写 ECS /etc/qre-saas.env 与本地 .env.saas-staging（0600）。
  代码未部署：等 commit 后 ECS git pull + apply schema + restart qre-saas。
- staging 实测（8091+aguhuice_local+真配置）：跳转 Authing 托管页链路通；
  **⚠️ Authing 报 redirect_uri_mismatch**——需用户在控制台「应用配置→登录回调 URL」
  确认白名单含 https://www.aguhuice.com/saas/login/callback。真实短信/扫码留用户实测。
- 截图：/tmp/qre-shots/auth-login-page.png / auth-login-expanded.png /
  auth-authing-hosted.png（mismatch 错误页）。

---

## Archive: QRE-SAAS-FEEDBACK-FACTOR-REQ (内测意见反馈页 + 申请新因子页 + 缺因子拦截跳转 + 全站侧边栏)

## Current Status

DONE (implementation; full test suite green (2185 passed + 4 skipped); 仅本地+staging 验证、未部署 ECS；awaiting user-approved git finalization)

## Task Note

- 侧边栏：此前 SaaS 页面无侧边栏（仅顶栏）。base.html 新增统一 `.sidenav`
  组件（「意见反馈」/saas/feedback、「申请新因子」/saas/factor-request 两入口，
  所有 extends base.html 的页面自动获得），样式用既有 tokens（--tint/--accent），
  ≤960px 降级为顶部横排；当前页高亮由 base.html 公共 JS 按路径标记。
- 反馈（需求 1）：新表 `feedback(id,user_id,content,page,contact,created_at)`。
  **仅登录用户可提交**（游客 401 并引导登录；决策记录见 06 日志）；
  content 必填 ≤2000 字，page/contact 可选；单用户每日 20 条上限（429）。
  端点：POST/GET /api/saas/feedback（本人列表）；管理台只读
  GET /api/saas/console/feedback + console.html 新「反馈」tab。
- 申请新因子（需求 2）：独立页 /saas/factor-request（因子名称* / 计算公式 /
  用途 / 关联策略），复用既有 POST /api/saas/factor-requests（幂等迁移
  factor_requests 补 formula/purpose 两列，旧载荷兼容）；页内含「我的申请」
  列表（状态徽章）。支持 ?factors=a,b&strategy=x 预填（缺因子弹层跳转来源）。
- 缺因子拦截（需求 3）：①NL 入口——编译返回 missing_factors 弹层标题改为
  「当前数据库中不含此因子」，新增「去申请新因子 →」跳转按钮（预填因子+策略名），
  保留原「提交因子需求」快捷提交。②向导/YAML 兜底——startRun 校验段新增
  unknownYamlFactors()：解析 YAML factor_fields 别名，与已加载因子目录比对，
  未知则流水线第①步失败 + 同弹层（目录未加载时跳过，NL 路径服务端已校验）。
- 部署注意：ECS 需先 apply deploy/saas/cloud_schema.sql（幂等，已验证对
  aguhuice_local 重跑安全），再 rsync gui/saas/ 与重启 qre-saas。未 commit。
- 验证：新 tests/test_saas_feedback.py +21（反馈 CRUD/权限三态/日上限/隔离、
  factor 扩展字段回透与审核兼容、新页面元素、全页面侧边栏断言、禁链扫描、
  弹层跳转与兜底校验断言）；全量 pytest 2185 passed + 4 skipped 零回归。
  Playwright（本地 8095 staging + aguhuice_local）截图 13 张存
  /tmp/qre-shots/saas-*.png：侧边栏/反馈提交/申请预填提交/console 反馈 tab/
  缺因子弹层跳转落地/向导兜底拦截，零 JS 报错。

---

## Archive: QRE-SAAS-LARGE-UNIVERSE-GUARD (公网 SaaS 大范围板块/全市场提交耗时护栏)

## Current Status

DONE (implementation; full test suite green; 仅本地+staging 验证、未部署 ECS；awaiting user-approved git finalization)

## Task Note

- 背景：公网新建策略页选大板块/概念或全部 A 股（5531 只）提交全量回测耗时
  分钟级起，lab 版早有护栏，SaaS 侧缺失。
- 阈值口径（与 lab 版一致）：universe.py `LARGE_UNIVERSE_THRESHOLD=3000`；
  全部 A 股恒提示；板块/概念成员数 >3000 提示；指定代码/随机 N（≤2000）不触发。
- 计数来源：板块成员数用 /api/saas/universes 既有 `items[].count`；全部 A 股
  补新元数据字段 `all_a_count`（universe.py 新 `all_a_count()` =
  reference.stock_basic 行数）；`scripts/sync_saas_metadata.py` 生成逻辑更新，
  deploy/saas/metadata.json 已重生成；/api/saas/universes 双路径透出，缺失
  降级 None。
- 前端 saas/templates/new.html：流水线第③步提交 full job 前弹
  `#big-univ-modal`（12 号规范 .modal-mask/.modal 组件，非原生 confirm），
  文案含预计股票数与「几分钟到十几分钟」；确认才提交，取消收起流水线。
- lab 侧零改动。测试 +3（test_gui_saas.py metadata 透出+降级、
  test_gui_saas_pages.py 弹层断言、test_gui_lab.py all_a_count fake engine）。
  全量 pytest 零回归。未 commit；未部署 ECS（metadata.json 需随部署 scp，
  见 sync_saas_metadata.py docstring 命令）。

---

## Archive: QRE-SAAS-SYMBOL-UX (股票代码规范化/显示脱敏 + 超额收益修复 + per-symbol 产物回传打通公网个股详情 + 板块弹层修复)

## Current Status

DONE (implementation; deployed to ECS via rsync 临时部署（最终 git pull 对齐由用户做）; full test suite green; awaiting user-approved git finalization)

## Task Note

- A 代码规范化：`gui/saas/symbol_norm.py`（新，纯函数：normalize_ts_code /
  normalize_ts_codes / strip_ts_suffix / resolve_ts_code；60/68→SH、00/30→SZ、
  4/8/920→BJ；非法代码 ValueError 中文友好报错）。POST /api/saas/jobs 在游客校验
  之前规范化 params.codes 并落库（内部存储/API 保持带后缀原样）。
  显示脱敏：base.html 公共 `dispCode()` 剥后缀；symbols.html / job.html 下钻 /
  symbol.html 标题与 URL 一律无后缀（URL /saas/jobs/<id>/symbols/000001，API 端
  resolve_ts_code 先按本任务实际交易个股匹配、再按号段推断，非法 400）。
  8081 lab 侧零改动。
- B 超额收益「-」：根因是引擎 shared_cash 模式 strategy_performance 恒写
  buy_hold_return=None（8081 同数据同样「—」，非公网独缺）。修法在 worker
  runner._fill_excess_return：excess 为空时按实际交易个股区间等权买入持有补齐
  （附 buy_hold_note 口径说明），DB 不可用保持 None。存量 8 条 completed job
  （1/2/3/7/8/15/16/17）已用本地行情库算好经 psql 回填 ECS results.chart_data。
- C per-symbol 产物回传（ECS 无行情库的打通方案）：worker runner
  build_symbol_detail_files——回测后对实际交易个股逐个 build_lab_symbol_detail，
  剔除基准序列（任务级 chart_data 已有，ECS 按个股净值日期对齐注入）后 gzip 写
  `<output_dir>/_symbol_details/<ts_code>.json.gz`，登记 artifacts 随既有
  result/files 通道上传（15MB 上限，按 |总净盈亏| 降序截断；collect_result_files
  让 _symbol_details 优先进 20MB 清单）。ECS api_result_symbol_detail 优先读
  上传 gzip，缺失回退本地 build（staging 不变）。saas/templates/symbol.html 重写
  对齐 lab 版个股页模块（概述 7 卡 → 收益曲线+区间五卡 → 交易磨损 →
  日K+买卖点+因子副图 → 交易明细 → 下单记录 → 失败订单），旧任务无产物优雅降级。
- D 板块弹层：job.html 下钻表补齐 lab 版 10 列 + 列头排序（null 恒排末位）+
  截断提示；点击个股行跳个股回测详情（此前无响应）。
- 部署/验证：rsync 6 个 saas 文件到 ECS + restart qre-saas；本地 restart
  qre-saas-worker 生效 runner；公网 demo01 实测 job 19 全链路（提交裸代码
  000001/600519 → worker 回测 → 产物回传 → 页面全模块渲染，截图
  /tmp/qre-shots/pub-*.png，零 JS 报错）。
- **顺手修生产事故**：ECS PG workers 表（E1-E3 迁移所建）未授权 aguhuice，
  worker claim 全部 500（任务停摆）——已 GRANT 修复并加默认权限，心跳恢复。
- 测试：tests/test_saas_symbol_ux.py +31；test_gui_saas.py 一处断言更新
  （非法后缀 400 / 无交易合法代码 404）。全量 pytest 零回归。
- 未 commit。恢复命令见 16 号文档第 5 节运维速查。

---

## Archive: QRE-SAAS-ADMIN-TUNNEL (SaaS 管理台撤公网改 SSH 隧道访问 + PG 每日备份；方案 A，用户拍板)

## Current Status

DONE (implementation; deployed to ECS; full test suite green; awaiting user-approved git finalization)

## Task Note

- 2026-09-27 追加 QRE-SAAS-UI-ALIGN-FIX（用户验收发现公网与 lab 版 UI 差距，已部署）：
  顶栏对齐 lab 版（品牌 15px/700 深色、纯文本导航 14px 灰、无胶囊/激活底色、hover 主紫）；
  入口卡选中态补「标题+描述变主紫」（lab 版实测为 style.css .entry-tab.active 遗留蓝
  #1E40AF，SaaS 用 var(--accent) 等效）；回测区间修 `input{width:100%}` 撑破
  .date-input（加 .date-input{width:auto}），日历弹层与 lab 版一致。改动全部在
  saas/templates/base.html 覆盖块；禁链注意：CSS 注释里 "8081" 也撞
  TestNoAdminLinks，用「lab 版」代称。随本轮部署后公网「管理台」入口同步消失
  （注入 JS 删除生效），/saas/console 保持 404。Playwright 截图 /tmp/qre-shots/。
- nginx（仓库 deploy/landing/nginx-aguhuice.conf，已 scp 同步线上并 nginx -t / reload）：
  `location = /saas/console`、`= /api/saas/console`、`/api/saas/console/` 直接 return 404。
  实测：公网 /saas/console → 404、/api/saas/console/overview → 404、/saas/new → 200；
  ECS 本机 127.0.0.1:8090/saas/console → 200（隧道通路）。
- base.html 删除顶栏「管理台」注入 JS；tests/test_gui_saas_console.py 断言反转为不注入。
  坑：注释里写 "deploy/saas/admin-tunnel.sh" 含子串 "/admin" 会撞禁链断言，须改写措辞。
- 隧道：deploy/saas/admin-tunnel.sh（ssh -N -L 9090:127.0.0.1:8090 root@47.119.127.40），
  浏览器开 http://localhost:9090/saas/console，管理员账号正常登录。
- PG 备份：ECS root cron `17 3 * * * /srv/aguhuice/backups/pg-backup.sh`（pg_dump custom，
  保留 7 天）；本地 WSL cron `23 4 * * * .../deploy/saas/pull-ecs-backup.sh` scp 拉最新
  dump 到 ~/quant-workspace/backups/ecs-aguhuice/（留 7 份）。两端手动触发已验证
  （aguhuice-20260927-105046.dump，两端均 300,547B）。
- 全量 pytest 2130 passed + 4 skipped 零回归；check-progress-docs.sh 通过。
- 未 commit。恢复命令见 16 号文档第 5 节运维速查。

---

## Archive: QRE-SAAS-ADMIN-E1E3 (SaaS 后台管理：E1 总览 / E2 用户与因子审核 / E3 worker 运维)

## Current Status

DONE (implementation; full test suite green; awaiting user-approved git finalization)

## Task Note

按 15 号文档 E 阶段实现 SaaS 管理后台（本地开发，不部署）：

- schema（deploy/saas/cloud_schema.sql 幂等迁移）：users + role/status 两列；
  新 workers 表（claim/heartbeat 时 upsert，3 分钟阈值判在线）。
- 权限：users.role='admin' 判定；_require_admin 门禁（401/403）；禁用账号
  登录 403 + 既有 session 立即失效；/api/saas/me 返回 is_admin。
- 管理 API 前缀 /api/saas/console/*（不用 /admin——禁链纪律含注释，决策入
  06 日志）：overview / users（tier 调整、禁用恢复）/ factor-requests 审核
  （approve/reject+note）/ workers / jobs（失败查看、retry 回队、cancel）。
- 页面 /saas/console（console.html 五 tab，lab-theme 组件规范）；顶栏
  「管理台」入口仅 is_admin 时注入（base.html 公共 JS）。
- 测试管理员账号：先正常注册再 SQL 提升——
  `UPDATE users SET role='admin' WHERE email='<邮箱>'`；本地测试用例使用
  admin@example.com / boss@example.com（测试临时库，非真实账号）。
- 测试：tests/test_gui_saas_console.py +12；全量 2130 项零回归
  （test_gui_risk_report 一次瞬时失败复跑即绿，同 09-20 flake 记录）。
- 未 commit。E3 裁剪留后续：worker 指令下发、家里 PG 状态卡（需 worker 协议扩展）。

---

## Archive: QRE-UI-DESIGN-SYSTEM-DOC (UI 设计系统文档：8081 lab 冻结版蒸馏为自包含规范)

## Current Status

DONE (documentation only; awaiting user-approved git finalization)

## Task Note

重写 docs/agent/12_UI_STYLE_GUIDE.md（8.6KB→25.3KB）：设计 tokens
（色板/字体/圆角/阴影全量色值）、布局体系（页面骨架/栅格/36px 行内控件
等高硬规则）、组件库（按钮 7 变体/表单/折叠区/三入口卡+PCB/徽章/toast/
弹层/表格排序/日历/流水线/磨损条）、ECharts 图表约定（系列配色硬规则、
主图双 grid、treemap 三档显隐、K线买卖点）、动效规范（reduced-motion
硬规则）、降级语义、禁链纪律（含注释也扫）、SaaS 复刻约定。每条标注
源码 文件:行号。8081 lab 侧代码零改动。验证：check-progress-docs.sh 通过。
未 commit。

---

## Archive: QRE-WORKER-RUNNER (A3：worker 执行端闭环——取消传播/两步回传/产物清单/env 新名)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

runner.py +collect_result_files（sha256 清单、20MB 上限、幂等覆盖）；
daemon.py 取消传播（心跳见 cancel_requested → fail(canceled) + 丢弃结果，
引擎单体不可中途杀的取舍已注释）+ 两步回传（QRE_WORKER_UPLOAD_FILES
默认关）+ claim 长轮询；client.py +upload_files（multipart）/upload_fn 注入
/env 新名优先（QRE_SAAS_BASE_URL 等）；python -m quant_research_engine.worker
入口。服务端顺带修：fail canceled 终态、meta 对 completed 幂等。测试 +4，
worker+saas 55 passed。未 commit。下一步 A4：本地双进程真实端到端
（saas app + daemon 真引擎 smoke job 跑通）。

---

## Archive: QRE-JOB-API (A2：Flask 侧 job API 按 17 号协议改造——claim 长轮询/心跳迁移/两步 result/fail 分类/取消/幂等/惰性回收)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

按 docs/agent/17_JOB_PROTOCOL.md 改造 gui/saas/app.py 过渡版（不另起炉灶）。
schema 幂等迁移（jobs 加 8 列 + 列改名 + 状态枚举 done→completed，旧库升级
实测通过；坑：先 DROP 旧 CHECK 再 UPDATE）。端点：worker claim（长轮询
30s/空响应 200+null/SKIP LOCKED）/heartbeat（progress+message，首跳
leased→running，带 cancel_requested）/result/meta→files（upload_token+
sha256，SAAS_UPLOAD_DIR 落盘）/fail（error_class 分类）；用户
POST/GET /api/jobs、POST /api/jobs/<id>/cancel（queued 直消/执行中置标记/
终态 409）。惰性租约回收（无后台线程）+ 硬超时 expired。/api/saas/* 别名
兼容；worker/client.py 与 saas 模板同步。测试 test_gui_saas.py +11
（TestProtocolA2），全量见 05。未 commit。遗留：claim capabilities 过滤、
parent_job_id 派生 full、文件分块续传（见 05 条目）。

---

## Archive: QRE-BATCH-STREAMING-EMPTYCSV (流式批量回测空 CSV 崩溃修复：EmptyDataError 容忍)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

run 20260914T125635220084（5 年全市场）死于聚合阶段 "No columns to parse
from file"：无交易个股的空 DataFrame（无列）落盘为无表头空文件，磁盘代理
read_csv 读回抛错（非流式路径空 DataFrame 一直在内存所以从不触发）。
修复仅 streaming_batch.py 一处：`_DiskBackedSingleResult._read` 捕获
pd.errors.EmptyDataError 返回空 DataFrame（读侧容忍，字节兼容既有产物）。
测试 +1（空结果个股全链路 write_batch_result 不炸）。失败 run 产物不可信
（共享 output_dir 已被后续 run 部分覆盖且 run_manifest 缺失），建议重跑。
未 commit。前一任务 QRE-BATCH-STREAMING（见下档）。

---

## Archive: QRE-BATCH-STREAMING (批量回测内存峰值控制：流式分块，OOM 7.7G → 实测 299MB@500只×2年)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

OOM 根因（profiling 实锤）：装配器一次性加载全池 frame（500×2y 即 691MB RSS，
5000×5y 膨胀至 7.7G）。修复：新 `portfolio/streaming_batch.py` 流式分块
（QRE_BATCH_CHUNK_SIZE 默认 250；块内跑既有 BatchBacktestEngine → 逐股落盘
→ `_DiskBackedSingleResult` 磁盘懒加载代理 → 释放），gui/engine.py 与
apps/cli.py 的 batch 路径在 >250 只或全市场时走流式，小样本不变；产物格式
零变化（500×2y 产物逐位一致）。tests/test_streaming_batch.py +2，全量
2071+4 绿。未重启 qre-gui-lab（进行中的全市场 run 不动），改动下次 run 生效。
未 commit。前一任务 QRE-LAB-UI-LANDING（见下档）。

---

## Archive: QRE-LAB-UI-LANDING (设计稿 synthesis.html 视觉层与已批准结构调整原位落地 8081 lab 版)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

规范来源 docs/agent/12_UI_STYLE_GUIDE.md；性能依据 13_UI_PERF_NOTES.md。
8080 管理台零改动（diff 只含 lab_* 模板 / gui/lab_result.py / lab 测试 /
新增 lab-theme.css + lab-ui.js + lab_symbols.html）。

- 主题抽到 static/lab-theme.css（tokens/字体/动效/组件类，仅 lab 模板 link），
  交互组件抽到 static/lab-ui.js（PCB 排线 / 日历 / 流水线步骤态）。
- lab.html：三入口并列卡+PCB；预览栏（#strategy-yaml 迁至参数区后为唯一真相源，
  pv-params-line 参数合并行、复制按钮）；param-sname 公共策略 ID（applyNameToYaml
  提交时写入 name，用户手改后不再自动覆盖）；LabUI.attachCalendar 日历（最大可选
  = /api/admin/refresh state.last_data_date，禁未来函数）；唯一「运行回测」流水线
  ①/api/validate（先验 ID 合法字符）→②saveToSandbox+smoke+waitForCheck→③/api/run
  沿用原 payload 与 >3000 只护栏，后端零改动；各入口旧最终按钮（btn-save-smoke/
  wz-save-smoke/wz-fill-editor/btn-validate/btn-run）删除，startBacktest 保留未用。
  记录表加「股票数量」列（原有标的数更名）+ 状态徽章 + 删除改 #run-del-mask 二次
  确认弹层（/api/lab/runs/<id>/delete 不变）。
- lab_result.py：build_lab_chart_data 新增 fees_summary（round_trips.csv 费用列
  全量聚合；缺文件/缺列返回 None 前端整块隐藏）；新路由 /lab/runs/<run_id>/symbols。
  worker 复用该函数（SaaS job chart_data 随之带 fees_summary，纯增量键无回归）。
- lab_result.html：顺序 概述→收益曲线→box-fees 磨损→FRM→归因 treemap→big-link
  个股明细入口；dataZoom 区间卡 rAF 节流；配色换淡紫规范。
- lab_symbols.html（新）：A 层聚合成全量个股表，排序/搜索/完整代码回车直跳。
- lab_symbol.html：顺序 概述→收益曲线（区间卡五卡+滑块 rAF）→box-wear 磨损（该股
  orders/trades 聚合）→K线→交易明细→下单记录→失败订单；配色同步。
- 术语纪律：沙箱/晋升仍禁；「冒烟测试：单股票 × 短期区间」为用户本轮批准文案，
  test_gui_lab 去术语断言已放行「冒烟」一词。
- 测试：test_gui_lab.py / test_gui_lab_result.py 更新 + 3 新用例；lab 65 全绿；
  全量 pytest tests/ -q → 2067 passed + 4 skipped（基线 2065+4，净增 2）。
- 验证：sudo systemctl restart qre-gui-lab 后 /、/lab/runs/<id>(+symbols+symbol)、
  两个静态文件、chart-data 全 200；fees_summary 真值已对账。
- 未 commit。前一任务 QRE-WORKER-ARTIFACT-PERSIST（见 05_PROGRESS）。

## 遗留风险

- 浏览器观感未截图实测（无头环境）：PCB 排线/日历弹层/流水线动画建议人工开 8081 过一遍。
- 流水线第②步 smoke 用策略默认标的（saveToSandbox/smoke 语义），第③步才应用参数区
  区间/标的——与母板 SAAS-011 原流程语义一致，未改。
- 预览栏未做行号/语法高亮（设计稿有）；落地为纯 textarea + 参数合并行，后续可补。

---

<details><summary>历史交接存档</summary>

# Task Handoff

## Task ID

QRE-WORKER-ARTIFACT-PERSIST (缺陷修复：SaaS Worker 回测产物拷回持久存储，/tmp 沙箱丢失导致详情页全空)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

worker/runner.py：execute_job 在 run_backtest 返回后（成功/失败都执行）
调新 `_persist_artifacts`——/tmp 沙箱 output_dir 整体 copytree 到
RUNS_DIR/<run_id>/artifacts/（旧副本先清），record 的 artifacts map 绝对
路径与 output_dir 改写指向持久副本并重写 status.json；/tmp 原件保留。
非沙箱路径不受影响。测试 tests/test_worker.py +2（持久副本存在+路径
改写+删沙箱后 loader 可用+重跑先清后拷；fixture 补 RUNS_DIR 隔离）。
未 commit。前一任务 QRE-SAAS-012（标的范围富化，见下档）。

---

## Archive: QRE-SAAS-012 (8081 标的范围富化：申万行业/东财·同花顺概念/聚类池/通用行业 七组归类)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

新 `gui/universe.py`（只读：list_universes 七组 + universe_members 解析
codes）；lab.py 挂 8081 专属 /api/lab/universes[/members]（_cached TTL，
8080 不挂）；lab.html 标的范围原位改三选单选（全部 A 股/板块概念可搜索
下拉+成员数提示/自定义代码），提交前解析为 codes 传既有 /api/run，
引擎零改动；>3000 只或全市场 confirm 护栏。真库验收：七组数据齐全
（sw1 电子 618、ths CPO 98 等），members 解析正确。测试 +4（20 总），
全量 2063+4 绿。未 commit。遗留：用户 8081 验收；部署 ECS 时 universe
数据源在 Worker 侧（本地大库）直接可用，云端不落明细的设计不变。

---

## Archive: QRE-SAAS-011 (lab 页面原位减法：删「新增因子」tab + 一键回测流程后台化 + 导航清理)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户批评 QRE-SAAS-010 重做模板（「我说过在原页面的基础上进行更改」）；
纠偏：lab*.py 冻结解除，8081 lab 页面原位减法。改动：lab.html 删因子
tab（按钮/面板/TAB3 JS 全块）+ 缺因子改弹窗（POST /api/lab/factor-requests
JSONL 落 outputs/factor_requests.jsonl，TODO(M4) 迁云）+ 「存入沙箱+冒烟」
两按钮统一为「开始回测」（自动 smoke→轮询→通过自动 promote 全量回测，
失败显示人话）+ 可见文案去术语（沙箱/冒烟/晋升 → 我的策略/验证/发布）；
base.html nav 改 block（8080 默认不变），lab 三模板覆盖去 /admin 链接。
gui/lab.py 加 factor-requests 路由。saas/templates（SAAS-010）废弃保留
备查。8080 未动、引擎/worker/security 未动。验收：8081 restart 后首页
200、无禁词/无 admin 链接、/api/lab/runs 200、申请落盘实测。测试
test_gui_lab.py 更新 +1（17 总），lab 相关 107 passed，全量回归见 05。
遗留：用户 8081 验收新首页；ECS 部署；factor_requests 迁云。

---

## Archive: QRE-SAAS-010 (SaaS 前端以 lab 观感重做 + 流程后台化；SAAS-009 方向修正落实)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户 2026-09-07：SaaS 前端以验收过的 lab 页面为蓝本做减法移植
（SAAS-009：自研模板验收不通过）。模板全部重写（gui/saas/templates/，
lab*.py 只读未动）：base.html 换 lab 风 CSS 全套；new.html 两 tab +
策略代码预览（高级）折叠 + 单一「开始回测」（后台静默 smoke→通过自动
提交 full→跳结果页，零「沙箱/晋升/试算」字样，缺因子弹窗保留）；
dashboard 过滤内部 smoke job、无管理面入口；job.html 结果页对齐
lab_result.html（指标卡/meta chips/基准切换+滑块+回撤副图/归因 treemap
三 tab+排行表+下钻静态明细）。保留 SAAS-009 防刷新环修复（bypass 注入
模板，requireLogin 跳过）。CR-0004 追加用户分层构想（仅文档）；
03_ROADMAP 加 Milestone 11。测试 27 passed（+4：新断言 + 零术语词表），
全量 2058+4 绿。8081 lab 未动。未 commit。遗留：用户 8081 观感验收、
ECS 部署（M4）、个股详情页（后续）。

---

## Archive: QRE-SAAS-008 (8081 重定位为 SaaS staging：qre-gui-lab 切换为 SaaS 应用 + 本地 Worker 常驻)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户 2026-09-07 决策：8081 = SaaS staging（预发），ECS = 生产；流程约定
「改动 → 8081 验证 → 用户验收 → 部署 ECS」（已记入 11_AGENT_STATE）。
lab*.py 一行未动，8080 未碰。变更：`qre saas` CLI 子命令；saas app 加
SAAS_STUB_ECHO=1 开关（auth/code 响应带 dev_code，生产严禁）；8081 服务
qre-gui-lab（沿用服务名）ExecStart 切换为 qre saas，env 走
.env.saas-staging（0600，gitignore 已覆盖）；新系统服务 qre-saas-worker
（轮询 8081/5s/只读大库账号）已 enable --now。repo 侧新增
deploy/saas/qre-saas-staging.service 与 qre-saas-worker.service。
端到端已验证（dev_code 登录→smoke→worker done 65s，8080 无恙）。
测试 +2，全量 2054 passed + 4 skipped 零回归。未 commit。
遗留：ECS 部署（M4：OSS/备案/生产 env）；8080 因子审核界面（SAAS-007 后续）。
用户使用说明见 05_PROGRESS.md QRE-SAAS-008 条目与本文件下方。

### 使用说明（staging 日常）
- **免登录**（2026-09-07 用户决策，SAAS_AUTH_BYPASS=1）：直接打开
  http://<本机>:8081/saas/ 即可用；/saas/login 自动跳工作台。
  所有操作归属默认用户 staging@local。生产 ECS 保持验证码登录
  （bypass 严禁开启）。
- 任务进度：http://<本机>:8081/saas/ 自动刷新。
- 服务状态：systemctl status qre-gui-lab（SaaS 应用）/
  qre-saas-worker（Worker）；日志 journalctl -u qre-saas-worker -f。
- 改了代码要验收：sudo systemctl restart qre-gui-lab（worker 按需）。

---

## Archive: QRE-SAAS-007 (SaaS 因子治理：缺因子申请人工审核通道 + 页面链接清理)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户新规：用户对因子零增/改/读操作；缺因子引导换策略 + 可申请入库
（运营按热度人工审核离线计算）。判断：saas 无独立因子浏览入口（快速
向导的因子下拉=构建策略必要交互，保留）；四模板本就无 /admin·8080/
8081·factor-admin·factor-create 链接（已加参数化断言固化）。实现：
cloud_schema.sql +factor_requests 表（幂等）；POST/GET
/api/saas/factor-requests（24h 同集合去重 409、用户隔离）；new.html 缺
因子模态框（missing_factors 触发，「换个策略」/「提交因子需求」→
已提交）；dashboard.html 底部折叠「我的因子申请」状态列表。未 commit、
未动 8080/8081/lab*.py、未改 NL 编译器。测试 +10（API 4 + 禁链·元素 6），
test_gui_saas_pages.py 21 总。遗留：8080 管理台审核界面（后续任务）。
前一任务 QRE-SAAS-004（四功能前端 + 归因打通，见下档）。

---

## Archive: QRE-SAAS-004 (CR-0004 M1：SaaS 四功能前端——登录/工作台/新建回测/结果页)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

全部在 `gui/saas/` 内：templates/{base,login,dashboard,new,job}.html +
saas/app.py 挂 4 个页面路由与 2 个 API。vanilla JS 无框架（同 admin.html
风格），echarts 复用 gui/static/echarts.min.js（saas app static_folder 指向
共享目录，不双份）。页面：/saas/login（验证码两步、token localStorage、
登录即注册）；/saas/（任务列表+状态徽章+每 5s 自刷+失败原因）；
/saas/new（NL tab：示例 chips→POST /api/saas/nl/compile→YAML 可编辑；
向导 tab：/api/saas/factors 二级下拉+出入场阈值+高级选项折叠；强制先
smoke 试算通过才允许提交 full）；/saas/jobs/<id>（指标卡+净值 vs 基准+
回撤图，数据全来自 result.chart_data，5s 轮询，下载按钮 artifacts 空隐藏
TODO(M4)）。API：/api/saas/nl/compile 直接调既有 compile_nl（含
factor_correction 纠错层，LLM key 服务端 env）；/api/saas/factors 直接调
factor_wizard.build_factor_groups；GET /api/saas/jobs/<id> 收紧为登录+属主
校验（他人 404）；列表加 data_until。未 commit、未动 lab*.py/8080。
测试 tests/test_gui_saas_pages.py +11（页面 200/关键元素/echarts 静态/
NL 与因子路由 401·400·200·503/groups 结构）；既有 saas/worker 测试补
鉴权头。全量回归见 05。遗留：下载按钮接 OSS（M4）、真实浏览器观感
走查。注：归因热力已同日补齐（见 05 QRE-SAAS-004 补条目）——runner
chart_data 补 tag_analysis（trim：板块聚合全量+个股 TOP/BOTTOM 各 50），
job.html 加行业 treemap + 板块下钻 + 个股贡献榜。
另：同日完成 QRE-SAAS-M4-DRYRUN 真机闭环演练（详见 05 顶部条目）——
SaaS app + Worker 本地同机全链路真实跑通（真实 DeepSeek NL 编译 +
smoke/full 两 job done + 归因数据齐全），修复 yaml_guard experiment 键
白名单漏项（NL 产物含 market_profile/frequency 会被误杀）+ StubSender
SAAS_STUB_LOG 落盘开关。结论：达到「备案下来即可部署」的代码状态。

---

## Archive: QRE-SAAS-005 (CR-0004 M2：NL 生成代码沙箱加固——表达式 AST 白名单 + Docker 隔离执行器)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

威胁模型：NL 写策略=声明式 YAML 无代码执行，但信号表达式求值器
（evaluation/signals.py）允许任意 getattr/方法调用（注入面）；NL 写因子
生成 Python 源码在 indicators_tushare subprocess 执行（唯一真执行点，
已有 AST 白名单但无执行隔离）。实现（全新文件，引擎零改动）：
①`security/yaml_guard.py`——validate_expression AST 白名单
（禁裸调用/裸属性/下划线标识符/字符串常量/下标等，方法链白名单 30 个）
+ validate_strategy_yaml 严格 schema（节/键白名单、类型、因子引用标识符
+schema 白名单防 SQL 注入）；接线 worker runner.execute_job 执行前强制，
不过 → job failed。②`worker/sandbox.py`——run_sandboxed（禁网/512m/
1cpu/100 pids/只读根/nobody/120s 强杀按名 kill/输出限 1MB），docker 前缀
可注入（SANDBOX_DOCKER_SUDO）。③deploy/saas/sandbox.Dockerfile
（python:3.12-slim+pandas/numpy/pandas_ta，本次未实机构建，测试用
python:3.12-slim 直跑）。未 commit、未动 lab*.py/8080、未碰
factor_correction.py。测试 tests/test_security_sandbox.py 34 passed
（schema 正反例 + 真容器禁网/内存/超时/只读 6 条）。遗留：因子冒烟
沙箱化接入 factor-create 流程（禁网下数据须预导出挂载，M4 时定）、
沙箱镜像实机构建、SaaS 前端入口挂 yaml_guard（8081 裁剪切片）。

---

## Archive: QRE-SAAS-M3 (CR-0004 M3：Worker 客户端本体——出站轮询云端任务、本地跑回测、结果回传)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

新 `src/quant_research_engine/worker/` 包（client.py / runner.py /
daemon.py）+ `apps/cli.py` 新增 `qre worker` 子命令（纯追加，与
gui/barometer 同模式）+ `deploy/saas/qre-worker.service`（user 级模板，
注释含安装命令，未安装）。lab*.py / 8080 零改动，未 commit、未重启服务。
①client.py CloudClient：stdlib urllib（venv 无 requests），超时 30s +
指数退避重试（仅传输错误/5xx，最多 3 次，4xx 抛 CloudError）；env
SAAS_CLOUD_URL/SAAS_WORKER_TOKEN/SAAS_WORKER_ID；request_fn 注入点供测试
直连 saas app test_client。②runner.py execute_job 复用既有链路不 fork：
`gui.engine.run_backtest`（同 8081 批量回测入口）；smoke=既有 precheck
（20 股+180 天），full=全量；summary=extract_run_summary、
chart_data=lab_result.build_lab_chart_data；artifacts=[] TODO(M4) OSS；
data_until=净值曲线末日。③daemon.py：轮询 lease（默认 15s）→ 执行 +
心跳线程（默认 60s）→ done/failed 回传；异常全兜底不死；SIGTERM 等手头
任务完成再退（TimeoutStopSec=900 兜底）。本地大库：引擎数据层全 SELECT
只读（已核查 data/postgres/assembler/portfolio/risk_report，写点均为本地
文件），QRE_MARKET_DB_URL 注入 qre_worker_ro 只读账号即可，零改造。
测试 tests/test_worker.py 10 passed：端到端 done 闭环（mock 引擎层 +
真实 lab_result 组装）、daemon 单轮/空轮、失败回队→耗尽、心跳线程、
重试/放弃/4xx 不重试/错 token、CLI 注册。tests/test_gui_*.py+test_cli.py
909 passed 零回归。遗留：OSS 产物上传（M4）、沙箱加固（SAAS-005）、
真实云端联调（M4 部署后）、systemd 实机安装。

---

## Archive: QRE-SAAS-006 (CR-0004 M2：SaaS 登录鉴权——验证码登录 + Bearer session + 限流/配额，替换 X-User-Id 占位)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

全部改动限于 `gui/saas/app.py`、`deploy/saas/cloud_schema.sql`、
`tests/test_gui_saas.py`；lab*.py / 8080 零改动，未 commit、未重启服务。
①发送层可插拔（SAAS_AUTH_CHANNEL）：email=默认（smtplib STARTTLS 10s
超时，SAAS_SMTP_* 配置）；sms=占位抛「短信通道未开通」；stub=测试通道
记录到 app.extensions['sent_codes']。②新路由：POST /api/saas/auth/code
（6 位码、5 分钟、sha256(code:target:salt) 落 sms_codes、发送失败 502、
不暴露注册态；限流：同 target 60s、同 IP 10 次/小时，内存计数重启清零）、
POST /api/saas/auth/login（compare_digest 校验最新未用未过期码→一次性
used→无用户自动注册 email/phone 按 @ 判定→sessions 表 30 天 token）、
GET /api/saas/me。③jobs 用户侧路由切 Bearer token；X-User-Id 保留为
SAAS_DEV_AUTH=1 dev 后门（默认关）。④配额：当日任务数（含 smoke）>=
quota_daily → 429。⑤schema 幂等迁移：users+email（部分唯一索引）/
phone 可空、sms_codes+channel（phone 列实存 target，注释说明）、
新增 sessions 表；已实测连 apply 两次幂等。worker token 鉴权不动。
测试 22 passed（+11：全流程/错码/过期/复用/限流两档/502/无 token/
dev 后门开关/配额）；tests/test_gui_*.py 子集 584 passed 零回归。
遗留：图形验证码（TODO 注释，内测省略）、Worker 客户端（M3）、
8081 前端四功能 UI、生产 SAAS_AUTH_SALT/SAAS_SMTP_* 配置。

---

## Archive: QRE-SAAS-001/002 (CR-0004 8081 SaaS MVP M1 切片：云小库 schema + 云侧任务队列协议 + QRE-SAAS-004 骨架 app)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

全部为新文件，既有 8080/8081 路由与冻结 lab*.py 零改动、未 git commit、
未重启任何服务、未碰沙箱。①QRE-SAAS-001：`deploy/saas/cloud_schema.sql`
五表（users/sms_codes/strategies/jobs/results）幂等可 apply（前置已验证）。
②QRE-SAAS-002 + SAAS-004 骨架：新 `src/quant_research_engine/gui/saas/`
（__init__.py + app.py），`create_saas_app()` 独立 Flask app，路由全挂
`/api/saas/`：用户侧 POST /api/saas/jobs（yaml+params+kind=smoke|full，
X-User-Id 占位鉴权、用户不存在自动建行 phone=pending_<id>，登录为
QRE-SAAS-006）、GET /api/saas/jobs[/<id>]（状态/error/done 时 result
摘要，列表 50 倒序）；Worker 侧 POST /api/saas/worker/jobs/lease
（X-Worker-Token 校验 env SAAS_WORKER_TOKEN，未配置 503；事务内
SELECT ... FOR UPDATE SKIP LOCKED 取最旧 queued 或 lease 过期且
attempts<max_attempts 重排 → attempts+1/leased/15min 租约/leased_by，
返回含 strategy yaml+params）、.../heartbeat（顺延 15min 校验 leased_by）、
.../result（done 写 results ON CONFLICT(job_id) 幂等 + job done；
failed 则 attempts 耗尽置 failed 否则清租回 queued）。DB 走 env
SAAS_DB_URL，SQLAlchemy text() 全参数化，驱动复用项目既有 psycopg3
（postgresql+psycopg:///）。测试 tests/test_gui_saas.py +11（真实本地
PG 临时库：psql 以 van 经 unix socket 建/销库 + apply schema + 每用例
TRUNCATE）：全生命周期、lease 过期重排、attempts 耗尽置 failed、token
错 401、token 未配置 503、用户隔离、他人心跳/回传 409。新测试 11
passed；全量 `pytest tests/ --ignore=tests/test_gui_saas.py` →
1963 passed + 4 skipped 零回归。遗留：Worker 客户端本体（M3）、登录
鉴权（QRE-SAAS-006）、8081 前端四功能裁剪 UI。

---

## Archive: QRE-NL-FACTOR-AUTOCORRECT-001 (NL 编译链路因子名自动纠错层：存在性校验 + 保守自动替换 + 候选提示 + prompt 注入真实目录)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

痛点（05 已记录）：DeepSeek 编造库中不存在的因子列名（rsi14/MACD 等），
NL 编译产出 YAML 因因子缺失而失败，用户只见红色报错。本任务在
引擎/编译器侧（8080/8081 共用，8081 gui/lab*.py 页面仍冻结）落地：
①新 `gui/factor_correction.py` 纯函数层——`auto_fix_column`（保守：
归一化等价 rsi14→rsi_14 / 唯一距离 1 且次优差距 ≥3 / 唯一前缀，
其余一律不动给候选）、`suggest_similar_columns`（归一化编辑距离
Top-5）、`correct_factor_fields`（同表候选优先，同表空则跨标准因子表
兜底，列名对表写错直接换表）、`COMMON_FACTOR_TARGETS` 常用清单、
中文提示格式化。②`gui/nl_compiler.compile_nl`：missing_factors 判定前
先纠错——全部纠正成功则重写 YAML 正常返回（warnings 标注「已自动纠正
X→Y」，响应带 corrections）；仍有未解决项则照旧入补因子队列，error 从
「编译失败」改为 actionable 提示（每因子 Top-5 候选 + 常用因子清单），
响应带 suggestions。③prompt 注入：build_system_prompt 追加「严禁编造
因子名」硬约束 + COMMON_FACTOR_TARGETS 常用已落库列。④
strategy_lab_routes 手工 YAML 通道（/api/strategies/create mode=manual）
同样先纠错再入队，8080/8081 共享生效。测试 +17
（tests/test_gui_factor_correction.py：编造名纠错/精确匹配不动/无匹配
给候选/歧义前缀不纠正/prompt 注入/compile_nl 集成），全量 1960
passed + 4 skipped（1943 + 17）。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-006 (「聚类动量」页 v5 榜单可读性：横向滚动 + 首列 sticky + 精简列开关 + 详情面板上移)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户反馈：concept 榜单 17+ 列横向溢出挤压、点池名后详情在页面最底部
需长滚。修复（admin.html + style.css，pool_momentum.py 零改动）：
①momTable 包 .mom-scroll 横向滚动容器 + 首列池名 sticky（热力行首列
background:inherit，行仅 heat 非空才输出 style）；②默认精简列（池名/
股票数/当前窗口 fwd/速度/加速度/共振/回避徽章/事后×3），扩展列标
mom-col-x + .mom-compact 隐藏，「#btn-mom-cols 展开更多列」开关切全量
列（colspan 随视图 concept 9/20、state 13/24）；③删除底部
data-section="mom-detail" 折叠区，新 #mom-detail-panel 固定在
#mom-summary 之下、榜单之上（标题 + #mom-detail-close 关闭按钮 +
scrollIntoView，点其他池原地替换）；④成员明细包 .mom-members-scroll
限高 420px 内部滚动（表头 sticky 沿用全局规则）。测试 +2（78 总：
v5 模板标记 + CSS 断言），全量 1942 passed + 4 skipped。qre-gui 已重启
active；curl /admin 200 含新标记、overview（真库 2026-09-03：concept
1066/state 14）与 detail API 200。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-005 (「聚类动量」页 v4 底部减速回避名单：⚠ 回避徽标 + 顶部回避卡 + 声明卡补句)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

依据 M7 全历史结论（fwd_ret_3 最弱 Bottom10 未来 3-5 日继续跑输约
0.2%/日，NW t=−3.86，FDR q=0.001；顶部信号全部无效）：纯函数
compute_bottom_avoid（组内 fwd_ret_3 最低 10 个标 avoid，None 与
n_stocks<10 剔除）+ avoid_list 摘要；overview payload 加 avoid/
avoid_bottom_n/avoid_min_stocks，历史回看按选中日截面保持 point-in-time；
榜单行加「⚠ 回避」徽章（title 注明依据）、顶部 #mom-avoid 汇总卡
（点击跳详情）、声明卡补「顶部无选股价值，主要价值=底部回避名单」。
测试 +11（76 总），全量 1940 passed + 4 skipped。qre-gui 已重启
active；真库 2026-08-31 concept 回避名单居首「申万L3:疫苗」−5.73%。
未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-004 (「聚类动量」页 v3 历史回看：日期选择器 + 事后验证列 + 验证摘要条)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

overview 加 trade_date 参与 fwd 可选日期列表（下拉切换 point-in-time 榜单）；
纯函数 compute_post_returns（post_w = T 后 w 日 fwd_ret 复利，不足窗口→NULL
未满窗口）加「事后3/5/20日」三个可排序列；纯函数 accel_top_summary（加速度
Top10 post_5 均值/中位/胜率 vs 全体，按 pool_type 各一行）渲染摘要条；
detail 加 end_date、members 传选中日期。测试 +11（65 总），全量 1929
passed + 4 skipped。qre-gui 已重启 active；真库：2025-09-05 concept 加速度
Top10 post_5 +0.19% vs 全体 +0.88%（该日无超额，如实呈现）。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-003 (「聚类动量」页升级 M7 v2 前瞻口径：fwd_ret 主口径 + 事件池统计)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

M7 v2 新列（fwd_ret/fwd_ret_3/5/20/50/next_premium/survive_3/5/win_rate_1）
接入 8080 聚类动量页：速度/加速度/热力/共振全部切 fwd 口径
（compute_acceleration/compute_heat 加 metric 参、resonance 判 fwd），
回看 ret_w 降级对照列；overview 默认展示最近 fwd 已补齐日 + fwd_lag
红色提示（末日 NULL=正常 T+1 滞后）；state 分区 artifact 池加事件 4 列
（has_event 行级标记，对标同花顺涨停复盘）；详情主线 fwd、回看浅色辅线；
声明卡改写。测试 +9（54 总），全量 1918 passed + 4 skipped。qre-gui 已
重启 active；真库实测榜单日 2026-08-31，concept fwd_ret_3 榜首
「昨日打二板以上表现」+15.38%。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-002 (「聚类动量」页三项优化：池内个股明细 / 表头排序 / 行热力色阶)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

①新 API /api/admin/pool-momentum/members（pool_type/pool_key/trade_date，
后者缺省=最新）：成员 concept=cluster.company_tags 快照、state=当日
daily_tags；`compute_member_metrics` 纯函数即时算 stock_daily（51 日窗口，
复权/vwap/均量比口径与 M7 管线逐位一致——华为概念成员等权 ret_3 与池表值
完全相等、有效成员 770==n_stocks）；名称 reference.stock_basic 降级可选。
②主榜单全部数值列+成员表全列点击排序（▼/▲，None 恒末位，前端
momGenericSort / Python 侧同口径 sort_rows）。③行热力：compute_heat
（ret_w 截面分位 heat∈[-1,1]，红涨绿跌）随窗口切换重算；「长弱短升」
改左侧绿边+加粗避免与热力背景冲突。测试 +21（45 总），全量 1909 passed
+ 4 skipped。qre-gui 已重启 active，curl 实测全 200。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-001 (8080 管理台新增「聚类动量因子研究」tab：cluster-ashare M7 池动量管线只读展示)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户直接指派 demo 只读页。新 `gui/pool_momentum.py`（market_risk.py 同款
只读数据层：_store/_cached TTL 300s/自降级）只读 `cluster.pool_momentum_daily`；
纯逻辑（rank_desc 竞争排名 / compute_acceleration 速度=ret_50 排名·
加速度=ret_50 排名−ret_3 排名·长弱短升=速度后半区且短窗前 10% /
resonance_flag 价量三同正 / sort_by_acceleration）零 DB 可测。
app.py +/api/admin/pool-momentum 与 /api/admin/pool-momentum/detail；
admin.html +「聚类动量」tab（偏差声明卡：concept 池当前快照前视偏差
demo 接受、state 池 point-in-time 无偏差；窗口 3/5/20/50 切换；concept/
state 两榜单含 4 窗 ret + 4 窗 vwap_ret + vol_chg + 速度/短窗排名/加速度/
共振标记；长弱短升高亮；点击池名看 250 日 7 序列 inline SVG，复用
riskSvgLine，零新前端框架）；style.css 纯追加。8081 零改动。
测试 +24（tests/test_gui_pool_momentum.py）；全量 1888 passed + 4 skipped。
qre-gui 已重启 active，/admin 200、两 API 真库实测正常
（2026-09-01：concept 1066 / state 14）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-LAB-RESULT-030 (B 层关键词换代：jieba 碎片词 → 东财+同花顺概念板块成分；8080 总览加「概念标签源」卡片)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

跨仓任务（cluster-ashare 改造 + 本仓消费/展示）：①cluster-ashare 新
`src/tags_lb_concept.py`（东财 akshare + 同花顺自带分页抓取双源采集，
layer='B' source='em_concept'/'ths_concept'，upsert 幂等 + 失败板块
extra_passes 补抓），`scripts/drop_lb_jieba.py` 删除旧 NLP B 层
（97,838 行 + 5,206 字典行，已执行），`tags_lb.py` 标 DEPRECATED，
`run_mvp1 build-tags` 周更接线（deploy 注释同步）。②本仓 admin.py 新
`overview_concept_tags`（B 层 source 分布，自降级），app.py 总览 payload
加 concept_tags，admin.html 加「概念标签源（B 层）」卡片。③8081 归因端
零改动验证：tag-analysis B 层已显示真概念词（华为概念/CPO概念/PCB 等）。
测试：本仓 1840 passed + 4 skipped（+7）；cluster-ashare 204 passed（+12）。
遗留：东财接口当日长时段断连，504 板块入库 290，网络恢复后重跑幂等补齐
（方法见 cluster-ashare README 已知限制）。

---

## Archive: QRE-GUI-LAB-PORT-017 (回测台新端口移植：新增策略 + 回测管理两页面 → 独立 Flask 应用 @8081)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

纯移植，零优化/美化/功能增删。新 `gui/strategy_lab_routes.py`::
`register_strategy_lab_routes(app)` 共享注册（create_app 尾部调用，
路由表与 git HEAD 逐条相等 59/59）；新 `gui/lab.py`（create_lab_app /
launch_lab_gui）+ `templates/lab.html`（「新增策略」自 index.html
strategy tab、「回测管理」自 admin.html onboard tab 脚本精确切片，
含排序 JS/搜索/toggle/删除/gate 徽标，附 /runs 页面）。CLI：
`qre gui --lab`（默认 8081，--port 优先）；`qre gui` 不变。systemd：
`deploy/hardened/qre-gui-lab.service`（端口 8081、
SyslogIdentifier=qre-gui-lab）已 sudo 安装 enable --now
（enabled/active）。测试 `tests/test_gui_lab.py` +12；全量
`uv run pytest -q` → 1807 passed + 4 skipped（基线 1795 + 12）。
冒烟：8081 / 双 tab、/api/admin/refresh stopped 118/118（与 8080
一致）、/admin/strategy/<id> 200；8080 / 与 /admin 200。两个 service
均已重启。无 CR（纯移植无设计决策）。未 commit。详见
09_CODING_HANDOFF.md 顶部、05_PROGRESS.md 顶部。
上一任务：QRE-GUI-SORT-016 / QRE-GUI-DERIV-FRESH-015（见 05/09）。

---

## Archive: QRE-DERIV-ADAPTER-013 (衍生品数据适配层：yc_curve/cb/opt 三个只读 loader + 示例管道，CR D1.5/D2.2/D3.2)

## Task Note

新 `src/quant_research_engine/data/derivatives.py`（只读适配层，QRE 唯一读
derivatives schema 的代码）：`load_zero_curve`（yc_curve 即期 8 节点，
yield%÷100 视为年复利→连续复利近似披露；当日无数据取 ≤trade_date 最近日，
`latest_curve_date` 披露实际日期）、`load_cb_terms`/`cb_cashflows`/
`cb_bond_floor`（现金流近似：常数票息/期限取整付息网格/面值到期无赎回
溢价/利差默认 100bp → convertible_bond_floor + cb_daily.bond_value 对比）、
`load_option_chain`（settle JOIN opt_basic，T=actual/365，r=0.25y 节点，
逐合约 implied_vol，平值隐波断言 (1%,150%)）。已知缺口：库内无 ETF 日线
（510050.SH 不在 stock_daily/index_daily），标的价缺失时须传
`underlying_price`，示例脚本用平值 put-call parity 反推（披露）。
示例 `scripts/derivatives_adapter_smoke.py` + 测试
`tests/test_data_derivatives.py` 15 个（纯函数 11 + DB 冒烟 4 无库 skip）。
冒烟 2026-08-21：曲线 1.164%–2.110%；5 只存续转债债底 99.14–101.74 vs
bond_value 105.4–111.2（差异主因到期赎回溢价未含，可解释已披露 CR §11）；
50ETF 平值 K=3.0 call/put IV 13.67%。全量 1795 绿 + 4 skipped
（基线 1784 + 11 净增）。未 commit、未重启 qre-gui。详见
09_CODING_HANDOFF.md 顶部、05_PROGRESS.md 顶部、CR §11。
上一任务：QRE-GUI-DERIV-CARD-012 / QRE-RISK-GUIDE-011（见 05/09）。

---

# Task Handoff (archive: QRE-RISK-BAROMETER-M3-010)

## Task ID

QRE-RISK-BAROMETER-M3-010 (大盘/板块风险风向标 M3：日更 timer 接入 + GUI 风向标页 + 阈值首轮校准观察)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

M3（CR 末阶段，CR 状态改「✅ M1–M3 已完成」）：deploy/hardened/
qre-barometer.{service,timer}（Mon..Fri 18:30、Persistent、hardened 护栏、
默认最近交易日单日模式，未 sudo）；`qre barometer` CLI；admin TIMER_UNITS
+ install_hint + daily_jobs PIPELINES 登记；/admin 新「大盘风险」tab——
新 `gui/market_risk.py::market_risk_overview`（只读 market_risk.daily、
_cached 300s、分区降级）+ 路由 /api/admin/market-risk + 仪表盘红黄绿灯/
五序列 inline SVG/行业+动态簇热力表/预警双判据详情（复用现有样式，零新
前端框架）；阈值首轮校准观察入 06（red 11/1850=0.59% 全为已知风险事件，
初值保留）。真库冒烟 ok（2026-08-20 总分 63.3 green）。1778 tests green
（+14）。未 commit、未重启 qre-gui、未装 timer（sudo 留主代理/用户）。
细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-BAROMETER-M2-009
（M2 装配+回填，1764 green，b0713d7）。

# Task Handoff (archive: QRE-RISK-BAROMETER-M2-009, 风向标 M2 数据装配与回填)

## Task ID

QRE-RISK-BAROMETER-M2-009 (大盘/板块风险风向标 M2：数据装配 + 历史回填 + market_risk_daily 产出)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

M2 在 M1（commit 64addd7，1754 绿）上落地：新 `risk/barometer_job.py`
（risk 包唯一读写 DB 层，业务表只读）——pct_chg/100 收益面板 +
total_mv 市值 + stock_basic.industry 行业 + cluster.daily_tags 当日簇
（<5 跳过）→ M1 纯函数 → 独立 schema `market_risk.daily` 表
（PK (trade_date, scope)，ON CONFLICT 幂等 upsert）+ JSON 产物
outputs/market_risk/<date>.json；年分块 + 312 交易日 buffer。真实回填
2019-01-02→2026-08-20 完成：220,034 行 / 1,850 日 × 120 scope，~21min。
方向性验证全过：2020-02-03 red（突破 85.2% P100）、2024-02 微盘连续 red
（总分 P99–100）、常态 green；全样本 red 11 天均为已知风险事件。
簇分数 M2 不算（成员逐日变动，披露）。1764 tests green（+10）。
未 commit、未重启 qre-gui。细节见 `09_CODING_HANDOFF.md` 顶部。
上一任务：QRE-RISK-BAROMETER-M1-008（M1 纯函数内核，1754 green，已提交 64addd7）。

# Task Handoff (archive: QRE-RISK-BAROMETER-M1-008, 风向标 M1 纯函数内核)

## Task ID

QRE-RISK-BAROMETER-M1-008 (大盘/板块风险风向标 M1：cross_section + barometer 纯函数内核)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

M1 在 R7（1724 绿）上落地（依据已批准 CR
`docs/frm/CR_2026-08-23_market_risk_barometer.md` §5 M1 阶段）：新
`risk/cross_section.py`（纯函数零 DB、向量化——EWMA 方差面板与单列口径
atol 1e-15 一致、截面波动率中位/90 分位、等权/市值加权离散度、滚动 60 日
平均两两相关等权 + w_i·w_j 偶权近似、VaR 突破计数/占比严格 r<−VaR 同
HIT 口径、cross_sectional_summary 一把梭 σ forecast shift(1) 防前视）；
新 `risk/barometer.py`（组合法封装 100% 复用 volatility/tail 出 EWMA σ
与 VaR/ES 95/99、252 日滚动分位分数 warmup 降级 None、红/黄/绿预警
双判据、build_barometer 全市场+板块统一 dict、分组映射调用方传入不感知
来源）；`risk/constants.py` 加 BAROMETER_CORR_WINDOW=60 /
BAROMETER_SCORE_WINDOW=252 / ALERT_CORR_LOOKBACK=20 / ALERT_CORR_JUMP
=0.10 / ALERT_BREACH_RATIO_MAX=0.03 / BREACH_CONFIDENCE=0.99 /
CROSS_SECTION_SIGMA_QUANTILE=0.90 全回显。1754 tests green（+30：
cross_section 17 + barometer 13）。未 commit、未重启 qre-gui（用户约束）。
细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-PORTFOLIO-007
（R7 组合层汇总，1724 green，待审批）。

# Task Handoff (archive: QRE-RISK-PORTFOLIO-007, R7 组合层汇总)

## Task ID

QRE-RISK-PORTFOLIO-007 (FRM 风险管理模块 R7：组合层汇总 + risk_report 扩展 + GUI 卡片 + 可选闸扩展)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R7 在 R6（期权内核 + DGV-VaR，1696 绿）上落地组合层与集成（依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R7 阶段，CR 状态已改
「R5–R7 已完成」）：新 `risk/portfolio.py`（纯函数零 DB，
`summarize_mixed_portfolio`——股票腿沿用 R1–R4 收益序列法
performance_summary + EWMA VaR/ES 参照、债券/转债腿 DV01 可加/D·C 市值
加权 + 可选 KR01 按节点加总、期权腿组合 Greeks 加权求和、config 显式给
dgv.spot_shock_sd 才计算 DGV-VaR；仅股票输入退化为仅 equity 节）；
`risk/report.py` config 显式传入非空 bond_positions/option_positions/bond_kr01
才追加 `portfolio` 节（meta.sections 回显）+ markdown 渲染「组合与衍生品风险」；
GUI `_risk_display` + run_detail.html 追加「衍生品风险（组合层）」卡片
（有节才显示）；`risk/constants.py` 加 GATE_DV01_MAX/GATE_GREEKS_MAX
（默认 None=不启用），`evaluate_gate_risk` 启用时追加组合 DV01/Greeks 限额
判据，默认关闭时返回与 R4 逐键一致。1724 tests green（+28：portfolio 14 +
report 7 + gui 7）。默认 run 产物零变化，老格式 report 三处（markdown/GUI/
闸）健壮性专项测试覆盖。未 commit、未重启 qre-gui（用户约束）。细节见
`09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-OPTIONS-006（R6 期权内核，
1696 green，待审批）。

# Task Handoff (archive: QRE-RISK-OPTIONS-006, R6 期权内核 + DGV-VaR)

## Task ID

QRE-RISK-OPTIONS-006 (FRM 风险管理模块 R6：期权计算内核 + DGV-VaR)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R6 在 R5（commit 5472832）上落地期权内核与 DGV-VaR 适配器（依据已批准
CR `docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R6 阶段，纯函数
零 DB 零行情）：新增 `risk/options.py`（BSM 式 15.6–15.9 无股息/q/离散
股息 S₀−D、Black's 式 15.12/15.13、隐波 brentq（IV_BRACKET）、CRR
式 14.4–14.7 欧式+美式含 q、第一层 delta、美式 Greeks 数值差分、
Greeks 全组 Table 16.2 含 q 版与期货期权版 rho=−f·T、组合 Greeks
加权求和）与 `risk/derivatives_var.py`（ΔV ≈ Δ·δS+½Γ(δS)²+vega·δσ、
非中心卡方累积量解析矩、正态/Cornish-Fisher 分位 VaR、VaR 序列对接
backtest_var.backtest_var_summary 复用 HIT/LR）；`risk/constants.py`
追加 IV_BRACKET/DEFAULT_TREE_STEPS=50/GREEK_SHOCK_*，全部结果 dict
回显。教材数值全复现：BSM 例 d1=0.2001/c=8.3069/p=7.9715+parity、
隐波 7.00→25.14%、美式 put 节点值 3.058/0.494/5.699（欧式 2.838）+
收敛 3.082/3.067/3.059/3.055（参数 S=29,K=30,r=3%,σ=25%,T=1 经教材
原文 p193 核对）、PDE 恒等式 1e-10、纯 gamma 解析二阶矩 Var=½Γ²sS⁴、
CF-VaR 对 MC rel 5%、VaR 序列回测违约率 ≈1% 不拒绝。1696 tests
green（+39）。既有 risk 模块零行为改动。未 commit、未重启 qre-gui
（用户约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-RATES-005（R5 利率与债券内核，1657 green，待审批）。

# Task Handoff (archive: QRE-RISK-RATES-005, R5 利率与债券内核)

## Task ID

QRE-RISK-RATES-005 (FRM 风险管理模块 R5：利率与债券计算内核)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R5 在 R1–R4 已完成的 risk 包上落地利率与债券计算内核（依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R5 阶段，纯函数
零 DB 零行情）：新增 `risk/rates.py`（式 16.1–16.5 复利换算、PV/FV、
spot↔折现因子、书4 Ch9 附息债 bootstrap 零息曲线、线性/对数线性插值、
远期利率连续式与式 10.5、par yield 式 16.7/10.4）与 `risk/bonds.py`
（YTM brentq、actual/actual 与 30/360 应计利息、式 12.6 久期凸性、
式 12.1/12.3 effective duration/convexity、DV01 与 D↔DV01 换算、
组合聚合与 DV01 对冲配比、式 12.4 平行移动二阶近似、书4 Ch13 KR01
含 ΣKR01=DV01 自检、书3 Ch16/17 转债债底折现与 spread duration）；
`risk/constants.py` 追加集中参数（day count/插值/key rate 节点/Δr bp/
YTM bracket，全部结果 dict 回显）；`pyproject.toml` 补 scipy 显式依赖。
教材数值全复现：bootstrap d=0.991909/0.980944/0.969406/0.956909、
par yield 2.2103%、平坦曲线年金解析解 P/D/C、DV01↔D 自洽、
ΣKR01=DV01、+100bp 二阶近似 vs 重定价 rel 1.9e-5。1657 tests green
（+52）。既有 risk 模块零行为改动。未 commit、未重启 qre-gui（用户
约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-GATE-004（R4 晋升闸风险判据，1605 green，待审批）。

# Task Handoff (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004 (FRM 风险管理模块 R4：晋升全量回测闸加入风险判据)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R4 在 R3（risk_report.json 随 completed run 自动生成）上给晋升全量回测闸
（QRE-GUI-PROMO-GATE-001，commit cfb860d）加风险维度：`risk/constants.py`
集中阈值（`GATE_ES99_MAX=0.03`、`GATE_VAR_CONFIDENCE=0.99`）；
`gui/risk_report.py::evaluate_gate_risk(run_id)` 读该 run 的
risk_report.json——99% ES（历史模拟日收益口径）> 3% 或 99% 覆盖率
Kupiec LR `reject_5pct` → `risk.status=warning`；report 缺失/损坏 →
unavailable 不阻断；`strategy_create.finalize_promotion_gate` 写 gate json
新 `risk` 节，主判据照旧；`refresh_registry.gate_blocks_daily` 扩展为
failed 或 risk=warning 且非 forced 即阻止日更（force 通道照评估不阻断）；
admin.html 闸列 warning 追加「⚠ 风险警示」徽标（tooltip ES99 + VaR 回测
结论）+ style.css `.gate-risk`。1605 tests green（+6 净增：四情形 + force
覆盖 + 徽标渲染）。存量 gate json 无 risk 节行为不变。未 commit、未重启
qre-gui（用户约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-INTEGRATION-003（R3 集成，1599 green，commit 6852eaa）。

# Task Handoff (archive: QRE-RISK-CORE-002, R2 VaR 回测/压力测试/Bootstrap)

## Task ID

QRE-RISK-CORE-002 (FRM 风险管理模块 R2：VaR 回测 + 压力测试 + Bootstrap 推断)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R2 在 R1（commit 96db59d）上落地三模块 + 报告扩展，公式以 FRM 知识摘要
为准：`backtest_var.py`（书2 Ch6：HIT 序列、覆盖率 Bernoulli LR + 精确
二项、独立性 Christoffersen 转移矩阵 LR——摘要未点名，注释标注出处
差异、多重检验假阳性 1−(1−α)ⁿ、backtest_var_summary 统一 dict）；
`stress.py`（书4 Ch8：A 股四历史情景库、回放=累计损失/峰谷/Peak/VaR +
相关性崩溃提示、reverse stress β 穿透反查市场冲击分位/σ 倍数）；
`inference.py`（书2 Ch13：arch CircularBlockBootstrap 块长 √n 给年化
收益/夏普/最大回撤算置信区间 + iid 对照 + MC 标准误 σ/√b）；`report.py`
升 R2（var_backtest 默认开用 EWMA μ=0 VaR、stress/bootstrap config 可选
开启）。46 个新测试全为已知答案核对（LR 手算 4.13085、转移计数手算、
情景回放手算 −0.119179/0.05/2.5、reverse β=2 穿透、bootstrap 固定 seed
CI 含真值 + MC 标准误核对、AR(1) 下 iid 低估 CBB）。1578 tests green
（+46 净增）。未 commit、未重启 qre-gui（用户约束）。细节见
`09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-CORE-001（R1 核心包，
1532 green，commit 96db59d）。

# Task Handoff (archive)

## Task ID

QRE-GUI-CREATE-GAPS-001 (新增策略/因子闭环四缺口)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

GUI「新增策略/新增因子」全链路四缺口补齐：①策略冒烟状态闭环——
engine._execute_and_finalize 终态钩子回写 `<name>.smoke.json`
（completed/failed + 关键指标 + finished_at，原子写），run 标记改由
run_backtest(mark=...) 预合并，list_sandbox 自愈滞留 running；前端沙箱列表
三色渲染 + 失败原因摘要 + 轮询刷新。②晋升状态闸——promote /
promote_factor 加 `force`，sidecar 非 completed → 409 smoke_not_passed，
force=true 管理员通道响应注明。③因子冒烟 120s 同步阻塞改异步——
start_smoke_job 复用 daily_jobs.start_script_job（lock_key=factor-smoke:<name>），
POST 即返 job_id + GET /api/factor-create/smoke/<job_id> 轮询 + 前端轮询，
120s 超时与 JSON 解析口径不变。④删 style.css .p3c-hidden 死代码。
1437 tests green（+20 净增）。未重启 qre-gui（用户约束），真实 E2E 待重启。
细节见 `09_CODING_HANDOFF.md` 顶部。

# Task Handoff (archive)

## Task ID

QRE-M5C-MINED-FACTOR-STRAT-001 (M5c：因子工厂 Top3 因子 → QRE 正式策略闭环验证)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

cluster-ashare M5c 联动任务：cluster.mined_factors Top3（MF_001/002/003）
转译为 cs07a/b/c（strategies/catalog/cross_sectional/），经沙箱→冒烟→晋升→
全市场近 1 年回测（批次 b21f1008ec98）→ report-audit 全通过。
截面分位语义由 cluster-ashare 物化表 cluster.mined_factor_flags 承载，
QRE 零代码改动。回测结论：近 1 年未复现 M3b 超额（超额 -11.1~-11.6%），
建议三因子转「衰减观察」——状态调整与是否 commit 均待用户审批。
细节见 `09_CODING_HANDOFF.md` 顶部。

## Task ID

QRE-STRATEGY-FIT-ANALYSIS-001 (M10.1, CR-0003 F3 phase 1)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

This handoff now covers QRE-CONTINUOUS-REFRESH-001 (M10.3). Summary: watermark-gated continuous refresh — `orchestration/refresh.py` + `scripts/refresh_batch.py` (check-only/force/rolling window), per-strategy delta report with manifest/audit parity, systemd user units documented (not installed); small-sample e2e passed; no full-scale execution per standing instruction.

## Current Owner

KIMI_CODE

## Problem Summary

The quick batch (106 strategies × 5,292 symbols × 2024) ranks strategies only by market-wide returns, which buries strategies with strong class-specific edge (user's example: 3% market-wide / 12% best-class). This slice adds the strategy-fit analysis layer: winner-stock enrichment across board/industry/cap/liquidity classes, noise filtering, and multiple-testing-adjusted rankings — reading existing batch artifacts only, no new backtest runs (user instruction 2026-07-19).

## Implementation Summary

Planning only so far (per approved roadmap order M9.1b → M10.1 → M10.2 → M10.3):

1. New `analysis/strategy_fit.py`: batch loading, read-only metadata join (class columns are absent from batch summary.csv — documented gap), configurable noise filters (min trades / min class size / NaN), **significance-tier winner selection** (exact binomial test on per-symbol win rate vs p=0.5 at 90%/99%/99.9% + magnitude gates — user refinement replacing top-10%), strategy-level meta-test vs false-positive expectation, hypergeometric enrichment (pure Python), BH-FDR adjustment, `class_edge` flagging.
2. `scripts/strategy_fit_report.py` command writing summary/classes/markdown report + `report_manifest.json` (new kind, `qre report-audit`-compatible).
3. Runner `--metadata-columns` passthrough so future batches embed class columns (optional for v1).
4. v1 explicitly excludes time-window stability (needs a per-symbol monthly-returns artifact — follow-up v1.1 recorded in CR-0003).

Previous task `QRE-VECTORIZED-ENGINE-001` (M9.1b) finalized in commit `c86441b` (42.8× speedup, metric-identical).

## Standing User Instructions

- No full-scale backtest runs until the core engine work is mostly complete (2026-07-19). Small-sample-first (R-QRE-009) applies to the future full-history (M9.4) runs.
- This slice complies: it executes zero backtests (reads existing CSV/JSON artifacts + one read-only metadata query).

## Hard Constraints

- No new dependencies; pure Python statistics (hypergeometric via `math.comb`, BH-FDR).
- Deterministic outputs; manifest audit parity (R-QRE-007); read-only DB access only (R-QRE-005).

## Validation Evidence

```bash
uv run pytest -q → 1045 passed
real batch: 106 analyzed / 5 skipped; metadata 5,256 symbols
qre report-audit outputs/strategy_fit/f365c8a07b33/report_manifest.json --require-match → status=ok, 0 issues
```

</details>
