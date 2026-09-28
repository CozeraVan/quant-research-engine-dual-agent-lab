#!/usr/bin/env python3
"""SaaS 元数据导出（QRE-SAAS-METADATA）：因子目录 + 板块/概念名单。

从本地行情库导出**元数据**（因子表/列分组、板块概念名+成分股数量，
不含任何行情/成分股明细），产物为几 MB 级 JSON，scp 上 ECS 后由 saas app
的 /api/saas/factors 与 /api/saas/universes 端点读取（端点不变，前端无感）。

用法（本地，因子库更新后再跑一次并 scp）：
  .venv/bin/python scripts/sync_saas_metadata.py \
      --out deploy/saas/metadata.json
  scp -i ~/.ssh/aguhuice_ed25519 deploy/saas/metadata.json \
      root@47.119.127.40:/srv/aguhuice/qre/deploy/saas/metadata.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def build_metadata(db_url: str | None = None) -> dict:
    from quant_research_engine.gui.factor_wizard import (
        build_factor_groups,
        load_factor_tables_columns,
    )
    from quant_research_engine.gui.universe import all_a_codes, all_a_count, list_universes

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "factors": build_factor_groups(load_factor_tables_columns(db_url)),
        "universes": list_universes(db_url)["groups"],
        # 全部 A 股成分股计数（QRE-SAAS-LARGE-UNIVERSE-GUARD：前端大范围耗时护栏用）
        "all_a_count": all_a_count(db_url),
        # 全 A 股代码清单（QRE-SAAS-GUEST-RANDOM-SYMBOL：随机抽股接口用；~60KB 可接受）
        "all_a_codes": all_a_codes(db_url),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 SaaS 元数据（因子目录+板块概念名单）")
    parser.add_argument("--out", default="deploy/saas/metadata.json")
    parser.add_argument("--db-url", default=None)
    args = parser.parse_args()
    data = build_metadata(args.db_url)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    n_factors = sum(len(g["items"]) for g in data["factors"])
    n_univ = sum(len(g["items"]) for g in data["universes"])
    print(f"written {out}: 因子 {n_factors} 项 / 板块概念 {n_univ} 项 / 全部A股 {data['all_a_count']} 只 / {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
