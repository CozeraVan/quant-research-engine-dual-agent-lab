"""启动 QRE MCP：stdio 或 Streamable HTTP。"""

from __future__ import annotations

import argparse

from .server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="QRE Backtest MCP Server")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8093)
    args = parser.parse_args()
    server = create_server()
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
