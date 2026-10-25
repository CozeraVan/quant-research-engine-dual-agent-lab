#!/usr/bin/env python
"""重新生成 NL 编译用真实因子目录快照（configs/factor_catalog_llm.txt）。

因子库更新（indicators_tushare 新增列/表）后跑一次：

    QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data \
        .venv/bin/python scripts/gen_factor_catalog_llm.py

产物入仓库（ECS 无行情库，靠仓库快照）；部署后 NL 编译即引用最新目录。

同时跑因子语义注册表防漂移校验（QRE-GUI-FACTOR-REGISTRY-001）：注册表
canonical 必须存在于本快照，别名不得指向不存在字段，新增列未注册时输出覆盖
告警——**不静默放过**。中文名/别名维护见 scripts/gen_factor_registry.py。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quant_research_engine.gui.factor_catalog_llm import (  # noqa: E402
    generate_catalog,
    registry_coverage,
    registry_validation,
)


def main() -> int:
    path = generate_catalog()
    lines = path.read_text(encoding="utf-8").splitlines()
    print(f"已生成 {path}（{len(lines)} 行）")

    issues = registry_validation()
    if issues:
        print(f"[WARN] 因子语义注册表校验发现 {len(issues)} 个问题：")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("因子语义注册表校验通过（无失效 canonical / 悬空别名）")

    coverage = registry_coverage()
    if coverage is not None:
        print(
            f"注册表覆盖：{coverage['registered_columns']}/{coverage['total_columns']} 列"
            f"（{coverage['coverage_pct']}%），未维护 {coverage['unregistered_columns']} 列"
            "（展示回退 canonical，未伪造中文名）"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
