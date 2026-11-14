"""标准 batch → M10 适配器边界测试。"""

from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from strategy_fit_batch import analyze_standard_batch
from quant_research_engine.analysis.ml_cluster import MlClusterConfig
from quant_research_engine.analysis.strategy_fit import FitConfig


def test_adapter_drops_duplicate_metadata_and_handles_empty_winner_pool(tmp_path, monkeypatch):
    batch = tmp_path / "batch"
    batch.mkdir()
    pd.DataFrame(
        {
            "symbol": ["A.SZ", "B.SZ"],
            "trade_count": [10, 10],
            "win_rate": [0.2, 0.3],
            "total_return": [-0.1, -0.2],
            "buy_hold_return": [0.1, 0.1],
            "excess_return_vs_buy_hold": [-0.2, -0.3],
            "board": ["main_board", "main_board"],
        }
    ).to_csv(batch / "summary.csv", index=False)
    monkeypatch.setattr(
        "strategy_fit_batch.write_fit_outputs",
        lambda *args, **kwargs: {"report_manifest": tmp_path / "fit-manifest"},
    )
    monkeypatch.setattr(
        "strategy_fit_batch.write_ml_outputs",
        lambda *args, **kwargs: {"ml_cluster_manifest": tmp_path / "ml-manifest"},
    )

    result = analyze_standard_batch(
        batch,
        tmp_path / "out",
        pd.DataFrame(columns=["ts_code"]),
        FitConfig(min_trades=1, min_class_size=1),
        MlClusterConfig(),
    )

    assert result["fit_summary"]["eligible_symbols"] == 2
    assert result["fit_summary"]["n_90"] == 0
    assert result["fit_summary"]["n_99"] == 0
    assert result["fit_summary"]["n_99.9"] == 0
    assert result["ml_status"][0]["status"] == "insufficient"
    assert result["ml_status"][0]["n_stocks"] == 0
