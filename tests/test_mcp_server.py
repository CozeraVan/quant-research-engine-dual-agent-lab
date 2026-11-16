from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest
import requests

from quant_research_engine.mcp_server.client import (
    AgentAPIClient,
    AgentAPIConfig,
    AgentAPIError,
    normalize_base_url,
)
from quant_research_engine.mcp_server.server import create_server


class FakeResponse:
    def __init__(self, payload: Any, status: int = 200, headers: dict[str, str] | None = None):
        self.payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.content = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def json(self):
        if isinstance(self.payload, bytes):
            raise ValueError("not json")
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.response


def make_client(response: FakeResponse) -> tuple[AgentAPIClient, FakeSession]:
    session = FakeSession(response)
    config = AgentAPIConfig(base_url="https://example.test/api/agent/v1", token="secret-token")
    return AgentAPIClient(config, session=session), session


def test_normalize_base_url():
    assert normalize_base_url("https://example.test/") == "https://example.test/api/agent/v1"
    assert normalize_base_url("https://example.test/api/agent/v1/") == "https://example.test/api/agent/v1"
    with pytest.raises(ValueError):
        normalize_base_url("file:///tmp/qre")


def test_client_sends_bearer_and_parses_json():
    client, session = make_client(FakeResponse({"ok": True}))
    assert client.request("GET", "/capabilities") == {"ok": True}
    call = session.calls[0]
    assert call["headers"]["Authorization"] == "Bearer secret-token"
    assert call["url"] == "https://example.test/api/agent/v1/capabilities"
    assert call["timeout"] == 30


def test_client_surfaces_upstream_error_without_leaking_token():
    client, _ = make_client(FakeResponse(
        {"error": {"code": "not_found", "message": "结果不存在"}}, status=404
    ))
    with pytest.raises(AgentAPIError) as caught:
        client.request("GET", "/jobs/9/result")
    assert caught.value.code == "not_found"
    assert "secret-token" not in str(caught.value)


def test_client_rejects_non_json_and_large_response():
    client, _ = make_client(FakeResponse(b"not-json"))
    with pytest.raises(AgentAPIError, match="非 JSON"):
        client.request("GET", "/capabilities")
    client, _ = make_client(FakeResponse({"ok": True}, headers={"Content-Length": "99999999"}))
    with pytest.raises(AgentAPIError, match="大小限制"):
        client.request("GET", "/capabilities")


def test_all_tools_map_to_agent_api():
    client, session = make_client(FakeResponse({"ok": True}))
    server = create_server(client)
    tools = server._tool_manager._tools
    assert set(tools) == {
        "get_capabilities", "get_strategy_schema", "validate_strategy",
        "get_backtest_result", "get_backtest_chart_data",
    }
    tools["get_capabilities"].fn()
    tools["get_strategy_schema"].fn()
    tools["validate_strategy"].fn(yaml="signal: {}", params={"random_n": 2})
    tools["get_backtest_result"].fn(job_id=7)
    tools["get_backtest_chart_data"].fn(job_id=7)
    assert [(c["method"], c["url"].split("/api/agent/v1")[-1]) for c in session.calls] == [
        ("GET", "/capabilities"), ("GET", "/schema/strategy"), ("POST", "/validate"),
        ("GET", "/jobs/7/result"), ("GET", "/jobs/7/result/chart-data"),
    ]


def test_stdio_initialize_and_list_tools():
    import os
    env = {
        **os.environ,
        "QRE_AGENT_TOKEN": "test-only",
        "QRE_API_BASE_URL": "https://example.test",
    }
    code = r'''
import os
import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command="python", args=["-m", "quant_research_engine.mcp_server"], env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            assert len(result.tools) == 5
            print("MCP_STDIO_OK", ",".join(sorted(t.name for t in result.tools)))

anyio.run(main)
'''
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30, env=env
    )
    assert result.returncode == 0, result.stderr
    assert "MCP_STDIO_OK" in result.stdout
