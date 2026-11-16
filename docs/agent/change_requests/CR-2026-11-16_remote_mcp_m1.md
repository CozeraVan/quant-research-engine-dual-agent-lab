# CR-2026-11-16 · Remote MCP M1 公网只读接入

## 范围

- M0 已提交 `a8fedfb`。本轮新增公网多用户 Bearer 透传、独立 ECS `qre-mcp.service` 和 nginx `/mcp`。
- 客户端必须携带自己的 `qre_agent_*` token；服务端不保存共享 token，不把 token 写入日志或配置仓库。
- 仅五个只读工具；validate 不建任务。不开放 M2 回测提交，不新增计费或配额。

## 验收

- 公网无 token 的工具调用失败，合法 token 才能访问既有 API。
- 不同 token 不串联会话或结果；上游继续执行 IDOR/scope。
- nginx 1MiB 请求体、60rpm、每 IP 5 连接；只代理 `/mcp`。
- 通用 MCP 客户端 initialize/list/call；千问真实接入若需平台侧配置则单独记录，不伪造通过。
