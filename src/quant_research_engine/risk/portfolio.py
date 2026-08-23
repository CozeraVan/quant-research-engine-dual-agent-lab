"""组合层风险汇总（R7）：混合头寸（股票 + 债券/转债 + 期权）统一汇总。

- 股票腿沿用 R1–R4 收益序列法：``performance.performance_summary``
  （Sharpe/Sortino/β 等）+ 当前 1 日 EWMA 参数 VaR/ES 参照
  （``tail.ewma_parametric_var_es``，损失取正号）。
- 债券/转债腿：``bonds.portfolio_aggregate``（DV01 可加、duration/convexity
  市值加权，书4 Ch12）；可选逐头寸 ``bonds.key_rate_shifts`` 的 KR01 按
  节点加总（书4 Ch13；``kr01_sum`` 与组合 DV01 并列披露，不做强制相等
  断言——KR01 由现金流曲线重定价而来，DV01 可由调用方按 duration 换算，
  口径可不同）。
- 期权腿：``options.portfolio_greeks``（数量×单值求和，书4 Ch16）。
- 可选 DGV-VaR（书4 Ch16 + Ch2）：``config["dgv"]`` 显式给出
  ``spot_shock_sd``（δS 日变动标准差，价格单位）才计算——组合层没有标的
  价格水平，无法从收益序列自动推导，必须调用方提供；``method`` 默认
  normal，可选 cornish_fisher（已知高偏度失真限制，见 derivatives_var）。

纯函数零 DB；输入为调用方给定参数。所有数值转 Python 标量/list，
输出可直接 json.dumps。三条腿至少给一条，否则 ValueError。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.risk import bonds, derivatives_var, options, performance, tail
from quant_research_engine.risk.constants import (
    ANNUALIZATION_FACTOR,
    CONFIDENCE_LEVELS,
    DEFAULT_RISK_FREE_RATE,
    EWMA_LAMBDA,
)

_DGV_METHODS = derivatives_var.DGV_METHODS


def _equity_leg(
    returns: pd.Series,
    benchmark: pd.Series | None,
    rf: float,
    ann: int,
    lam: float,
    confidence: float,
) -> dict[str, Any]:
    return {
        "n_obs": int(len(returns)),
        "performance": performance.performance_summary(returns, benchmark, rf, ann),
        "var_es_reference": tail.ewma_parametric_var_es(returns, confidence, lam),
        "note": "股票腿沿用 R1–R4 收益序列法（performance_summary + 当前 1 日 "
        "EWMA 参数 VaR/ES 参照，μ=0 RiskMetrics 口径，损失取正号）",
    }


def _fixed_income_leg(
    bond_positions: list[dict[str, Any]],
    bond_kr01: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    agg = bonds.portfolio_aggregate(bond_positions)
    leg: dict[str, Any] = {
        "n_positions": agg["n_positions"],
        "total_market_value": agg["total_market_value"],
        "dv01": agg["dv01"],
        "duration": agg["duration"],
        "convexity": agg["convexity"],
        "weights": [float(w) for w in agg["weights"]],
        "note": "书4 Ch12：DV01 可加，duration/convexity 市值加权；转债腿并入本腿",
    }
    if bond_kr01:
        tenors: tuple[float, ...] | None = None
        total_kr01: np.ndarray | None = None
        for pos in bond_kr01:
            res = bonds.key_rate_shifts(pos["times"], pos["amounts"], pos["curve"])
            if tenors is None:
                tenors = tuple(res["key_tenors"])
                total_kr01 = np.zeros(len(tenors), dtype=float)
            elif tuple(res["key_tenors"]) != tenors:
                raise ValueError("bond_kr01 各头寸的 key rate 节点必须一致")
            total_kr01 = total_kr01 + np.asarray(res["kr01"], dtype=float)
        assert tenors is not None and total_kr01 is not None
        leg["kr01"] = {
            "key_tenors": [float(k) for k in tenors],
            "kr01": [float(v) for v in total_kr01],
            "kr01_sum": float(total_kr01.sum()),
            "note": "书4 Ch13：逐头寸 KR01 按节点加总；kr01_sum 与 dv01 并列披露"
            "（口径可不同，不强制相等）",
        }
    return leg


def _options_leg(option_positions: list[dict[str, Any]]) -> dict[str, Any]:
    agg = options.portfolio_greeks(option_positions)
    return {
        "n_positions": agg["n_positions"],
        "delta": agg["delta"],
        "gamma": agg["gamma"],
        "vega": agg["vega"],
        "theta": agg["theta"],
        "rho": agg["rho"],
        "note": "书4 Ch16：组合 Greeks = Σ 数量×单值（可加性）",
    }


def summarize_mixed_portfolio(
    *,
    returns: Any = None,
    benchmark: Any = None,
    bond_positions: list[dict[str, Any]] | None = None,
    option_positions: list[dict[str, Any]] | None = None,
    bond_kr01: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """混合头寸组合风险汇总（纯函数零 DB，输出 JSON 可序列化 dict）。

    - ``returns``：股票腿逐日 simple 收益序列（可选基准 ``benchmark``）；
    - ``bond_positions``：``bonds.portfolio_aggregate`` 口径
      （{"market_value", "duration", "convexity", "dv01"}，转债腿并入）；
    - ``bond_kr01``：可选逐头寸 {"times", "amounts", "curve"}，KR01 按节点加总；
    - ``option_positions``：``options.portfolio_greeks`` 口径
      （{"quantity", "delta", "gamma", "vega", "theta", "rho"}）；
    - ``config``：rf/lam/annualization_factor/confidence 覆盖 + ``dgv`` 子 dict
      （{"spot_shock_sd", "vol_shock_sd", "confidence", "method"}，显式给出才
      计算 DGV-VaR，作用于期权腿组合 Greeks）。

    三条腿至少给一条。仅 ``returns`` 输入时退化为仅 equity 节（无衍生品键）。
    """
    cfg = dict(config or {})
    rf = float(cfg.get("risk_free_rate", DEFAULT_RISK_FREE_RATE))
    ann = int(cfg.get("annualization_factor", ANNUALIZATION_FACTOR))
    lam = float(cfg.get("lam", EWMA_LAMBDA))
    confidence = float(cfg.get("confidence", max(CONFIDENCE_LEVELS)))

    bond_positions = [dict(p) for p in (bond_positions or [])]
    option_positions = [dict(p) for p in (option_positions or [])]
    has_equity = returns is not None
    if not has_equity and not bond_positions and not option_positions:
        raise ValueError("至少需要一条腿：returns / bond_positions / option_positions")

    result: dict[str, Any] = {
        "meta": {
            "legs": {
                "equity": has_equity,
                "fixed_income": bool(bond_positions),
                "options": bool(option_positions),
            },
            "risk_free_rate_annual": rf,
            "annualization_factor": ann,
            "ewma_lambda": lam,
            "confidence": confidence,
            "loss_sign_convention": "loss = -return（损失取正号，书4 Ch1）",
        },
    }

    if has_equity:
        r = pd.Series(returns, dtype=float).dropna()
        b = pd.Series(benchmark, dtype=float) if benchmark is not None else None
        result["equity"] = _equity_leg(r, b, rf, ann, lam, confidence)
    if bond_positions:
        result["fixed_income"] = _fixed_income_leg(bond_positions, bond_kr01)
    if option_positions:
        result["options"] = _options_leg(option_positions)

    dgv_cfg = cfg.get("dgv")
    if dgv_cfg is not None:
        if "options" not in result:
            result["dgv_var"] = {"error": "dgv 需要期权腿（option_positions）提供组合 Greeks"}
        else:
            greeks = result["options"]
            method = str(dgv_cfg.get("method", "normal"))
            if method not in _DGV_METHODS:
                raise ValueError(f"dgv.method must be one of {_DGV_METHODS}")
            result["dgv_var"] = derivatives_var.dgv_var(
                greeks["delta"],
                greeks["gamma"],
                greeks["vega"],
                float(dgv_cfg["spot_shock_sd"]),
                float(dgv_cfg.get("vol_shock_sd", 0.0)),
                confidence=float(dgv_cfg.get("confidence", confidence)),
                method=method,
            )
    return result
