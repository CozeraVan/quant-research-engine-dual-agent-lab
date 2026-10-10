#!/usr/bin/env python
"""重新生成 NL 编译用真实因子目录快照（configs/factor_catalog_llm.txt）。

因子库更新（indicators_tushare 新增列/表）后跑一次：

    QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data \
        .venv/bin/python scripts/gen_factor_catalog_llm.py

产物入仓库（ECS 无行情库，靠仓库快照）；部署后 NL 编译即引用最新目录。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant_research_engine.gui.factor_catalog_llm import generate_catalog  # noqa: E402


def main() -> int:
    path = generate_catalog()
    lines = path.read_text(encoding="utf-8").splitlines()
    print(f"已生成 {path}（{len(lines)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
