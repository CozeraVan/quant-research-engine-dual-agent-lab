import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "classic_catalog" / "inventory.py"
_SPEC = importlib.util.spec_from_file_location("classic_catalog_inventory", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
build_inventory = _MODULE.build_inventory
render_markdown = _MODULE.render_markdown


def test_current_catalog_inventory_is_complete_and_readable():
    strategies = build_inventory(Path("strategies/catalog"))

    assert len(strategies) == 118
    assert len({row["strategy_id"] for row in strategies}) == 118
    assert all(row["name"] and row["entry"] for row in strategies)
    assert all(row["exit"] or row["max_holding_days"] for row in strategies)
    assert all(row["factors"] is not None for row in strategies)
    assert any(row["semantic_notes"] for row in strategies)

    document = render_markdown(strategies)
    assert "共 118 个策略" in document
    assert "实际 YAML 入场" in document
    assert "文字说明含穿越语义" in document


def test_inventory_marks_text_cross_without_lagged_yaml():
    strategies = build_inventory(Path("strategies/catalog"))
    macd = next(row for row in strategies if row["strategy_id"] == "tf02a_macd_golden_cross")

    assert "上穿" in macd["description"]
    assert ".shift(1)" not in macd["entry"]
    assert macd["semantic_notes"]
    assert {factor["alias"] for factor in macd["factors"]} == {"macd_12_26_9", "macds_12_26_9"}
