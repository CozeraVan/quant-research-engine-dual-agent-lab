"""P2-14 参数网格产物侧：变体列选择 helper（纯函数，无 DB）。

规则对应 `CR-2026-11-01_param_grid_wake_semantics.md`：
- 同族多参数组已入库时，主参数组优先，其余按参数数值升序补；
- 单参数组不扩展，存量产物行为零变化；
- MACD 三元组（macd/macds/macdh）同族同参数一起入选。
"""

from __future__ import annotations

from quant_research_engine.gui.lab_result import (
    _param_family_params,
    _select_param_variant_columns,
)


def test_param_family_params_basic():
    assert _param_family_params("macd_12_26_9") == ("macd", "12_26_9")
    assert _param_family_params("macds_15_35_10") == ("macd", "15_35_10")
    assert _param_family_params("macdh_6_13_5") == ("macd", "6_13_5")
    assert _param_family_params("rsi_14") == ("rsi", "14")
    assert _param_family_params("sma_20") == ("ma", "20")
    assert _param_family_params("close") is None
    # 非数字参数后缀（如 macd_cn_12_26_9）不是参数变体
    assert _param_family_params("macd_cn_12_26_9") is None


def test_single_group_returns_primary_only():
    cols = ["macd_12_26_9", "macds_12_26_9", "macdh_12_26_9"]
    assert _select_param_variant_columns("macd_12_26_9", cols) == ["macd_12_26_9"]


def test_macd_variants_keep_triple_together_and_primary_first():
    existing = [
        "macd_12_26_9", "macds_12_26_9", "macdh_12_26_9",
        "macd_15_35_10", "macds_15_35_10", "macdh_15_35_10",
        "macd_24_52_18", "macds_24_52_18", "macdh_24_52_18",
        "macd_6_13_5", "macds_6_13_5", "macdh_6_13_5",
    ]
    out = _select_param_variant_columns("macd_12_26_9", existing)
    assert out[0] == "macd_12_26_9"
    # 主参数组的三列必须紧跟主列
    assert out[:3] == ["macd_12_26_9", "macds_12_26_9", "macdh_12_26_9"]
    # 变体组也必须三元组完整
    assert {"macd_6_13_5", "macds_6_13_5", "macdh_6_13_5"} <= set(out)
    assert len(out) <= 12  # 默认最多 4 组 × 3 列


def test_rsi_variants_sorted_numerically():
    existing = [f"rsi_{p}" for p in (2, 6, 7, 9, 12, 14, 21, 24, 28)]
    out = _select_param_variant_columns("rsi_14", existing)
    assert out[0] == "rsi_14"
    assert out[1:4] == ["rsi_2", "rsi_6", "rsi_7"]
