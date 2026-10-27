"""Tests for analysis.ml_cluster (M10.4).

Covers synthetic known groups + outliers, 90/99/99.9 tier preservation,
missing/constant features, insufficient samples, single-cluster and
all-noise boundaries, reproducibility, the manifest contract, optional
scikit-learn degradation, and the CLI happy path.

The suite runs in both environments: with .venv-ml (scikit-learn present)
for the full analysis, and in the main environment (no scikit-learn) the
degradation tests still pass because sklearn is imported lazily.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from quant_research_engine.analysis.ml_cluster import (
    MANIFEST_KIND,
    MlClusterConfig,
    MlUnavailableError,
    STATUS_ALL_NOISE,
    STATUS_INSUFFICIENT,
    STATUS_OK,
    STATUS_SINGLE_CLUSTER,
    analyze_fit_stocks,
    build_feature_matrix,
    cluster_strategy,
    load_fit_stocks,
    load_metadata_csv,
    ml_cluster_available,
    write_ml_outputs,
)

FIT_COLUMNS = [
    "strategy_id", "category", "symbol", "tier", "in_pool", "binomial_p",
    "trade_count", "win_rate", "total_return", "buy_hold_return",
    "excess_return_vs_buy_hold", "board", "industry_group",
    "market_cap_bucket", "liquidity_bucket",
]

# Tests that exercise actual clustering require scikit-learn (.venv-ml).
# In the main environment they skip; the degradation tests below still run.
requires_sklearn = pytest.mark.skipif(
    not ml_cluster_available(), reason="scikit-learn not installed (main environment)"
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _stock_row(
    strategy_id,
    symbol,
    *,
    tier="90",
    in_pool=False,
    binomial_p=0.05,
    trade_count=20,
    win_rate=0.6,
    total_return=0.1,
    buy_hold=0.05,
    excess=0.05,
    board="main_board",
    industry_group="unknown",
    market_cap_bucket="small",
    liquidity_bucket="mid",
    category="test",
):
    return {
        "strategy_id": strategy_id,
        "category": category,
        "symbol": symbol,
        "tier": tier,
        "in_pool": in_pool,
        "binomial_p": binomial_p,
        "trade_count": trade_count,
        "win_rate": win_rate,
        "total_return": total_return,
        "buy_hold_return": buy_hold,
        "excess_return_vs_buy_hold": excess,
        "board": board,
        "industry_group": industry_group,
        "market_cap_bucket": market_cap_bucket,
        "liquidity_bucket": liquidity_bucket,
    }


def _two_groups_frame():
    """Two well-separated groups (A/B) plus two extreme outliers."""
    rows = []
    # group A: many trades, high win rate, large cap main board
    for i in range(10):
        rows.append(_stock_row(
            "two_groups", f"60000{i}.SH", tier="99" if i < 8 else "99.9",
            trade_count=40, win_rate=0.85, total_return=0.30, buy_hold=0.10,
            excess=0.20, board="main_board", market_cap_bucket="large",
            liquidity_bucket="high", binomial_p=0.001,
        ))
    # group B: few trades, modest win rate, small cap chinext
    for i in range(10):
        rows.append(_stock_row(
            "two_groups", f"30000{i}.SZ", tier="90",
            trade_count=12, win_rate=0.55, total_return=0.08, buy_hold=0.05,
            excess=0.03, board="chinext", market_cap_bucket="small",
            liquidity_bucket="mid", binomial_p=0.05,
        ))
    # outliers: extreme win rate / return, star market
    for i in range(2):
        rows.append(_stock_row(
            "two_groups", f"68800{i}.SH", tier="90",
            trade_count=90, win_rate=1.0, total_return=0.90, buy_hold=0.0,
            excess=0.90, board="star_market", market_cap_bucket="large",
            liquidity_bucket="high", binomial_p=0.03,
        ))
    return pd.DataFrame(rows, columns=FIT_COLUMNS)


def _write_fit_dir(tmp_path: Path, frame: pd.DataFrame, name: str = "fitTEST") -> Path:
    fit_dir = tmp_path / name
    fit_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(fit_dir / "strategy_fit_stocks.csv", index=False)
    return fit_dir


# ---------------------------------------------------------------------------
# clustering behavior
# ---------------------------------------------------------------------------


@requires_sklearn
def test_two_known_groups_and_outliers():
    frame = _two_groups_frame()
    config = MlClusterConfig(eps=1.0, min_samples=5, min_cluster_size=3)
    result = cluster_strategy(frame, config)

    assert result.status == STATUS_OK
    real_clusters = [r for r in result.cluster_rows if r["status"] == STATUS_OK]
    assert len(real_clusters) == 2
    noise_row = next(r for r in result.cluster_rows if r["status"] == "noise")
    assert noise_row["size"] == 2

    stocks = {r["symbol"]: r for r in result.stock_rows}
    assert stocks["688000.SH"]["is_noise"] and stocks["688001.SH"]["is_noise"]
    assert not stocks["600000.SH"]["is_noise"]
    assert not stocks["300000.SZ"]["is_noise"]

    # dominant categorical features identify the constructed groups
    by_board = {r["dominant_features"].split(";")[0]: r for r in real_clusters}
    main = next(r for r in real_clusters if "board=main_board" in r["dominant_features"])
    chinext = next(r for r in real_clusters if "board=chinext" in r["dominant_features"])
    assert main["size"] == 10 and chinext["size"] == 10
    assert main["mean_excess_return"] == pytest.approx(0.20)
    assert chinext["mean_excess_return"] == pytest.approx(0.03)
    assert len(by_board) == 2


@requires_sklearn
def test_tiers_90_99_999_preserved():
    frame = _two_groups_frame()
    config = MlClusterConfig()
    result = cluster_strategy(frame, config)

    input_tiers = dict(zip(frame["symbol"], frame["tier"]))
    output_tiers = {r["symbol"]: r["tier"] for r in result.stock_rows}
    assert output_tiers == input_tiers
    assert set(output_tiers.values()) == {"90", "99", "99.9"}

    # tier counts across cluster rows (incl. noise) add up to the input
    counted = {"90": 0, "99": 0, "99.9": 0}
    for row in result.cluster_rows:
        counted["90"] += row["n_tier_90"]
        counted["99"] += row["n_tier_99"]
        counted["99.9"] += row["n_tier_99_9"]
    expected = frame["tier"].value_counts().to_dict()
    assert counted == expected


@requires_sklearn
def test_single_cluster_boundary():
    # a tight gradient of near-identical stocks forms exactly one cluster
    rows = [
        _stock_row("flat", f"0000{i:02d}.SZ", trade_count=20 + i,
                   win_rate=0.6 + i * 0.001, total_return=0.1,
                   buy_hold=0.05, excess=0.05)
        for i in range(10)
    ]
    result = cluster_strategy(pd.DataFrame(rows, columns=FIT_COLUMNS), MlClusterConfig())
    assert result.status == STATUS_SINGLE_CLUSTER
    assert len([r for r in result.cluster_rows if r["status"] == STATUS_OK]) == 1
    assert all(not r["is_noise"] for r in result.stock_rows)


@requires_sklearn
def test_all_noise_boundary():
    # two tight mini-groups of 3 (< min_samples=5) far apart from each other
    rows = []
    for i in range(3):
        rows.append(_stock_row("sparse", f"10000{i}.SH", trade_count=10,
                               win_rate=0.9, excess=0.4))
    for i in range(3):
        rows.append(_stock_row("sparse", f"20000{i}.SH", trade_count=50,
                               win_rate=0.4, excess=-0.1))
    result = cluster_strategy(pd.DataFrame(rows, columns=FIT_COLUMNS), MlClusterConfig())
    assert result.status == STATUS_ALL_NOISE
    assert all(r["is_noise"] for r in result.stock_rows)
    assert result.cluster_rows[-1]["status"] == "noise"


def test_insufficient_samples():
    rows = [_stock_row("tiny", f"00000{i}.SZ") for i in range(3)]
    result = cluster_strategy(pd.DataFrame(rows, columns=FIT_COLUMNS), MlClusterConfig())
    assert result.status == STATUS_INSUFFICIENT
    assert "min_samples" in result.reason
    assert all(r["cluster"] is None and not r["is_noise"] for r in result.stock_rows)
    assert result.cluster_rows[0]["status"] == STATUS_INSUFFICIENT
    assert result.cluster_rows[0]["size"] == 0


@requires_sklearn
def test_missing_and_constant_features():
    rows = []
    for i in range(6):
        rows.append(_stock_row("gappy", f"60010{i}.SH", trade_count=30,
                               win_rate=0.6, total_return=0.2, buy_hold=0.1,
                               excess=0.1, board="main_board"))
    for i in range(6):
        rows.append(_stock_row("gappy", f"30010{i}.SZ", trade_count=8,
                               win_rate=0.6, total_return=0.02, buy_hold=0.0,
                               excess=0.02, board="chinext"))
    frame = pd.DataFrame(rows, columns=FIT_COLUMNS)
    # win_rate is constant everywhere; total_return missing for 4 stocks
    frame["win_rate"] = 0.6
    frame.loc[frame.index[:4], "total_return"] = float("nan")
    config = MlClusterConfig()
    result = cluster_strategy(frame, config)

    assert result.status in {STATUS_OK, STATUS_SINGLE_CLUSTER}
    assert result.imputed_features.get("total_return") == 4
    assert "win_rate" in result.constant_features
    # no NaN leaked into the feature matrix
    features = build_feature_matrix(frame, None, config)
    assert not pd.isna(features.values).any()


@requires_sklearn
def test_all_features_constant_is_single_cluster():
    # identical stocks carry no distinguishing signal; DBSCAN on the
    # all-zero standardized matrix deterministically yields one cluster —
    # no structure is fabricated and none is hidden.
    rows = [
        _stock_row("const", f"00000{i}.SZ", trade_count=20, win_rate=0.6,
                   total_return=0.1, buy_hold=0.05, excess=0.05, board="main_board")
        for i in range(6)
    ]
    frame = pd.DataFrame(rows, columns=FIT_COLUMNS)
    result = cluster_strategy(frame, MlClusterConfig())
    assert result.status == STATUS_SINGLE_CLUSTER
    assert result.constant_features  # recorded, never fabricated into structure
    assert len([r for r in result.cluster_rows if r["status"] == STATUS_OK]) == 1


@requires_sklearn
def test_reproducible_across_runs(tmp_path):
    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    stocks = load_fit_stocks(fit_dir)
    config = MlClusterConfig()
    first = analyze_fit_stocks(stocks, None, config)
    second = analyze_fit_stocks(stocks, None, config)
    assert first[0].equals(second[0])
    assert first[1].equals(second[1])
    assert first[2] == second[2]


@requires_sklearn
def test_pool_only_filter(tmp_path):
    frame = _two_groups_frame()
    frame["in_pool"] = False
    frame.loc[frame["symbol"].str.startswith("600"), "in_pool"] = True
    fit_dir = _write_fit_dir(tmp_path, frame)
    stocks = load_fit_stocks(fit_dir)
    stocks_df, _, status_rows = analyze_fit_stocks(stocks, None, MlClusterConfig(pool_only=True))
    assert set(stocks_df["symbol"]) == set(frame.loc[frame["in_pool"], "symbol"])
    assert status_rows[0]["n_stocks"] == 10


@requires_sklearn
def test_metadata_enriches_features(tmp_path):
    frame = _two_groups_frame()
    fit_dir = _write_fit_dir(tmp_path, frame)
    metadata = pd.DataFrame(
        {
            "ts_code": frame["symbol"],
            "total_mv": [1e9 if s.startswith("600") else 1e8 for s in frame["symbol"]],
            "turnover_rate_f": [3.0] * len(frame),
        }
    )
    meta_path = tmp_path / "meta.csv"
    metadata.to_csv(meta_path, index=False)
    loaded = load_metadata_csv(meta_path)
    stocks = load_fit_stocks(fit_dir)
    stocks_df, clusters_df, status_rows = analyze_fit_stocks(stocks, loaded, MlClusterConfig())
    # metadata columns never leak into the per-stock output contract
    assert "total_mv" not in stocks_df.columns
    assert status_rows[0]["status"] == STATUS_OK


# ---------------------------------------------------------------------------
# outputs + manifest
# ---------------------------------------------------------------------------


@requires_sklearn
def test_tiers_survive_csv_round_trip(tmp_path):
    # pandas parses the M10.1 tier column as float on read ('90' -> 90.0);
    # the module must restore the '90'/'99'/'99.9' labels verbatim.
    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    stocks = load_fit_stocks(fit_dir)
    stocks_df, clusters_df, _ = analyze_fit_stocks(stocks, None, MlClusterConfig())
    assert set(stocks_df["tier"].astype(str)) == {"90", "99", "99.9"}
    counted = {"90": 0, "99": 0, "99.9": 0}
    for row in clusters_df.itertuples():
        counted["90"] += row.n_tier_90
        counted["99"] += row.n_tier_99
        counted["99.9"] += row.n_tier_99_9
    assert counted == {"90": 12, "99": 8, "99.9": 2}


@requires_sklearn
def test_write_outputs_and_manifest(tmp_path):
    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    stocks = load_fit_stocks(fit_dir)
    config = MlClusterConfig(eps=1.0, min_samples=5, random_state=7)
    stocks_df, clusters_df, status_rows = analyze_fit_stocks(stocks, None, config)
    out = tmp_path / "ml_out"
    paths = write_ml_outputs(out, stocks_df, clusters_df, status_rows,
                             fit_dir=fit_dir, config=config,
                             generated_at="2026-10-27T00:00:00+00:00")
    for path in paths.values():
        assert path.exists()

    manifest = json.loads(paths["ml_cluster_manifest"].read_text(encoding="utf-8"))
    assert manifest["kind"] == MANIFEST_KIND
    assert manifest["schema_version"] == 1
    assert manifest["config"]["eps"] == 1.0
    assert manifest["config"]["min_samples"] == 5
    assert manifest["config"]["random_state"] == 7
    assert manifest["model"]["algorithm"] == "DBSCAN"
    assert manifest["model"]["version"]  # scikit-learn version recorded
    assert "trade_count" in manifest["input_fields"]["fit_dir"]
    assert manifest["strategies"][0]["strategy_id"] == "two_groups"
    assert manifest["strategies"][0]["status"] == STATUS_OK
    assert "determinism" in manifest

    stocks_csv = pd.read_csv(paths["ml_cluster_stocks"])
    assert {"strategy_id", "symbol", "tier", "cluster", "is_noise"} <= set(stocks_csv.columns)
    clusters_csv = pd.read_csv(paths["ml_cluster_clusters"])
    assert {"strategy_id", "cluster", "size", "mean_excess_return",
            "dominant_features", "summary"} <= set(clusters_csv.columns)
    report = paths["ml_cluster_report"].read_text(encoding="utf-8")
    assert "two_groups" in report and "DBSCAN" in report
    assert "90%/99%/99.9%" in report


@requires_sklearn
def test_manifest_registered_and_validated_by_report_manifest(tmp_path):
    """The M10.4 manifest kind must pass the shared report audit contract."""
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    stocks = load_fit_stocks(fit_dir)
    config = MlClusterConfig()
    stocks_df, clusters_df, status_rows = analyze_fit_stocks(stocks, None, config)
    out = tmp_path / "ml_out"
    paths = write_ml_outputs(out, stocks_df, clusters_df, status_rows,
                             fit_dir=fit_dir, config=config,
                             generated_at="2026-10-27T00:00:00+00:00")

    report_manifest = ReportManifest.from_path(paths["ml_cluster_manifest"])
    assert report_manifest.kind == MANIFEST_KIND
    assert report_manifest.validate_contents() == []
    # every declared file entry is discoverable by role
    assert {f.role for f in report_manifest.files()} == {
        "ml_cluster_stocks", "ml_cluster_clusters", "ml_cluster_report", "ml_cluster_manifest",
    }


def test_manifest_registration_covers_insufficient_case(tmp_path):
    """Insufficient strategies still produce a manifest that audits clean."""
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    rows = [_stock_row("tiny", f"00000{i}.SZ") for i in range(2)]
    fit_dir = _write_fit_dir(tmp_path, pd.DataFrame(rows, columns=FIT_COLUMNS))
    stocks = load_fit_stocks(fit_dir)
    stocks_df, clusters_df, status_rows = analyze_fit_stocks(stocks, None, MlClusterConfig())
    out = tmp_path / "ml_out"
    paths = write_ml_outputs(out, stocks_df, clusters_df, status_rows,
                             fit_dir=fit_dir, config=MlClusterConfig(),
                             generated_at="2026-10-27T00:00:00+00:00")
    report_manifest = ReportManifest.from_path(paths["ml_cluster_manifest"])
    assert report_manifest.validate_contents() == []


@requires_sklearn
def test_manifest_content_validation_detects_missing_columns(tmp_path):
    """Role column requirements catch a corrupted ml_cluster_stocks.csv."""
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    stocks = load_fit_stocks(fit_dir)
    stocks_df, clusters_df, status_rows = analyze_fit_stocks(stocks, None, MlClusterConfig())
    out = tmp_path / "ml_out"
    paths = write_ml_outputs(out, stocks_df, clusters_df, status_rows,
                             fit_dir=fit_dir, config=MlClusterConfig(),
                             generated_at="2026-10-27T00:00:00+00:00")

    broken = stocks_df.drop(columns=["is_noise"])
    broken.to_csv(paths["ml_cluster_stocks"], index=False)
    issues = ReportManifest.from_path(paths["ml_cluster_manifest"]).validate_contents()
    assert any(i.code == "missing_columns" and i.key == "ml_cluster_stocks" for i in issues)
    assert "is_noise" in next(i for i in issues if i.key == "ml_cluster_stocks").message


def test_manifest_content_validation_detects_missing_file(tmp_path):
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    rows = [_stock_row("tiny", f"00000{i}.SZ") for i in range(2)]
    fit_dir = _write_fit_dir(tmp_path, pd.DataFrame(rows, columns=FIT_COLUMNS))
    stocks = load_fit_stocks(fit_dir)
    stocks_df, clusters_df, status_rows = analyze_fit_stocks(stocks, None, MlClusterConfig())
    out = tmp_path / "ml_out"
    paths = write_ml_outputs(out, stocks_df, clusters_df, status_rows,
                             fit_dir=fit_dir, config=MlClusterConfig(),
                             generated_at="2026-10-27T00:00:00+00:00")
    paths["ml_cluster_clusters"].unlink()
    issues = ReportManifest.from_path(paths["ml_cluster_manifest"]).validate_contents()
    assert any(i.code == "missing_file" and i.key == "ml_cluster_clusters" for i in issues)


def test_write_outputs_insufficient_strategy(tmp_path):
    rows = [_stock_row("tiny", f"00000{i}.SZ") for i in range(2)]
    fit_dir = _write_fit_dir(tmp_path, pd.DataFrame(rows, columns=FIT_COLUMNS))
    stocks = load_fit_stocks(fit_dir)
    stocks_df, clusters_df, status_rows = analyze_fit_stocks(stocks, None, MlClusterConfig())
    out = tmp_path / "ml_out"
    paths = write_ml_outputs(out, stocks_df, clusters_df, status_rows,
                             fit_dir=fit_dir, config=MlClusterConfig(),
                             generated_at="2026-10-27T00:00:00+00:00")
    manifest = json.loads(paths["ml_cluster_manifest"].read_text(encoding="utf-8"))
    assert manifest["strategies"][0]["status"] == STATUS_INSUFFICIENT
    assert "insufficient" in manifest["strategies"][0]["reason"]
    report = paths["ml_cluster_report"].read_text(encoding="utf-8")
    assert "insufficient" in report
    # M10.1 artifacts are never touched
    assert (fit_dir / "strategy_fit_stocks.csv").exists()
    assert not (out / "strategy_fit_stocks.csv").exists()


def test_load_fit_stocks_requires_m10_1_artifact(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_fit_stocks(tmp_path / "missing")


# ---------------------------------------------------------------------------
# optional dependency degradation
# ---------------------------------------------------------------------------


def _block_sklearn(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sklearn" or name.startswith("sklearn."):
            raise ImportError("sklearn blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_module_imports_and_degrades_without_sklearn(monkeypatch):
    _block_sklearn(monkeypatch)
    assert ml_cluster_available() is False
    frame = _two_groups_frame()
    with pytest.raises(MlUnavailableError, match="scikit-learn"):
        analyze_fit_stocks(frame, None, MlClusterConfig())


def test_cli_degrades_without_sklearn(tmp_path, monkeypatch, capsys):
    _block_sklearn(monkeypatch)
    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    out = tmp_path / "ml_out"
    monkeypatch.setattr(sys, "argv", [
        "strategy_fit_ml_report.py", "--fit-dir", str(fit_dir), "--output-dir", str(out),
    ])
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "strategy_fit_ml_report", Path(__file__).resolve().parent.parent / "scripts" / "strategy_fit_ml_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = module.main()
    assert code == 2
    assert "scikit-learn" in capsys.readouterr().err


def test_cli_happy_path(tmp_path, monkeypatch, capsys):
    pytest.importorskip("sklearn")
    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    out = tmp_path / "ml_out"
    monkeypatch.setattr(sys, "argv", [
        "strategy_fit_ml_report.py", "--fit-dir", str(fit_dir),
        "--output-dir", str(out), "--min-samples", "5",
    ])
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "strategy_fit_ml_report", Path(__file__).resolve().parent.parent / "scripts" / "strategy_fit_ml_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
    manifest = json.loads((out / "ml_cluster_manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == MANIFEST_KIND
    assert manifest["strategies"][0]["status"] == STATUS_OK
    assert "noise" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# optional eps-grid sensitivity (opt-in; defaults stay byte-compatible)
# ---------------------------------------------------------------------------

CLI_PATH = Path(__file__).resolve().parent.parent / "scripts" / "strategy_fit_ml_report.py"
SENSITIVITY_FILES = (
    "ml_cluster_sensitivity.csv",
    "ml_cluster_sensitivity_strategies.csv",
    "ml_cluster_sensitivity.json",
)
MAIN_FILES = (
    "ml_cluster_stocks.csv",
    "ml_cluster_clusters.csv",
    "ml_cluster_report.md",
    "ml_cluster_manifest.json",
)


def _run_cli(monkeypatch, argv):
    import importlib.util

    monkeypatch.setattr(sys, "argv", ["strategy_fit_ml_report.py", *argv])
    spec = importlib.util.spec_from_file_location("strategy_fit_ml_report", CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


def _manifest_without_timestamp(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.pop("generated_at", None)
    return manifest


def test_parse_eps_grid():
    from quant_research_engine.analysis.ml_cluster import parse_eps_grid

    assert parse_eps_grid(None) is None
    assert parse_eps_grid("1.0, 1.5,2.0") == [1.0, 1.5, 2.0]
    with pytest.raises(ValueError, match="empty"):
        parse_eps_grid("1.0,,2.0")
    with pytest.raises(ValueError):
        parse_eps_grid("not-a-number")


@requires_sklearn
def test_eps_grid_default_off_keeps_main_contract(tmp_path, monkeypatch, capsys):
    """Without --eps-grid: four main artifacts, unchanged manifest file roles, no sensitivity files."""
    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    out_a = tmp_path / "ml_a"
    out_b = tmp_path / "ml_b"
    assert _run_cli(monkeypatch, ["--fit-dir", str(fit_dir), "--output-dir", str(out_a)]) == 0
    assert _run_cli(monkeypatch, ["--fit-dir", str(fit_dir), "--output-dir", str(out_b)]) == 0
    out = capsys.readouterr().out
    assert "EPS sensitivity" not in out

    for directory in (out_a, out_b):
        assert sorted(p.name for p in directory.iterdir()) == sorted(MAIN_FILES)
        assert not any((directory / name).exists() for name in SENSITIVITY_FILES)
        manifest = _manifest_without_timestamp(directory / "ml_cluster_manifest.json")
        assert [entry["role"] for entry in manifest["files"]] == list(
            ["ml_cluster_stocks", "ml_cluster_clusters", "ml_cluster_report", "ml_cluster_manifest"]
        )
        assert "sensitivity" not in manifest

    # main payloads are reproducible run to run (only generated_at may differ)
    assert (out_a / "ml_cluster_stocks.csv").read_bytes() == (out_b / "ml_cluster_stocks.csv").read_bytes()
    assert (out_a / "ml_cluster_clusters.csv").read_bytes() == (out_b / "ml_cluster_clusters.csv").read_bytes()


@requires_sklearn
def test_eps_grid_is_deterministic_and_separate_from_main_outputs(tmp_path, monkeypatch, capsys):
    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    out_a = tmp_path / "ml_grid_a"
    out_b = tmp_path / "ml_grid_b"
    for out in (out_a, out_b):
        assert _run_cli(monkeypatch, [
            "--fit-dir", str(fit_dir), "--output-dir", str(out),
            "--eps-grid", "1.0,1.5,2.0",
        ]) == 0
    assert "EPS sensitivity" in capsys.readouterr().out

    for directory in (out_a, out_b):
        for name in MAIN_FILES:
            assert (directory / name).exists()
        for name in SENSITIVITY_FILES:
            assert (directory / name).exists()
        # main manifest still declares only the four primary artifacts
        manifest = _manifest_without_timestamp(directory / "ml_cluster_manifest.json")
        assert len(manifest["files"]) == 4

    for name in SENSITIVITY_FILES:
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()

    summary = pd.read_csv(out_a / "ml_cluster_sensitivity.csv")
    assert list(summary["eps"]) == [1.0, 1.5, 2.0]
    assert set(summary["n_strategies"]) == {1}
    manifest = json.loads((out_a / "ml_cluster_sensitivity.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "strategy_fit_ml_cluster_sensitivity"
    assert manifest["eps_grid"] == [1.0, 1.5, 2.0]
    assert manifest["config"]["random_state"] == 42
    assert manifest["model"]["version"]


@requires_sklearn
def test_eps_grid_single_value_matches_default_eps(tmp_path):
    from quant_research_engine.analysis.ml_cluster import analyze_eps_grid

    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    stocks = load_fit_stocks(fit_dir)
    config = MlClusterConfig()

    stocks_df, _clusters_df, status_rows = analyze_fit_stocks(stocks, None, config)
    summary_rows, detail_df = analyze_eps_grid(stocks, None, config, [config.eps])

    assert len(summary_rows) == 1
    row = summary_rows[0]
    assert row["eps"] == config.eps
    assert row["n_strategies"] == len(status_rows)
    assert row["n_stocks"] == len(stocks_df)
    assert row["n_noise_stocks"] == int(stocks_df["is_noise"].sum())
    assert len(detail_df) == len(status_rows)
    assert set(detail_df["eps"]) == {config.eps}
    assert list(detail_df["strategy_id"]) == [r["strategy_id"] for r in status_rows]


@requires_sklearn
def test_eps_grid_handles_empty_and_insufficient_input():
    from quant_research_engine.analysis.ml_cluster import analyze_eps_grid

    config = MlClusterConfig()
    empty_summary, empty_detail = analyze_eps_grid(
        pd.DataFrame(columns=FIT_COLUMNS), None, config, [1.0, 2.0]
    )
    assert len(empty_summary) == 2
    for row in empty_summary:
        assert row["n_strategies"] == 0
        assert row["n_clustered_strategies"] == 0
        assert row["n_clusters"] == 0
        assert row["n_stocks"] == 0
        assert row["n_noise_stocks"] == 0
        assert row["status_insufficient"] == 0
    assert empty_detail.empty

    tiny = pd.DataFrame([_stock_row("tiny", f"00000{i}.SZ") for i in range(3)], columns=FIT_COLUMNS)
    summary_rows, _detail = analyze_eps_grid(tiny, None, config, [1.0, 2.0])
    for row in summary_rows:
        assert row["n_strategies"] == 1
        assert row["status_insufficient"] == 1
        assert row["n_clustered_strategies"] == 0
        assert row["n_noise_stocks"] == 0


def test_cli_rejects_empty_eps_grid(tmp_path, monkeypatch):
    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame(), name="fit-empty-grid")
    out = tmp_path / "ml_out"
    with pytest.raises(SystemExit) as excinfo:
        _run_cli(monkeypatch, [
            "--fit-dir", str(fit_dir), "--output-dir", str(out), "--eps-grid", "",
        ])
    assert excinfo.value.code == 2
    assert not out.exists()


def test_cli_degrades_without_sklearn_with_eps_grid(tmp_path, monkeypatch, capsys):
    _block_sklearn(monkeypatch)
    fit_dir = _write_fit_dir(tmp_path, _two_groups_frame())
    out = tmp_path / "ml_out"
    code = _run_cli(monkeypatch, [
        "--fit-dir", str(fit_dir), "--output-dir", str(out), "--eps-grid", "1.0,2.0",
    ])
    assert code == 2
    assert "scikit-learn" in capsys.readouterr().err
    assert not out.exists()
