# Implementation Brief

## Task ID

QRE-SAAS-PUBLIC-BETA-OPS（P1：公测运营反馈闭环与关键浏览器自动化）

## Created By

KIMI_CODE（2026-10-26；依据 `14_LAUNCH_ROADMAP.md` §11.3 条目 4「运营反馈闭环」）

## 目标与边界

1. **9090 管理台新增「公测运营」tab（GET /api/saas/console/ops，admin 门禁不变）**，指标全部来自权威库/执行路径，明确时间窗口、分母与空数据口径，不编造历史：
   - NL 编译：成功率、缓存命中率、热门失败原因。新增最小隐私安全事件表 `nl_compile_events`（ok/cache_hit/error_class/scope/created_at；**不存策略文本、API key、原始 IP**）；**自本功能上线起统计**，上线前显示「—」。
   - 回测（kind='full'，smoke 内部试算不计入）：成功率、平均排队时长（started_at−created_at）、平均执行时长（finished_at−started_at）、热门失败原因（error_class 分组）。jobs 表有全量历史，窗口 今日/近7天/近30天/累计 均为真实值。
   - 游客到注册转化：游客独立会话数（jobs.guest_key 去重，**仅统计提交过任务的游客，未提交访客不可见——口径明示**）与当日/窗口新增注册（users.created_at）两个**独立计数**。二者无跨会话关联：**不计算转化率**（ratio=null + measurement=unlinked；未关联总量的比可超过 100%，是误导），未来做真实转化须先建会话关联记录，本切片只做诚实降级、不扩展用户追踪 schema。
   - 空数据口径：分母为 0 时比率返回 null，前端显示「—」。时间窗口 today 按 **Asia/Shanghai 自然日**（A 股运营口径；UTC 零点会漏当日凌晨 8 小时），7d/30d/all 为滚动窗口/不限。
2. **意见反馈分类与处理状态闭环（最小可用，不建工单系统）**：`feedback` 新增 `category`（bug/experience/factor/other，默认 other，提交端 allowlist 校验）与 `status`（open/doing/done/closed，默认 open）。提交页加类型选择、本人列表透出类型/状态；管理台反馈 tab 支持按类型/状态筛选与状态流转（POST /api/saas/console/feedback/<id>/status，仅 admin，非法状态 400、不存在 404）。保留既有用户隔离、每日 20 条上限、管理员鉴权。
3. **关键浏览器自动化**：可重复执行资产落 `deploy/saas/public-beta-audit/`（seed.py + browser_audit.py + run_audit.sh，复用 `.tmp/browser-venv` Playwright 与 `.tmp/ms-playwright` Chromium；Playwright 仅测试工具，不进生产依赖）。场景覆盖：游客/登录、新建页、NL 编译 stub、任务等待/失败恢复、结果只读与权限、反馈分类、管理台运营指标；桌面 1280 与 375 只验证不破版；不启动真实 worker、不跑真实回测，任务状态经 seed/worker 协议模拟。
4. **Schema 由 postgres 幂等 apply**（`nl_compile_events` 建表 + feedback 两列 DO 块；ECS 表 owner 是 postgres，应用层懒自愈只兜底本地/测试库）；发布仅同步 app.py、console.html、feedback.html、cloud_schema.sql 并重启 qre-saas，不重启 worker。
5. TDD 先 RED 后 GREEN：新 `tests/test_saas_public_beta_ops.py`；相关套件 + 全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` 必须通过。证据落 `.tmp/public-beta-ops/`。
6. 遵守 R-UI-001（无灰色小字备注，解释用 tip-trigger+data-tip+LabUI.helpTips）、R-ADMIN-001（运营指标展示与执行/库同源）、R-DEPLOY-001（先部署后验收再提交）。

## 验证

- 单测：事件记录（成功/失败/缓存命中/scope、无文本无 IP）、ops 窗口与比率/排队/失败分组/转化口径与空数据 null、反馈分类 allowlist 与状态流转权限矩阵、页面标记（ops tab、反馈筛选与状态列、feedback.html 分类控件）。
- 真实 Chromium（临时 PG + 8099 staging + stub LLM + worker 协议模拟）：上述 7 类场景零 JS error、零横向溢出（1280 与 375）。
- ECS：备份 → postgres apply schema → scp 四文件 → 仅重启 qre-saas → 9090 隧道验证 ops API/tab 与反馈流转；公网临时数据彻底清理，不输出凭证。保留「已部署待用户验收，未 commit/push」。

## 实施结果（2026-10-26，用户验收通过，已部署并发布）

- **改动文件**：`src/quant_research_engine/gui/saas/ops_support.py`（新）、`src/quant_research_engine/gui/saas/app.py`、`src/quant_research_engine/gui/saas/templates/console.html`、`src/quant_research_engine/gui/saas/templates/feedback.html`、`deploy/saas/cloud_schema.sql`、`deploy/saas/public-beta-audit/{seed.py,browser_audit.py,run_audit.sh}`（新）、`tests/test_saas_public_beta_ops.py`（新）。未改引擎/worker/数值/配额/NL A2A3 语义。
- **TDD**：RED=17 errors（对 HEAD 基线 stash 实现）；GREEN=17 passed；相关 5 文件 227 passed + 1 skipped；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2770 passed + 6 skipped**（基线 2753+6 零回归）。证据 `.tmp/public-beta-ops/{red,green,full-tests}-evidence.txt`。
- **真实 Chromium**（临时库 + 8099 staging + stub LLM + worker 协议模拟，未启动真实 worker/回测）：9/9、零 JS error、零横溢；`browser-evidence.json` + 11 截图（含 375 两张）。
- **生产缺陷热修**：`feedback_id_seq` 缺 USAGE → 登录用户提交反馈 500（feedback 特性此前从未部署 ECS，首次上线暴露；同 share_links 序列坑）。生产 GRANT USAGE, SELECT；schema 增加角色存在时幂等 DO 块（含序列存在性检查）。
- **发布**：ECS 四文件与 HEAD 基线 SHA256 一致 → 备份 `/tmp/qre-public-beta-ops-pre-20261026/` → scp 五文件 → postgres 幂等 apply → 仅重启 qre-saas（active，worker 在家未动）。生产 ops 鉴权三态、空口径诚实（编译前 nl.total=0/first_event_at=None）、反馈闭环、游客真实 DeepSeek 编译两次 cache_hit false→true（A2A3 无回归）、ops all 窗口 nl.total=2/first_event_at=2026-10-26；临时数据清理（temp_users=0/feedback=0）；9090 隧道 console 200 含 ops 标记、ops API 无 token 401；公网 /saas/、login、new、feedback、help 200，/saas/console 仍 404。证据 `production-verification.txt`。
- **遗留**：NL 指标自功能上线起统计（上线前无历史，不回填）；游客访客口径仅覆盖提交过任务的独立会话；转化率不计算（需会话关联）；反馈状态无备注字段；`nl_compile_events` 无自动清理（仅索引）。

## 复核修正（2026-10-26，主 Agent 2 项 Required Fixes 已解决，重新部署待人工验收）

1. **转化比率误导**：`compute_ops` 不再计算 new_users/guest_sessions 之比（生产实测「注册 / 游客 300.0%」）；返回 `ratio=None` + `measurement="unlinked"`；console 卡改「转化率 —」，保留两个真实计数；未扩展用户追踪 schema。回归 `test_conversion_ratio_never_computed`。
2. **今日边界**：`window_start('today')` 改上海当日零点（`_now_shanghai()` + `ZoneInfo("Asia/Shanghai")`，转 UTC 比较）；7d/30d/all 不变。回归 `test_today_start_is_shanghai_midnight` + DB 级 `test_today_window_includes_shanghai_early_morning`。
- TDD：RED=4 failed → GREEN；ops 测试 20 passed；相关 3 文件 135 passed；**全量 2772 passed + 6 skipped**（1 例已知 flake 复跑通过）。Chromium 重跑 9/9 零 JS error 零横溢（console-ops-1280/375 确认无伪转化率）。ECS 备份 `/tmp/qre-public-beta-ops-review1-pre-20261026/` 后仅同步 ops_support.py + console.html 并重启 qre-saas（无 schema 变更）。

## Archive: QRE-SAAS-NL-A2A3（持久限频与版本化编译缓存）

## Created By

KIMI_CODE 规划，Step 5 实施（2026-10-26，批准计划 `mister-terrific-echo-vision.md`）

## 目标与边界

1. `nl_rate_limits` 用 PostgreSQL 原子计数替代游客文件计数；游客仍每日 10 次且 403/code 不变，会员每日次数不限但 6 次/分钟防突发（超限 429），admin 不限。
2. `nl_compile_cache` 以规范化描述 + model/base_url + 完整 prompt 哈希 + 编译缓存版本生成 key；同 key advisory lock 防并发重复调用。只缓存 ok=true 结果，命中不调用 LLM、不占配额，失败不缓存。
3. 不改 `gui/nl_compiler.py` 的编译/纠错/YAML 校验，不运行真实回测，不公开缓存、不存 API key、不新增灰色小字备注。生产先 postgres apply schema 再发代码。
4. 新支撑模块 `gui/saas/nl_compile_support.py` + app.py 编排 + schema + `tests/test_saas_nl_compile_cache.py`；TDD 先 RED 后 GREEN，覆盖缓存命中/版本失效/并发/限流持久化/恢复窗口/admin/失败不缓存。
5. **R-ADMIN-001（用户补充）**：9090 总览必须展示 NL 真实生效权限（游客每日 10、会员每分钟 6、admin 不限）与缓存/限流计数，值直接来自执行常量与两张表，不复制第二套配置；完成可视化与公网核验后才允许 commit/push。

## 发布规则

遵循 R-DEPLOY-001：备份 `/tmp/qre-nl-a2a3-pre-20261026/`，直接部署并仅重启 qre-saas；用临时 session 对生产 MACD 描述纯编译两次，第二次 cache_hit=true 且 YAML 一致，不创建回测。更新 04/05/09/10/11/14/16/17，保留「已部署待人工验收，未 commit/push」。验收通过后才提交；不通过立即回滚。建议提交 `feat(saas): 增加持久编译限流与策略缓存`。

## Archive: QRE-SAAS-CLASSIC-ACTIONS-UI（经典策略按钮与结果操作卡精修）

## Created By

KIMI_CODE 规划，Step 5 实施（2026-10-26，批准计划 `amadeus-cho-cannonball-cyborg.md`）

## 目标与边界

1. 经典策略页删除灰色长文/弱链接与重复提示，底部改为「复现经典策略」+「新建同款策略」主按钮，页头说明移入既有问号提示；策略 subtitle 保留。
2. job 将 `#box-actions` 与 `#box-share` 合并进 `#result-actions-card`，保存=主按钮、信号/分享=次按钮；保留全部现有 ID、权限、事件绑定和 API。新增空安全 `syncResultActionCard()`，任一组可见才显示外层。
3. 改动区域禁止 `.opt`、muted/faint 段落或灰色小字备注；解释统一 `tip-trigger + data-tip + LabUI.helpTips`。按钮至少 44px 高，375px 不横溢。
4. 不改 API/schema/引擎/worker/数值/权限，不跑真实回测；TDD 先 RED 后 GREEN，临时 PG + Chromium 模拟任务验收。

## 发布规则

遵循 R-DEPLOY-001：测试后核对基线并备份 `/tmp/qre-classic-actions-pre-20261026/`，直接同步 `showcase.html`、`job.html`、`lab-theme.css` 到 ECS 并仅重启 qre-saas；公网验证后保留「已部署待人工验收，未 commit/push」。用户通过后才提交；不通过立即回滚。更新 04/05/09/10/11/14/16 与必要的 12 号 UI 文档。

## 实施结果（2026-10-26，已部署待人工验收，未 commit/push）

- **改动文件**：`src/quant_research_engine/gui/saas/templates/showcase.html`、`src/quant_research_engine/gui/saas/templates/job.html`、`src/quant_research_engine/gui/static/lab-theme.css`、`tests/test_saas_classic_actions_ui.py`（新）、`tests/test_saas_access_hardening.py`（3 处更新）、`tests/test_gui_saas_pages.py`（1 处 marker）。未改 API/schema/引擎/worker/数值/权限。
- **TDD**：RED=新测试 11 失败 + access_hardening 2 失败；GREEN=新 12 passed、access_hardening 66 passed、相关 10 文件 289 passed、全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → **2701 passed + 5 skipped**（基线 2689+5 零回归）。证据 `.tmp/classic-actions-ui/red-evidence.txt`、`green-evidence.txt`、`full-tests.txt`。
- **真实 Chromium**（临时库 `qre_readonly_share_browser` + 8099 staging，worker 协议模拟 completed，未跑真实回测）：9/9、零 JS error、零横溢；`browser-evidence.json` + 7 截图（showcase/job/signal-panel/guest/readonly 桌面 1280 + showcase/job 375）。
- **发布**：ECS 三文件与 HEAD 基线 SHA256 一致 → 备份 `/tmp/qre-classic-actions-pre-20261026/` → scp 三文件 → 仅重启 qre-saas。公网：showcase/job58/`/static/lab-theme.css` 200 且新标记齐全、删除标记为零、CSS SHA256 与本地一致；`/saas/`、help、login、new、symbols 两页 200。证据 `public-verification.txt`。
- **遗留**：`syncResultActionCard` 只在 init 两个入口同步；若未来新增第三种操作组需同步纳入数组。游客/只读整体隐藏已由 Node 矩阵 + 真实浏览器双重覆盖。

## Archive: QRE-SAAS-UI-DECLUTTER-001（结果页口径展示与说明页导航精简）

## Created By

KIMI_CODE 直接实施（2026-10-26，用户明确指定三项 UI 删减）

## 目标与边界

1. job/showcase/个人回测记录三处不显示结果合同、验证徽标、合同版本与新旧口径；`result_contract` 继续留在 API 和系统内部，showcase verified 公开门槛不得放宽。
2. 删除 job/symbol 各模块的 `/saas/help#...` 说明链接，保留既有悬停提示；`renderContract` 只驱动曲线口径提示。
3. `/saas/help` 顶部跳转为桌面 sticky 侧边栏目，卡片标题 20px；窄屏无横溢。帮助页不再展示验证状态或新旧口径。
4. 仅改模板、`lab-theme.css` 与测试；不改 API/schema/引擎/worker/数值/权限，不跑真实回测。

## 验证

TDD 先 RED 后 GREEN；相关套件 + 全量测试；真实 Chromium 检查 job/symbol/showcase/profile/help 桌面与 help 375 的标签消失、侧边布局、字体、锚点、零 JS error 与零横向溢出。证据 `.tmp/ui-declutter/`。不自动 commit/push/ECS。

## Archive: QRE-SAAS-READONLY-SHARE（P1：默认私有的可撤销只读分享）

## Created By

KIMI_CODE 布置，Step 5 实施（2026-10-26，用户批准计划 superman-hellcat-crystal）

## 目标

让登录用户把自己的已完成回测结果分享给他人只读查看，同时保持默认私有、链接可撤销、可设有效期、明文令牌只显示一次：

1. **最小 schema**：`share_links`（token_hash 唯一 / job_id ON DELETE CASCADE / owner_id / expires_at / revoked_at / created_at + 两个索引）；不要 token 明文/前缀、guest_key、last_used_at。应用层按现有 information_schema + 进程 guard 懒自愈建表；生产发布前必须由 postgres 幂等 apply `cloud_schema.sql`，避免表 owner/权限问题。
2. **令牌生命周期**：`secrets.token_urlsafe(32)`；库中只存完整 SHA-256(token + 现有 salt) 哈希；明文仅出现在创建响应。创建 URL `/saas/jobs/<job_id>?share=<token>`；校验只允许未撤销、未过期且 job_id 一致的记录。
3. **所有者管理 API**：创建（登录+本人+completed；游客 401、他人/不存在 404、未完成 409；有效期只接受 1/7/30/0 天，默认 7，服务端算 expires_at）；列表（仅本人最近 50 条，状态 active/expired/revoked，不回 hash/token）；撤销（仅创建者，重复/他人/不存在统一 404，立即失效）。
4. **公开只读通道**：`_require_completed_result` 在有效 `?share=` 时按 token 对应 job 放行只读（readonly_kind=share），不依赖登录或游客会话；无效/过期/撤销/错 job 不降级授权（匿名 401、登录他人 404，错误体与既有语义一致，不泄露任务或链接状态）。范围仅现有结果 GET；不开放 jobs/results 列表、用户策略 API 或 worker/console；generate 对 showcase 和 share 都 403；其余写端点仍只认原归属。
5. **未验证与 showcase 边界**：未验证历史结果允许所有者主动分享，合同徽标「旧口径·未验证」必须保留；showcase 仍只允许 verified；游客不能创建分享。
6. **UI**：job 页登录+completed+非公开只读显示「分享结果」（自定义模态选有效期、成功后代只读 input + 复制、明确只显示一次、不写 localStorage）；profile「我的分享」列表与撤销二次确认；分享视图 chip「只读分享」+ 中性返回文案，与 showcase 区分；隐藏取消/保存/信号/重跑/游客引导。

## 实施边界

- 不改回测引擎、worker 执行逻辑、结果数值、配额、NL A2/A3、策略库、默认私有语义；不跑真实回测；不做压测/性能/硬件；不做移动/App 专项（仅保持 375 不破版）；不 commit/push/部署 ECS。
- 游客每日清理 jobs 逻辑不改（CASCADE 自动清理孤儿分享）；showcase verified 门与 P0-2 游客隔离语义零变化。
- 复用既有自定义模态/淡紫组件与 Clipboard API，不新增依赖、不新增长篇灰字。

## Validation

- TDD 先 RED 后 GREEN：重点扩展 `tests/test_saas_access_hardening.py`（fixture 清理纳入 share_links），覆盖创建准入/存储形态/全端点绑定/过期/撤销/写保护/CASCADE/未验证/showcase 不变 + 前端 Node harness（job 分享流、只读文案分流、profile 列表与撤销、token 传播、localStorage 零痕迹）；`tests/test_gui_saas_pages.py` 三个既有 Node harness 补 shareUrl/shareSuffix/initShareButton 透传桩。
- 相关 22 个文件 655 passed；全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q`（2687 passed + 5 skipped，基线 2651+5，零回归）。
- 真实 Chromium（临时 PG + 8099 staging + seed/worker 协议模拟，不启动真实 worker/回测）：登录创建复制→匿名只读渲染→异 job/过期/撤销拒绝→profile 撤销二次确认；URL 不写 localStorage；零 JS error、零横向溢出；证据 `.tmp/readonly-share/`。
- `scripts/check-progress-docs.sh`、`scripts/git-finalize-check.sh`、`git diff --check` 通过；凭证扫描命中项均为 token 字段名/测试 dummy，人工核对无真实凭证；更新 04/05/06/08/09/10/11/14/16/17/19。

## Archive: QRE-SAAS-RESULT-UNDERSTANDING（P1 第二切片：结果理解、集中帮助与数据/费用口径）

## Created By

KIMI_CODE 布置，Step 5 实施（2026-10-25，用户批准计划 wonder-woman-medusa-psylocke）

## 目标

让普通用户能看懂回测结果，而不在结果页堆叠长备注：新增公开、集中的「使用说明」页，从结果页各模块精准跳转；同时补齐交易费用、数据截止和 VaR/ES 的关键口径。只整理和展示现有数据。

1. 新增 `GET /saas/help`（游客与登录用户均可访问，继承 base，不新增 API 或数据库表）：按 `#contract`/`#metrics`/`#benchmark`/`#fees`/`#risk`/`#attribution`/`#replay` 锚点分节，内容简明可扫描；合同口径文案由路由传入 `DAILY_RETURN_BASIS`/`TOTAL_RETURN_BASIS`（result_contract 常量同源，不复制权威口径）。主导航加入精简「使用说明」入口，沿用现有 active 状态和移动样式，不增加侧边悬浮按钮。
2. job/symbol 各模块标题区加入小型「说明 →」链接（合同/收益曲线/交易磨损/FRM/归因分别跳对应锚点；个股摘要数据截止跳 `#contract`）；job 收益曲线 tip 在 `renderContract(c)` 时用合同口径更新，无合同时保留静态回退；主指标仍保持 6 张，盈亏比只在帮助页与重播解释。
3. 五张交易磨损卡增加卡级提示（佣金/卖出印花税/过户费及其他残差含滑点/总磨损/磨损占买入成交额合计；毛收益=未扣费、净收益=扣除费用）；job 费率 chip 增加默认/自定义配置提示；`bench-bar` 增加基准含义提示；重播指标为盈亏比、持仓暴露度、当前持仓增加统一提示。全部复用 `LabUI.helpTips`，桌面重复 hover、键盘 focus、移动 tap 可用，不新增常驻灰字。
4. symbol worker gzip 与本地 fallback 两条返回路径都注入 `data_until`（不改 gzip 产物、不回填）；头部 `#sym-note` 显示数据截止并链接 `#contract`，缺字段显示「未声明」；VaR/ES UI 与 job/风险报告统一为损失正数，仅改显示符号，不改风险原值与计算。

## 实施边界

- 不改 schema、收益/风险/费用数值、回测引擎、worker 执行逻辑、配额、NL A2/A3；不运行真实回测；不做性能/容量/硬件/云迁移；不 commit/push/部署 ECS。
- 不新增主指标卡（第 7 张）、不重算指标、不改 `risk` 原值；帮助页不写营销文案、不堆灰字、不引入第四色相或新 JS 框架。
- 保留 P0 权限语义（默认私有、游客会话归属、showcase verified 公开只读）与结果合同语义（verified/unverified 分类、两种收益口径权威文案）。

## Validation

- TDD 先 RED 后 GREEN：`tests/test_saas_result_help.py`（新，17 例）+ `test_saas_help_copy.py`（+2）+ `test_saas_symbol_ux.py`（+2 API）+ `test_gui_saas_pages.py`（+1 Node harness）；P0-2/P0-1B 既有用例全保留。
- 相关套件 502 passed；全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q`（2651 passed + 5 skipped，零回归）。
- 真实 Chromium（临时 PG + 8099 staging + seed/worker 协议模拟，不跑真实回测）：帮助页锚点导航、模块深链、连续 hover/focus/tap、symbol data_until 与 VaR/ES 正号、1280/375 零 JS error 零横溢；证据 `.tmp/result-understanding/`。
- `scripts/check-progress-docs.sh`、`scripts/git-finalize-check.sh`、`git diff --check` 通过；更新 04/05/08/09/10/11/14/16/17。

## Archive: QRE-SAAS-FIRST-SUCCESS-UX-001（P1 首切片：回测等待状态、worker 离线提示与失败恢复）

## Created By

KIMI_CODE 布置，Step 5 实施（2026-10-25，用户批准计划 big-barda-red-tornado-ghost-rider）

## 目标

在不跑真实回测、不做压测/性能/硬件、不改数据库 schema 的前提下，把已有但未被公网使用的队列位置、worker 心跳和取消能力接到用户界面：

1. 统一任务运行态响应：`GET /api/saas/jobs/<id>` 与 `/api/results/<id>/summary` 的 409 共用一套只读口径（queue_position 仅 queued、worker_online 布尔）；409 增补 strategy_id/error_class/error_message/cancel_requested，failed 返回真实失败原因；不泄露 worker 细节。
2. new.html 准确表达等待：排队位置/离线提示/已等待时间进 wait-mask；单次 15s AbortError 继续轮询；HTTP 500/终态 fail-fast；80 轮上限是独立 PollTimeoutError（不冒充策略失败、不自动提交全量）；createJob 15s 提交超时。
3. job.html 队列/离线/取消/失败恢复：活跃任务取消（自定义模态二次确认，复用 P0-2 游客会话归属）；failed/expired 展示真实 error_message；登录用户可「按原策略重新回测」跳 `/saas/new?strategy=<id>`，游客仅返回新建页；showcase 只读零取消入口。
4. 可访问性与移动：wait-mask 状态文本 aria-live=polite，秒数行纯视觉；375px 无横溢、按钮 44px；不改设计 token/8080/18080。

## 实施边界

- 不改 schema、回测引擎、worker 执行逻辑、结果数值、配额、NL A2/A3；不启动真实 worker、不跑真实回测（浏览器任务全部 seed/worker 协议端点模拟）；不做压测/性能/硬件；不 commit/push/部署 ECS。
- 游客取消必须复用 P0-2 `qre_guest_sid`/guest_key 归属：同会话成功、异会话 401、缺失会话不得看到或取消旧任务；登录用户他人 404；匿名/他人/不存在语义不泄露存在性。

## Validation

- TDD 先 RED 后 GREEN：`tests/test_saas_first_success_ux.py`（21 例）+ `tests/test_gui_saas_wait_mask.py`（3 例）+ `tests/test_gui_saas_pages.py` 新增 25 例 Node harness；旧 fail-fast 用例的 body-pending 预期改为「超时后继续轮询」。
- 相关套件 + 全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q`（2627 passed + 5 skipped，零回归）。
- 真实 Chromium（临时 PG + 8099 staging + seed/协议模拟）：queued N/离线/running/failed 恢复、游客同会话取消与异会话 401、登录用户取消与原策略重跑回填、15s 临时超时重试恢复、桌面 1280 与移动 375，证据 `.tmp/first-success-ux/`。
- `scripts/check-progress-docs.sh`、`scripts/git-finalize-check.sh`、`git diff --check` 通过；更新 04/05/08/09/10/11/14/17。

## Archive: QRE-SAAS-ACCESS-HARDENING-001（P0-2 测试账号、结果 IDOR 与游客归属）

## Task ID

QRE-SAAS-ACCESS-HARDENING-001（P0-2 测试账号、结果 IDOR 与游客归属）

## Created By

KIMI_CODE 布置，Step 5 实施（2026-10-25，用户批准按统一 Todo 推进）

## 目标

1. 核查 ECS `SAAS_TEST_ACCOUNT_EMAIL/PASSWORD` 是否存在，只报告存在性，不输出凭证。若存在，备份 `/etc/qre-saas.env` 后移除/注释并重启验证正式 Authing/账号登录不受影响。
2. 枚举全部面向用户的 job/result/symbol GET 端点，补齐匿名与其他用户的 IDOR 测试：不得泄露任务存在性，统一既有 401/404 语义；showcase verified 公开行为不变。
3. 新游客结果从“纯 IP 归属”改为随机、HttpOnly、SameSite=Lax 的游客会话 Cookie 归属，防止同 Wi-Fi 互见。Cookie 缺失时由应用自动签发，密钥只用现有 salt，不明文存敏感信息。
4. 旧游客结果允许在原 guest_key 匹配时迁移一次到新随机会话；迁移后旧 key 不再作为新任务归属。明确历史同 IP 风险只限旧数据，新会话彼此隔离。
5. 默认私有、Authing、worker token、结果合同和 showcase verified 语义不变；主动分享留 P1，不做。

## 实施边界

- 使用现有请求/响应和用户鉴权链路，保持最小改动；数据库如需迁移必须幂等、可回滚。
- 不运行真实全量回测，不删除历史任务，不输出或提交任何凭证，不 commit/push/部署，待主 Agent 与用户验收。

## Validation

- 枚举端点清单与测试一一对应；匿名/其他用户/本人/不存在/公开白名单各分支通过。
- 两个独立游客会话结果互不可见；旧结果迁移一次后属新会话，其他会话不得访问；新游客任务不依赖 IP。
- ECS 测试账号只读检查与必要的安全配置修改有备份和正式登录验证。
- 相关与全量测试，真实 Chromium 双游客上下文与移动检查，证据 `.tmp/access-hardening/`。
- 更新 04/05/06/09/10/11/14/16/17/19（如涉及权限）和最终检查；不 commit/push/ECS 代码部署。
