"""risk.dependence 单测：秩相关手算小样本 + 正定性 + simple/log 往返。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.risk import dependence


class TestRankCorrelations:
    def test_hand_computed_small_sample(self):
        """书2 Ch12 式 12.13/12.14 手算：x=[1,2,3], y=[1,3,2]。

        秩差 d=[0,−1,1] → ρS = 1 − 6·2/(3·8) = 0.5；
        对 (1,2)(1,3)(2,3)：concordant (1,2)、(1,3)，discordant (2,3) →
        τ = (2−1)/3 = 1/3。
        """
        spearman = dependence.spearman_corr([1, 2, 3], [1, 3, 2])
        kendall = dependence.kendall_corr([1, 2, 3], [1, 3, 2])
        assert spearman["coefficient"] == pytest.approx(0.5)
        assert kendall["coefficient"] == pytest.approx(1.0 / 3.0)

    def test_monotone_invariance(self):
        """单调变换不变：对 y 取 exp 后秩相关不变。"""
        rng = np.random.default_rng(12)
        x = rng.normal(0, 1, 100)
        y = rng.normal(0, 1, 100)
        base_s = dependence.spearman_corr(x, y)["coefficient"]
        base_k = dependence.kendall_corr(x, y)["coefficient"]
        assert dependence.spearman_corr(x, np.exp(y))["coefficient"] == pytest.approx(base_s)
        assert dependence.kendall_corr(x, np.exp(y))["coefficient"] == pytest.approx(base_k)

    def test_perfect_monotone(self):
        assert dependence.spearman_corr([1, 2, 3, 4], [2, 4, 8, 16])["coefficient"] == pytest.approx(1.0)
        assert dependence.kendall_corr([1, 2, 3, 4], [16, 8, 4, 2])["coefficient"] == pytest.approx(-1.0)

    def test_nan_pairs_dropped(self):
        result = dependence.spearman_corr([1.0, 2.0, np.nan, 4.0], [1.0, 2.0, 3.0, 4.0])
        assert result["n_obs"] == 3


class TestPositiveDefinite:
    def test_equicorrelation_passes(self):
        n, rho = 5, 0.3
        mat = np.full((n, n), rho)
        np.fill_diagonal(mat, 1.0)
        result = dependence.is_positive_definite(mat)
        assert result["positive_definite"] is True
        assert result["min_eigenvalue"] == pytest.approx(1.0 - rho, rel=1e-10)

    def test_invalid_correlation_rejected(self):
        result = dependence.is_positive_definite(np.array([[1.0, 2.0], [2.0, 1.0]]))
        assert result["positive_definite"] is False
        assert result["min_eigenvalue"] == pytest.approx(-1.0)

    def test_dataframe_input(self):
        mat = pd.DataFrame([[1.0, 0.5], [0.5, 1.0]], index=["a", "b"], columns=["a", "b"])
        assert dependence.is_positive_definite(mat)["positive_definite"] is True

    def test_non_square_raises(self):
        with pytest.raises(ValueError):
            dependence.is_positive_definite(np.ones((2, 3)))


class TestReturnConversion:
    def test_round_trip(self):
        rng = np.random.default_rng(1)
        simple = rng.normal(0.0, 0.02, 200)
        log = dependence.simple_to_log_returns(simple)
        back = dependence.log_to_simple_returns(log)
        np.testing.assert_allclose(back.to_numpy(), simple, rtol=1e-12, atol=1e-15)

    def test_known_values(self):
        """式 12.5：R=0.10 → r=ln(1.1)≈0.0953102；r=−0.05 → R=e^−0.05−1。"""
        log = dependence.simple_to_log_returns([0.10])
        assert log.iloc[0] == pytest.approx(np.log(1.1))
        simple = dependence.log_to_simple_returns([-0.05])
        assert simple.iloc[0] == pytest.approx(np.expm1(-0.05))

    def test_total_loss_rejected(self):
        with pytest.raises(ValueError):
            dependence.simple_to_log_returns([-1.0, 0.0])
