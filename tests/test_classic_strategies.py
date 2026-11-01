"""经典策略 YAML 合同测试（QRE-SAAS-SHOWCASE 重新填充前置）。

这些 YAML 是公网「经典策略」页重新填充的唯一策略真相源，必须在提交前保证：
1. 能被 `StrategySpec` 解析；
2. 信号表达式引用的字段都在 `market_fields` / `factor_fields` 中声明；
3. 因子目标能在 `configs/factor_registry.json` 注册表中找到（防止写错因子列）；
4. 成交与持仓语义符合经典策略约定（T+1 开盘成交、持仓天数 0=不限）。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from quant_research_engine.evaluation.signals import referenced_fields  # noqa: E402
from quant_research_engine.strategies.spec import StrategySpec  # noqa: E402

CLASSIC_DIR = REPO_ROOT / "strategies" / "classic"
YAML_PATHS = sorted(CLASSIC_DIR.glob("*.yaml"))


def test_classic_strategy_yamls_exist() -> None:
    assert YAML_PATHS, f"未找到经典策略 YAML: {CLASSIC_DIR}"


@pytest.mark.parametrize("path", YAML_PATHS, ids=lambda p: p.name)
def test_classic_yaml_parses_and_declares_signal_fields(path: Path) -> None:
    spec = StrategySpec.from_yaml(path)

    assert spec.signal_expression
    assert spec.exit_signal_expression
    assert spec.holding_days == 0

    declared = set(spec.market_fields) | {f.logical_name for f in spec.factor_fields}
    used = referenced_fields(spec.signal_expression) | referenced_fields(spec.exit_signal_expression)
    assert used <= declared, f"{path.name}: 信号引用未声明字段 {sorted(used - declared)}"


@pytest.mark.parametrize("path", YAML_PATHS, ids=lambda p: p.name)
def test_classic_factor_targets_are_registered(path: Path) -> None:
    spec = StrategySpec.from_yaml(path)
    registry = json.loads((REPO_ROOT / "configs" / "factor_registry.json").read_text(encoding="utf-8"))
    registered = {entry["canonical"] for entry in registry["factors"]}

    for field in spec.factor_fields:
        target = f"{field.source_schema}.{field.source_table}.{field.source_column}"
        assert target in registered, f"{path.name}: 因子未注册 {target}"
