# CR-2026-11-16 · 付费 Remote MCP 路线与只读 MVP

## 背景

用户希望把现有回测系统包装为可在千问等平台分发的付费 MCP 工具，并要求设计路线后开始实施。

## 决策

采用薄适配层复用 `/api/agent/v1/*`，不另写回测、权限或任务系统。首版 M0 只提供能力发现、策略 schema、免执行校验和结果读取；异步提交与计费分别留到 M2/M3。

## 影响面

- 新增 `src/quant_research_engine/mcp_server/` 与对应测试。
- 新增官方 `mcp` Python 依赖并更新 lockfile。
- 新增路线文档；不改既有 SaaS 路由、worker、数据库和回测产物。
- 不新增权限/配额，9090 无需新增展示项。

## 验收

- 模拟上游验证 Bearer 透传、URL 归一、超时、HTTP/JSON 错误和五工具响应。
- 使用 MCP SDK 客户端做真实协议 initialize/list/call。
- 无真实 token、无公网调用、无新回测。
