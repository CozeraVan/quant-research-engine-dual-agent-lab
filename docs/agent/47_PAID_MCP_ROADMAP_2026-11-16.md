# 47. 付费 Remote MCP 路线（2026-11-16）

## 目标与边界

把现有 A 股回测能力包装为标准 MCP 服务，供千问、Claude、Cursor 等客户端调用。MCP 是协议适配层，不复制回测引擎，不直接访问数据库，不调用模型，不生成投资建议。

复用已上线的 `/api/agent/v1/*`：Bearer 令牌、scope、限流、日提交量、在飞上限、夜间窗口、研究预算、幂等键和结果权限仍由原 API 强制执行。首阶段不新增权限或配额，因此不另建管理台配置。

## 分阶段路线

### M0：只读 MCP MVP（本轮）

- 使用官方 Python MCP SDK，新增独立 `quant_research_engine.mcp_server` 包。
- 配置：`QRE_API_BASE_URL`、`QRE_AGENT_TOKEN`；令牌只从环境变量读取。
- 工具：`get_capabilities`、`get_strategy_schema`、`validate_strategy`、`get_backtest_result`、`get_backtest_chart_data`。
- 同时支持 stdio 与 Streamable HTTP；HTTP 默认只监听 `127.0.0.1`，公网鉴权与部署属 M1。
- `validate_strategy` 不执行回测、不创建任务、不计提交配额。
- 验收：模拟 HTTP 上游的工具级契约测试；SDK 客户端实际完成 initialize/list/call；不创建真实回测、不跑全量任务。

### M1：公网 Remote MCP 与客户端验收

- ECS 部署独立服务，nginx 仅转发 `/mcp`，不暴露 8081 或内部管理接口。
- 使用平台 OAuth 或用户自带 QRE token；不得把管理员 token 固化成公共凭证。
- 对 MCP 入口补充请求体、连接时长、并发和响应大小限制。
- 用千问及至少一种通用 MCP 客户端做真实 initialize/list/call 验收。
- 申请千问商店前确认第三方服务商入驻、计量、分成与结算条款。

### M2：异步回测提交

- 增加研究会话创建、screen 抽样提交、sweep 状态、聚合排名等工具。
- 回测必须返回 `sweep_id/job_id`，由客户端轮询；MCP 请求不得阻塞到全市场任务结束。
- 默认仅允许小样本；全市场由既有 `allow_full_market`、预算和夜间窗口控制。
- 增加用量反馈和可读错误，不在 MCP 层绕过既有容量闸。

### M3：商业化

- 套餐和计费优先按计算量（标的数 × 日期跨度 × 配置数）而非 MCP 调用次数。
- 状态查询和已保存结果读取免费或低价；校验免费；新回测消耗计算点数。
- 保留自有 Remote MCP + REST API 双入口；千问作为付费分发候选，Smithery/ModelScope/官方 Registry 作为发现渠道。
- 在真实结算条款、发票、退款和成本核算完成前，不对外宣称已支持自动分账。

### M4：规模化前置条件

- 计算、数据库和产物存储按既有上云方案同地域部署，不能依赖家庭 PC 与 SSH 隧道承接公开付费 SLA。
- 补监控、审计、账单对账、任务保留期、服务条款与风险提示。

## 平台事实边界

- 千问文档确认商店 MCP 可按量后付费，但第三方服务商结算规则需另行确认。
- Smithery 与官方 MCP Registry 可分发/发现，不等同于收款平台。
- RapidAPI 可商业化 REST API，再通过本 MCP 适配层接入 Agent 客户端。

## 本轮明确不做

不开放付费提交、不改价格/会员、不接支付、不申请商店、不新增生产数据库写入、不改回测引擎、不跑新回测。
