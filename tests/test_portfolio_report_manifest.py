import json
from pathlib import Path

import pytest

from quant_research_engine.portfolio.report_manifest import ReportManifest


def test_report_manifest_loads_and_filters_entries(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "summary",
                        "path": "summary.csv",
                        "filename": "summary.csv",
                        "role": "summary",
                    },
                    {
                        "key": "window_summary_M_by_board",
                        "path": "window_summary_M_by_board.csv",
                        "filename": "window_summary_M_by_board.csv",
                        "role": "window_summary",
                        "window": "M",
                        "group_by": "board",
                    },
                    {
                        "key": "window_summary_M_by_board_ranked_symbols",
                        "path": "window_summary_M_by_board_ranked_symbols.csv",
                        "filename": "window_summary_M_by_board_ranked_symbols.csv",
                        "role": "window_ranked_symbols",
                        "window": "M",
                        "group_by": "board",
                    },
                    {
                        "key": "000001.SZ_orders",
                        "path": "000001.SZ/orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                        "symbol": "000001.SZ",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = ReportManifest.from_path(manifest_path)

    assert manifest.kind == "batch_backtest_report_manifest"
    assert [entry.key for entry in manifest.files(role="window_summary", window="M")] == [
        "window_summary_M_by_board"
    ]
    assert [entry.key for entry in manifest.files(role="window_ranked_symbols", group_by="board")] == [
        "window_summary_M_by_board_ranked_symbols"
    ]
    assert manifest.paths(role="orders", symbol="000001.SZ") == [tmp_path / "000001.SZ/orders.csv"]


def test_report_manifest_rejects_non_manifest_json(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(json.dumps({"kind": "other", "files": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="batch_backtest_report_manifest"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_loads_shared_cash_manifest(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "window_metrics_M",
                        "path": "window_metrics_M.csv",
                        "filename": "window_metrics_M.csv",
                        "role": "window_metrics",
                        "window": "M",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = ReportManifest.from_path(manifest_path)

    assert manifest.kind == "shared_cash_backtest_report_manifest"
    assert manifest.paths(role="window_metrics", window="M") == [tmp_path / "window_metrics_M.csv"]


def test_report_manifest_validate_contents_accepts_valid_report_files(tmp_path):
    (tmp_path / "orders.csv").write_text("symbol,trade_date,side\n000001.SZ,2026-01-05,buy\n", encoding="utf-8")
    (tmp_path / "window_metrics_M.csv").write_text("window,total_return\n2026-01,0.1\n", encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps({"trade_count": 1}), encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "orders", "path": "orders.csv", "filename": "orders.csv", "role": "orders"},
                    {
                        "key": "window_metrics_M",
                        "path": "window_metrics_M.csv",
                        "filename": "window_metrics_M.csv",
                        "role": "window_metrics",
                        "window": "M",
                    },
                    {"key": "summary", "path": "summary.json", "filename": "summary.json", "role": "summary"},
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = ReportManifest.from_path(manifest_path)

    assert manifest.validate_contents() == []


def test_report_manifest_validate_contents_reports_missing_columns(tmp_path):
    (tmp_path / "orders.csv").write_text("symbol,side\n000001.SZ,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "orders", "path": "orders.csv", "filename": "orders.csv", "role": "orders"},
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()

    assert len(issues) == 1
    assert issues[0].key == "orders"
    assert issues[0].code == "missing_columns"
    assert "trade_date" in issues[0].message


def test_report_manifest_loads_without_schema_version(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "summary",
                        "path": "summary.csv",
                        "filename": "summary.csv",
                        "role": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = ReportManifest.from_path(manifest_path)

    assert manifest.kind == "batch_backtest_report_manifest"
    assert manifest.schema_version is None
    assert len(manifest.files()) == 1
    assert manifest.files()[0].key == "summary"
    assert manifest.paths() == [tmp_path / "summary.csv"]


def test_report_manifest_exposes_schema_version_when_present(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "window_metrics_M",
                        "path": "window_metrics_M.csv",
                        "filename": "window_metrics_M.csv",
                        "role": "window_metrics",
                        "window": "M",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = ReportManifest.from_path(manifest_path)

    assert manifest.schema_version == 1
    assert manifest.kind == "shared_cash_backtest_report_manifest"
    assert manifest.paths(role="window_metrics", window="M") == [tmp_path / "window_metrics_M.csv"]


def test_report_manifest_rejects_unsupported_schema_version_number(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "summary",
                        "path": "summary.csv",
                        "filename": "summary.csv",
                        "role": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported manifest schema_version"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_non_integer_schema_version(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "summary",
                        "path": "summary.csv",
                        "filename": "summary.csv",
                        "role": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported manifest schema_version"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_boolean_schema_version(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": True,
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "summary",
                        "path": "summary.csv",
                        "filename": "summary.csv",
                        "role": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported manifest schema_version"):
        ReportManifest.from_path(manifest_path)
