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


def test_report_manifest_rejects_file_entry_missing_path(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "summary",
                        "filename": "summary.csv",
                        "role": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required field 'path'"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_file_entry_missing_role(tmp_path):
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
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required field 'role'"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_non_list_files(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": {"key": "summary", "path": "summary.csv", "filename": "summary.csv", "role": "summary"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest 'files' must be a list"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_non_object_file_entry(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [1],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest file entry 0 must be an object"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_list_root(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(json.dumps([]), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest root must be an object"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_scalar_root(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text("null", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest root must be an object"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_incomplete_json_object(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text('{"', encoding="utf-8")

    with pytest.raises(ValueError, match="manifest contains invalid JSON"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_non_json_text(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest contains invalid JSON"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_missing_kind(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"files": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest missing top-level 'kind' field"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_non_string_kind(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"kind": 123, "files": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest 'kind' must be a string"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_null_kind(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"kind": None, "files": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest 'kind' must be a string"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_non_string_required_entry_field(tmp_path):
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
                        "role": 123,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest file entry field 'role' must be a string"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_non_string_optional_entry_field(tmp_path):
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
                        "symbol": 456,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest file entry field 'symbol' must be a string or null"):
        ReportManifest.from_path(manifest_path)


def test_report_manifest_rejects_missing_files(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"kind": "batch_backtest_report_manifest"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest missing top-level 'files' field"):
        ReportManifest.from_path(manifest_path)


def test_validate_contents_accepts_run_manifest_as_json_object(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": "backtest-single", "strategy_path": "strategy.yaml", "request": {}, "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_validate_contents_reports_non_object_run_manifest(tmp_path):
    (tmp_path / "run_manifest.json").write_text("[1, 2, 3]", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].key == "run_manifest"
    assert issues[0].code == "invalid_json_object"


# --- evaluation_report_manifest ---


def test_report_manifest_loads_evaluation_kind(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "evaluation_report_manifest",
                "files": [
                    {
                        "key": "events",
                        "path": "events.csv",
                        "filename": "events.csv",
                        "role": "events",
                    },
                    {
                        "key": "summary",
                        "path": "summary.csv",
                        "filename": "summary.csv",
                        "role": "evaluation_summary",
                    },
                    {
                        "key": "run_manifest",
                        "path": "run_manifest.json",
                        "filename": "run_manifest.json",
                        "role": "run_manifest",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.kind == "evaluation_report_manifest"
    assert len(manifest.files()) == 3
    events_entries = manifest.files(role="events")
    assert len(events_entries) == 1
    assert events_entries[0].key == "events"


def test_report_manifest_validates_evaluation_events_columns(tmp_path):
    events_csv = tmp_path / "events.csv"
    events_csv.write_text("other,col\n1,2\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "events", "path": "events.csv", "filename": "events.csv", "role": "events"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "ts_code" in issues[0].message
    assert "trade_date" in issues[0].message


def test_report_manifest_validates_evaluation_summary_columns(tmp_path):
    summary_csv = tmp_path / "summary.csv"
    summary_csv.write_text("other,col\n1,2\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "summary", "path": "summary.csv", "filename": "summary.csv", "role": "evaluation_summary"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "horizon" in issues[0].message
    assert "event_count" in issues[0].message


def test_report_manifest_validates_evaluation_ic_summary_columns(tmp_path):
    ic_csv = tmp_path / "ic_summary.csv"
    ic_csv.write_text("other\n1\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "ic_summary", "path": "ic_summary.csv", "filename": "ic_summary.csv", "role": "ic_summary"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "factor" in issues[0].message
    assert "horizon" in issues[0].message
    assert "observation_dates" in issues[0].message


def test_report_manifest_validates_evaluation_quantile_summary_columns(tmp_path):
    q_csv = tmp_path / "quantile_summary.csv"
    q_csv.write_text("other\n1\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "quantile_summary", "path": "quantile_summary.csv", "filename": "quantile_summary.csv", "role": "quantile_summary"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "factor" in issues[0].message
    assert "horizon" in issues[0].message
    assert "quantile" in issues[0].message
    assert "row_count" in issues[0].message


def test_report_manifest_validates_evaluation_group_summary_columns(tmp_path):
    g_csv = tmp_path / "group_summary.csv"
    g_csv.write_text("other\n1\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "group_summary", "path": "group_summary.csv", "filename": "group_summary.csv", "role": "evaluation_group_summary"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "group_by" in issues[0].message
    assert "group_value" in issues[0].message
    assert "horizon" in issues[0].message
    assert "event_count" in issues[0].message


def test_report_manifest_validates_evaluation_artifacts_with_full_columns(tmp_path):
    (tmp_path / "events.csv").write_text("ts_code,trade_date,forward_return_1\n000001.SZ,2026-01-05,0.1\n", encoding="utf-8")
    (tmp_path / "summary.csv").write_text("horizon,event_count,mean_forward_return\n1,1,0.1\n", encoding="utf-8")
    (tmp_path / "ic_summary.csv").write_text("factor,horizon,observation_dates,mean_ic\nrsi_2,1,1,1.0\n", encoding="utf-8")
    (tmp_path / "quantile_summary.csv").write_text("factor,horizon,quantile,row_count,mean_forward_return\nrsi_2,1,1,1,0.1\n", encoding="utf-8")
    (tmp_path / "group_summary.csv").write_text("group_by,group_value,horizon,event_count\nboard,main,1,1\n", encoding="utf-8")
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "evaluation_run_manifest", "run_id": None, "command": "eval-config", "strategy_path": "strategy.yaml", "artifacts": ["events", "summary"]}),
        encoding="utf-8",
    )

    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "events", "path": "events.csv", "filename": "events.csv", "role": "events"},
                    {"key": "summary", "path": "summary.csv", "filename": "summary.csv", "role": "evaluation_summary"},
                    {"key": "ic_summary", "path": "ic_summary.csv", "filename": "ic_summary.csv", "role": "ic_summary"},
                    {"key": "quantile_summary", "path": "quantile_summary.csv", "filename": "quantile_summary.csv", "role": "quantile_summary"},
                    {"key": "group_summary", "path": "group_summary.csv", "filename": "group_summary.csv", "role": "evaluation_group_summary"},
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 0


def test_report_manifest_validates_evaluation_group_by_per_column(tmp_path):
    """validate_contents handles per-column evaluation grouped files with group_by metadata."""
    # Valid per-column grouped CSV
    (tmp_path / "group_summary_by_board.csv").write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nboard,chinext,1,30\n",
        encoding="utf-8",
    )
    # Valid combined grouped CSV
    (tmp_path / "group_summary.csv").write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nboard,chinext,1,30\nsector,Tech,1,40\n",
        encoding="utf-8",
    )

    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "group_summary", "path": "group_summary.csv", "filename": "group_summary.csv",
                     "role": "evaluation_group_summary"},
                    {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
                     "filename": "group_summary_by_board.csv", "role": "evaluation_group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)

    # All files valid
    issues = manifest.validate_contents()
    assert len(issues) == 0

    # validate_contents filtered to specific group_by only checks that file
    board_issues = manifest.validate_contents(role="evaluation_group_summary", group_by="board")
    assert len(board_issues) == 0

    # Missing per-column file is reported
    (tmp_path / "group_summary_by_board.csv").unlink()
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_file"
    assert "group_summary_by_board.csv" in str(issues[0].path)

    # validate_contents with group_by filter finds only the missing file
    board_issues2 = manifest.validate_contents(role="evaluation_group_summary", group_by="board")
    assert len(board_issues2) == 1
    assert board_issues2[0].code == "missing_file"


def test_report_manifest_validates_evaluation_per_column_missing_columns(tmp_path):
    """validate_contents catches missing columns in a per-column grouped evaluation file."""
    (tmp_path / "group_summary_by_industry.csv").write_text(
        "wrong_col\n1\n",
        encoding="utf-8",
    )

    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "group_summary_by_industry", "path": "group_summary_by_industry.csv",
                     "filename": "group_summary_by_industry.csv", "role": "evaluation_group_summary",
                     "group_by": "industry"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"

    # Filtered to the specific group_by
    industry_issues = manifest.validate_contents(role="evaluation_group_summary", group_by="industry")
    assert len(industry_issues) == 1
    assert industry_issues[0].code == "missing_columns"


def test_report_manifest_rejects_evaluation_missing_file(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "events", "path": "events.csv", "filename": "events.csv", "role": "events"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_file"


def test_report_manifest_validates_random_baseline_summary_columns(tmp_path):
    rb_csv = tmp_path / "random_baseline_summary.csv"
    rb_csv.write_text("other\n1\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "random_baseline_summary", "path": "random_baseline_summary.csv", "filename": "random_baseline_summary.csv", "role": "random_baseline_summary"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "horizon" in issues[0].message
    assert "event_count" in issues[0].message


def test_report_manifest_validates_factor_decay_summary_columns(tmp_path):
    decay_csv = tmp_path / "factor_decay_summary.csv"
    decay_csv.write_text("other\n1\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "factor_decay_summary", "path": "factor_decay_summary.csv", "filename": "factor_decay_summary.csv", "role": "factor_decay_summary"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "factor" in issues[0].message
    assert "horizon" in issues[0].message
    assert "base_horizon" in issues[0].message


def test_report_manifest_accepts_valid_factor_decay_summary(tmp_path):
    decay_csv = tmp_path / "factor_decay_summary.csv"
    decay_csv.write_text(
        "factor,horizon,base_horizon,observation_dates,mean_ic,mean_rank_ic,ic_decay_from_base,rank_ic_decay_from_base\nmomentum,1,1,10,0.10,0.09,0.0,0.0\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "factor_decay_summary", "path": "factor_decay_summary.csv", "filename": "factor_decay_summary.csv", "role": "factor_decay_summary"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 0


def test_validate_contents_accepts_valid_run_manifest_with_run_id_string(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": "research-run-42", "command": "backtest-single", "strategy_path": "strategy.yaml", "request": {}, "artifacts": ["orders", "trades"]}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_validate_contents_accepts_valid_evaluation_run_manifest(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "evaluation_run_manifest", "run_id": None, "command": "eval-config", "strategy_path": "strategy.yaml", "artifacts": ["events", "summary"]}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_validate_contents_reports_missing_run_manifest_field(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": "backtest-single"}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 2
    codes = {issue.code for issue in issues}
    assert "missing_run_manifest_field" in codes
    messages = " ".join(issue.message for issue in issues)
    assert "strategy_path" in messages
    assert "artifacts" in messages


def test_validate_contents_reports_invalid_run_id_type(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": 123, "command": "backtest-single", "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "run_id" in issues[0].message
    assert "int" in issues[0].message


def test_validate_contents_reports_artifacts_not_list(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": "backtest-single", "strategy_path": "strategy.yaml", "artifacts": "not_a_list"}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "artifacts" in issues[0].message
    assert "list" in issues[0].message


def test_validate_contents_reports_artifacts_entry_not_string(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": "backtest-single", "strategy_path": "strategy.yaml", "artifacts": ["valid", 42]}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "artifacts[1]" in issues[0].message


def test_validate_contents_reports_unsupported_run_manifest_kind(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "unsupported_kind", "run_id": None, "command": "cmd", "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "unsupported run manifest kind" in issues[0].message
    assert "unsupported_kind" in issues[0].message


def test_validate_contents_reports_invalid_schema_version(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 2, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": "backtest-single", "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "schema_version" in issues[0].message


def test_validate_contents_reports_null_schema_version(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": None, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": "backtest-single", "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "schema_version" in issues[0].message
    assert "null" in issues[0].message


def test_validate_contents_reports_null_kind(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": None, "run_id": None, "command": "backtest-single", "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "kind" in issues[0].message
    assert "null" in issues[0].message


def test_validate_contents_reports_null_command(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": None, "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "command" in issues[0].message
    assert "null" in issues[0].message


def test_validate_contents_reports_null_strategy_path(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": "backtest-single", "strategy_path": None, "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "strategy_path" in issues[0].message
    assert "null" in issues[0].message


def test_validate_contents_reports_null_artifacts(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": "backtest-single", "strategy_path": "strategy.yaml", "artifacts": None}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_run_manifest_field"
    assert "artifacts" in issues[0].message
    assert "null" in issues[0].message


def test_validate_contents_accepts_null_run_id(tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "portfolio_backtest_run_manifest", "run_id": None, "command": "backtest-single", "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "run_manifest", "path": "run_manifest.json", "filename": "run_manifest.json", "role": "run_manifest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


# --- group_by content consistency ---


def test_validate_contents_reports_group_by_mismatch_evaluation(tmp_path):
    (tmp_path / "group_summary_by_board.csv").write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nsector,Tech,1,40\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
                     "filename": "group_summary_by_board.csv", "role": "evaluation_group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].key == "group_summary_by_board"
    assert issues[0].code == "group_by_mismatch"
    assert "board" in issues[0].message
    assert "sector" in issues[0].message


def test_validate_contents_reports_group_by_mismatch_shared_orders(tmp_path):
    (tmp_path / "shared_orders_group_summary_by_board.csv").write_text(
        "group_by,group_value,order_count\nboard,main,10\nsector,Tech,5\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "shared_orders_group_summary_by_board",
                     "path": "shared_orders_group_summary_by_board.csv",
                     "filename": "shared_orders_group_summary_by_board.csv",
                     "role": "shared_orders_group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "group_by_mismatch"
    assert "board" in issues[0].message
    assert "sector" in issues[0].message


def test_validate_contents_reports_group_by_mismatch_shared_trades(tmp_path):
    (tmp_path / "shared_trades_group_summary_by_board.csv").write_text(
        "group_by,group_value,trade_count\nboard,main,8\nindustry,Tech,3\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "shared_trades_group_summary_by_board",
                     "path": "shared_trades_group_summary_by_board.csv",
                     "filename": "shared_trades_group_summary_by_board.csv",
                     "role": "shared_trades_group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "group_by_mismatch"


def test_validate_contents_reports_group_by_mismatch_shared_failed_orders(tmp_path):
    (tmp_path / "shared_failed_orders_group_summary_by_board.csv").write_text(
        "group_by,group_value,failed_order_count\nboard,main,2\nsector,Tech,1\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "shared_failed_orders_group_summary_by_board",
                     "path": "shared_failed_orders_group_summary_by_board.csv",
                     "filename": "shared_failed_orders_group_summary_by_board.csv",
                     "role": "shared_failed_orders_group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "group_by_mismatch"


def test_validate_contents_accepts_matching_group_by_evaluation(tmp_path):
    (tmp_path / "group_summary_by_board.csv").write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nboard,chinext,1,30\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
                     "filename": "group_summary_by_board.csv", "role": "evaluation_group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_validate_contents_accepts_matching_group_by_shared_orders(tmp_path):
    (tmp_path / "shared_orders_group_summary_by_board.csv").write_text(
        "group_by,group_value,order_count\nboard,main,10\nboard,chinext,5\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "shared_orders_group_summary_by_board",
                     "path": "shared_orders_group_summary_by_board.csv",
                     "filename": "shared_orders_group_summary_by_board.csv",
                     "role": "shared_orders_group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_validate_contents_no_group_by_check_without_manifest_metadata(tmp_path):
    """Combined group_summary.csv with no manifest group_by must not be checked for consistency."""
    (tmp_path / "group_summary.csv").write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nsector,Tech,1,40\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "group_summary", "path": "group_summary.csv",
                     "filename": "group_summary.csv", "role": "evaluation_group_summary"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_validate_contents_group_by_mismatch_checks_all_non_empty_cells(tmp_path):
    (tmp_path / "group_summary_by_board.csv").write_text(
        "group_by,group_value,horizon,event_count\n"
        "sector,Tech,1,40\n"
        "industry,Manufacturing,1,30\n"
        "board,main,1,50\n"
        "sector,Finance,1,20\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
                     "filename": "group_summary_by_board.csv", "role": "evaluation_group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "group_by_mismatch"
    assert "sector" in issues[0].message
    assert "industry" in issues[0].message
    assert "'board'" in issues[0].message


def test_validate_contents_skips_group_by_check_when_columns_missing(tmp_path):
    """Only emit missing_columns when required-column validation fails, even if group_by mismatches."""
    (tmp_path / "group_summary_by_board.csv").write_text(
        "group_by,group_value,horizon\nsector,main,1\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "evaluation_report_manifest",
                "files": [
                    {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
                     "filename": "group_summary_by_board.csv", "role": "evaluation_group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "event_count" in issues[0].message


# --- batch group_by header consistency ---


def test_validate_contents_reports_batch_header_mismatch_group_summary(tmp_path):
    (tmp_path / "group_summary_by_board.csv").write_text(
        "symbol_count,sector\n10,Technology\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
                     "filename": "group_summary_by_board.csv", "role": "group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "group_by_header_mismatch"
    assert "'board'" in issues[0].message
    assert "sector" in issues[0].message


def test_validate_contents_reports_batch_header_mismatch_window_summary(tmp_path):
    (tmp_path / "window_summary_M_by_board.csv").write_text(
        "window,symbol_count,sector\nM,50,Tech\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {"key": "window_summary_M_by_board", "path": "window_summary_M_by_board.csv",
                     "filename": "window_summary_M_by_board.csv", "role": "window_summary",
                     "window": "M", "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "group_by_header_mismatch"


def test_validate_contents_reports_batch_header_mismatch_window_ranked_symbols(tmp_path):
    (tmp_path / "window_summary_M_by_board_ranked.csv").write_text(
        "window,rank_type,rank,symbol,total_return,industry\nM,return,1,000001.SZ,0.15,Technology\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {"key": "window_summary_M_by_board_ranked",
                     "path": "window_summary_M_by_board_ranked.csv",
                     "filename": "window_summary_M_by_board_ranked.csv",
                     "role": "window_ranked_symbols",
                     "window": "M", "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "group_by_header_mismatch"


def test_validate_contents_accepts_matching_batch_header(tmp_path):
    (tmp_path / "group_summary_by_board.csv").write_text(
        "symbol_count,board\n10,main_board\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
                     "filename": "group_summary_by_board.csv", "role": "group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_validate_contents_batch_header_mismatch_skipped_when_columns_missing(tmp_path):
    """Only emit missing_columns when required-column validation fails, even if group_by header mismatches."""
    (tmp_path / "group_summary_by_board.csv").write_text(
        "other\n1\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
                     "filename": "group_summary_by_board.csv", "role": "group_summary",
                     "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "symbol_count" in issues[0].message


def test_validate_contents_batch_header_without_group_by_is_not_checked(tmp_path):
    """Batch entry without manifest group_by metadata is not checked for header consistency."""
    (tmp_path / "group_summary.csv").write_text(
        "symbol_count,board,sector\n10,main,Tech\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {"key": "group_summary", "path": "group_summary.csv",
                     "filename": "group_summary.csv", "role": "group_summary"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


# --- window_size parsing and filtering ---


def test_report_file_parses_window_size(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_20",
                        "path": "rolling_summary_20.csv",
                        "filename": "rolling_summary_20.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    entry = manifest.files()[0]
    assert entry.window_size == 20


def test_report_file_window_size_defaults_to_none(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary",
                        "path": "rolling_summary.csv",
                        "filename": "rolling_summary.csv",
                        "role": "rolling_summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    entry = manifest.files()[0]
    assert entry.window_size is None


def test_report_file_window_size_accepts_null(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary",
                        "path": "rolling_summary.csv",
                        "filename": "rolling_summary.csv",
                        "role": "rolling_summary",
                        "window_size": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    entry = manifest.files()[0]
    assert entry.window_size is None


def test_report_file_rejects_string_window_size(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary",
                        "path": "rolling_summary.csv",
                        "filename": "rolling_summary.csv",
                        "role": "rolling_summary",
                        "window_size": "20",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="window_size"):
        ReportManifest.from_path(manifest_path)


def test_report_file_rejects_boolean_window_size(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary",
                        "path": "rolling_summary.csv",
                        "filename": "rolling_summary.csv",
                        "role": "rolling_summary",
                        "window_size": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="window_size"):
        ReportManifest.from_path(manifest_path)


def test_files_filters_by_window_size(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_20",
                        "path": "rolling_summary_20.csv",
                        "filename": "rolling_summary_20.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                    },
                    {
                        "key": "rolling_summary_60",
                        "path": "rolling_summary_60.csv",
                        "filename": "rolling_summary_60.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    entries = manifest.files(window_size=20)
    assert len(entries) == 1
    assert entries[0].key == "rolling_summary_20"


def test_paths_filters_by_window_size(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_20",
                        "path": "rolling_summary_20.csv",
                        "filename": "rolling_summary_20.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                    },
                    {
                        "key": "rolling_summary_60",
                        "path": "rolling_summary_60.csv",
                        "filename": "rolling_summary_60.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    paths = manifest.paths(window_size=60)
    assert len(paths) == 1
    assert paths[0] == tmp_path / "rolling_summary_60.csv"


def test_validate_contents_filters_by_window_size(tmp_path):
    (tmp_path / "rolling_summary_20.csv").write_text(
        "window_size,end_date,symbol_count\n20,2026-01-05,50\n",
        encoding="utf-8",
    )
    (tmp_path / "rolling_summary_60.csv").write_text(
        "window_size,end_date,symbol_count\n60,2026-01-05,30\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_20",
                        "path": "rolling_summary_20.csv",
                        "filename": "rolling_summary_20.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                    },
                    {
                        "key": "rolling_summary_60",
                        "path": "rolling_summary_60.csv",
                        "filename": "rolling_summary_60.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents(window_size=20)
    assert len(issues) == 0


def test_validate_contents_window_size_filters_missing_file(tmp_path):
    # Only create rolling_summary_60, not rolling_summary_20
    (tmp_path / "rolling_summary_60.csv").write_text(
        "window_size,end_date,symbol_count\n60,2026-01-05,30\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_20",
                        "path": "rolling_summary_20.csv",
                        "filename": "rolling_summary_20.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                    },
                    {
                        "key": "rolling_summary_60",
                        "path": "rolling_summary_60.csv",
                        "filename": "rolling_summary_60.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents(window_size=20)
    assert len(issues) == 1
    assert issues[0].code == "missing_file"
    assert "rolling_summary_20" in str(issues[0].path)


def test_validate_contents_accepts_valid_research_run_manifest(tmp_path):
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "research_run_manifest",
                "run_id": "research-abc123",
                "command": "research-run",
                "strategy_path": "/tmp/strategy.yaml",
                "output_dir": "/tmp/run_output",
                "stages": {"preflight": "ok", "eval": "ok", "backtest": "ok"},
                "backtest_artifacts": {"summary_csv": "summary.csv"},
                "artifacts": ["summary_csv"],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "run_manifest",
                        "path": "research_run_manifest.json",
                        "filename": "research_run_manifest.json",
                        "role": "run_manifest",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


# --- research_run_report_manifest ---


def test_report_manifest_accepts_research_run_report_manifest_kind(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "research_run_report_manifest",
                "files": [
                    {
                        "key": "research_run_manifest",
                        "path": "research_run_manifest.json",
                        "filename": "research_run_manifest.json",
                        "role": "run_manifest",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.kind == "research_run_report_manifest"


def test_research_run_report_manifest_validates_run_manifest_role(tmp_path):
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "research_run_manifest",
                "run_id": "test-123",
                "command": "research-run",
                "strategy_path": "strategy.yaml",
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "research_run_report_manifest",
                "files": [
                    {
                        "key": "research_run_manifest",
                        "path": "research_run_manifest.json",
                        "filename": "research_run_manifest.json",
                        "role": "run_manifest",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents(role="run_manifest") == []


def test_research_run_report_manifest_reports_missing_files(tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "research_run_report_manifest",
                "files": [
                    {
                        "key": "research_run_manifest",
                        "path": "research_run_manifest.json",
                        "filename": "research_run_manifest.json",
                        "role": "run_manifest",
                    },
                    {
                        "key": "preflight_report",
                        "path": "preflight/preflight_report.json",
                        "filename": "preflight_report.json",
                        "role": "preflight_report",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 2
    codes = {i.code for i in issues}
    assert codes == {"missing_file"}


def test_research_run_report_manifest_with_all_stage_entries(tmp_path):
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "research_run_manifest",
                "run_id": "r1",
                "command": "research-run",
                "strategy_path": "s.yaml",
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text('{"status": "ok"}', encoding="utf-8")
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text(
        json.dumps({"kind": "evaluation_report_manifest", "files": []}),
        encoding="utf-8",
    )
    backtest_dir = tmp_path / "backtest"
    backtest_dir.mkdir()
    (backtest_dir / "report_manifest.json").write_text(
        json.dumps({"kind": "batch_backtest_report_manifest", "files": []}),
        encoding="utf-8",
    )

    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "research_run_report_manifest",
                "files": [
                    {
                        "key": "research_run_manifest",
                        "path": "research_run_manifest.json",
                        "filename": "research_run_manifest.json",
                        "role": "run_manifest",
                    },
                    {
                        "key": "preflight_report",
                        "path": "preflight/preflight_report.json",
                        "filename": "preflight_report.json",
                        "role": "preflight_report",
                    },
                    {
                        "key": "eval_report_manifest",
                        "path": "eval/report_manifest.json",
                        "filename": "report_manifest.json",
                        "role": "eval_report_manifest",
                    },
                    {
                        "key": "backtest_report_manifest",
                        "path": "backtest/report_manifest.json",
                        "filename": "report_manifest.json",
                        "role": "backtest_report_manifest",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_research_run_report_manifest_run_manifest_validation_reports_errors(tmp_path):
    """run_manifest role validation catches broken research_run_manifest payloads."""
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "research_run_manifest",
                "run_id": "r1",
                "command": "research-run",
                # missing strategy_path and artifacts
            }
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "research_run_report_manifest",
                "files": [
                    {
                        "key": "research_run_manifest",
                        "path": "research_run_manifest.json",
                        "filename": "research_run_manifest.json",
                        "role": "run_manifest",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 2
    codes = {i.code for i in issues}
    assert codes == {"missing_run_manifest_field"}


# --- recursive nested stage manifest validation ---


def test_research_run_report_manifest_recursive_validates_nested_eval_manifest(tmp_path):
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "events.csv").write_text("ts_code,trade_date\n000001.SZ,2024-01-05\n", encoding="utf-8")
    (eval_dir / "report_manifest.json").write_text(
        json.dumps({
            "kind": "evaluation_report_manifest",
            "files": [
                {"key": "events", "path": "events.csv", "filename": "events.csv", "role": "events"},
            ],
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_research_run_report_manifest_recursive_validates_nested_backtest_manifest(tmp_path):
    bt_dir = tmp_path / "backtest"
    bt_dir.mkdir()
    summary_csv = bt_dir / "summary.csv"
    summary_csv.write_text("symbol,trade_date\n000001.SZ,2024-01-05\n", encoding="utf-8")
    (bt_dir / "report_manifest.json").write_text(
        json.dumps({
            "kind": "batch_backtest_report_manifest",
            "files": [
                {"key": "summary", "path": "summary.csv", "filename": "summary.csv", "role": "summary"},
            ],
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "backtest_report_manifest", "path": "backtest/report_manifest.json",
                 "filename": "report_manifest.json", "role": "backtest_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_research_run_report_manifest_reports_invalid_nested_manifest(tmp_path):
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_nested_report_manifest"
    assert "eval_report_manifest" in issues[0].message
    assert issues[0].key == "eval_report_manifest"


def test_research_run_report_manifest_reports_nested_missing_artifact(tmp_path):
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    # events.csv does not exist, so nested validation should report it
    (eval_dir / "report_manifest.json").write_text(
        json.dumps({
            "kind": "evaluation_report_manifest",
            "files": [
                {"key": "events", "path": "events.csv", "filename": "events.csv", "role": "events"},
            ],
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "nested_report_manifest_issue"
    assert "eval_report_manifest" in issues[0].message
    assert "events" in issues[0].message
    assert "missing_file" in issues[0].message


def test_role_run_manifest_does_not_trigger_nested_validation(tmp_path):
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    # Nested eval manifest is malformed, but --role run_manifest skips it
    (eval_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                     "run_id": "r1", "command": "research-run",
                     "strategy_path": "s.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "research_run_manifest", "path": "research_run_manifest.json",
                 "filename": "research_run_manifest.json", "role": "run_manifest"},
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    # Unfiltered: should see the invalid nested manifest issue
    all_issues = manifest.validate_contents()
    assert any(i.code == "invalid_nested_report_manifest" for i in all_issues)
    # Filtered to run_manifest: no nested validation
    run_issues = manifest.validate_contents(role="run_manifest")
    codes = {i.code for i in run_issues}
    assert codes == set()
    assert len(run_issues) == 0


def test_role_eval_report_manifest_triggers_nested_validation(tmp_path):
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    # events.csv does not exist, nested validation should catch it
    (eval_dir / "report_manifest.json").write_text(
        json.dumps({
            "kind": "evaluation_report_manifest",
            "files": [
                {"key": "events", "path": "events.csv", "filename": "events.csv", "role": "events"},
            ],
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents(role="eval_report_manifest")
    assert len(issues) == 1
    assert issues[0].code == "nested_report_manifest_issue"
    assert "missing_file" in issues[0].message


def test_non_research_run_manifest_no_recursive_validation(tmp_path):
    """Non-research-run-report manifest with eval_report_manifest role does NOT recurse."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "batch_backtest_report_manifest",
            "files": [
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    # No recursive validation for non-research-run kinds; file exists so no missing_file either
    assert manifest.validate_contents() == []


# --- preflight report content validation ---


def test_research_run_report_manifest_valid_preflight_passes(tmp_path):
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text(
        json.dumps({"status": "ok", "checks": [], "missing_factor_requests": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []


def test_research_run_report_manifest_preflight_invalid_json(tmp_path):
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text("not valid json", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_preflight_report_json"
    assert issues[0].key == "preflight_report"


def test_research_run_report_manifest_preflight_non_object(tmp_path):
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text("[1, 2, 3]", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_preflight_report_object"


def test_research_run_report_manifest_preflight_missing_status(tmp_path):
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text(
        json.dumps({"checks": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_preflight_report_field"


def test_research_run_report_manifest_preflight_non_string_status(tmp_path):
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text(
        json.dumps({"status": 42}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_preflight_report_field"
    assert "status" in issues[0].message


def test_research_run_report_manifest_preflight_non_list_checks(tmp_path):
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text(
        json.dumps({"status": "ok", "checks": "not_a_list"}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_preflight_report_field"
    assert "checks" in issues[0].message


def test_research_run_report_manifest_preflight_non_list_missing_factor_requests(tmp_path):
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text(
        json.dumps({"status": "ok", "missing_factor_requests": 123}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "invalid_preflight_report_field"
    assert "missing_factor_requests" in issues[0].message


def test_role_preflight_report_triggers_validation(tmp_path):
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text("not valid json", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents(role="preflight_report")
    assert len(issues) == 1
    assert issues[0].code == "invalid_preflight_report_json"


def test_non_research_run_manifest_preflight_no_validation(tmp_path):
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text("not valid json", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "kind": "batch_backtest_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []
