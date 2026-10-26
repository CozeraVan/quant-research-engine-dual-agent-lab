# Implementation Brief

## Task ID

QRE-SAAS-READONLY-SHARE（P1：默认私有的可撤销只读分享）

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
