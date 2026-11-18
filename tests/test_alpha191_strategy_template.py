from pathlib import Path

import pytest
import yaml

from quant_research_engine.security.yaml_guard import validate_strategy_yaml
from quant_research_engine.strategies.alpha191 import build_alpha191_rank_strategy
from quant_research_engine.strategies.spec import StrategySpec


def test_high_rank_defaults_match_existing_pv06a_contract():
    raw = build_alpha191_rank_strategy("alpha083")
    existing = yaml.safe_load(Path(
        "strategies/catalog/price_volume/pv06a_alpha083_high_rank_mvp.yaml"
    ).read_text())
    for key in ("market_fields", "factor_fields"):
        assert raw["data"][key] == existing["data"][key]
    assert raw["signal"]["entry"] == existing["signal"]["entry"]
    assert raw["signal"]["exit"] == existing["signal"]["exit"]
    assert raw["holding"]["max_holding_days"] == existing["holding"]["max_holding_days"]
    assert raw["risk"] == existing["risk"]
    assert raw["evaluation"] == existing["evaluation"]
    assert raw["experiment"]["market_profile"] == "ashare_daily_default"
    # 旧目录里的展示性扩展键不进入安全闸白名单，模板不复制这些键。
    assert "execution" not in raw and "objective" not in raw["experiment"]


def test_low_rank_direction_uses_normalized_thresholds():
    defaults = build_alpha191_rank_strategy("alpha042", direction="low")
    assert defaults["signal"] == {"entry": "alpha042 < 0.2", "exit": "alpha042 > 0.5"}

    raw = build_alpha191_rank_strategy(
        "alpha042", direction="low", entry_threshold=0.15, exit_threshold=0.6,
        holding_days=5, stop_loss_pct=0.06,
    )
    assert raw["signal"] == {"entry": "alpha042 < 0.15", "exit": "alpha042 > 0.6"}
    assert raw["holding"]["max_holding_days"] == 5
    assert raw["risk"]["stop_loss_pct"] == 0.06
    assert raw["data"]["factor_fields"] == {"alpha042": "factors.stock_daily_alpha191.alpha042"}


def test_generated_mapping_passes_spec_and_safety_guard(tmp_path):
    raw = build_alpha191_rank_strategy("alpha001")
    spec = StrategySpec.from_mapping(raw)
    assert spec.signal_expression == "alpha001 > -0.2"
    assert spec.holding_days == 10
    path = tmp_path / "alpha001.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
    result = validate_strategy_yaml(path.read_text())
    assert result["ok"] is True and result["issues"] == []


@pytest.mark.parametrize("alpha", ["alpha1", "alpha000", "alpha192", "Alpha083", "alpha083;drop"])
def test_invalid_alpha_identifier_rejected(alpha):
    with pytest.raises(ValueError):
        build_alpha191_rank_strategy(alpha)


@pytest.mark.parametrize("kwargs", [
    {"direction": "sideways"},
    {"entry_threshold": -0.8, "exit_threshold": -0.2},
    {"direction": "low", "entry_threshold": 0.8, "exit_threshold": 0.2},
    {"holding_days": -1},
    {"stop_loss_pct": -0.1},
])
def test_invalid_parameters_rejected(kwargs):
    with pytest.raises(ValueError):
        build_alpha191_rank_strategy("alpha083", **kwargs)
