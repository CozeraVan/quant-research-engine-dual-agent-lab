#!/usr/bin/env python3
"""Export the classic strategy catalog as readable documentation and JSON.

This command is read-only: it parses strategy YAML/comments and the factor registry,
but never connects to a database or starts a backtest.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from quant_research_engine.gui.factor_wizard import registry_display_fields

CROSS_WORDS = ("上穿", "下穿", "金叉", "死叉")
CATEGORY_ZH = {
    "breakout": "突破",
    "composite": "复合",
    "cross_sectional": "截面因子",
    "kline_pattern": "K 线形态",
    "mean_reversion": "均值回归",
    "price_volume": "量价",
    "trend_following": "趋势跟踪",
    "catalog": "其他",
}


def _comment(text: str, key: str) -> str:
    match = re.search(rf"^#\s*{re.escape(key)}:\s*(.*)$", text, re.M)
    return match.group(1).strip() if match else ""


def _factor_meaning(column: str) -> str:
    if column.startswith("sma_"):
        return "简单移动平均线，用于衡量趋势与价格相对位置"
    if column.startswith("ema_"):
        return "指数移动平均线，对近期价格赋予更高权重"
    if column.startswith("wma_"):
        return "加权移动平均线，用于平滑价格与判断趋势"
    if column.startswith("rsi_"):
        return "相对强弱指标，用于观察超买、超卖与动量状态"
    if column.startswith("macd_"):
        return "MACD 的 DIF 快线，反映快慢指数均线之差"
    if column.startswith("macds_"):
        return "MACD 的 DEA 慢线，即 DIF 的信号线"
    if column.startswith("willr_"):
        return "威廉指标，用于观察短期超买与超卖区域"
    if column.startswith("adx_"):
        return "平均趋向指标，用于衡量趋势强度而非方向"
    if column.startswith("atr_") or column.startswith("atrr_"):
        return "真实波幅指标，用于衡量价格波动水平"
    if column.startswith("bbu_"):
        return "布林带上轨，用于观察价格上侧波动边界"
    if column.startswith("bbm_"):
        return "布林带中轨，用于观察价格中枢"
    if column.startswith("bbl_"):
        return "布林带下轨，用于观察价格下侧波动边界"
    if column.startswith("alpha"):
        return "Alpha191 横截面量价信号，具体含义以该编号公式为准"
    if column.startswith("mf_"):
        return "聚类研究挖掘的因子标记，具体含义以研究产物为准"
    return "策略引用的预计算因子"


def factor_display(reference: str) -> dict[str, str]:
    table, column = reference.rsplit(".", 1)
    try:
        info = registry_display_fields(table, column)
    except (KeyError, ValueError, TypeError):
        info = {"zh": None, "canonical": reference}
    return {
        "reference": reference,
        "zh": info.get("zh") or column,
        "meaning": _factor_meaning(column),
    }


def load_strategy(path: Path, catalog_dir: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    spec = yaml.safe_load(text)
    category = "catalog" if path.parent == catalog_dir else path.parent.relative_to(catalog_dir).as_posix()
    factor_fields = (spec.get("data") or {}).get("factor_fields") or {}
    signal = spec.get("signal") or {}
    holding = spec.get("holding") or {}
    risk = spec.get("risk") or {}
    description = _comment(text, "说明") or "原策略文件未提供文字说明；以实际 YAML 规则为准。"
    entry = str(signal.get("entry") or "")
    exit_ = str(signal.get("exit") or "")
    semantic_notes = []
    if any(word in description for word in CROSS_WORDS) and ".shift(1)" not in entry + exit_:
        semantic_notes.append("文字说明含穿越语义，但实际 YAML 未使用 .shift(1)；两者不得视为等价。")
    return {
        "strategy_id": path.stem,
        "category": category,
        "category_zh": CATEGORY_ZH.get(category, category),
        "yaml_path": path.relative_to(catalog_dir).as_posix(),
        "name": _comment(text, "策略名称") or path.stem,
        "description": description,
        "declared_dependencies": _comment(text, "数据依赖"),
        "declared_entry": _comment(text, "入场规则"),
        "declared_exit": _comment(text, "出场规则"),
        "entry": entry,
        "exit": exit_,
        "max_holding_days": holding.get("max_holding_days"),
        "direction": holding.get("direction"),
        "risk": risk,
        "factors": [
            {"alias": alias, **factor_display(str(reference))}
            for alias, reference in sorted(factor_fields.items())
        ],
        "semantic_notes": semantic_notes,
    }


def build_inventory(catalog_dir: Path) -> list[dict[str, Any]]:
    return [load_strategy(path, catalog_dir) for path in sorted(catalog_dir.rglob("*.yaml"))]


def _md(text: Any) -> str:
    return str(text if text is not None else "—").replace("\n", " ").strip()


def render_markdown(strategies: list[dict[str, Any]]) -> str:
    lines = [
        "# 经典策略目录说明（当前 YAML 口径）",
        "",
        f"> 共 {len(strategies)} 个策略。文字说明来自 YAML 注释；实际执行以 YAML 表达式为准。",
        "> 本文只解释规则，不构成收益结论或投资建议。",
        "",
    ]
    categories = sorted({row["category"] for row in strategies})
    for category in categories:
        rows = [row for row in strategies if row["category"] == category]
        lines.extend([f"## {rows[0]['category_zh']}（{len(rows)} 个）", ""])
        for row in rows:
            lines.extend([
                f"### {_md(row['name'])} `{row['strategy_id']}`",
                "",
                f"- **说明**：{_md(row['description'])}",
                f"- **声明的数据依赖**：{_md(row['declared_dependencies'])}",
                "- **实际使用指标**：",
            ])
            if row["factors"]:
                for factor in row["factors"]:
                    lines.append(
                        f"  - `{factor['alias']}` = {_md(factor['zh'])} "
                        f"（`{factor['reference']}`）：{_md(factor['meaning'])}。"
                    )
            else:
                lines.append("  - 无预计算因子；仅使用行情字段与表达式。")
            lines.extend([
                f"- **文字入场 / 出场**：{_md(row['declared_entry'])} / {_md(row['declared_exit'])}",
                f"- **实际 YAML 入场**：`{_md(row['entry'])}`",
                f"- **实际 YAML 出场**：`{_md(row['exit'])}`",
                f"- **持仓 / 风控**：最长 {_md(row['max_holding_days'])} 天；"
                f"止损 {_md(row['risk'].get('stop_loss_pct'))}；"
                f"止盈 {_md(row['risk'].get('take_profit_pct'))}；"
                f"移动止损 {_md(row['risk'].get('trailing_stop_pct'))}。",
            ])
            for note in row["semantic_notes"]:
                lines.append(f"- **语义差异**：{_md(note)}")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("strategies/catalog"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/agent/classic_catalog"))
    args = parser.parse_args()
    strategies = build_inventory(args.catalog)
    if not strategies:
        raise SystemExit(f"no strategies found: {args.catalog}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog": str(args.catalog),
        "count": len(strategies),
        "categories": dict(sorted(Counter(row["category"] for row in strategies).items())),
        "factor_reference_count": len({
            factor["reference"] for row in strategies for factor in row["factors"]
        }),
        "semantic_note_count": sum(bool(row["semantic_notes"]) for row in strategies),
        "strategies": strategies,
    }
    (args.output_dir / "inventory.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "README.md").write_text(render_markdown(strategies), encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "strategies"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
