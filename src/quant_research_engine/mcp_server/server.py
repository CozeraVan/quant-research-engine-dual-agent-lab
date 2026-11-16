"""QRE 回测 MCP 工具。"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.mcpserver import Context, MCPServer

from .client import AgentAPIClient, AgentAPIConfig, AgentAPIError, DEFAULT_BASE_URL, normalize_base_url

DISCLAIMER = "本研究结果仅供研究使用，不构成投资建议。"


def _bearer_token(ctx: Context) -> str:
    headers = ctx.headers or {}
    authorization = headers.get("authorization", "")
    if not authorization.lower().startswith("bearer ") or not authorization[7:].strip():
        raise AgentAPIError("请在 MCP 客户端配置自己的 QRE Agent Bearer token", code="unauthorized")
    return authorization[7:].strip()


def create_server(client: AgentAPIClient | None = None, *, public: bool = False) -> MCPServer:
    private_client = client or (None if public else AgentAPIClient(AgentAPIConfig.from_user()))

    def api_for(ctx: Context) -> AgentAPIClient:
        if private_client is not None:
            return private_client
        return AgentAPIClient(AgentAPIConfig(
            base_url=normalize_base_url(os.environ.get("QRE_API_BASE_URL", DEFAULT_BASE_URL)),
            token=_bearer_token(ctx),
        ))

    server = MCPServer(
        name="qre-backtest",
        title="QRE A股回测研究",
        version="0.2.0",
        instructions=(
            "提供 A 股日线策略校验、异步小样本回测与结果读取。"
            "提交前先校验；提交后立即返回 sweep_id，使用状态工具轮询。"
            "图表数据可能较大，仅在用户明确需要时读取。" + DISCLAIMER
        ),
    )

    @server.tool(description="读取回测规模、预计耗时、资源消耗和默认容量限制。")
    def get_capabilities(ctx: Context) -> dict[str, Any]:
        return api_for(ctx).request("GET", "/capabilities")

    @server.tool(description="读取策略 StrategySpec 的 JSON Schema，用于生成可校验的策略 YAML。")
    def get_strategy_schema(ctx: Context) -> dict[str, Any]:
        return api_for(ctx).request("GET", "/schema/strategy")

    @server.tool(description="校验策略 YAML 和回测参数并估计成本；不会执行回测或消耗提交配额。")
    def validate_strategy(yaml: str, params: dict[str, Any], ctx: Context) -> dict[str, Any]:
        return api_for(ctx).request("POST", "/validate", {"yaml": yaml, "params": params})

    @server.tool(description="创建回测研究会话和计算预算；此操作本身不执行回测。")
    def create_research_run(
        title: str,
        boundary_text: str,
        budget: dict[str, Any],
        ctx: Context,
    ) -> dict[str, Any]:
        return api_for(ctx).request("POST", "/research-runs", {
            "title": title,
            "boundary_text": boundary_text,
            "todo": [{"step": 1, "what": "通过 MCP 执行小样本回测并读取结果"}],
            "budget": budget,
        })

    @server.tool(description="提交一个异步 screen 小样本回测；须先校验并创建研究会话。立即返回 sweep_id，不等待完成。")
    def submit_backtest(
        research_run_id: int,
        yaml: str,
        params: dict[str, Any],
        idempotency_key: str,
        ctx: Context,
    ) -> dict[str, Any]:
        return api_for(ctx).request("POST", "/sweeps", {
            "research_run_id": research_run_id,
            "base_yaml": yaml,
            "grid": {},
            "params": params,
            "stage": "screen",
            "idempotency_key": idempotency_key,
            "labels": {"purpose": "mcp-backtest"},
        })

    @server.tool(description="查询异步回测及其子 job 状态；completed/failed/canceled 为终态。")
    def get_backtest_status(sweep_id: int, ctx: Context) -> dict[str, Any]:
        return api_for(ctx).request("GET", f"/sweeps/{sweep_id}")

    @server.tool(description="读取回测扫描的数值聚合；不提供投资解读。")
    def get_backtest_aggregate(sweep_id: int, ctx: Context, sort_by: str = "total_return") -> dict[str, Any]:
        from urllib.parse import urlencode

        allowed = {"total_return", "annual_return", "sharpe", "max_drawdown", "win_rate",
                   "trades", "avg_holding_days", "excess_return"}
        if sort_by not in allowed:
            raise AgentAPIError(f"sort_by 须为 {'/'.join(sorted(allowed))}", code="invalid_sort")
        query = urlencode({"sort_by": sort_by})
        return api_for(ctx).request("GET", f"/sweeps/{sweep_id}/aggregate?{query}")

    @server.tool(description="读取本人已完成回测的标准化结果摘要；job_id 为数字任务 ID。")
    def get_backtest_result(job_id: int, ctx: Context) -> dict[str, Any]:
        return api_for(ctx).request("GET", f"/jobs/{job_id}/result")

    @server.tool(description="按需读取本人回测的收益与回撤图表数据；响应可能较大。")
    def get_backtest_chart_data(job_id: int, ctx: Context) -> dict[str, Any]:
        return api_for(ctx).request("GET", f"/jobs/{job_id}/result/chart-data")

    return server
