# QRE MCP 本地使用

首版提供五个只读工具：能力/成本发现、策略 Schema、免执行策略校验、回测摘要、图表数据。不会创建回测任务。

## 启动

需要先在 SaaS 创建外部 Agent token，并通过环境变量提供；不要把 token 写进配置仓库或命令行。

```bash
export QRE_AGENT_TOKEN='<你的 agent token>'
export QRE_API_BASE_URL='https://aguhuice.com'
uv run qre-mcp
```

stdio 客户端配置示例：

```json
{
  "mcpServers": {
    "qre-backtest": {
      "command": "/home/van/quant-workspace/quant-research-engine-dual-agent-lab/.venv/bin/qre-mcp",
      "env": {
        "QRE_API_BASE_URL": "https://aguhuice.com",
        "QRE_AGENT_TOKEN": "<你的 agent token>"
      }
    }
  }
}
```

## 本地 Streamable HTTP 冒烟

```bash
uv run qre-mcp --transport streamable-http --host 127.0.0.1 --port 8093
```

地址为 `http://127.0.0.1:8093/mcp`。当前 HTTP 模式只用于回环测试；公网部署、OAuth 和 nginx 限制属于路线 M1，不能直接把该端口暴露到公网。

## 工具说明

- `get_capabilities()`：查看规模档、预计耗时和容量限制。
- `get_strategy_schema()`：取得策略 YAML 的 JSON Schema。
- `validate_strategy(yaml, params)`：校验并估算成本，不执行、不建单。
- `get_backtest_result(job_id)`：读取本人已完成任务摘要。
- `get_backtest_chart_data(job_id)`：按需读取图表数据，默认上限 32MiB。

所有权限、任务归属、限流和免责声明由 `/api/agent/v1/*` 保持权威。历史回测结果不构成投资建议。
