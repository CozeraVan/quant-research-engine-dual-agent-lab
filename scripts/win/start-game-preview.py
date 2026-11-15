#!/usr/bin/env python
"""《我不是股神》Windows 预览启动入口：本地样本 + 真实游戏代码，零数据库连接。

用法（仓库根目录）：

    uv run python scripts/win/start-game-preview.py            # 默认 8091 + 合成样本
    uv run python scripts/win/start-game-preview.py --port 8093
    uv run python scripts/win/start-game-preview.py --store-source /path/snapshot_store.py:SnapshotStore

与 scripts/win/start-ui-preview.ps1 的 SaaS 预览相互独立：本入口只服务
/game（game.web.create_game_app），不创建 SaaS app，不读 SAAS_DB_URL，
也不读 QRE_MARKET_DB_URL —— 默认行情与因子来自 game_preview_sample 的
合成样本（store 契约与 tests/test_trading_game_web.py::FakeStore 一致）；
--store-source / 环境变量 QRE_GAME_STORE_SOURCE 可切换到 WSL 交付的脱敏快照
同构 store（W5），供真实快照双视口审计复跑，零数据库连接。
游戏逻辑、状态机、匿名揭盲、复权换算与审计跑的都是仓库真实代码。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from game_store_source import load_store, resolve_source

from quant_research_engine.game.data import PostgresGameDataProvider
from quant_research_engine.game.web import create_game_app


def main() -> int:
    parser = argparse.ArgumentParser(description="我不是股神 Windows 本地预览（默认合成样本，零 DB）")
    parser.add_argument("--host", default="127.0.0.1", help="只允许回环地址")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--store-source", default=None,
                        help="module:Class 或 path/file.py:Class；默认合成样本（环境变量 QRE_GAME_STORE_SOURCE 同效）")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        parser.error("游戏预览只允许回环地址，禁止对外监听")

    source = resolve_source(args.store_source)
    # 候选池持久化（下一轮）：预览默认落本地 scratch 缓存，重启同日磁盘命中；
    # QRE_GAME_POOL_CACHE 可覆盖路径，设空字符串则关闭（纯内存）。生产路径由 WSL 接线。
    default_cache = Path(__file__).resolve().parents[2] / ".tmp" / "game-windows-dev" / "preview_pool_cache.json"
    cache_env = os.environ.get("QRE_GAME_POOL_CACHE")
    cache_path = (cache_env if cache_env is not None else str(default_cache)) or None
    provider = PostgresGameDataProvider(load_store(source), pool_cache_path=cache_path)
    app = create_game_app(provider)
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    print(f"* 我不是股神 Windows 预览: http://{args.host}:{args.port}/game")
    print(f"* 数据源: {source}（零数据库连接）")
    print(f"* 候选池缓存: {cache_path or '关闭（纯内存）'}")
    app.run(host=args.host, port=args.port, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())