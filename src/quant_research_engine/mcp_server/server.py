"""QRE 只读回测 MCP 工具。"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .client import AgentAPIClient, AgentAPIConfig

DISCLAIMER = "本研究结果仅供研究使用，不构成投资建议。"


def create_server(client: AgentAPIClient | None = None) -> MCPServer:
    api = client or AgentAPIClient(AgentAPIConfig.from_env())
    server = MCPServer(
        name="qre-backtest",
        title="QRE A股回测研究",
        version="0.1.0",
        instructions=(
            "提供 A 股日线策略校验、成本估计与既有回测结果读取。"
            "校验不会执行回测。图表数据可能较大，仅在用户明确需要时读取。" + DISCLAIMER
        ),
    )

    @server.tool(description="读取回测规模、预计耗时、资源消耗和默认容量限制。")
    def get_capabilities() -> dict[str, Any]:
        return api.request("GET", "/capabilities")

    @server.tool(description="读取策略 StrategySpec 的 JSON Schema，用于生成可校验的策略 YAML。")
    def get_strategy_schema() -> dict[str, Any]:
        return api.request("GET", "/schema/strategy")

    @server.tool(description="校验策略 YAML 和回测参数并估计成本；不会执行回测或消耗提交配额。")
    def validate_strategy(yaml: str, params: dict[str, Any]) -> dict[str, Any]:
        return api.request("POST", "/validate", {"yaml": yaml, "params": params})

    @server.tool(description="读取本人已完成回测的标准化结果摘要；job_id 为数字任务 ID。")
    def get_backtest_result(job_id: int) -> dict[str, Any]:
        return api.request("GET", f"/jobs/{job_id}/result")

    @server.tool(description="按需读取本人回测的收益与回撤图表数据；响应可能较大。")
    def get_backtest_chart_data(job_id: int) -> dict[str, Any]:
        return api.request("GET", f"/jobs/{job_id}/result/chart-data")

    return server
