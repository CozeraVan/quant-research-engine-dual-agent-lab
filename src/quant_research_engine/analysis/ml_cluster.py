"""ML clustering & noise analysis on M10.1 strategy-fit stock pools (M10.4).

Answers "do the effective stocks of one strategy share interpretable common
features" on top of the M10.1 significance framework (binomial tiers
90%/99%/99.9%, excess-return magnitude gate, class enrichment). This module
never re-runs statistics and never lowers tier standards: it only reads the
per-stock rows that ``analysis/strategy_fit.py`` already judged significant.

Design contract:

- scikit-learn is imported lazily; without it this module still imports and
  every entry point raises a clear ``MlUnavailableError``. The main
  environment therefore keeps working unchanged.
- DBSCAN is used because it needs no pre-committed cluster count and labels
  outliers as noise (label ``-1``). Small samples and degenerate inputs get
  explicit ``insufficient`` / ``single_cluster`` / ``all_noise`` statuses
  instead of fabricated clusters.
- Deterministic: inputs are sorted by ``(strategy_id, symbol)``, imputation
  uses medians, one-hot columns are sorted, and DBSCAN has no stochastic
  component. ``random_state`` is recorded in the manifest as part of the
  reproducibility contract.
- All tier/gate semantics are reused verbatim from M10.1
  (``strategy_fit.TIER_LABELS``, ``DIMENSIONS``); nothing is recomputed here.
- The optional eps sensitivity sweep (``analyze_eps_grid``) re-clusters the
  same fit rows once per eps. It is opt-in and writes only
  ``ml_cluster_sensitivity_*`` files, so the default artifacts and manifest
  stay unchanged.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from quant_research_engine.analysis.strategy_fit import DIMENSIONS, UNKNOWN_BUCKET

MANIFEST_KIND = "strategy_fit_ml_cluster_manifest"
ALGORITHM = "DBSCAN"

# Performance columns carried over from the M10.1 per-stock fit rows.
# ``binomial_p`` is intentionally excluded: it is a monotone function of
# ``win_rate`` and ``trade_count`` and would double-count significance.
DEFAULT_NUMERIC_FEATURES: tuple[str, ...] = (
    "trade_count",
    "win_rate",
    "total_return",
    "buy_hold_return",
    "excess_return_vs_buy_hold",
)

# Required columns of the M10.1 strategy_fit_stocks.csv input.
REQUIRED_INPUT_COLUMNS = (
    "strategy_id",
    "symbol",
    "tier",
    "in_pool",
    "binomial_p",
    "trade_count",
    "win_rate",
    "total_return",
    "buy_hold_return",
    "excess_return_vs_buy_hold",
)

STATUS_OK = "ok"
STATUS_SINGLE_CLUSTER = "single_cluster"
STATUS_ALL_NOISE = "all_noise"
STATUS_SMALL_CLUSTERS = "small_clusters_only"
STATUS_INSUFFICIENT = "insufficient"
NOISE_LABEL = -1

SENSITIVITY_KIND = "strategy_fit_ml_cluster_sensitivity"
STATUS_CHOICES = (
    STATUS_OK,
    STATUS_SINGLE_CLUSTER,
    STATUS_ALL_NOISE,
    STATUS_SMALL_CLUSTERS,
    STATUS_INSUFFICIENT,
)


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "1.0"}


def _normalize_tier(value: Any) -> str:
    """Restore M10.1 tier labels ('90'/'99'/'99.9') after a CSV round-trip."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class MlUnavailableError(RuntimeError):
    """Raised when a clustering entry point is called without scikit-learn."""


def ml_cluster_available() -> bool:
    """True when scikit-learn can be imported (checked lazily, no caching)."""
    try:
        import sklearn  # noqa: F401
    except Exception:
        return False
    return True


def _require_sklearn() -> tuple[Any, Any]:
    try:
        from sklearn.cluster import DBSCAN
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:  # pragma: no cover - exercised via monkeypatched env
        raise MlUnavailableError(
            "scikit-learn is required for ML clustering but is not installed "
            "in this environment. Use the project's .venv-ml "
            "(scikit-learn 1.9.0 / pandas / numpy); the main environment "
            "degrades gracefully and keeps all non-ML functionality."
        ) from exc
    return DBSCAN, StandardScaler


def _sklearn_version() -> str | None:
    try:
        import sklearn
    except Exception:
        return None
    return str(getattr(sklearn, "__version__", "unknown"))


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MlClusterConfig:
    eps: float = 1.0
    min_samples: int = 5
    min_cluster_size: int = 3
    random_state: int = 42
    numeric_features: tuple[str, ...] = DEFAULT_NUMERIC_FEATURES
    categorical_features: tuple[str, ...] = DIMENSIONS
    pool_only: bool = False

    def to_manifest(self) -> dict[str, Any]:
        return {
            "algorithm": ALGORITHM,
            "eps": self.eps,
            "min_samples": self.min_samples,
            "min_cluster_size": self.min_cluster_size,
            "random_state": self.random_state,
            "numeric_features": list(self.numeric_features),
            "categorical_features": list(self.categorical_features),
            "pool_only": self.pool_only,
        }


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------


def load_fit_stocks(fit_dir: Path) -> pd.DataFrame:
    """Load the M10.1 per-stock fit rows from an existing fit output dir."""
    stocks_path = Path(fit_dir) / "strategy_fit_stocks.csv"
    if not stocks_path.exists():
        raise FileNotFoundError(
            f"strategy_fit_stocks.csv not found in {fit_dir}; run "
            f"scripts/strategy_fit_report.py first (M10.1 artifacts are the "
            f"only input for M10.4 clustering)"
        )
    frame = pd.read_csv(stocks_path)
    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"strategy_fit_stocks.csv missing columns: {missing}")
    return frame


def load_metadata_csv(path: Path) -> pd.DataFrame:
    """Load an optional read-only metadata snapshot keyed by ts_code/symbol."""
    frame = pd.read_csv(path)
    key = "ts_code" if "ts_code" in frame.columns else ("symbol" if "symbol" in frame.columns else None)
    if key is None:
        raise ValueError(f"metadata CSV {path} must contain a 'ts_code' or 'symbol' column")
    frame = frame.rename(columns={key: "symbol"})
    return frame.drop_duplicates(subset=["symbol"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# feature engineering
# ---------------------------------------------------------------------------


@dataclass
class FeatureMatrix:
    values: Any  # np.ndarray, standardized
    feature_names: list[str]
    imputed_counts: dict[str, int]
    constant_features: list[str]
    metadata_columns: list[str]


def build_feature_matrix(
    frame: pd.DataFrame,
    metadata: pd.DataFrame | None,
    config: MlClusterConfig,
) -> FeatureMatrix:
    """Numeric median-imputation + one-hot categoricals + standardization.

    Deterministic: medians over the given frame, one-hot columns sorted by
    name, StandardScaler (zero-variance columns map to zeros, never NaN).
    """
    work = frame.copy()
    metadata_columns: list[str] = []
    if metadata is not None and not metadata.empty:
        extra_columns = [c for c in metadata.columns if c != "symbol" and c not in work.columns]
        if extra_columns:
            extra = metadata.loc[:, ["symbol", *extra_columns]]
            work = work.merge(extra, left_on="symbol", right_on="symbol", how="left")
            metadata_columns = [str(c) for c in extra_columns]

    numeric_columns = [c for c in config.numeric_features if c in work.columns]
    # ``binomial_p`` is deliberately excluded from auto-detected numeric
    # columns: it is a monotone function of win_rate/trade_count.
    numeric_columns += [
        c for c in work.select_dtypes(include="number").columns
        if c not in numeric_columns
        and c not in {"symbol", "strategy_id", "category", "binomial_p", "in_pool"}
        and not c.startswith("ml_")
    ]
    categorical_columns = [c for c in config.categorical_features if c in work.columns]

    imputed_counts: dict[str, int] = {}
    numeric_frame = pd.DataFrame(index=work.index)
    for column in numeric_columns:
        series = pd.to_numeric(work[column], errors="coerce")
        n_missing = int(series.isna().sum())
        if n_missing:
            imputed_counts[column] = n_missing
        median = series.median()
        series = series.fillna(0.0 if pd.isna(median) else float(median))
        numeric_frame[column] = series.astype(float)

    constant_features = sorted(
        c for c in numeric_frame.columns if numeric_frame[c].nunique(dropna=False) <= 1
    )

    encoded = numeric_frame
    for column in categorical_columns:
        values = work[column].fillna(UNKNOWN_BUCKET).astype(str)
        dummies = pd.get_dummies(values, prefix=column, dtype=float)
        encoded = pd.concat([encoded, dummies], axis=1)
        for dummy_column in dummies.columns:
            if dummies[dummy_column].nunique(dropna=False) <= 1:
                constant_features.append(str(dummy_column))
    constant_features = sorted(set(constant_features))
    encoded = encoded.reindex(sorted(encoded.columns), axis=1)

    _, StandardScaler = _require_sklearn()
    scaler = StandardScaler()
    values = scaler.fit_transform(encoded.to_numpy(dtype=float))
    return FeatureMatrix(
        values=values,
        feature_names=[str(c) for c in encoded.columns],
        imputed_counts=imputed_counts,
        constant_features=constant_features,
        metadata_columns=metadata_columns,
    )


# ---------------------------------------------------------------------------
# clustering
# ---------------------------------------------------------------------------


@dataclass
class StrategyMlResult:
    strategy_id: str
    category: str
    status: str
    reason: str
    stock_rows: list[dict[str, Any]]
    cluster_rows: list[dict[str, Any]]
    imputed_features: dict[str, int] = field(default_factory=dict)
    constant_features: list[str] = field(default_factory=list)


def _dominant(frame: pd.DataFrame, column: str) -> tuple[str | None, float | None]:
    if frame.empty or column not in frame.columns:
        return None, None
    counts = frame[column].fillna(UNKNOWN_BUCKET).astype(str).value_counts()
    if counts.empty:
        return None, None
    # deterministic: highest count first, then lexicographic
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    value, count = ordered[0]
    return str(value), count / len(frame)


def _fmt_share(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def cluster_strategy(
    frame: pd.DataFrame,
    config: MlClusterConfig,
    metadata: pd.DataFrame | None = None,
) -> StrategyMlResult:
    """Cluster one strategy's significant stocks; never fabricates structure."""
    strategy_id = str(frame["strategy_id"].iloc[0])
    category = str(frame["category"].iloc[0]) if "category" in frame.columns and not frame.empty else ""
    work = frame.sort_values(["symbol"]).reset_index(drop=True)

    context_columns = [
        c for c in (
            "symbol", "tier", "in_pool", "trade_count", "win_rate",
            "total_return", "buy_hold_return", "excess_return_vs_buy_hold",
            "board", "industry_group", "market_cap_bucket", "liquidity_bucket",
        )
        if c in work.columns
    ]

    def _stock_rows(labels: list[int] | None) -> list[dict[str, Any]]:
        rows = []
        for idx, row in work.iterrows():
            label = None if labels is None else int(labels[idx])
            rows.append(
                {
                    "strategy_id": strategy_id,
                    "category": category,
                    "symbol": str(row["symbol"]),
                    "tier": _normalize_tier(row["tier"]),
                    "in_pool": _as_bool(row["in_pool"]),
                    "cluster": label,
                    "is_noise": bool(label == NOISE_LABEL) if label is not None else False,
                    **{c: row[c] for c in context_columns if c not in {"symbol", "tier", "in_pool"}},
                }
            )
        return rows

    def _insufficient(reason: str) -> StrategyMlResult:
        return StrategyMlResult(
            strategy_id=strategy_id,
            category=category,
            status=STATUS_INSUFFICIENT,
            reason=reason,
            stock_rows=_stock_rows(None),
            cluster_rows=[
                {
                    "strategy_id": strategy_id,
                    "category": category,
                    "cluster": "",
                    "status": STATUS_INSUFFICIENT,
                    "size": 0,
                    "mean_total_return": None,
                    "mean_excess_return": None,
                    "mean_win_rate": None,
                    "n_tier_90": 0,
                    "n_tier_99": 0,
                    "n_tier_99_9": 0,
                    "dominant_features": "",
                    "summary": reason,
                }
            ],
        )

    if len(work) < config.min_samples:
        return _insufficient(
            f"insufficient: {len(work)} significant stocks < min_samples={config.min_samples}"
        )

    features = build_feature_matrix(work, metadata, config)

    DBSCAN, _ = _require_sklearn()
    model = DBSCAN(eps=config.eps, min_samples=config.min_samples)
    labels = model.fit_predict(features.values)

    noise_count = int(sum(1 for x in labels if int(x) == NOISE_LABEL))
    cluster_ids = sorted({int(x) for x in labels if int(x) != NOISE_LABEL})

    tier_counts_by_cluster: dict[int, dict[str, int]] = {}
    for idx, label in enumerate(labels):
        bucket = tier_counts_by_cluster.setdefault(int(label), {"90": 0, "99": 0, "99.9": 0})
        tier = _normalize_tier(work.loc[idx, "tier"])
        if tier in bucket:
            bucket[tier] += 1

    cluster_rows: list[dict[str, Any]] = []
    for label in cluster_ids:
        members = work.loc[[int(x) == label for x in labels]]
        if len(members) < config.min_cluster_size:
            continue
        tiers = tier_counts_by_cluster.get(label, {"90": 0, "99": 0, "99.9": 0})
        dominants = []
        for dim in config.categorical_features:
            if dim not in members.columns:
                continue
            value, share = _dominant(members, dim)
            if value is not None:
                dominants.append(f"{dim}={value} ({_fmt_share(share)})")
        mean_total = float(members["total_return"].mean()) if "total_return" in members.columns else None
        mean_excess = (
            float(members["excess_return_vs_buy_hold"].mean())
            if "excess_return_vs_buy_hold" in members.columns else None
        )
        mean_win = float(members["win_rate"].mean()) if "win_rate" in members.columns else None
        dominant_text = "; ".join(dominants)
        summary = (
            f"cluster {label}: {len(members)} significant stocks; "
            f"mean total_return {_fmt(mean_total)}, mean excess {_fmt(mean_excess)}; "
            f"tiers 90/99/99.9 = {tiers['90']}/{tiers['99']}/{tiers['99.9']}; "
            f"dominant features: {dominant_text or 'none'}"
        )
        cluster_rows.append(
            {
                "strategy_id": strategy_id,
                "category": category,
                "cluster": label,
                "status": STATUS_OK,
                "size": int(len(members)),
                "mean_total_return": mean_total,
                "mean_excess_return": mean_excess,
                "mean_win_rate": mean_win,
                "n_tier_90": tiers["90"],
                "n_tier_99": tiers["99"],
                "n_tier_99_9": tiers["99.9"],
                "dominant_features": dominant_text,
                "summary": summary,
            }
        )

    if cluster_rows:
        status = STATUS_SINGLE_CLUSTER if (len(cluster_rows) == 1 and noise_count == 0) else STATUS_OK
        reason = ""
    elif cluster_ids:
        status = STATUS_SMALL_CLUSTERS
        reason = (
            f"small_clusters_only: {len(cluster_ids)} cluster(s) found but every one is "
            f"smaller than min_cluster_size={config.min_cluster_size}"
        )
    else:
        status = STATUS_ALL_NOISE
        reason = f"all_noise: every one of {len(work)} stocks is an outlier (eps={config.eps})"

    if noise_count:
        noise_rows = work.loc[[int(x) == NOISE_LABEL for x in labels]]
        cluster_rows.append(
            {
                "strategy_id": strategy_id,
                "category": category,
                "cluster": NOISE_LABEL,
                "status": "noise",
                "size": noise_count,
                "mean_total_return": float(noise_rows["total_return"].mean()) if "total_return" in noise_rows.columns else None,
                "mean_excess_return": float(noise_rows["excess_return_vs_buy_hold"].mean()) if "excess_return_vs_buy_hold" in noise_rows.columns else None,
                "mean_win_rate": float(noise_rows["win_rate"].mean()) if "win_rate" in noise_rows.columns else None,
                "n_tier_90": tier_counts_by_cluster.get(NOISE_LABEL, {}).get("90", 0),
                "n_tier_99": tier_counts_by_cluster.get(NOISE_LABEL, {}).get("99", 0),
                "n_tier_99_9": tier_counts_by_cluster.get(NOISE_LABEL, {}).get("99.9", 0),
                "dominant_features": "",
                "summary": (
                    f"noise: {noise_count} outlier stocks do not belong to any "
                    f"cluster (eps={config.eps}, min_samples={config.min_samples})"
                ),
            }
        )

    return StrategyMlResult(
        strategy_id=strategy_id,
        category=category,
        status=status,
        reason=reason,
        stock_rows=_stock_rows([int(x) for x in labels]),
        cluster_rows=cluster_rows,
        imputed_features=dict(features.imputed_counts),
        constant_features=list(features.constant_features),
    )


# ---------------------------------------------------------------------------
# batch orchestration and outputs
# ---------------------------------------------------------------------------


def analyze_fit_stocks(
    stocks: pd.DataFrame,
    metadata: pd.DataFrame | None,
    config: MlClusterConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    """Cluster every strategy's significant stocks in a fit-stocks frame.

    Returns (stocks_df, clusters_df, strategy_status_rows). Metadata (if any)
    enriches the feature matrix but never changes tier/gate columns.
    """
    frame = stocks.copy()
    if config.pool_only and "in_pool" in frame.columns:
        frame = frame.loc[frame["in_pool"].astype(str).str.lower().isin(["true", "1"])]
    frame = frame.loc[frame["tier"].notna() & (frame["tier"].astype(str) != "")]

    stock_rows: list[dict[str, Any]] = []
    cluster_rows: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    if frame.empty:
        return pd.DataFrame(), pd.DataFrame(), status_rows

    for strategy_id, group in frame.groupby("strategy_id", sort=True):
        result = cluster_strategy(group, config, metadata)
        status_rows.append(
            {
                "strategy_id": result.strategy_id,
                "category": result.category,
                "status": result.status,
                "reason": result.reason,
                "n_stocks": len(result.stock_rows),
                "n_clusters": sum(1 for r in result.cluster_rows if r["status"] == STATUS_OK),
                "n_noise": sum(1 for r in result.stock_rows if r["is_noise"]),
                "imputed_features": result.imputed_features,
                "constant_features": result.constant_features,
            }
        )
        stock_rows.extend(result.stock_rows)
        cluster_rows.extend(result.cluster_rows)

    stocks_df = pd.DataFrame(stock_rows)
    if not stocks_df.empty:
        stocks_df = stocks_df.sort_values(["strategy_id", "symbol"]).reset_index(drop=True)
    clusters_df = pd.DataFrame(cluster_rows)
    if not clusters_df.empty:
        order = clusters_df["cluster"].map(lambda v: int(v) if isinstance(v, int) else -2)
        clusters_df = (
            clusters_df.assign(_order=order)
            .sort_values(["strategy_id", "_order"])
            .drop(columns="_order")
            .reset_index(drop=True)
        )
    return stocks_df, clusters_df, status_rows


def write_ml_outputs(
    output_dir: Path,
    stocks_df: pd.DataFrame,
    clusters_df: pd.DataFrame,
    status_rows: list[dict[str, Any]],
    *,
    fit_dir: Path,
    config: MlClusterConfig,
    metadata: pd.DataFrame | None = None,
    generated_at: str | None = None,
) -> dict[str, Path]:
    """Write M10.4 ML outputs + ml_cluster_manifest.json into its own dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()

    paths: dict[str, Path] = {
        "ml_cluster_stocks": output_dir / "ml_cluster_stocks.csv",
        "ml_cluster_clusters": output_dir / "ml_cluster_clusters.csv",
        "ml_cluster_report": output_dir / "ml_cluster_report.md",
        "ml_cluster_manifest": output_dir / "ml_cluster_manifest.json",
    }
    stocks_df.to_csv(paths["ml_cluster_stocks"], index=False)
    clusters_df.to_csv(paths["ml_cluster_clusters"], index=False)

    lines = [
        "# ML Cluster & Noise Report (M10.4)",
        "",
        f"- fit_dir: `{fit_dir}`",
        f"- generated_at: {generated_at}",
        f"- algorithm: {ALGORITHM} (scikit-learn {_sklearn_version() or 'unavailable'})",
        f"- eps: {config.eps}; min_samples: {config.min_samples}; "
        f"min_cluster_size: {config.min_cluster_size}; random_state: {config.random_state}",
        f"- pool_only: {config.pool_only}",
        f"- strategies analyzed: {len(status_rows)}",
        "",
        "> Screening evidence only — not a research conclusion (R-QRE-008).",
        "> Stocks, tiers (90%/99%/99.9%) and the excess-return gate are inherited",
        "> unchanged from M10.1; this report only clusters them.",
        "",
    ]
    for row in status_rows:
        lines.append(f"## {row['strategy_id']} ({row['category']}) — {row['status']}")
        lines.append("")
        if row["status"] == STATUS_INSUFFICIENT:
            lines.append(f"- {row['reason']}")
            lines.append("")
            continue
        strategy_clusters = (
            clusters_df.loc[clusters_df["strategy_id"] == row["strategy_id"]]
            if not clusters_df.empty else pd.DataFrame()
        )
        lines.append(
            f"- stocks: {row['n_stocks']}; clusters: {row['n_clusters']}; noise: {row['n_noise']}"
        )
        lines.append("")
        lines.append("| cluster | size | mean_total | mean_excess | tiers 90/99/99.9 | dominant features |")
        lines.append("|---|---|---|---|---|---|")
        for cluster_row in strategy_clusters.itertuples():
            lines.append(
                f"| {cluster_row.cluster} | {cluster_row.size} | "
                f"{_fmt(cluster_row.mean_total_return)} | {_fmt(cluster_row.mean_excess_return)} | "
                f"{cluster_row.n_tier_90}/{cluster_row.n_tier_99}/{cluster_row.n_tier_99_9} | "
                f"{cluster_row.dominant_features or '-'} |"
            )
        lines.append("")
    paths["ml_cluster_report"].write_text("\n".join(lines), encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "kind": MANIFEST_KIND,
        "generated_at": generated_at,
        "fit_dir": str(fit_dir),
        "model": {
            "library": "scikit-learn",
            "version": _sklearn_version(),
            "algorithm": ALGORITHM,
        },
        "config": config.to_manifest(),
        "python": sys.version.split()[0],
        "input_fields": {
            "fit_dir": sorted(REQUIRED_INPUT_COLUMNS),
            "metadata": (
                sorted(str(c) for c in metadata.columns if c != "symbol")
                if metadata is not None and not metadata.empty else []
            ),
        },
        "determinism": (
            "inputs sorted by (strategy_id, symbol); median imputation; sorted "
            "one-hot columns; StandardScaler; DBSCAN is deterministic given "
            "fixed input order (random_state recorded for the reproducibility "
            "contract)"
        ),
        "strategies": status_rows,
        "files": [
            {"key": key, "path": path.name, "filename": path.name, "role": key}
            for key in (
                "ml_cluster_stocks",
                "ml_cluster_clusters",
                "ml_cluster_report",
                "ml_cluster_manifest",
            )
            for path in [paths[key]]
        ],
    }
    paths["ml_cluster_manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return paths


def parse_eps_grid(raw: str | None) -> list[float] | None:
    """Parse a comma-separated ``--eps-grid`` value; ``None`` keeps the default off."""
    if raw is None:
        return None
    values: list[float] = []
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            raise ValueError("--eps-grid contains an empty value")
        values.append(float(token))
    if not values:
        raise ValueError("--eps-grid must contain at least one eps value")
    return values


def analyze_eps_grid(
    stocks: pd.DataFrame,
    metadata: pd.DataFrame | None,
    config: MlClusterConfig,
    eps_values: list[float],
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Re-cluster the same fit rows once per eps; no statistics are recomputed.

    Returns (summary_rows, per_strategy_rows). The summary carries one row per
    eps with status counts, clustered-strategy count and total noise stocks.
    """
    summary_rows: list[dict[str, Any]] = []
    detail_frames: list[pd.DataFrame] = []
    for eps in eps_values:
        combo = replace(config, eps=eps)
        stocks_df, clusters_df, status_rows = analyze_fit_stocks(stocks, metadata, combo)
        counts = {status: 0 for status in STATUS_CHOICES}
        for row in status_rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        n_noise = (
            int(stocks_df["is_noise"].sum())
            if not stocks_df.empty and "is_noise" in stocks_df.columns
            else 0
        )
        summary_rows.append(
            {
                "eps": float(eps),
                "n_strategies": len(status_rows),
                "n_clustered_strategies": sum(1 for row in status_rows if row["n_clusters"] > 0),
                "n_clusters": sum(int(row["n_clusters"]) for row in status_rows),
                "n_stocks": len(stocks_df),
                "n_noise_stocks": n_noise,
                **{f"status_{status}": counts[status] for status in STATUS_CHOICES},
            }
        )
        if status_rows:
            detail = pd.DataFrame(status_rows)
            detail.insert(0, "eps", float(eps))
            detail_frames.append(detail)
    detail_df = (
        pd.concat(detail_frames, ignore_index=True) if detail_frames else pd.DataFrame()
    )
    return summary_rows, detail_df


def write_eps_sensitivity(
    output_dir: Path,
    summary_rows: list[dict[str, Any]],
    detail_df: pd.DataFrame,
    *,
    fit_dir: Path,
    config: MlClusterConfig,
    eps_values: list[float],
) -> dict[str, Path]:
    """Write deterministic sensitivity files; the four ml_cluster_* artifacts stay untouched."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {
        "ml_cluster_sensitivity": output_dir / "ml_cluster_sensitivity.csv",
        "ml_cluster_sensitivity_strategies": output_dir / "ml_cluster_sensitivity_strategies.csv",
        "ml_cluster_sensitivity_manifest": output_dir / "ml_cluster_sensitivity.json",
    }
    pd.DataFrame(summary_rows).to_csv(paths["ml_cluster_sensitivity"], index=False)
    detail_df.to_csv(paths["ml_cluster_sensitivity_strategies"], index=False)

    manifest = {
        "schema_version": 1,
        "kind": SENSITIVITY_KIND,
        "fit_dir": str(fit_dir),
        "eps_grid": [float(eps) for eps in eps_values],
        "model": {
            "library": "scikit-learn",
            "version": _sklearn_version(),
            "algorithm": ALGORITHM,
        },
        "config": config.to_manifest(),
        "python": sys.version.split()[0],
        "determinism": (
            "same fit_dir rows as the main run; one DBSCAN pass per eps on the "
            "identically sorted/standardized matrix; files carry no timestamp so "
            "repeated runs are byte-identical for the same input and environment"
        ),
        "combos": summary_rows,
        "files": [
            {"key": key, "path": path.name, "filename": path.name, "role": key}
            for key, path in paths.items()
        ],
    }
    paths["ml_cluster_sensitivity_manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return paths


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)
