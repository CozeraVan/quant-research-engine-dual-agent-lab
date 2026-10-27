#!/usr/bin/env python3
"""SaaS 元数据导出（QRE-SAAS-METADATA）：因子目录 + 板块/概念名单。

从本地行情库导出**元数据**（因子表/列分组、板块概念名+成分股数量，
不含任何行情/成分股明细），产物为几 MB 级 JSON，scp 上 ECS 后由 saas app
的 /api/saas/factors 与 /api/saas/universes 端点读取（端点不变，前端无感）。

因子目录每项带因子语义注册表增量字段 ``zh`` / ``canonical`` /
``price_basis`` / ``aliases``（QRE-GUI-FACTOR-REGISTRY-001），弹窗与搜索据此
中文展示；未维护中文名的列 ``zh`` 为 null，前端回退既有 label。导出时同步跑
注册表防漂移校验与覆盖报告。

用法（本地，因子库更新后再跑一次并 scp）：
  .venv/bin/python scripts/sync_saas_metadata.py \
      --out deploy/saas/metadata.json
  ./deploy/saas/deploy-ecs.sh deploy/saas/metadata.json

QRE-ECS-SSH-HARDENING（2026-10-27）起 root 直连已禁，scp 一律走 deploy 用户；
部署用 `deploy/saas/deploy-ecs.sh`（scp 到 /tmp → sudo install 到业务路径 →
sudo systemctl restart qre-saas → 校验），不要再写 `root@47.119.127.40`。
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

    tables_columns = load_factor_tables_columns(db_url)
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        # 因子目录（每项带 zh / canonical / price_basis / aliases 增量字段）
        "factors": build_factor_groups(tables_columns),
        "universes": list_universes(db_url)["groups"],
        # 全部 A 股成分股计数（QRE-SAAS-LARGE-UNIVERSE-GUARD：前端大范围耗时护栏用）
        "all_a_count": all_a_count(db_url),
        # 全 A 股代码清单（QRE-SAAS-GUEST-RANDOM-SYMBOL：随机抽股接口用；~60KB 可接受）
        "all_a_codes": all_a_codes(db_url),
    }


def _report_registry(tables_columns: dict[str, list[str]]) -> int:
    """因子语义注册表防漂移校验 + 覆盖报告（QRE-GUI-FACTOR-REGISTRY-001）。

    返回问题数。注册条目指向不存在的字段、别名指向不存在字段都要报出来；
    新增列未注册只告警不阻塞（展示回退 canonical，不伪造中文名）。
    """
    from quant_research_engine.gui.factor_registry import (
        load_registry,
        validate_registry,
    )

    registry = load_registry()
    issues = validate_registry(tables_columns, registry=registry)
    if issues:
        print(f"[WARN] 因子语义注册表校验发现 {len(issues)} 个问题：")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("因子语义注册表校验通过（无失效 canonical / 悬空别名）")
    coverage = registry.coverage_report(tables_columns)
    print(
        f"注册表覆盖：{coverage['registered_columns']}/{coverage['total_columns']} 列"
        f"（{coverage['coverage_pct']}%），未维护 {coverage['unregistered_columns']} 列"
        "（回退 canonical 展示）"
    )
    return len(issues)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 SaaS 元数据（因子目录+板块概念名单）")
    parser.add_argument("--out", default="deploy/saas/metadata.json")
    parser.add_argument("--db-url", default=None)
    args = parser.parse_args()
    from quant_research_engine.gui.factor_wizard import load_factor_tables_columns

    data = build_metadata(args.db_url)
    _report_registry(load_factor_tables_columns(args.db_url))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    n_factors = sum(len(g["items"]) for g in data["factors"])
    n_univ = sum(len(g["items"]) for g in data["universes"])
    print(f"written {out}: 因子 {n_factors} 项 / 板块概念 {n_univ} 项 / 全部A股 {data['all_a_count']} 只 / {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
