# Review Report

## Current Release

PASS + RELEASED（2026-10-26 用户验收通过，QRE-SAAS-NL-A2A3 含管理台同步，已 commit/push + ECS）：持久限频、版本化编译缓存与 9090 管理台同步。发布前复核全量 2753 passed + 6 skipped；公网两次纯编译 cache_hit false→true、YAML 一致、未创建回测，overview nl 字段与执行常量/两表计数一致。以下保留各任务自审记录。

## Task ID

QRE-SAAS-NL-A2A3（持久限频与版本化编译缓存 + 管理台同步）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS + RELEASED（2026-10-26 用户验收通过，已 commit/push + ECS）。发布前复核全量 2753 passed + 6 skipped；生产两表/授权/文件哈希与服务状态核实，公网纯编译两次与管理台 overview 验证通过。

## Self-Review Findings

- 业务语义零漂移：游客每日 10 次与 403/code=guest_nl_limit 文案不变；会员「每日不限」保持，仅新增 6 次/分钟防突发（429/nl_rate_limited/reset_seconds）；admin 不限；`gui/nl_compiler.py` 编译/纠错/YAML 校验未改一行。
- 缓存只存 ok=true 完整结果（yaml/warnings/corrections/fix_attempts 保真，无 cache_hit、无 API key）；失败/not_configured 不缓存；命中不调用 LLM 也不占配额，miss（含失败）才计数，无绕过路径。
- 计数原子性：单条 INSERT … ON CONFLICT DO UPDATE … WHERE hits < limit RETURNING；16 并发游客请求实测 10×200 + 6×403；计数跨 app 实例/重启持久（PG 行）。
- 同 key `pg_advisory_xact_lock(hashtext(key))`：3 并发同 key 只调用 1 次 LLM 且只消耗 1 次配额；不同会员不同 key 双 LLM 调用可同时进行（不串行）。
- R-ADMIN-001 同源：管理台 overview 的 nl.guest_daily/member_minute 直接读执行常量（测试用 monkeypatch 改常量验证 API 即时跟随），计数读两表真实行；管理台展示与执行不可能脱节；管理员鉴权（匿名 401/会员 403）不变。
- 权限与不泄露：游客 subject 复用既有 `_guest_key(ip)`（sha256(guest:ip:salt) 截断），会员 `sha256("nl:user:"+uid+salt)` 截断，均不落原始 IP；不公开缓存列表；DB 故障时游客回退既有文件计数、会员 503 fail-closed，不悄悄放开限流。
- 连接池安全：配额与缓存同在锁事务单连接执行，消除「持锁再取连接」死锁；16 并发不再出现 QueuePool 超时。
- UI 纪律：console 新卡仅用 metric-card + tip-trigger + title，无 `.opt`/灰色小字（Node harness 与静态断言双重锁定）。
- 证据链完整：`.tmp/nl-a2a3/`（red=24 errors → green=23 passed+1 skipped、related、full、staging HTTP、public-verification）与 `.tmp/nl-console/`（red 4 failed → green 24 passed、related 206、full 2731+6、HTTP+Node harness、public-verification）。

## Required Fixes

无。待用户人工验收；不通过立即恢复 `/tmp/qre-nl-a2a3-pre-20261026/` 与 `/tmp/qre-nl-console-pre-20261026/` 并重启 qre-saas。

## Task ID

QRE-SAAS-SHARE-ABSOLUTE-URL（分享链接补全公网域名）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS + 已部署待人工复验，未 commit/push（2026-10-26）。最终全量 2703 passed + 5 skipped；生产完整 URL 创建、公开读取与撤销通过。

## Self-Review Findings

- 用户链接本身有效，未误删或撤销；先用 API 与真实 Chromium 证明只读通道正常，再修相对 URL 的展示/分发缺陷。
- 公网 base 由显式 `SAAS_PUBLIC_BASE_URL` 配置，避免反代 scheme/Host 推断错误；本地无配置时保留 request.url_root 回退。
- access_hardening 68 passed，全量 2703 passed + 5 skipped；生产创建返回 `https://www.aguhuice.com/...`，公开页面 200、撤销 200，临时数据清理。

## Required Fixes

无。

## Task ID

QRE-SAAS-SHARE-SEQUENCE-GRANT（分享创建 HTTP 500 权限热修）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS + 已部署待人工复验，未 commit/push（2026-10-26）。最终全量 2702 passed + 5 skipped；生产真实创建/撤销均 HTTP 200。

## Self-Review Findings

- 生产日志直接证明缺少序列 USAGE，表 CRUD 权限原本存在；未从前端或结果操作卡猜测修复。
- schema GRANT 采用角色存在检查的幂等 DO 块，既修复 postgres-owner 生产库，也不破坏本地临时库 apply。
- 全量测试另发现 showcase 新库缺表；补齐与既有应用层完全同构的 showcase/showcase_daily 后，先前失败用例与全量均通过（2702+5）。
- 真实生产 API 创建/撤销均为 200，临时 session/link 清理，share_links=0；schema 哈希一致，未跑真实回测。

## Required Fixes

无。

## Task ID

QRE-SAAS-CLASSIC-ACTIONS-UI（经典策略按钮与结果操作卡精修）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS + 已部署待人工验收，未 commit/push（2026-10-26）。相关 10 文件 289 passed + access_hardening 66 passed，全量 **2701 passed + 5 skipped**（基线 2689+5，零回归）；真实 Chromium 9/9 零 JS error 零横向溢出；ECS 三文件与 HEAD 基线一致、备份 `/tmp/qre-classic-actions-pre-20261026/`、仅重启 qre-saas；公网验证通过。验收通过后才可 commit/push。

## Self-Review Findings

- **边界遵守**：未改 API/schema/引擎/worker/数值/权限；`box-actions`/`box-share`/`btn-save-lib`/`btn-signal-open`/`btn-signal-confirm`/`action-status`/`signal-panel`/`sig-univ-*`/`btn-share`/`share-status`/分享模态全部 ID 保留；保存/信号/分享三个 API 与状态回填、`actionsBound`/`shareBound` 防重绑不变；radio/select/scope 值不变。showcase subtitle 为内容保留。
- **R-UI-001**：改动区域（外层结果操作卡内含两组与信号面板、showcase 页头与 CTA 卡）零 `.opt`/muted/`--faint`/小字号灰字；解释全部走 `tip-trigger + data-tip + LabUI.helpTips`（页头只读提示、CTA 复现提示、外层结果操作提示、扫描范围 T+1 提示共 4 处新增问号，真实浏览器 hover 均出完整文案）。showcase 全页仅剩 subtitle 一处 `.opt`（策略内容，计划明确保留）。
- **可见性矩阵**（Node 完整脚本段 + 真实浏览器双证）：保存+信号+分享、仅分享（无 strategy_id）、游客、showcase 只读四形态外层卡显隐正确；连续两次 poll 与失败重试后 4 个按钮 click 监听均为 1；`syncResultActionCard` 对缺失元素不抛错。
- **按钮层级与触控**：保存/确认信号=主按钮、信号/分享=次按钮（真实浏览器 computed class + 高度 44px×4 与 CTA 44px）；375px 零横溢、CTA 全宽纵排。
- **回归**：P0-2/P0-1B/只读分享/帮助文案/参数提示/信号/首成功/等待遮罩/symbol 既有用例全保留（3 处既有断言随行为更新：只读隐藏清单、readonly harness、share 透传桩、readonly marker）；临时 staging 与临时库未清理（供复跑），生产零临时数据。
- **检查脚本**：`scripts/check-progress-docs.sh` 通过、`git diff --check` clean；`scripts/git-finalize-check.sh` 的凭证扫描命中均为既有标识符 `saasToken()`（函数名含 token 子串，出现在本次改动的 init 分支行）与 CSS 注释「token 与按钮体系」——人工核对无真实凭证，按既往惯例未改产品代码规避扫描。

## Required Fixes

无。

## Archive: QRE-SAAS-UI-DECLUTTER-001（结果页口径展示与说明页导航精简）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS + RELEASED（2026-10-26 用户批准提交并部署；实现 `8accb66` 已 push + ECS；全量 2689 passed + 5 skipped，真实 Chromium 6/6；未跑真实回测）。公网五个页面 200，合同标签与帮助深链删除标记为零，六文件哈希一致。

## Self-Review Findings

- 三处合同/新旧口径展示均已移除，模板中无 `contract-badge`、`contract-note`、`contractBadge` 或新旧标签残留；API、历史分类、showcase verified 与分享权限不变。
- job/symbol 不再包含 `/saas/help#`，但 tip-trigger、曲线口径和费用/风险说明仍保留，未误删核心解释。
- 帮助页桌面侧栏与 20px 标题、375px 双列静态导航经真实 Chromium computed style 验证；七锚点可跳转，零 JS error、零横向溢出，截图已复核。
- TDD RED=9 项后转绿；相关 138 passed，全量 2689 passed + 5 skipped。无 schema/API/引擎/worker/数值改动，临时 staging/数据库已清理。

## Required Fixes

无。

## Archive: QRE-SAAS-READONLY-SHARE（P1：默认私有的可撤销只读分享）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS + RELEASED（2026-10-26 用户批准提交并部署；实现 `08b4a27` 已发布；最终全量 2688 passed + 5 skipped、真实 Chromium 12/12；未跑真实回测）。生产复核新增 showcase 边界回归：显式无效/撤销 share 不得回退公开 showcase，无参数 showcase 保持公开；公网 job58/74 验证通过，临时链接已清理。

## Self-Review Findings

- **范围铁律逐条核对**：回测引擎、worker 执行逻辑、结果数值、配额、NL A2/A3、策略库、默认私有语义均未触碰；未启动真实 worker、未跑任何回测（浏览器任务由 seed + 真实 POST /api/jobs + worker 协议端点 claim/result/meta 模拟）；无压测/性能/硬件/移动 App 专项内容（仅 375 验证不破版）。
- **Schema 最小化已核对**：`share_links` 列集 = id/token_hash/job_id/owner_id/expires_at/revoked_at/created_at（测试以 information_schema 精确集合锁定）；无明文/前缀/guest_key/last_used；`job_id ON DELETE CASCADE`，游客每日清理 jobs 逻辑零改动即无孤儿（测试删 job 后 share_links 为空）。
- **令牌只存哈希已核对**：`token_hash` 为 64 位十六进制且等于 `sha256("share:"+token+salt)`（测试逐字重算）；两条链接 hash 不同；明文只出现在创建响应（测试断言响应无 token_hash 字段、DB 行序列化不含明文）；列表响应字段集锁定、无 token 痕迹。
- **不降级授权已核对**：无效/过期/撤销/错 job token 一律走原有匿名 401 / 登录他人 404 分支，错误体与「不存在/他人」逐字节一致（测试 deepEqual 锁定）；`_ensure_share_links` 失败（生产未 apply schema）时读取侧按无效 token 处理、创建侧 503，不放宽任何访问。
- **公开只读范围已核对**：分享通道只放行现有 7 个结果 GET；`/api/results`、`/api/jobs*`、`/api/saas/strategies|signals|me|share-links`、console、worker 在带 share token 的匿名请求下全部 401（测试逐一锁定）；generate 对 share/showcase 都 403（文案区分，showcase 原文不变）；delete/cancel/save/watch 仍按原归属。
- **未验证与 showcase 边界已核对**：未验证结果（无 result_contract）可被 owner 分享，summary 的 `result_contract.verified=false`、`label=旧口径·未验证` 原样返回（API 测试 + 浏览器徽标截图）；showcase verified 门零变化（`test_showcase_verified_public_readonly`/`test_showcase_unverified_not_public` 原样通过）；游客创建 401。
- **前端纪律已核对**：分享链接不写 localStorage（Node harness 计数器 + 浏览器 `Object.entries(localStorage)` 双重锁定）；一次性链接只在创建模态出现；复制走 Clipboard API 失败回退手动选择；分享视图隐藏取消/保存/信号/下载/游客引导，chip 与返回文案按 readonly_kind 分流（showcase 文案回归锁定）；profile 撤销二次确认且 revoked/expired 无撤销按钮。
- **测试卫生**：RED 先于实现（65 errors：fixture TRUNCATE share_links 即失败）；全量 2687 passed + 5 skipped（基线 2651+5，+36 新例，零回归）；`test_gui_saas_pages.py` 三个既有 harness 只加透传桩（token 传播由专用 harness 覆盖），未改任何既有断言语义。

## Required Fixes

无。

## 复核修正记录（2026-10-26，自查发现并已在实现中修正）

1. `_ensure_share_links` 首次 CREATE 失败后不能永久返回可用：拆「已尝试」与「可用」两个进程级状态，失败后持续返回 False（分享创建 503、读取按无效 token），避免生产未 apply schema 时误放行。
2. 有效期 allowlist 严格化：拒绝 `1.5`/`"7"`/布尔（`int()` 静默取整会把 1.5 变 1），只接受整数 1/7/30/0。
3. 过期用例改为全表置过去时间，避免「取最新一条」的歧义。
4. 浏览器审计三处脚本问题（非产品缺陷）：相对 URL 补 BASE 前缀；异 job token 断言改用匿名上下文（登录所有者访问本人任务本就 200，不构成越权）；撤销按 `#{job_id}` 定位行（列表倒序，first 行是另一条链接）。

## 主 Agent 截图复核 Required Fixes（2026-10-26，2 项，已聚焦修正并补回归）

1. **公开只读页全局游客条未隐藏**：分享页顶部仍显示 base.html 的 `#guest-strip`（「游客模式…注册/登录」），与「游客引导全部隐藏」的报告表述不符，且对匿名接收者是误导。已修正：job.html 公开只读分支隐藏清单加入 `guest-strip`（showcase 与 share 都适用）；分享视图在脚本解析时（`SHARE_TOKEN` 存在）即隐藏，消除摘要返回前的闪现；`symbols.html`/`symbol.html` 分享视图同样处理；base 游客条逻辑与撤销/无权页行为零改动。回归：Node readonly harness 两 kind 断言 `guest-strip` hidden + marker；真实 Chromium 以 `getComputedStyle` 断言 share 桌面/移动/showcase 三处 `display=none`（新增 showcase 用例与截图）。
2. **分享时间直接展示 ISO 微秒**：创建成功 modal 与 profile「我的分享」原样输出 `2026-10-27T00:35:53.414386+08:00`，不符合全站时间显示。已修正：新增 `fmtShareTime` 统一走既有 `LabUI.fmtLocalTime`（本地 `YYYY-MM-DD HH:mm`，无微秒），LabUI 缺失回退原值（不编日期），NULL=永久。回归：两个 Node harness 注入与 lab-ui.js 同实现的 LabUI 桩，断言本地可读格式且不含 ISO/微秒；新增缺失回退与「永久有效」用例；浏览器同步断言并截图复核（modal「有效期至 2026-10-27 00:57」、profile「2026-10-26 00:57」）。
3. 复跑：`test_saas_access_hardening.py` 66 passed、相关 23 文件 656 passed、真实 Chromium 12/12 零 JS error 零横溢；`share-job-1280.png` 顶部已无游客条。未 commit/push/ECS、未跑真实回测、无格式化 churn。

## Archive: QRE-SAAS-RESULT-UNDERSTANDING（P1 第二切片）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS + RELEASED（2026-10-25 用户批准提交并部署；实现 `9fd3b3d` 已发布；全量 2653 passed + 5 skipped、真实 Chromium 10/10；未跑真实回测）

## Self-Review Findings

- **范围铁律逐条核对**：schema（`cloud_schema.sql` 零改动）、收益/风险/费用数值、回测引擎、worker 执行逻辑、配额、NL A2/A3 均未触碰；`replay.js` 只改指标卡呈现结构（4 列加 tip），`frameMetrics` 纯逻辑零改动；symbol 仅把 `pct(-var)` 改为 `pct(var)`（显示符号），`risk` 原值与 FRM 计算未动；未启动真实 worker、未跑任何回测（浏览器任务由 seed + 真实 POST /api/jobs + worker 协议端点 claim/result/meta 模拟）。
- **不新增第七张主指标卡已核对**：`renderMetrics` 仍产出 6 张卡（测试以 `body.count("card('") == 6` 锁定），盈亏比只出现在帮助页与重播指标；job.html 静态文本不含「盈亏比」。
- **合同口径单一权威已核对**：帮助页两种收益口径由 `DAILY_RETURN_BASIS`/`TOTAL_RETURN_BASIS` 注入（测试断言与常量逐字一致）；`renderContract` 用合同字段更新曲线 tip，无合同时保留模板静态回退（harness 锁定不清空）。
- **权限与合同语义零变化已核对**：`/saas/help` 不触碰任何数据端点；symbol detail 的 `data_until` 只在已通过 `_require_completed_result` 归属校验后返回（匿名 401/他人 404/不存在同体/showcase verified 公开只读语义由 `test_saas_access_hardening.py` 与 `test_saas_result_contract.py` 原样通过）；未验证历史结果仍不公开。
- **提示组件复用已核对**：所有新提示走 `[data-tip]` + `LabUI.helpTips` 文档事件委托（动态重绘无需 refresh）；卡片/标签加 `tabindex=0` 支持键盘；真实 Chromium 连续 3 次 hover、focus、移动 tap 均给完整文案，二次 tap 关闭；未新增常驻灰字（帮助页 `class="opt"` 仅 1 处免责）。
- **移动端硬门槛已核对**：375px 三页零 JS error、零横向溢出、顶栏导航单行（末项 right=368≤375）；期间发现并修复真实缺陷——第 5 个导航项使登录态顶栏溢出 14px，修法为 ≤400px 断点 `gap:0`+logo 24px+11.5px（未动桌面渲染）；审计断言改为对比固定视口宽以规避移动模拟撑大 innerWidth 的漏报。
- **测试卫生**：RED 先于实现（19 失败证据存档 `.tmp/result-understanding/red-evidence.txt`）；全量 2651 passed + 5 skipped（基线 2629+5，零回归）；未改动任何既有断言语义（仅 symbol harness 补 `esc` helper 桩）。

## Required Fixes

无。（主 Agent 复核提出的 1 项 Required Fix 已于 2026-10-25 聚焦修正并补回归，见下。）

## 复核修正记录（2026-10-25）

1. **过户费/其他重复计入（symbol worker 回传分支）**：`wear.other_cost = total_cost − commission − stamp_tax` 已含 `transfer_fee` 与滑点残差（与 job `fees_summary.other_cost` 同口径），模板却再叠加 `w.transfer_fee`，导致双算（夹具显示 1.00 元，正确 0.50 元）。已改为只显示 `w.other_cost`；runner、费用原值、总磨损零改动；本地 fallback 分支（按订单拆分的 `过户费合计`）保持现状。回归 `TestSymbolWearNoDoubleCount`（RED：实际 1.00 元 → GREEN：0.50 元 + 勾稽校验）+ `test_saas_symbol_ux.py` 数据契约断言；真实 Chromium 重跑 symbol 页确认 12.80 元且 42.10+28.40+12.80=83.30，证据 `.tmp/result-understanding/`（`red-double-count.txt`、`green-double-count.txt`、`browser-evidence.json`、截图）。

## Archive: QRE-SAAS-FIRST-SUCCESS-UX-001（P1 首切片）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS + RELEASED（2026-10-25 用户批准 commit + push + ECS；实现 `a84a9a3` 已发布；全量 2629 passed + 5 skipped、真实 Chromium 12/12；未跑真实回测）

## Self-Review Findings

- **范围铁律逐条核对**：schema（`cloud_schema.sql` 零改动）、回测引擎、worker 执行逻辑、结果数值、配额、NL A2/A3 均未触碰；未启动真实 worker、未跑任何回测（浏览器任务全部由 seed SQL 与 worker 协议端点 claim/heartbeat/fail/status 模拟）；无压测/性能/硬件内容。
- **不泄露 worker 细节已核对**：新增响应字段只有 `queue_position`（计数）与 `worker_online`（布尔）；测试用 `home-secret-worker` 作 worker_id 断言新字段不含其名称。`_job_view` 既有 `leased_by` 字段为 P0 前既有契约，本次未扩大暴露面（不改既有字段）。
- **权限语义零变化已核对**：409 增补字段只对「已通过归属校验」的调用方可见（匿名/他人/不存在仍在 `_require_completed_result` 入口 401/404 且错误体逐字节一致，测试锁定）；showcase verified 公开只读 200 不变；游客取消与 GET job 同一归属函数（`_guest_identity`），异会话/无 Cookie 401 且与不存在同体，登录用户他人 404。
- **取消防重复与终态已核对**：queued 取消成功即 `clearPollTimer`；running 只置 `cancel_requested`（最终状态以服务端为准，UI 明示）；`cancelInFlight` + 按钮 disabled 双闸；终态 409 既有行为保留（测试锁定）。
- **不误报失败已核对**：单次 15s AbortError → 继续轮询（旧测试的「body pending 必须立即失败」预期已按计划改写）；HTTP 500/无权限/终态仍 fail-fast；80 轮上限是独立 `PollTimeoutError`，冒烟超时走 `pipeStopAt`（无「失败」前缀、有任务页入口、不提交全量）；「策略在小样本上没跑通」仅保留给真实终态失败。
- **不虚构数据已核对**：等待态只渲染 queue_position / worker_online / 已等待时间；测试断言文案 JSON 不含 `%` 与「预计」。
- **可访问性与移动已核对**：wait-mask title/sub aria-live=polite、秒数行 `.wm-meta` aria-hidden 且无 aria-live（轮询 3~5s 刷新不会每秒朗读）；375px 实测取消按钮 44px、零横溢；禁 ESC/禁背板/keepMask/spinner 停转/reduced-motion 既有语义有用例锁定；未动设计 token、8080/18080。
- **测试卫生**：RED 先于实现（15 + 14 失败证据存档）；`workers` 表加入新测试 fixture TRUNCATE（避免心跳跨用例污染在线判定）；游客第二个任务用 smoke（不占每日 full 配额）。

## Required Fixes

无。（主 Agent 复核提出的 4 项 Required Fixes 已于 2026-10-25 聚焦修正并补回归，见下。）

## 复核修正记录（2026-10-25）

1. `pipeStopAt` 中性化：去掉 `fail` 类（移除 doing/fail + `.pipe-st`「后台等待中」文案），前台等待超时不再显示红色失败态；`pipeFailAt` 失败红态仅保留给真实失败。回归 `test_pipe_stop_at_is_neutral_not_failure` 锁定不加 fail、有任务页入口、不写「失败」。
2. `jobWaitStatus` 离线提示扩展至全部活跃态（queued/leased/running/uploading；终态不读）；`pollJob` 终态抛出优先取后端 `error_message`。回归覆盖 4 活跃态、终态不读离线、真实 error_message 与无该字段时的回退。
3. wait-mask `apply` 仅在 title/sub 文本实际变化时写 DOM——aria-live 不再被每轮轮询重复触发；meta（秒数）照常更新；API 与既有语义不变。回归用 textContent 写计数器锁定（未变 0 写、变化 1 写）。
4. 浏览器取消模态截图证据修正：截图前等待可见与动画稳定，断言 computed display（flex/none）、bounding box、按钮可见与尺寸（确认钮 102×38 ≥36px），桌面/移动/登录用户三处一致；截图已肉眼复核模态清晰可见，`browser-evidence.json` 记录上述事实（不再只报 class 计数）。
5. 文档格式化 churn 已清除：04/08/09/10 的历史标题层级恢复为与 HEAD 一致（纯新增，无批量重排）；09 归档的 P0-2 Release Status 同步为已发布事实（`0799890`，不再写"待部署"）。

## Archive: QRE-SAAS-ACCESS-HARDENING-001（P0-2）

## Task ID

QRE-SAAS-ACCESS-HARDENING-001（P0-2）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS（实现、全量回归与真实 Chromium 通过；未 commit/push、未 ECS 代码部署，待用户验收）

## Self-Review Findings

- **凭证零输出已核对**：ECS 核查只用键名/计数/长度（email 20、password 24 字符）；
  「bypass 移除前生效」与「移除后失效」两次登录验证的凭证均以 ECS 端 shell 变量
  从备份文件取用、不回显；报告与文档只记录备份文件路径，不记录任何值。
- **归属改造最小侵入已核对**：新键与旧 guest_key 同形（32 hex）同列，`jobs` 表
  零 schema 变更（ECS app 账号非 owner 的 ALTER 坑完全绕开）；`_guest_identity`
  有 Cookie 必复用（不存在轮换/丢会话风险）；401/403/404/409 错误元组统一经
  `_with_guest_cookie` 补挂，配额 403 也带 Cookie（否则迁移后的归属浏览器拿不到）。
- **迁移边界已核对**：只读路径不迁移（防被动访客摘历史）；先迁移后计数（今日旧
  任务照占配额，无绕过）；guard 为进程级性能优化，UPDATE 本身幂等——复测临时
  staging 时「重建库不重启服务」会命中旧 guard（测试手法问题，已在报告记录为
  踩坑，单测 fresh app 全过）。
- **IDOR 矩阵已核对**：匿名对「他人任务」与「不存在」错误体逐字节一致（测试断言
  JSON 相等）；登录用户对两者 404 同体；showcase 未验证白名单项与未挂白名单同样
  401/404；`GET /api/jobs/<id>` 维持无公开通道（job 页数据走 results 系列，
  与既有行为一致，未扩大公开面）。
- **不变式已核对**：默认私有、Authing、worker token（错 token 401 有用例）、
  结果合同注入点、showcase verified 公开语义、409/404 业务语义、游客 NL 限流
  （IP 口径，有用例）全部未动；主动分享未做。
- **遗留（不阻塞）**：游客清 Cookie 可重获当日 1 次配额（软限额，持久限频属
  P1 NL A2）；console 游客统计口径变为 distinct 会话（预期略高于独立访客数）；
  ECS 部署新代码后 `SAAS_GUEST_COOKIE_SECURE=1` 才生效；users 表测试账号遗留行
  未清（无 password_hash，不可密码登录）；真人 Authing 端到端登录待用户验收。

## Verification Commands

```
.venv/bin/pytest tests/test_saas_access_hardening.py -q          # 31 passed
.venv/bin/pytest tests/test_gui_saas.py tests/test_gui_saas_pages.py \
  tests/test_saas_result_contract.py tests/test_gui_saas_console.py \
  tests/test_saas_authing.py tests/test_saas_feedback.py \
  tests/test_saas_signals.py tests/test_saas_worker_status.py \
  tests/test_worker.py -q                                        # 329 passed（相关）
.venv/bin/pytest tests/ --ignore=tests/data_test -q              # 2590 passed + 5 skipped
PLAYWRIGHT_BROWSERS_PATH=.tmp/ms-playwright \
  .tmp/browser-venv/bin/python .tmp/access-hardening/browser_audit.py   # 三上下文同 IP 全通过
```

证据 `.tmp/access-hardening/`；ECS 验证记录见 `05_PROGRESS.md` 与 `.tmp/access-hardening/report.md`。

---

# Review Report

## Task ID

QRE-SAAS-PARAMETER-TIPS-001

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS（参数提示与真实浏览器验收完成，全量 2536 passed + 5 skipped；用户批准本地 commit + ECS 部署，不 push）

## Holding Hotfix Review

真实 NL 抽查确认别名链接正确，但模型漏 holding/编造 999 导致编译不稳定。默认 0 的归一已覆盖缺段与编造值，明确期限保留，YAML 原文格式回归通过。staging `/api/saas/nl/compile` 的 MACD/RSI/BOLL/KDJ/MA 五例均 ok 且 `max_holding_days: 0`，未运行回测；报告 `.tmp/factor-registry/nl-holding-default-report.json`。

## Findings

- **契约零改动是本任务唯一高风险面，已逐项核对**：canonical `schema.table.column`
  未被改写（`configs/factor_registry.json` 只新增语义层，不动数据库列名）；YAML、
  `usedFactors()`、`readGroup()`、`snapshotWzArea()`、固定值切换、策略还原、
  price basis 归一全部未触。`/api/saas/factors` 只增 `zh/canonical/price_basis/aliases`
  四个字段，`label` 保留，旧 metadata 缺字段时前端回退 label（Node VM 用无新字段的
  旧 fixture 跑了全部既有弹窗用例，13 passed 证明回退路径未回归）。
- **发现并修复三个真实缺陷**：①`stock_daily_momentum_average_price` 等表的
  category/price_basis 曾因生成器循环变量泄漏而全部错记成最后一张表的属性，导致
  `macds` 的消歧默认到了错误口径——改为从 `tables` 段读取；②`_family_from_text` 用全部
  族别名全量当识别词，使 `macd_signal_12_26_9` 被误判成 MACD 快线（正确行为是交回旧别名字典
  子串兜底）——改为识别词只取 abbr/zh_base/规则显式声明项，且识别词之外的剩余
  部分不得含英文字母；③`alma`/`sqz`/`stc`/`psar` 等族的中文名把 `0_0_85` 这类下划线参数
  渲染成 `0.0.85`，改用 `zh_params` 只显示主参数，参数细节留在 canonical。
- **不伪造中文名**：未维护条目 `zh` 记 null（`build_factor_groups` 测试显式断言），
  `coverage_report` 如实输出 554/895（61.9%）与 341 条未注册清单；`gen_factor_catalog_llm.py`
  与 `sync_saas_metadata.py` 导出时都打印覆盖报告，漏注册不会静默。
- **别名不膨胀 Prompt**：`COMMON_FACTOR_TARGETS` 由注册表 core 条目（25 条）派生，
  测试断言 `20日指数移动均线`/`MACD(12,26,9)` 等规则生成别名不在 prompt 中且 prompt
  < 60000 字符。
- **歧义不猜**：`布林带`/`kdj`/`dmi` 均返回 candidates 且 canonical 为 None；
  `registry_resolve_column` 只在本表内替换，跨表只给候选（不偷偷改表）。
- **待用户复核的设计延伸**：族名未给参数时按该族默认周期处理并提示（MACD 12,26,9 为
  设计批准项，EMA/SMA/RSI 等为同口径延伸）。若不接受，可把这些族的 `default_params`
  置空并让裸族别名挂到全部常用条目上，即可改为返回候选。
- Required Fixes：无。

---


## Archive: QRE-GUI-POOL-MOM-004（「聚类动量」页 v3 历史回看：日期选择器 + 事后验证列 + 验证摘要条）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **无前视**：历史日 T 的榜单字段全部来自 `WHERE trade_date = :d` 单行截面
  （排名/共振/热力为组内截面计算）；post 列单独取 T 之后的数据且明确标注
  「事后」；detail/members 以 end_date/trade_date 截断到 T。表本身
  point-in-time（fwd_ret_w 只依赖 ≤T 数据），符合 R-QRE-003。
- **post 口径**：∏(1+fwd_ret)−1 over (T, T+w]，与 M7 v2 文档口径一致；
  不足 w 日或窗口含 None → NULL + 页面「未满窗口」注明（摘要条与列均有）。
- **摘要统计**：加速度 None 的池不进 Top N（避免污染），但计入全体对照；
  post 缺失各自剔除；全缺 → None 不炸（专项测试）。
- **性能**：post 查询限定 T 后 20 个交易日（先 DISTINCT LIMIT 20 再区间
  拉取），避免最早日期全表扫描；缓存键含 trade_date。
- **范围**：pool_momentum.py / app.py（2 路由加参透传）/ admin.html /
  测试文件；8081 零改动。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1929 passed, 4 skipped（1918 + 11 净增）
tests/test_gui_pool_momentum.py → 65 passed
node --check admin.html script → 通过
sudo -n systemctl restart qre-gui → active；curl /admin → 200
真库 /api/admin/pool-momentum?trade_date=2025-09-05：
  concept 加速度 Top10 post_5 均值 +0.19%（胜率 0.3）vs 全体 1064 池 +0.88%
  state Top10 post_5 均值 +0.64%（胜率 0.9）vs 全体 14 池 +0.95%
  2025-08-21：concept Top10 post_5 −1.92% vs 全体 −0.29%；Top1 赛马概念 post_20 +16.14%
detail end_date=2025-09-05 → 序列正确截断；members trade_date 生效
scripts/check-progress-docs.sh → passed；git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-SAAS-FACTOR-PICKER-MODAL（自选因子三栏弹窗选择器）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS（TDD RED→GREEN、相关回归与全量零回归、真实 Chromium 双视口 64/64 通过、ECS 已部署待用户验收）

## Findings

- 数据契约是本任务唯一高风险面。审查确认 `.wz-left`/`.wz-rfield` select 的类名、change
  监听、`readGroup()`/`snapshotWzArea()`/`usedFactors()` 读取路径完全未动，弹窗只通过
  `syncFactorSelect` + 一次 `change` 事件回填，不存在第二处策略状态。Node VM 用例对
  `collectWizardState()` 做了快照→还原深比较，确认还原值与快照逐字段相等。
- 实现审查中发现并修复一个真实缺陷：搜索后清空关键词切回三栏时，`#factor-picker-results`
  里残留的旧按钮仍留在 DOM（容器 `hidden`），会成为 Tab 焦点链的「末位」，导致焦点锁失效、
  Tab 把焦点带出弹窗。修复为切回三栏即 `res.innerHTML = ''`，同时焦点链过滤
  `[hidden]` 容器内的节点；两端都补了回归断言（Node VM 断言 results 子节点被清空，
  真实 Chromium 断言末位 Tab 回卷到关闭按钮）。
- 焦点返回原先用 `document.activeElement`，审查后改为直接持有打开弹窗的那个按钮元素，
  规避 Safari 点击按钮不自动聚焦导致焦点丢失的差异；真实浏览器两视口均验证焦点回到原按钮。
- 样式审查：全部使用既有主题变量，无第四种色相、无循环动效；`.factor-picker-field
  select{display:none}` 通过新增类名隔离，不影响 lab 侧 `lab.html` 的同名 `.wz-factsel`
  结构（lab 侧冻结未改）。
- 可访问性：`role="dialog"`/`aria-modal`/`aria-label`、按钮 `aria-haspopup` 与
  `aria-label`、打开即聚焦搜索、Esc 关闭、Tab 焦点锁、`:focus-visible` 紫环均在位。
- 无 Required Fix。

## Validation Evidence

```text
tests/test_saas_factor_picker.py                        10 passed
+ tests/test_gui_saas_pages.py                          83 passed
相关 SaaS 回归（7 个文件）                              242 passed
全量 pytest tests/ --ignore=tests/data_test            2474 passed, 5 skipped
真实 Chromium（桌面 1280x900 + 移动 375x812）            64/64 通过
Node 解析渲染后 new.html 内联脚本                       通过
check-progress-docs.sh / git-finalize-check.sh / git diff --check   通过
ECS：qre-saas active；new.html/lab-theme.css SHA256 本地=线上；
公网 /saas/new 200 且含全部弹窗标记；公网 CSS 与本地逐字节一致
```

未运行真实全量回测，未 commit、未 push；等用户实机验收与提交授权。

## Required Fixes

无。

---

---

## Task ID

QRE-SAAS-ACCESS-FALLBACK-T4-AUX-ACCESS-FIX（Task 4 复审剩余问题）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS

## Findings

- 附属模块 401/404 已与主列表整页无权路径分离：`showRecordsAuxAccess` 只替换对应 tbody 并保留重试，不调用 `clearRecordsTimer`、`abortRecordsLoad` 或 `.wrap.replaceChildren`。
- 两个模块的正常响应分支和 apiFetch 抛错分支均使用局部 helper；重试成功后按既有 loaded/loading 规则恢复内容。
- 主列表自身 401/404 仍调用整页 `showRecordsAccess()`，既有权限语义不变；500 局部失败与超时/epoch 逻辑未改。
- 测试覆盖主 DOM 节点引用、主 epoch、主请求 signal、单轮询 timer 与模块重试恢复，无 Required Fix。

## Validation Evidence

```text
RED: 1 failed, 63 deselected in 0.54s（实际命中整页 showAccessFallback 调用）
GREEN: 1 passed, 63 deselected in 0.49s
扩展回归: 167 passed in 17.23s
Node new Function: 三页 15 段内联脚本全部通过
git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-SAAS-ACCESS-FALLBACK-T4-REVIEW-FIX（Task 4 全部审查问题）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS

## Findings

- 主列表/profile/new 及两个附属模块的请求与 JSON body 消费均处于同一 controller/deadline；operation 与 cancellation 竞速，body 不响应 abort 也能在 15 秒后收口。new 非 2xx 在 consume 内先于 JSON 返回并立即抛错。
- 主 `load()` 的 epoch 与 controller 成对更新，旧 Promise 的渲染、catch、finally、附属初始化和调度均不能污染新轮次；手动重试可恢复。
- 策略库/因子申请仅在 HTTP 200、业务 ok、目标数组有效后渲染并置 loaded；失败保持未加载并显示本模块错误，后续主列表成功或本模块按钮可重试，401/404 走统一无权卡。
- 空态严格区分服务端 `items=[]` 与客户端筛选无匹配；既有单轮询 timer、5 分钟暂停和 80 次 new 轮询上限保留。
- 无 Required Fix。

## Validation Evidence

```text
RED 审查测试: 6 failed, 58 deselected in 1.41s（筛选测试修正 this 后单独仍按预期失败）
GREEN 指定页面: 64 passed in 7.11s
扩展回归: tests/test_gui_saas_pages.py + tests/test_gui_saas.py + tests/test_saas_symbol_ux.py → 167 passed in 17.25s
Node new Function: 三页 15 段内联脚本全部通过
git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-SAAS-ACCESS-FALLBACK-T4（SDD Task 4：回测记录/profile/new 小修）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS

## Findings

- 记录页不再顶层强制登录；`/api/results` 的 401/404 复用统一无权卡，其他 HTTP、业务 JSON 与解析失败复用加载失败卡，不再把失败渲染成空记录。仅 `200 + ok + Array.isArray(items)` 进入列表渲染，空数组才显示空态。
- 策略库与因子申请延后到首次列表成功，且由 `recordsModulesLoaded` 保证只初始化一次；失败响应不会触发附属模块请求。
- 每次加载与调度先清旧 timer；活跃集合包含 uploading，5 分钟到期暂停而非伪报失败，暂停卡与原刷新按钮都可手动恢复并复位等待起点。终态、无权与失败均停止自动刷新。
- profile 的 `/api/saas/me` 关闭旧 401 跳转并检查 `resp.ok`；new 注册链接复用 `saasLoginUrl()`，`pollJob` 对非 2xx、`!ok`、缺 `job` 立即抛错，80 次上限未改。
- 未改 job/symbol/base、公共 helper 或后端，showcase 与 `can_generate` 路径不受影响；无 Required Fix。

## Validation Evidence

```text
RED: 4 failed, 55 deselected in 0.85s
GREEN: 4 passed, 55 deselected in 0.88s
完整页面测试: 59 passed in 6.46s
Node new Function: /saas/、/saas/profile、/saas/new 共 15 段内联脚本全部通过
git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-SAAS-ACCESS-FALLBACK-T3-BODY-TIMEOUT-FIX（Task 3 响应体 pending 修复）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS

## Findings

- 根因已消除：统一 helper 在同一 controller/deadline 内等待 apiFetch 和 consume，consume 包含响应体读取/JSON 解析；不再在响应头到达时提前清 timeout。
- cancellation Promise 与 operation 竞速，手动 abort 和 deadline 都能收口；测试 body 故意永不响应 abort，三条链路仍可超时并重试。
- HTTP 优先语义保持在 consume 内：401/404 统一无权，主详情 404 仅为 `can_generate` 解析；404 body 的 AbortError 继续抛出，不误判为普通非 JSON 无权。
- epoch、旧 controller abort、15 秒/5 分钟双上限均未改变；只写不读的 `symbolPollInFlight`/`symbolLoadInFlight` 已删除，无行为替代。
- 无 Required Fix。

## Validation Evidence

```text
RED body pending: 3 failed, 52 deselected in 0.85s（三条链路均无剩余 timeout）
GREEN body pending: 3 passed, 52 deselected in 0.79s
状态机相关: 12 passed, 43 deselected in 2.06s
扩展回归: tests/test_gui_saas_pages.py + tests/test_gui_saas.py + tests/test_saas_symbol_ux.py → 158 passed in 16.37s
Node new Function: 渲染后的 symbol/base 3 段内联脚本全部通过
git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-SAAS-ACCESS-FALLBACK-T3-REVIEW-FIX（Task 3 审查问题修复）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS

## Findings

- 永久 pending 根因已消除：三条请求均有 AbortSignal 和明确超时，超时取 15 秒与 5 分钟剩余等待的较小值；5 分钟硬上限包含请求等待，超时显示加载失败并提供重试。
- 重试卡死根因已消除：新轮次先 abort 并释放旧 in-flight，poll/generate/load 独立 epoch 防止旧 catch/finally 清除新状态；连续重试只保留最新请求，无重复 timer。
- 旧 load 覆盖根因已消除：主 load 仅最新 epoch 可渲染，ready 与手动重试交叉时旧响应被忽略，重播初始化只发生在新一轮成功渲染。
- 三条请求均先分流 HTTP 401/404；主详情仅为 `can_generate` 解析 404 JSON，解析失败仍统一无权。500 与非 JSON 500 不误判权限，生成 POST 失败恢复按钮。
- 无 Required Fix。

## Validation Evidence

```text
RED pending/retry: 3 failed, 47 deselected → GREEN: 3 passed, 47 deselected
RED load epoch: 1 failed, 50 deselected → GREEN: 1 passed, 50 deselected
RED HTTP/JSON: 1 failed, 51 deselected → GREEN: 1 passed, 51 deselected
状态机相关: 9 passed, 43 deselected
扩展回归: tests/test_gui_saas_pages.py + tests/test_gui_saas.py + tests/test_saas_symbol_ux.py → 155 passed
Node new Function: 渲染后的 symbol/base 3 段内联脚本全部通过
git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-SAAS-ACCESS-FALLBACK-T3（SDD Task 3：个股详情与按需生成有限轮询）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS

## Findings

- 主详情、生成 POST、gen-status 均使用 `redirectOn401:false` 并处理 HTTP/JSON/网络异常；`404 + can_generate` 严格先于通用 401/404 无权分支，showcase GET 后端与只读语义未改。
- 主资源和轮询的 401/404 均复用统一无权卡，其他失败复用加载失败卡；仅替换 `.wrap` 内容并保存/恢复原节点，公共导航不受影响。
- 仅活跃生成状态续轮；ready/failed/none/unknown/401/404 都停止。生成请求失败与生成终态失败均恢复可点击按钮及明确文案。
- 连续异常 3 次和总等待 5 分钟均有上限；调度、重试、终态清 timer，`symbolPollInFlight` 防重入。超时显示暂停而非失败，重试不产生重复 timer。
- 测试用 Node `vm` 直接执行渲染模板中的真实状态机脚本，覆盖业务 404、权限、HTTP/JSON、全部终态、异常上限、5 分钟暂停与重复重试；无 Required Fix。

## Validation Evidence

```text
RED: tests/test_gui_saas_pages.py -k 个股状态机相关5项 → 5 failed, 43 deselected
GREEN: 同上 → 5 passed, 43 deselected
扩展回归: tests/test_gui_saas_pages.py + tests/test_gui_saas.py + tests/test_saas_symbol_ux.py → 151 passed
Node new Function: 渲染后的 symbol/base 3 段内联脚本全部通过
git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-SAAS-ACCESS-FALLBACK-T2-REVIEW-FIX（Task 2 审查问题修复）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS

## Findings

- Important 1 已修复：`consecutiveErrors=0` 移至 summary、chart/tag 和结果渲染整轮成功之后；completed 资源连续失败同样三次暂停，无无限 timer，重试入口保留。
- Important 2 已修复：`handlePollError` 通过 `summaryLoaded` 限定统一无权卡只服务 summary 主资源401/404；chart 404走加载失败，tag 404仍按无归因完成。
- Minor 1 已修复：`loadRisk` 关闭401自动跳转，所有网络/HTTP/JSON/render 异常在函数内捕获，仅替换风险区内容并提供重试，不误判整页权限。
- 行为测试直接执行模板提取的真实 JS，fake-fetch/fake-timer 无新依赖；覆盖审查指出的两类根因及风险区四类异常，不再仅依赖静态断言。
- 无 Required Fix。

## Validation Evidence

```text
RED: 新增3项行为测试 → 3 failed, 40 deselected（计数1≠3、chart404误报无权、risk offline rejection）
GREEN: 同上 → 3 passed, 40 deselected
指定回归: tests/test_gui_saas_pages.py + tests/test_gui_saas.py → 108 passed
扩展回归: 上述两文件 + tests/test_saas_symbol_ux.py → 146 passed
Node new Function: 渲染后的 job/base 3段内联脚本全部通过
git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-SAAS-ACCESS-FALLBACK-T2（SDD Task 2：job 详情状态机与 showcase 严格只读）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS

## Findings

- 主容器限定为 `.container`，401/404 仅替换主内容并保留公共导航；匿名 401、登录 404、本人 409 后端契约未改。失败与暂停均不把任务伪报为 failed。
- 单一 timer 在调度、重试、终态和无权出口均清理；`pollInFlight` 防重入。ACTIVE/TERMINAL 集合、5秒轮询、连续异常3次和活跃5分钟上限与 brief 一致。
- `tag-analysis` 仅 404 降级为无归因，其他 HTTP/JSON/网络异常进入失败收口。showcase GET 及 `can_generate` 业务 404 保持原语义。
- 前端 readonly 在结果操作初始化首行返回；后端写守护位于 `_require_completed_result` 之后、产物检查与任务插入之前，覆盖匿名和非所有者，所有者路径不受影响。
- 无 Required Fix。

## Validation Evidence

```text
RED: tests/test_gui_saas_pages.py + tests/test_gui_saas.py → 2 failed, 103 passed（状态机缺失；POST 409≠403）
GREEN: 同上 → 105 passed
扩展回归: 上述两文件 + tests/test_saas_symbol_ux.py → 143 passed
Node new Function: 渲染后的 job/base 3 段内联脚本全部通过
git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-SAAS-ACCESS-FALLBACK-T1（SDD Task 1：公共无权卡与安全登录回跳）

## Reviewer

KIMI_CODE（single agent self-review）

## Review Status

PASS

## Findings

- `_safe_saas_next` 与 brief 规则逐条一致；Authing next 只经 Flask session 暂存，callback 消费时再次校验，覆盖恶意 session 值回归测试。
- 公共 helper 使用 DOM API 与既有 `.card/.btn-primary/.btn-ghost/.opt`，未新增颜色或字体；`apiFetch` 默认行为兼容，关闭 401 跳转时仍清理失效 token 并抛出 `status=401`。
- 仅改 Task 1 指定后端、母板、登录模板与测试；job/symbol/records、showcase 和既有 401/404/409 语义均未改。
- 无 Required Fix。

## Validation Evidence

```text
RED: tests/test_gui_saas_pages.py + tests/test_saas_authing.py → 10 failed, 59 passed（功能缺失）
GREEN: 同上 → 69 passed
相关回归: 上述两文件 + tests/test_gui_saas.py → 133 passed
Node new Function: base+login 3 段、login_callback 1 段渲染后脚本全部通过
git diff --check → clean
```

## Required Fixes

无。

---

## Task ID

QRE-GUI-POOL-MOM-006（「聚类动量」页 v5 榜单可读性：横向滚动 + 首列 sticky + 精简列开关 + 详情面板上移）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **纯前端展示改动**：pool_momentum.py 零改动、零 API 契约变化、零 DB
  行为变化；精简列只是 CSS `display:none`（完整列 DOM 仍在，排序绑定
  不受影响），「展开更多列」可随时看全量数据——符合「默认一屏可读、
  完整数据可及」。
- **sticky 首列正确性**：热力行（tr 带 inline style）首列
  `background: inherit` 继承行背景保持热力连续；momTable 行改为仅
  heat 非空才输出 style 属性，避免空 style 匹配 `tr[style]` 导致首列
  透明穿底；斑马纹 even 行首列 var(--bg) 与普通行 var(--card) 分层；
  thead 角格 z-index 3 高于 tbody 首列 z-index 2。
- **colspan 随视图**：精简 concept 9 / state 13，全量 20 / 24，与两种
  模式的列数逐列数过一致。
- **详情面板位置**：DOM 序 mom-summary < mom-detail-panel <
  mom-concept（模板测试锁定）；旧底部 data-section="mom-detail" 区已删，
  #mom-detail/#mom-members id 唯一；关闭按钮隐藏 + 清空 + momMembers
  置 null；loadMomentumDetail 先 unhide + scrollIntoView 再拉数据，
  点其他池原地替换（复用既有 fetch 链路，无重复请求）。
- **排序回归**：momBindPoolLinks 的选择器按容器 id（#mom-concept/
  #mom-state / #mom-members）取后代 th.mom-sort，新增的 .mom-scroll
  包裹层不影响；momTh/momPctCell 的 cls 参可选，成员表调用零改动。
- **范围**：仅 admin.html / style.css（纯追加 v5 块）/ 测试文件；
  8081 零改动；既有 76 测试零改动全绿。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1942 passed, 4 skipped（1940 + 2 净增）
tests/test_gui_pool_momentum.py → 78 passed（+2：v5 模板标记 + CSS 断言）
node --check admin.html 内联 script → JS-OK
sudo -n systemctl restart qre-gui → active
curl 8080 /admin → 200，含 mom-detail-panel/btn-mom-cols/mom-col-x（24 处）
curl /api/admin/pool-momentum → ok，latest 2026-09-03，concept 1066 / state 14
curl /api/admin/pool-momentum/detail?pool_type=state&pool_key=量比:突增 → ok
```

## Required Fixes

无。

---

---

## Archive: QRE-GUI-POOL-MOM-003（「聚类动量」页升级 M7 v2 前瞻口径）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **口径切换完整**：速度/加速度（compute_acceleration metric="fwd_ret"）、
  热力（compute_heat 同参）、共振（resonance_flag 判 fwd_ret_w）、默认排序
  与窗口切换键（fwd_ret_w）四处全部落 fwd；回看 ret_w 仅展示对照
  （列名标「回看」），回看口径经 metric="ret" 仍可选并有测试锁定。
- **滞后处理**：末日 fwd 全 NULL 时不展示空白榜单——默认切到最近
  fwd 已补齐日 + fwd_lag 红色提示；全表无 fwd 的极端情形回退最新日、
  加速度/热力全 None 不炸（专项测试）。
- **事件列**：has_event 行级标记与 cluster-ashare M7 文档一致（仅
  selection_artifact=true 的 8 个状态池）；concept 分区无事件列；
  survive_3/5 末日 NULL 在声明卡注明。
- **只读边界**：仅 SELECT；无写库；8081 零改动；既有测试仅 fixture
  同步改 fwd 列（口径切换的预期更新），无逻辑删改。
- **范围**：仅 pool_momentum.py / admin.html / 测试文件；app.py 与
  style.css 本轮零改动。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1918 passed, 4 skipped（1909 + 9 净增）
tests/test_gui_pool_momentum.py → 54 passed
node --check admin.html script → 通过
sudo -n systemctl restart qre-gui → active；curl /admin → 200
真库 /api/admin/pool-momentum：
  latest_date=2026-08-31 / overall=2026-09-01 / fwd_lag=true（提示文案正确）
  concept fwd_ret_3 榜首「昨日打二板以上表现」+15.38%（heat3=1.0、共振=true）
  state：8 个 artifact 池 has_event=true（跳空:高开 win_rate_1=0.658），
        非 artifact 池 has_event=false
detail（state/连涨:3日）：250 日 fwd_ret 序列，末日 None（一日滞后）正常
scripts/check-progress-docs.sh → passed；git diff --check → clean
```

## Required Fixes

无。

---

## Archive: QRE-GUI-POOL-MOM-002（「聚类动量」页三项优化：池内个股明细 / 表头排序 / 行热力色阶）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **只读边界**：members 端点仅 SELECT（company_tags / daily_tags /
  stock_daily / stock_basic），无写库；名称查询独立 try/except 降级。
- **口径一致性**：`compute_member_metrics` 与 cluster-ashare M7 管线
  `compute_stock_metrics` 同语义（复权 close×adj_factor 比值、vwap 直接
  比值、近 w 日均量/近 50 日均量、窗口内缺行→None）；真库验证成员等权
  ret_3 与 cluster.pool_momentum_daily 池值**逐位相等**
  （0.017031048806369808），有效成员数 770 == n_stocks。
- **热力色阶**：分位口径（heat=2×分位−1）抗极值，并列共享（rank_desc
  同规则），None 与单有效值均降级 None；红涨绿跌符合 A 股惯例；「长弱
  短升」改左边框+加粗，与热力背景无冲突（旧背景 CSS 规则已移除并注释）。
- **排序**：前端 momGenericSort 与 Python sort_rows 同口径（None 恒末位、
  双向切换、当前列 ▼/▲）。
- **性能**：单池查询 ~数百股 ×51 交易日 × 一次 SQL，TTL 300s 缓存。
- **范围**：仅 pool_momentum.py / app.py / admin.html / style.css /
  测试文件；8081 零改动；既有测试零改动全绿。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1909 passed, 4 skipped（1888 + 21 净增）
tests/test_gui_pool_momentum.py → 45 passed
node --check admin.html script → 通过
sudo -n systemctl restart qre-gui → active
curl /admin → 200；/api/admin/pool-momentum/members 两池类型 → ok
  concept/华为概念：771 成员（770 有行情，== n_stocks），成员等权 ret_3 与池表逐位一致
  state/量比:突增：正常返回
scripts/check-progress-docs.sh → passed；git diff --check → clean
```

## Required Fixes

无。

---

## Archive: QRE-GUI-POOL-MOM-001（8080 管理台「聚类动量因子研究」tab，只读 cluster.pool_momentum_daily）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **只读边界**：pool_momentum.py 仅两条 SELECT（max(trade_date) + 当日截面
  / 单池序列），无任何写库语句；沿用 market_risk.py 的 _store/_cached/
  ok=False 自降级模式，表缺失/DB 挂返回降级 payload 不拖垮整页。
- **范围裁切**：`git diff --name-only HEAD` 仅 `gui/app.py`（+2 路由）、
  `gui/templates/admin.html`（+1 tab）、`gui/static/style.css`（纯追加 3 类）、
  新增 `gui/pool_momentum.py` 与 `tests/test_gui_pool_momentum.py`；
  8081（gui/lab*.py）零改动；既有测试零改动全绿。
- **口径一致性**：速度/加速度/长弱短升/共振四个纯逻辑口径在模块 docstring、
  页面声明卡、测试中三处一致（加速度=ret_50 排名−ret_3 排名；
  共振严格 >0；vol_chg_50 恒 0 已注明 50 日窗永不共振）。
- **偏差声明**：concept 池当前快照前视偏差、state 池 point-in-time、
  「不构成投资建议」均在页面顶部声明卡中（模板断言锁定）。
- **参数安全**：pool_type 白名单（concept/state），其余 SQL 全参数绑定。
- **JS 健壮性**：admin.html 单 <script> 块 node --check 过；detail 加载
  失败/空数据有降级文案；零新前端框架（复用 riskSvgLine inline SVG）。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1888 passed, 4 skipped（基线 1864 + 24 净增）
tests/test_gui_pool_momentum.py → 24 passed
node --check admin.html script → 通过
sudo -n systemctl restart qre-gui → is-active=active
curl 8080 /admin → 200，含 data-tab="mom" 与 /api/admin/pool-momentum（3 处）
curl /api/admin/pool-momentum → ok，latest=2026-09-01，concept 1066 / state 14
curl /api/admin/pool-momentum/detail（concept/华为概念、state/量比:突增）→ ok，250 日序列
```

## Required Fixes

无。

---

## Archive: QRE-GUI-LAB-ENTRY-018（8081 回测台「新增策略」tab 三入口递进重构：自然语言 / 快速向导 / 高级 YAML）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围裁切**：`git diff --name-only HEAD` 仅 `templates/lab.html`、
  `static/style.css`、`tests/test_gui_lab.py`；8080 模板（index.html/
  admin.html）与 app.py 零改动，`test_create_app_routes_unchanged`
  （lab⊂create_app、59 条专有规律互斥）原样通过。
- **规格映射核对**：三入口 tab（nl 默认 active / wizard / yaml）；
  NL 4 示例句含规格指定两句且点击填入；向导条件行 = 搜索下拉 →
  比较符（上穿/下穿/大于/小于/≥/≤）→ 右值（因子下拉 或 固定值勾选+数字）；
  入场/出场红色 * 必选且 buildYamlPreview 两组均强制；占位示例
  EMA5 上/下穿 EMA200（真库 /api/factors 实测含 ema_5/ema_200，
  JS 内置 close/pre_close 回退）；高级选项/高级参数两面板的默认值
  与 PORT-017 逐字段一致（佣金 0.0003、最低 5.0、印花税 0.0005 等不变）。
- **上穿/下穿语义**：编译为 `(l > r) and (l.shift(1) <= r.shift(1))`——
  表达式 DSL（evaluation/signals.py）实测支持 `.shift` 方法调用，
  比 nl_compiler 的"当日状态改写"更贴近用户直觉；右值为固定数字时
  shift 项退化为常量比较，无非法语法。
- **两步确认**：原有"存入沙箱 → 冒烟 → 晋升触发全量回测"流程不变，
  仅显性化——新增 #btn-save-smoke（第 1 步一键入箱+冒烟）、晋升按钮
  改「正式回测（晋升）」且 confirm 带冒烟指标摘要；无摘要时明示风险。
  后端 API 契约零变化（create/smoke/promote 参数与响应结构未动）。
- **零依赖**：搜索下拉为原生 JS（filter 输入重建 optgroup），
  无新前端框架/CDN；style.css 纯追加新类，既有规则逐字未动。
- **JS 健壮性**：三个 <script> 块 node `new Function` 语法自检全过；
  目录加载失败时向导显示中文错误并提示回退高级 YAML 通道；
  因子别名冲突 `_2` 后缀保证表达式唯一；usedFactors() 只收集条件
  实际引用的因子（未用不进 factor_fields）。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1808 passed, 4 skipped, 4 warnings（基线 1807 + 1 净增）
tests/test_gui_lab.py → 13 passed（含新 test_lab_strategy_three_entry_tabs）
node 语法自检：script 0/1/2 syntax ok
冒烟（qre-gui-lab 重启后）：
  systemctl is-active qre-gui-lab → active
  curl 8081 / → 200，含 data-entry-tab="nl"/"wizard"/"yaml"（18 处新结构命中）
  curl 8080 / → 200（8080 未重启，模板零改动）
scripts/check-progress-docs.sh → Progress docs check passed.
```

## Required Fixes

无。

## Nice-to-Have

- 向导下拉项 500+ 因子时下拉较长，可考虑后续加分页/常用置顶（本轮规格未要求）。
- NL 通道的 missing_factors 链接仍指向 8080「新增因子」概念（lab 无该 tab，
  沿用 PORT-017 已知留白）。

---

## Archive: QRE-GUI-LAB-PORT-017（回测台新端口移植：新增策略 + 回测管理两页面 → 独立 Flask 应用 @8081）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **8080 零行为变化（机械核对）**：新 create_app 的 url_map（rule+methods）
  与 git HEAD 版本逐条相等（59/59）；被搬走路由的函数体逐字不变，仅从
  create_app 闭包迁入 `strategy_lab_routes.register_strategy_lab_routes`，
  create_app 尾部调用同一函数。Flask endpoint 名随函数 __name__ 不变。
- **既有测试锚点兼容**：test_gui_strategy_create.py 把 monkeypatch 打在
  `gui.app.try_acquire_run_slot/release_run_slot/run_backtest`——app.py
  保持三符号 re-export，共享模块经 gui.app 命名空间调用时解析，
  该测试文件零改动通过（重构后首轮全量曾因此 14 errors，已修复复跑全绿）。
- **lab.html 原样性**：两个 tab 的 HTML/JS 由脚本按行号从 index.html /
  admin.html 精确切片组装（非手抄），含 QRE-GUI-SORT-016 排序 JS、
  搜索框、toggle/删除、gate/风险徽标；helpers（esc/fetchWithTimeout/
  cardError/isAbort）随 onboard JS 一并移植；两个 <script> 均为独立
  IIFE，无 DOM id 冲突。
- **范围裁切**：lab 不挂 /admin、/api/admin/overview、factor-create/*、
  builder/* 等 8080 专有路由（测试断言 lab⊂create_app 且专有规律互斥）；
  /runs、/runs/<id> 及 run artifact/risk-report API 一并在共享集内，
  保证新增策略 tab 的冒烟/回测/深度验证链接在 8081 可用。
- **运维**：qre-gui-lab.service enabled/active，与 qre-gui 并存互不干扰；
  base.html 顶栏「管理台 Admin」链接在 8081 上 404（指向 8080 功能，
  已知留白，待用户对齐优化方向时处理）。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1807 passed, 4 skipped, 4 warnings（基线 1795 + 12 净增）
路由集合核对：create_app() vs git HEAD → equal: True（59/59）
冒烟（两个 service 均重启后）：
  curl 8081 / → 含「新增策略」「回测管理」、data-tab strategy/onboard
  curl 8081 /api/admin/refresh → ok True, registered 0/118, stopped 118
  curl 8080 /api/admin/refresh → 同上（一致）
  curl 8081 /admin/strategy/bo01a_donchian_20_breakout → 200（8080 同 200）
  curl 8080 / → 200；curl 8080 /admin → 200
  curl 8081 /api/strategies/sandbox → ok true
systemctl is-enabled qre-gui-lab → enabled；is-active → active
```

## Required Fixes

无。

## Nice-to-Have

- lab 顶栏导航与 8080 的互链口径、页面标题/样式对齐等，留待用户明天
  对齐优化方向后处理（本任务明确只做移植）。

---

# Review Report (archive: QRE-DERIV-ADAPTER-013)

## Task ID

QRE-DERIV-ADAPTER-013（衍生品数据适配层：yc_curve/cb/opt 三个只读 loader + 示例管道）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §6 D1.5/D2.2/D3.2 行一一对应**：三个 loader + 示例管道 +
  单测；内核函数签名零改动，data/derivatives.py 是唯一直接读
  derivatives schema 的新代码（QRE 只读，无任何写库语句）。
- **口径披露齐全**：连续复利转换近似（yield%÷100 视为年复利）、8 节点
  插值近似、最近日回填 + latest_curve_date 披露、转债现金流四近似
  （常数票息/网格取整/面值到期/利差假设）、T=actual/365、parity 反推
  标的价——均写入 docstring、示例输出与 CR §11。
- **已知边界**：①库内无 ETF 日线（510050.SH 不在 stock_daily/
  index_daily），load_option_chain 标的价缺失时明确抛错引导传
  underlying_price，示例用 parity 反推（欧式近似）——缺口补数列后续；
  ②转债债底 vs bond_value 系统性差 −5.6~−9.5，主因到期赎回溢价
  106–115 未含（cb_basic 无赎回价字段），差异可解释，CR 验收本就
  「不求一致」；③平值隐波 call=put 同值（13.67%）是 settle 口径下
  parity 自洽的结果，非 bug。
- **测试纪律**：纯函数 11 个真单测；DB 冒烟 4 个按 QRE_MARKET_DB_URL
  skip（与仓库「单测不依赖真实库」惯例一致）；带库 15/15 绿。
- **偏差**：无 Required Fix。

## Validation Evidence

```
uv run pytest -q → 1795 passed, 4 skipped, 4 warnings（基线 1784 + 11 净增）
带库：QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data
  pytest tests/test_data_derivatives.py -q → 15 passed
冒烟：scripts/derivatives_adapter_smoke.py 2026-08-21 → 曲线 8 节点
  1.164%–2.110%；债底 5 只全正、spread_duration 1.00–1.98；
  50ETF 平值 K=3.0 call/put IV 13.67%（断言通过）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

## Nice-to-Have

- fund_daily（ETF 日线）入库后可去掉 parity 反推旁路；
- cb_coupon 精确票息与到期赎回价字段接入可收窄债底差异；均不阻塞本 CR。

---

# Review Report (archive: QRE-RISK-BAROMETER-M3-010)

## Task ID

QRE-RISK-BAROMETER-M3-010（大盘/板块风险风向标 M3：日更 timer + GUI 风向标页 + 阈值校准观察）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §5 M3 行一一对应**：deploy/hardened/qre-barometer.{service,
  timer}（Mon..Fri 18:30、Persistent、oneshot、沿用 qre-refresh hardened
  模板护栏；安装说明在头部注释，未 sudo）、barometer_job 默认最近交易日、
  `qre barometer` CLI、admin TIMER_UNITS + install_hint + daily_jobs
  PIPELINES 登记、/admin「大盘风险」tab（仪表盘/五序列 SVG/双口径
  热力表/预警详情）、阈值首轮校准观察入 06、CR 状态改 M1–M3 已完成。
- **纪律一致**：GUI 只读 market_risk.daily（cluster tab 同款 _store +
  _cached TTL 300s + 分区降级）；图表沿用项目 inline SVG 方案（客户端
  polyline，与 run_detail equity_svg 同思路），零新前端框架；
  timer/service 与现有 hardened 模板逐字段对齐（User/WorkingDirectory/
  Environment/Restart/MemoryMax/Nice/IOScheduling*/SyslogIdentifier）。
- **真实冒烟**：market_risk_overview 直连真库 ok——latest 2026-08-20、
  market 总分 63.3/green/5541 只、序列 252 日、行业 105（top 黄金 86.1）、
  簇 14（top 跳空:低开 breach 10.8%）。
- **阈值校准观察（06 已记录）**：1,850 日 red 11（0.59%，全为已知风险
  事件）、amber 219（11.8%）；corr 阈值 0.10≈P95、breach 阈值 3%≈P93；
  初值保留，若 amber 嫌多 breach 可上调 4–5%。
- **披露**：GUI 页面未经浏览器人工核对（qre-gui 未重启，用户约束）；
  timer 未安装（sudo 由主代理/用户执行）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1778 passed, 4 warnings（基线 1764 + 14 净增，全绿）
真实冒烟：market_risk_overview() 真库 ok（2026-08-20，63.3 green）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-BAROMETER-M2-009, 风向标 M2 数据装配与回填)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §5 M2 行一一对应**：barometer_job.py（唯一读写 DB 层：
  业务表只读，只写自有 market_risk schema）+ 单日/区间两模式 + 年分块
  312 交易日 buffer + 幂等 upsert + JSON 产物 + 真实回填 + 方向性验证。
  M1 内核零行为改动（仅 build_barometer indicators 增列 n_stocks 序列，
  纯增量）。
- **schema 决策**：独立 schema `market_risk`（QRE 产出与 cluster-ashare
  的 cluster schema 分空间；van 已验证 CREATE SCHEMA 权限；写库通道沿用
  cluster 日更同款 sqlalchemy engine + 事务，行级 ON CONFLICT 幂等）。
  表 `market_risk.daily(trade_date, scope, n_stocks, indicators/scores/alert
  jsonb, created_at)`，PK (trade_date, scope)，120 个 scope
  （1 market + 105 industry + 14 cluster tag）。
- **口径**：收益 = pct_chg/100（tushare 前收盘口径，与 cluster-ashare
  tags_daily 一致）；市值 = daily_basic.total_mv 行内归一化；行业静态
  映射（stock_basic.industry）；簇 = cluster.daily_tags 当日 tag→成员，
  <5 只跳过。簇行只出当日截面指标（scores=None + note 披露：成员逐日
  变动，252 日分数需固定成员历史，M2 不算）。
- **真实回填**：2019-01-02 → 2026-08-20，8 个年块（每块 312 交易日
  buffer），约 21 分钟单进程，220,034 行 / 1,850 交易日 × 120 scope；
  每日 JSON 产物 outputs/market_risk/<date>.json（共 1,850 个）。
- **方向性验证（CR §5 M2 硬要求，全过）**：market 行全样本分位对照——
  - 2020-02-03 疫情暴跌：突破占比 85.2%（P100）、总分 87.7（P99）、
    alert=red；次日 02-04 red。
  - 2024-01-29~02-05 微盘危机：总分 93.9–99.4（P99–100）、
    02-05 突破占比 58.6%（P100）、连续 red。
  - 常态对照 2023-06：总分 28–36（P10–21）、alert=green。
  - 全样本 red 共 11 天，全部为已知风险事件：2020-02-03/04/28（疫情）、
    2024-01-29~02-05、2024-02-28（微盘）、2024-10-09（国庆后回撤）、
    2025-04-07（关税暴跌）——方向性与选择性俱佳。
- **披露/已知边界**：2020-02-04 离散度 12.0（P100）为新股首日 ±44%
  无涨跌幅限制的极端收益所致（数据特征非 bug，等权标准差对离群敏感，
  如实披露）；回填期间单日冒烟发现 daily_basic 缺个别 BJ 股
  （920395.BJ 等）市值列，已修为 reindex 缺列补 NaN（加权时剔除）。
- **测试**：+10（分块边界/DDL/幂等 upsert SQL 与 NaN→None/簇 <5 跳过/
  端到端 monkeypatch 管线 + JSON 产物），全量 1764 绿。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1764 passed, 4 warnings（基线 1754 + 10 净增，全绿）
真实回填：2019-01-02→2026-08-20，8 chunks，220,034 行 / 1,850 日 × 120 scope，~21min
方向性验证：2020-02-03 red（breach 85.2% P100）、2024-02-05 red（score 99.4 P100）、
  常态 2023-06 green（score P10–21）；全样本 red 11 天全部为已知风险事件
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-BAROMETER-M1-008, 风向标 M1 纯函数内核)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §5 M1 行一一对应**：cross_section.py（EWMA 方差面板、
  截面波动率中位/90 分位、等权/市值加权离散度、滚动 60 日平均两两
  相关等权 + w_i·w_j 偶权近似、VaR 突破计数/占比）+ barometer.py
  （组合法封装复用 volatility/tail、252 日滚动分位分数、红/黄/绿
  预警、全市场+板块组装）+ constants 集中参数全回显 + 合成面板单测，
  全覆盖；M2 数据装配（barometer_job.py）按 CR 分期不做。
- **纪律一致**：两新模块纯函数零 DB；参数集中 constants.py
  （BAROMETER_CORR_WINDOW/SCORE_WINDOW/ALERT_*/BREACH_CONFIDENCE/
  CROSS_SECTION_SIGMA_QUANTILE）并全部在结果 dict 回显；既有 risk
  模块零行为改动（仅 __init__ 增列）。
- **数值自检**：EWMA 面板逐列 == volatility.ewma_variance_series
  （atol 1e-15，含 NaN 顺延对 dropna 语义）；两股面板平均相关 ==
  np.corrcoef（1e-12）；完全相关/反相面板均值 −1/3 手算；离散度
  等权 ddof=1 与加权 Σw(r−μ_w)² 手算核对；VaR 突破严格 r<−VaR 与
  backtest_var HIT 同口径；组合法 VaR/ES 与 tail 直接调用逐键一致；
  预警三态（green/amber×2/red）与阈值回显断言；warmup 降级 None
  不伪造分数；权重倾斜下等权 vs 市值加权组合序列差异用例。
- **披露**：加权平均相关为 w_i·w_j 偶权常规近似（非严格加权相关
  系数）；相关窗口内个股需完整 window 观测否则当日剔除；加权离散度
  未做 1−Σw² 集中度校正；预警阈值 +0.10/3% 为 CR 注明待校准初值；
  相关历史不足 20 日时 corr 判据不触发（None 披露）。

## Validation Evidence

```
uv run pytest tests/test_risk_cross_section.py tests/test_risk_barometer.py → 30 passed
uv run pytest tests/ -x -q → 1754 passed, 4 warnings（基线 1724 + 30 净增，全绿）
scripts/check-progress-docs.sh → passed
git diff --check → clean
注：全量首跑 test_gui_risk_report.py::TestRiskReportEndpoints::test_post_conflict_409
失败，单独 24/24 绿、全量复跑全绿（环境敏感 flake，同既往 test_job_lock_conflict 类）
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-PORTFOLIO-007, R7 组合层汇总)

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §2 R7 一一对应**：组合层汇总（risk/portfolio.py：股票腿
  R1–R4 收益序列法、债券/转债腿 DV01/KR01、期权腿组合 Greeks、可选
  DGV-VaR）、risk_report 扩展（可选 portfolio 节 + markdown 渲染）、
  GUI 卡片组（沿用 risk-card 模式，有节才显示）、晋升闸可选判据
  （默认关闭）全覆盖。
- **纪律一致**：portfolio.py 纯函数零 DB；参数集中 constants.py 并回显；
  既有 risk 模块零行为改动（仅 report.py 增加可选节 + __init__ 增列）。
- **向后兼容（专项测试覆盖）**：默认 run 产物零变化（收尾钩子不传衍生品
  键，top-level keys 测试未改动仍绿）；老格式 report（无 portfolio 节、
  老 meta 无 sections）markdown/GUI/闸三处均不炸；闸阈值默认 None 时
  evaluate_gate_risk 返回与 R4 逐键一致（set(risk) 断言）。
- **数值自检**：KR01 按节点加总 = 合并现金流单独跑 key_rate_shifts
  （rel 1e-12），kr01_sum ≈ 曲线口径 DV01（一阶恒等式 rel 1e-4）；
  债券聚合/期权 Greeks 加对手算；DGV-VaR 复用 R6 已验证内核。
- **披露**：DGV 需调用方显式给 spot/vol shock（组合层无标的价格水平）；
  kr01_sum 与 portfolio DV01 口径可不同不强制相等（并列披露）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1724 passed, 4 warnings（基线 1696 + 28 净增，全绿）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-OPTIONS-006, R6 期权内核 + DGV-VaR)

## Task ID

QRE-RISK-OPTIONS-006（FRM 风险管理模块 R6：期权计算内核 + DGV-VaR）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §2 R6 表一一对应**：options.py（BSM 无股息/q/离散股息、
  Black's、隐波 brentq、CRR 欧式+美式含 q、树第一层 delta、美式 Greeks
  数值差分、Greeks 全组含 q 版与期货期权版、组合 Greeks 加权）与
  derivatives_var.py（DGV 近似 P&L、正态/CF 分位、VaR 序列对接
  backtest_var_summary 复用 HIT/LR，未新造回测引擎）全覆盖；不做项
  （Heston/波动率曲面/LSM/奇异期权）未触碰。
- **纪律一致**：纯函数零 DB；参数集中 constants.py（IV_BRACKET/
  DEFAULT_TREE_STEPS/GREEK_SHOCK_SIGMA/GREEK_SHOCK_RATE）并全部在
  结果 dict 回显；既有 risk 模块零行为改动（仅 __init__ 增列）。
- **数值验收（CR §4 R6 行全部通过）**：BSM 教材例 d1=0.2001/
  d2=−0.1674/c=8.3069/p=7.9715 + parity 1e-10 自洽；隐波 7.00→25.14%；
  美式 put 教材节点值（A=3.058/B=0.494/C=5.699 行权/欧式 2.838）+
  收敛 20/50/100/500 → 3.082/3.067/3.059/3.055；PDE 恒等式
  （q=0 与 q 版 (r−q)SΔ 形式）1e-10；纯 gamma 组合解析二阶矩
  Var=½Γ²sS⁴ 核对；CF-VaR 对 MC 分位 rel 5%（偏度<0.5 适用域）；
  VaR 序列→backtest_var_summary 集成回测违约率 ≈1% 不拒绝。
- **教材参数溯源**：二叉树收敛例参数（S=29,K=30,r=3%,σ=25%,T=1）
  摘要未载明，已从教材原文 PDF p193 抽取确认（Figure 14.5/14.6
  及收敛段），注释写入测试文件头。
- **自审修正**：Black76 theta 首版符号错误（−r·c 应为 +r·f 结构），
  由有限差分自检测试发现后修正为 θ = r·f − F₀e^{−rT}N′(d1)σ/(2√T)，
  修正后五值全对有限差分（rel 1e-5）。
- **遗留/披露**：CF 在高偏度（纯 gamma χ² 型）下分位失真为已知限制
  （docstring+测试注明，矩核对不受影响）；DGV 的 δS/δσ 独立假设披露；
  CRR 树↔BSM 收敛测试容差 abs 3e-3（O(1/n) 振荡收敛性质）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1696 passed, 4 warnings（基线 1657 + 39 净增，全绿）
tests/test_risk_options.py + tests/test_risk_derivatives_var.py 单独 39/39 绿
scripts/check-progress-docs.sh → 待 docs 同步后运行
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-RATES-005, R5 利率与债券内核)

## Task ID

QRE-RISK-RATES-005（FRM 风险管理模块 R5：利率与债券计算内核）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **范围与 CR §2 R5 表一一对应**：rates.py（式 16.1–16.5 复利换算、
  PV/FV、spot↔折现因子、书4 Ch9 bootstrap、线性/对数线性插值、
  远期利率连续式与式 10.5、par yield 式 16.7/10.4）与 bonds.py
  （YTM brentq、式 9.2/30-360 应计利息、式 12.6 久期凸性、式 12.1/12.3
  effective、DV01 与 D↔DV01、组合聚合与对冲配比、式 12.4 二阶近似、
  书4 Ch13 KR01、书3 Ch16/17 转债债底与 spread duration）全覆盖；
  不做项（PCA/条款引擎/信用违约/互换期货）未触碰。
- **纪律一致**：纯函数、零 DB、零行情依赖；参数集中 constants.py
  （DEFAULT_DAY_COUNT/CURVE_INTERPOLATION/KEY_RATE_TENORS/
  RATE_SHOCK_BP/YTM_BRACKET）并全部在结果 dict 回显；day count 默认
  actual/actual 符合中国惯例约束；曲线统一连续复利零息利率口径并在
  docstring 披露。既有 risk 模块零行为改动（仅 __init__ 增列）。
- **数值验收（CR §4 R5 行全部通过）**：
  - 书4 Ch9 bootstrap：d = 0.991909/0.980944/0.969406/0.956909
    （实测 1e-6 内精确复现，另加折现回验自洽）；
  - par yield：2.2103%（式 16.7 手算一致）+ 平价债回验 100.0；
  - 平坦曲线连续年金解析解 P/D/C = 8.6394/4.7504/30.862（周网格
    离散逼近 rel<1e-2）；
  - DV01↔D 换算自洽（duration_from_dv01 = effective duration，1e-12）；
  - ΣKR01 = DV01（一阶，rel 3.5e-6 内，rtol 1e-4 自检通过）；
  - +100bp 平行移动二阶近似 vs 直接重定价 rel 偏差 1.9e-5 < 1e-3。
- **顺手修复**：pyproject.toml 补 scipy>=1.11.0 显式依赖（constants.py
  自 R1 起 import scipy 但未声明，CR §3 已点名）。
- **遗留/披露**：KR01 的 Σ=DV01 为一阶恒等式（二阶残差已写进 note 与
  测试容差）；插值域外平坦外推已披露；测试 3 处首版手算/口径错误
  （0.928597→0.928599、年金网格 int、spread duration 对比基准应为
  r+s 水平）已在实现内修正，非源码缺陷。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1657 passed, 4 warnings（基线 1605 + 52 净增，全绿）
tests/test_risk_rates.py + tests/test_risk_bonds.py 单独 52/52 绿
scripts/check-progress-docs.sh → 待 docs 同步后运行
```

## Required Fixes

无。

---

# Review Report (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004（FRM 风险管理模块 R4：晋升全量回测闸加入风险判据）

## Reviewer

KIMI_CODE (single agent self-review, per R-AGENT-001)

## Review Status

PASS

## Findings

- **改动最小、复用到位**：闸判据挂在唯一收口点
  `refresh_registry.gate_blocks_daily`（refresh_batch.py /
  list_catalog_strategies / refresh_overview 三处调用方零改动自动生效）；
  风险数据复用 R3 既有 `risk_report.load_risk_report` 与
  `runs/<run_id>/risk_report.json`，无新增存储、无 DB 访问。
- **判据语义符合任务书**：ES99 取历史模拟口径（经验日收益，非参数
  假设）阈值 3%（`risk/constants.py::GATE_ES99_MAX`，可调整）；VaR 回测
  取 99% 节覆盖率 Kupiec LR `reject_5pct`（与 ES99 同置信，
  `GATE_VAR_CONFIDENCE`）；主判据（交易≥30 且超额>0）逻辑零改动，
  warning 只影响 `gate_blocks_daily` 与 admin 徽标。unavailable（无
  report/损坏/run 失败）不阻断——专项测试覆盖。
- **force 通道**：warning + forced → 评估照跑、`forced` 透传、
  gate_blocks_daily=False（专项测试）；admin tooltip 注明「force 晋升，
  不阻止日更」。
- **存量兼容**：旧 gate json 无 risk 节 → `gate.get("risk")` 为 None，
  gate_blocks_daily 行为与 R4 前完全一致（test_gui_admin_p3b 既有用例
  未改动、全绿佐证）；admin 仅在 risk.status==='warning' 时追加徽标。
- **字段缺失健壮性**：老格式 report 缺 tail/var_backtest 键时子项记
  None、不触发 warning（evaluate_gate_risk 逐层 `or {}` 取值）。
- **偏差**：无 Required Fix。已知边界：①风险判据取 99% 单置信节
  （95% 节拒绝不触发 warning），与任务书「ES99 + VaR 回测」口径一致；
  ②独立性 LR 不进闸判据（仅报告层展示），因任务书只点名 Kupiec
  覆盖率；③run 失败时 risk=unavailable（此时 gate 已 failed 阻断，
  risk 维度无增量信息）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1605 passed, 4 warnings（2026-08-22，
  QRE-RISK-GATE-004；基线 1599 + 6 净增：test_gui_strategy_create.py
  R4 节 5 新 + test_gui_admin_strat_tab.py 徽标 1 新）
定向：tests/test_gui_strategy_create.py test_gui_admin_strat_tab.py
  test_refresh.py test_gui_admin_p3b.py → 103 passed（2.86s）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Required Fixes

无。

## Nice-to-Have

- 后续可考虑把 95% 节 VaR 回测也纳入判据、或对存量 gate 回填 risk 节；
  均不影响本次正确性，留待用户决策。


## 2026-10-24 FRM 回传优先级修复自审

- 改动仅限 `worker/runner.py::collect_result_files` 排序与一条回归测试；未改回传上限、计算口径或前端。
- RED→GREEN：新测试先复现 risk_report 被 100B 预算排除；修复后风险文件优先且 _symbol_details 次序保持。
- 验证：tests/test_saas_symbol_ux.py 38 passed；tests/test_worker.py + test_gui_saas.py + test_gui_risk_report.py 118 passed。另一次异步轮询测试偶发 404，单测复跑通过，最终组合复跑全绿。
- 历史回填不重跑回测；58/66 先重算修正口径 FRM，58/66/74 公网 API 已验证 has_report=true。
- Required Fixes：无。


## 2026-10-24 无权页最终修复自审补充

- job 请求与响应体统一超时、取消和 epoch；风险模块独立收口。
- 长等待只暂停不伪报失败；重复渲染的事件绑定和 resize 均幂等。
- showcase 只读不展示无效生成入口；new expired 不再无意义轮询。
- 最终相关回归（含提交检查脚本 2 例）228 passed；无 Required Fixes。真实浏览器矩阵未自动化，部署后由用户实机抽查。
- `git-finalize-check.sh` 只扫描新增 diff 行，不再把未修改上下文中的函数名或测试 stub 判为密钥；新增敏感赋值拒绝路径有回归测试。
