"""家庭端《我不是股神》服务：按需直读本地只读行情库，仅监听回环地址。"""

from __future__ import annotations

import os

from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.settings import DatabaseSettings
from quant_research_engine.game.data import PostgresGameDataProvider
from quant_research_engine.game.web import create_game_app


def create_app():
    store = PostgresDataStore(DatabaseSettings.from_env())
    provider = PostgresGameDataProvider(
        store, pool_cache_path=os.environ.get("QRE_GAME_POOL_CACHE") or None,
    )
    app = create_game_app(provider)
    app.config["GAME_COOKIE_SECURE"] = os.environ.get("QRE_GAME_COOKIE_SECURE") == "1"
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8092, use_reloader=False)
