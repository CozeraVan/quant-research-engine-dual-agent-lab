#!/usr/bin/env python
"""《我不是股神》Windows 预览启动入口：本地样本 + 真实游戏代码，零数据库连接。

用法（仓库根目录）：

    uv run python scripts/win/start-game-preview.py            # 默认 8091
    uv run python scripts/win/start-game-preview.py --port 8093

与 scripts/win/start-ui-preview.ps1 的 SaaS 预览相互独立：本入口只服务
/game（game.web.create_game_app），不创建 SaaS app，不读 SAAS_DB_URL，
也不读 QRE_MARKET_DB_URL —— 行情与因子全部来自 game_preview_sample 的
合成样本（store 契约与 tests/test_trading_game_web.py::FakeStore 一致）。
游戏逻辑、状态机、匿名揭盲、复权换算与审计跑的都是仓库真实代码。
"""

from __future__ import annotations

import argparse

from game_preview_sample import SampleGameStore

from quant_research_engine.game.data import PostgresGameDataProvider
from quant_research_engine.game.web import create_game_app


def main() -> int:
    parser = argparse.ArgumentParser(description="我不是股神 Windows 本地预览（合成样本，零 DB）")
    parser.add_argument("--host", default="127.0.0.1", help="只允许回环地址")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        parser.error("游戏预览只允许回环地址，禁止对外监听")

    provider = PostgresGameDataProvider(SampleGameStore())
    app = create_game_app(provider)
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    print(f"* 我不是股神 Windows 预览: http://{args.host}:{args.port}/game")
    print("* 数据源: 本地合成样本 scripts/win/game_preview_sample.py（零数据库连接）")
    app.run(host=args.host, port=args.port, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())