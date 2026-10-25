# Implementation Brief

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
