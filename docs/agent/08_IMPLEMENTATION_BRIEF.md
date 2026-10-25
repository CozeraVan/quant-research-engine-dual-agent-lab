# Implementation Brief

## Task ID

QRE-SAAS-FIRST-SUCCESS-UX-001（P1 首切片：回测等待状态、worker 离线提示与失败恢复）

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
