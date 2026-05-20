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
