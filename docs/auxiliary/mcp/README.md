# QRE MCP 本地使用

当前提供九个工具：能力/成本发现、策略 Schema、免执行策略校验、研究会话、异步小样本提交、状态、聚合、回测摘要、图表数据。提交固定走 screen，不开放全市场 confirm。

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

地址为 `http://127.0.0.1:8093/mcp`。

## 公网 Remote MCP

地址：`https://aguhuice.com/mcp`。客户端必须配置 HTTP 请求头：

```text
Authorization: Bearer <自己的 QRE Agent token>
```

公网服务不保存共享 token；每次工具调用由现有 Agent API 校验。无 token 或无效 token 的调用会被拒绝。普通 GET `/mcp` 返回 400/421 不代表服务异常，MCP 客户端需使用协议规定的 Accept/POST 流程。

## 工具说明

- `get_capabilities()`：查看规模档、预计耗时和容量限制。
- `get_strategy_schema()`：取得策略 YAML 的 JSON Schema。
- `validate_strategy(yaml, params)`：校验并估算成本，不执行、不建单。
- `create_research_run(title, boundary_text, budget)`：创建研究边界和计算预算。
- `submit_backtest(research_run_id, yaml, params, idempotency_key)`：提交单个 screen 异步回测。
- `get_backtest_status(sweep_id)`：轮询 sweep 与子 job 状态。
- `get_backtest_aggregate(sweep_id, sort_by)`：读取数值聚合，不生成投资解读。
- `get_backtest_result(job_id)`：读取本人已完成任务摘要。
- `get_backtest_chart_data(job_id)`：按需读取图表数据，默认上限 32MiB。

## 导出到本地电脑

Agent 在 MCP 中得到 completed 的 `job_id` 后，可调用本机命令保存紧凑结果包：

```bash
export QRE_AGENT_TOKEN='<自己的 agent token>'
export QRE_API_BASE_URL='https://aguhuice.com'
uv run qre-mcp-export 360 --output ./qre-results
```

输出为 `./qre-results/job_360/`，含 `local_manifest.json`、`result.json`、核心指标、收益/回撤、交易汇总和 HTML 报告。默认不下载逐股目录、图片和 Excel；每个下载文件校验上游 SHA-256，失败清理 partial，不覆盖已有目录。

此命令由用户本机 Agent 调用，远程 MCP 服务器不会直接写用户磁盘。当前不改变网页、云端产物和 TTL；本地导出不代表云端已删除，也不作为删除授权。

所有权限、任务归属、限流和免责声明由 `/api/agent/v1/*` 保持权威。历史回测结果不构成投资建议。
