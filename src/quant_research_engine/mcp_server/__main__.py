"""启动 QRE MCP：stdio 或 Streamable HTTP。"""

from __future__ import annotations

import argparse

from .server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="QRE Backtest MCP Server")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8093)
    parser.add_argument(
        "--public",
        action="store_true",
        help="公网多用户模式：每次工具调用使用客户端自己的 Bearer token",
    )
    args = parser.parse_args()
    if args.public and args.transport != "streamable-http":
        parser.error("--public 仅可用于 streamable-http")
    server = create_server(public=args.public)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        kwargs = {}
        if args.public:
            from mcp.server.transport_security import TransportSecuritySettings

            kwargs["transport_security"] = TransportSecuritySettings(
                allowed_hosts=["aguhuice.com", "www.aguhuice.com", f"{args.host}:{args.port}"],
                allowed_origins=["https://aguhuice.com", "https://www.aguhuice.com"],
            )
        server.run(transport="streamable-http", host=args.host, port=args.port, **kwargs)


if __name__ == "__main__":
    main()
