# CR-2026-11-16 · MCP Agent token 自助管理

## 根因纠正

SaaS 网页会话通过 `Authorization: Bearer <session>` 传递，不是 Cookie。此前诊断中的手工 `fetch` 未使用页面的 `apiFetch`，因此 401 是探针构造错误，不是登录系统缺陷。不得据此改认证代码。

## 范围

个人中心新增 MCP 接入页：创建 token、有效天数、仅夜间开关、单次明文/复制/清除、列表和吊销。复用既有 `/api/agent/v1/tokens*` 和 9090 `_agent_api_console_view`，不新增权限模型、配额或数据库字段。

## 验证

- 224 项相关测试通过，13 项既有跳过。
- 真实登录浏览器创建 token id=2，明文长度正常但内容未读取/记录；清除后列表吊销成功。
- 页面截图 `.tmp/mcp-token-self-service.png`（WebBridge 实际返回路径保存在其输出日志）。
- 仅 profile.html 部署 ECS，qre-saas active；未跑新回测。
