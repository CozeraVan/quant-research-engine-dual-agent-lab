"""Strategy-fit analysis (M10.1): significant winner selection, strategy
meta-test, class enrichment, and fit reports — reading existing batch
artifacts only. No backtest execution.

Statistics (pure Python, no new dependencies):

- Per-symbol significance: exact one-sided binomial test on the strategy's
  per-symbol win rate (fraction of net-profitable trades) vs H0: p=0.5.
- Confidence tiers: 90% / 99% / 99.9% (p <= 0.10 / 0.01 / 0.001).
- Magnitude gate: total_return > 0 AND excess_return_vs_buy_hold > 0 — the
  strategy must beat the stock's own natural (buy-and-hold) return.
- Strategy meta-test: significant-stock count vs binomial false-positive
  expectation (eligible_symbols x tier alpha). A no-edge strategy lands at
  ~expectation and is correctly judged ineffective.
- Class enrichment: hypergeometric p-value of the significant pool's class
  shares vs universe, with Benjamini-Hochberg FDR across all tests.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

TIER_ALPHAS: tuple[float, ...] = (0.10, 0.01, 0.001)
TIER_LABELS: dict[float, str] = {0.10: "90", 0.01: "99", 0.001: "99.9"}
DIMENSIONS: tuple[str, ...] = ("board", "industry_group", "market_cap_bucket", "liquidity_bucket")
UNKNOWN_BUCKET = "unknown"
MANIFEST_KIND = "strategy_fit_report_manifest"


@dataclass(frozen=True)
class FitConfig:
    tiers: tuple[float, ...] = TIER_ALPHAS
    pool_tier: float = 0.01
    min_trades: int = 5
    min_class_size: int = 30
    class_edge_min_pp: float = 0.02


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def binomial_pvalue_ge(k: int, n: int, p: float = 0.5) -> float:
    """Exact one-sided P(X >= k) for X ~ Binomial(n, p), via log-gamma."""
    if n <= 0 or k <= 0:
        return 1.0
    if k > n:
        return 0.0
    log_terms = [
        math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
        + i * math.log(p) + (n - i) * math.log(1 - p)
        for i in range(k, n + 1)
    ]
    m = max(log_terms)
    return min(1.0, sum(math.exp(t - m) for t in log_terms) * math.exp(m))


def hypergeom_pvalue_ge(universe: int, successes: int, draws: int, observed: int) -> float:
    """P(X >= observed) for X ~ Hypergeometric(N=universe, K=successes, n=draws)."""
    if draws <= 0 or universe <= 0:
        return 1.0
    upper = min(successes, draws)
    if observed > upper:
        return 0.0
    log_denom = math.lgamma(universe + 1) - math.lgamma(draws + 1) - math.lgamma(universe - draws + 1)
    log_terms = []
    for i in range(observed, upper + 1):
        if i > successes or draws - i > universe - successes:
            continue
        log_terms.append(
            (math.lgamma(successes + 1) - math.lgamma(i + 1) - math.lgamma(successes - i + 1))
            + (math.lgamma(universe - successes + 1) - math.lgamma(draws - i + 1) - math.lgamma(universe - successes - (draws - i) + 1))
            - log_denom
        )
    if not log_terms:
        return 1.0
    m = max(log_terms)
    return min(1.0, sum(math.exp(t - m) for t in log_terms) * math.exp(m))


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """BH-adjusted q-values in the original order."""
    n = len(pvalues)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvalues[i])
    adjusted = [0.0] * n
    running_min = 1.0
    for rank_from_end, idx in enumerate(reversed(order)):
        rank = n - rank_from_end
        running_min = min(running_min, pvalues[idx] * n / rank)
        adjusted[idx] = min(1.0, running_min)
    return adjusted


# ---------------------------------------------------------------------------
# batch loading
# ---------------------------------------------------------------------------


@dataclass
class StrategyBatchData:
    strategy_id: str
    category: str
    frame: pd.DataFrame
    monthly: pd.DataFrame | None = None


def load_batch(batch_dir: Path) -> tuple[list[StrategyBatchData], list[dict[str, str]]]:
    """Load per-strategy summary.csv files from a compact batch directory.

    Returns (loaded strategies, skipped entries with reasons).
    """
    summary_path = batch_dir / "batch_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"batch_summary.json not found in {batch_dir}")
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    loaded: list[StrategyBatchData] = []
    skipped: list[dict[str, str]] = []
    for entry in payload.get("results", []):
        strategy_id = entry.get("strategy_id", "")
        category = entry.get("category", "")
        if entry.get("status") != "ok":
            skipped.append({"strategy_id": strategy_id, "category": category,
                            "reason": f"status={entry.get('status')}"})
            continue
        csv_path = Path(entry.get("output_dir", "")) / "backtest" / "summary.csv"
        if not csv_path.exists():
            skipped.append({"strategy_id": strategy_id, "category": category,
                            "reason": "summary.csv missing"})
            continue
        frame = pd.read_csv(csv_path)
        monthly_path = Path(entry.get("output_dir", "")) / "backtest" / "symbol_month_returns.csv"
        monthly = pd.read_csv(monthly_path) if monthly_path.exists() else None
        loaded.append(
            StrategyBatchData(strategy_id=strategy_id, category=category, frame=frame, monthly=monthly)
        )
    return loaded, skipped


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------


@dataclass
class StrategyFitResult:
    summary_row: dict[str, Any]
    stock_rows: list[dict[str, Any]] = field(default_factory=list)
    class_rows: list[dict[str, Any]] = field(default_factory=list)


def _tier_label(alpha: float) -> str:
    return TIER_LABELS.get(alpha, str(alpha))


def analyze_strategy(
    data: StrategyBatchData,
    metadata: pd.DataFrame,
    config: FitConfig,
) -> StrategyFitResult:
    frame = data.frame.copy()
    meta_columns = ["ts_code", *[d for d in DIMENSIONS if d in metadata.columns]]
    meta = metadata.loc[:, meta_columns].copy() if not metadata.empty else pd.DataFrame(columns=meta_columns)
    for dim in DIMENSIONS:
        if dim not in meta.columns:
            meta[dim] = UNKNOWN_BUCKET
    frame = frame.merge(meta, left_on="symbol", right_on="ts_code", how="left")
    for dim in DIMENSIONS:
        frame[dim] = frame[dim].fillna(UNKNOWN_BUCKET).astype(str)

    eligible = frame.loc[
        (frame["trade_count"].fillna(0) >= config.min_trades)
        & frame["total_return"].notna()
        & frame["excess_return_vs_buy_hold"].notna()
    ].copy()
    eligible_symbols = int(len(eligible))

    free_riders = frame.loc[
        (frame["trade_count"].fillna(0) >= config.min_trades)
        & (frame["total_return"] > 0)
        & (frame["excess_return_vs_buy_hold"] <= 0)
    ]
    free_rider_count = int(len(free_riders))

    wins = (eligible["win_rate"].fillna(0.0) * eligible["trade_count"]).round().astype(int)
    eligible["binomial_p_"] = [
        binomial_pvalue_ge(int(k), int(n), 0.5)
        for k, n in zip(wins, eligible["trade_count"].astype(int))
    ]
    magnitude_gate = (eligible["total_return"] > 0) & (eligible["excess_return_vs_buy_hold"] > 0)
    eligible["gate_pass"] = magnitude_gate

    tier_counts: dict[float, int] = {}
    meta_p: dict[float, float] = {}
    meta_tier = ""
    for alpha in config.tiers:
        significant = eligible.loc[eligible["gate_pass"] & (eligible["binomial_p_"] <= alpha)]
        tier_counts[alpha] = int(len(significant))
        meta_p[alpha] = binomial_pvalue_ge(tier_counts[alpha], eligible_symbols, alpha)
    for alpha in sorted(config.tiers):  # tightest first; first pass wins
        if meta_p[alpha] <= alpha:
            meta_tier = _tier_label(alpha)
            break

    def _symbol_tier(p: float) -> str:
        for alpha in sorted(config.tiers):
            if p <= alpha:
                return _tier_label(alpha)
        return ""

    stock_rows: list[dict[str, Any]] = []
    loosest = max(config.tiers)
    significant_any = eligible.loc[eligible["gate_pass"] & (eligible["binomial_p_"] <= loosest)]
    for row in significant_any.itertuples():
        p = float(row.binomial_p_)
        stock_rows.append(
            {
                "strategy_id": data.strategy_id,
                "category": data.category,
                "symbol": row.symbol,
                "tier": _symbol_tier(p),
                "in_pool": bool(p <= config.pool_tier),
                "binomial_p": p,
                "trade_count": int(row.trade_count),
                "win_rate": float(row.win_rate),
                "total_return": float(row.total_return),
                "buy_hold_return": float(row.buy_hold_return),
                "excess_return_vs_buy_hold": float(row.excess_return_vs_buy_hold),
                "board": row.board,
                "industry_group": row.industry_group,
                "market_cap_bucket": row.market_cap_bucket,
                "liquidity_bucket": row.liquidity_bucket,
            }
        )
    stock_rows.sort(key=lambda r: (r["strategy_id"], r["binomial_p"], -r["excess_return_vs_buy_hold"], r["symbol"]))

    pool = eligible.loc[eligible["gate_pass"] & (eligible["binomial_p_"] <= config.pool_tier)]
    pool_size = int(len(pool))
    market_mean_excess = float(eligible["excess_return_vs_buy_hold"].mean()) if eligible_symbols else None
    pool_mean_excess = float(pool["excess_return_vs_buy_hold"].mean()) if pool_size else None
    pool_mean_total = float(pool["total_return"].mean()) if pool_size else None
    pool_mean_bh = float(pool["buy_hold_return"].mean()) if pool_size else None

    stability_months_covered = None
    stability_ratio = None
    stability_pool_month_mean_min = None
    if data.monthly is not None and not data.monthly.empty and pool_size:
        monthly = data.monthly.dropna(subset=["total_return"])
        universe_monthly = monthly.groupby("window")["total_return"].mean()
        pool_symbols = set(pool["symbol"].astype(str))
        pool_monthly = (
            monthly.loc[monthly["symbol"].astype(str).isin(pool_symbols)]
            .groupby("window")["total_return"]
            .mean()
            .dropna()
        )
        common = pool_monthly.index.intersection(universe_monthly.index)
        if len(common):
            stability_months_covered = int(len(common))
            stability_ratio = float((pool_monthly.loc[common] > universe_monthly.loc[common]).mean())
            stability_pool_month_mean_min = float(pool_monthly.loc[common].min())

    class_rows: list[dict[str, Any]] = []
    for dim in DIMENSIONS:
        universe_counts = eligible.groupby(eligible[dim]).size()
        for class_value, universe_count in universe_counts.items():
            if int(universe_count) < config.min_class_size:
                continue
            pool_in_class = int((pool[dim] == class_value).sum())
            p_value = hypergeom_pvalue_ge(eligible_symbols, int(universe_count), pool_size, pool_in_class)
            class_pool = pool.loc[pool[dim] == class_value]
            class_rows.append(
                {
                    "strategy_id": data.strategy_id,
                    "category": data.category,
                    "dimension": dim,
                    "class_value": class_value,
                    "universe_count": int(universe_count),
                    "pool_count": pool_in_class,
                    "pool_share": pool_in_class / pool_size if pool_size else None,
                    "universe_share": int(universe_count) / eligible_symbols if eligible_symbols else None,
                    "pool_mean_excess": float(class_pool["excess_return_vs_buy_hold"].mean()) if pool_in_class else None,
                    "p_value": p_value,
                }
            )
    class_rows.sort(key=lambda r: (r["strategy_id"], r["dimension"], r["p_value"], r["class_value"]))

    best = min(class_rows, key=lambda r: r["p_value"], default=None)
    summary_row: dict[str, Any] = {
        "strategy_id": data.strategy_id,
        "category": data.category,
        "eligible_symbols": eligible_symbols,
        "free_rider_count": free_rider_count,
        "market_mean_excess": market_mean_excess,
        "pool_tier": _tier_label(config.pool_tier),
        "pool_size": pool_size,
        "pool_mean_excess": pool_mean_excess,
        "pool_mean_total_return": pool_mean_total,
        "pool_mean_buy_hold_return": pool_mean_bh,
        "meta_tier": meta_tier,
        "stability_months_covered": stability_months_covered,
        "stability_ratio": stability_ratio,
        "stability_pool_month_mean_min": stability_pool_month_mean_min,
        "best_dimension": best["dimension"] if best else None,
        "best_class": best["class_value"] if best else None,
        "best_class_pool_count": best["pool_count"] if best else None,
        "best_class_pool_mean_excess": best["pool_mean_excess"] if best else None,
        "best_class_p": best["p_value"] if best else None,
    }
    for alpha in config.tiers:
        label = _tier_label(alpha)
        summary_row[f"n_{label}"] = tier_counts[alpha]
        summary_row[f"fpe_{label}"] = eligible_symbols * alpha
        summary_row[f"meta_p_{label}"] = meta_p[alpha]
    return StrategyFitResult(summary_row=summary_row, stock_rows=stock_rows, class_rows=class_rows)


# ---------------------------------------------------------------------------
# batch-level orchestration and outputs
# ---------------------------------------------------------------------------


def analyze_batch(
    batch_dir: Path,
    metadata: pd.DataFrame,
    config: FitConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, str]]]:
    """Run fit analysis over all strategies in a batch.

    Returns (summary_df, stocks_df, classes_df, skipped). BH-FDR q-values are
    computed globally across all (strategy x dimension x class) tests.
    """
    loaded, skipped = load_batch(batch_dir)
    summary_rows: list[dict[str, Any]] = []
    stock_rows: list[dict[str, Any]] = []
    class_rows: list[dict[str, Any]] = []
    for data in loaded:
        result = analyze_strategy(data, metadata, config)
        summary_rows.append(result.summary_row)
        stock_rows.extend(result.stock_rows)
        class_rows.extend(result.class_rows)

    q_values = benjamini_hochberg([r["p_value"] for r in class_rows])
    q_by_key = {
        (r["strategy_id"], r["dimension"], r["class_value"]): q
        for r, q in zip(class_rows, q_values)
    }
    for row in class_rows:
        row["q_value"] = q_by_key[(row["strategy_id"], row["dimension"], row["class_value"])]

    for row in summary_rows:
        key = (row["strategy_id"], row.get("best_dimension"), row.get("best_class"))
        best_q = q_by_key.get(key)
        row["best_class_q"] = best_q
        row["class_edge"] = bool(
            row["meta_tier"]
            and row.get("best_class_pool_mean_excess") is not None
            and row.get("market_mean_excess") is not None
            and best_q is not None
            and best_q <= 0.05
            and (row["best_class_pool_mean_excess"] - row["market_mean_excess"]) >= config.class_edge_min_pp
        )

    summary_df = pd.DataFrame(summary_rows)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(
            ["meta_tier", "pool_mean_excess", "strategy_id"],
            ascending=[True, False, True],
            na_position="last",
        ).reset_index(drop=True)
    stocks_df = pd.DataFrame(stock_rows)
    classes_df = pd.DataFrame(class_rows)
    return summary_df, stocks_df, classes_df, skipped


def write_fit_outputs(
    output_dir: Path,
    summary_df: pd.DataFrame,
    stocks_df: pd.DataFrame,
    classes_df: pd.DataFrame,
    skipped: list[dict[str, str]],
    *,
    batch_dir: Path,
    config: FitConfig,
    generated_at: str | None = None,
) -> dict[str, Path]:
    """Write strategy_fit outputs + report_manifest.json. Returns paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()

    paths: dict[str, Path] = {
        "strategy_fit_summary": output_dir / "strategy_fit_summary.csv",
        "strategy_fit_stocks": output_dir / "strategy_fit_stocks.csv",
        "strategy_fit_classes": output_dir / "strategy_fit_classes.csv",
        "strategy_fit_report": output_dir / "strategy_fit_report.md",
        "report_manifest": output_dir / "report_manifest.json",
    }
    summary_df.to_csv(paths["strategy_fit_summary"], index=False)
    stocks_df.to_csv(paths["strategy_fit_stocks"], index=False)
    classes_df.to_csv(paths["strategy_fit_classes"], index=False)

    lines = [
        "# Strategy Fit Report",
        "",
        f"- batch_dir: `{batch_dir}`",
        f"- generated_at: {generated_at}",
        f"- pool_tier: {_tier_label(config.pool_tier)}% (binomial p <= {config.pool_tier})",
        f"- min_trades: {config.min_trades}; min_class_size: {config.min_class_size}",
        f"- strategies analyzed: {len(summary_df)}; skipped: {len(skipped)}",
        "",
        "> Screening evidence only — not a research conclusion (R-QRE-008).",
        "> Winners require: net return > 0, excess vs buy-hold > 0, and binomial significance.",
        "",
        "## Strategy ranking (by meta tier, then pool mean excess)",
        "",
        "| rank | strategy | meta_tier | n_99 | pool_excess | market_excess | stability | best class | class_edge |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for rank, row in enumerate(summary_df.head(30).itertuples(), start=1):
        best_class = (
            f"{row.best_dimension}={row.best_class}" if getattr(row, "best_dimension", None) else "-"
        )
        stability = "-"
        if getattr(row, "stability_ratio", None) is not None and not pd.isna(row.stability_ratio):
            stability = f"{row.stability_ratio:.2f}/{int(row.stability_months_covered)}m"
        lines.append(
            f"| {rank} | {row.strategy_id} | {row.meta_tier or '-'} | {getattr(row, 'n_99', 0)} | "
            f"{_fmt(row.pool_mean_excess)} | {_fmt(row.market_mean_excess)} | {stability} | {best_class} | "
            f"{'YES' if row.class_edge else ''} |"
        )
    lines += [
        "",
        "## Class-edge strategies",
        "",
    ]
    edge = summary_df.loc[summary_df["class_edge"]] if not summary_df.empty and "class_edge" in summary_df.columns else pd.DataFrame()
    if edge.empty:
        lines.append("(none)")
    else:
        for row in edge.itertuples():
            lines.append(
                f"- **{row.strategy_id}** ({row.category}): pool_excess {_fmt(row.pool_mean_excess)} "
                f"vs market {_fmt(row.market_mean_excess)}; best class `{row.best_dimension}={row.best_class}` "
                f"(q={_fmt(row.best_class_q, 4)})"
            )
    if skipped:
        lines += ["", "## Skipped strategies", ""]
        lines.extend(f"- {s['strategy_id']} ({s['category']}): {s['reason']}" for s in skipped)
    lines.append("")
    paths["strategy_fit_report"].write_text("\n".join(lines), encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "kind": MANIFEST_KIND,
        "generated_at": generated_at,
        "batch_dir": str(batch_dir),
        "config": {
            "tiers": list(config.tiers),
            "pool_tier": config.pool_tier,
            "min_trades": config.min_trades,
            "min_class_size": config.min_class_size,
        },
        "files": [
            {"key": key, "path": path.name, "filename": path.name, "role": role}
            for key, role in (
                ("strategy_fit_summary", "strategy_fit_summary"),
                ("strategy_fit_stocks", "strategy_fit_stocks"),
                ("strategy_fit_classes", "strategy_fit_classes"),
                ("strategy_fit_report", "strategy_fit_report"),
                ("report_manifest", "report_manifest"),
            )
            for path in [paths[key]]
        ],
    }
    paths["report_manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return paths


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)
