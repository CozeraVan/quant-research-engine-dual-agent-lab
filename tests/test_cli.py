from argparse import Namespace
import json

import pandas as pd

import quant_research_engine.apps.cli as cli_module
from quant_research_engine.apps.cli import (
    main,
    resolve_rebalance_controls,
    resolve_risk_controls,
    resolve_weight_controls,
)
from quant_research_engine.portfolio.batch import BatchBacktestResult
from quant_research_engine.portfolio.shared import SharedCashBacktestResult
from quant_research_engine.strategies.spec import StrategySpec


def test_cli_smoke_prints_loaded_profile(capsys):
    exit_code = main(["profile", "configs/market_profiles/ashare_daily_default.yaml"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "ashare_daily_default" in captured.out
    assert "A-share daily" in captured.out


def test_cli_db_smoke_requires_db_url_or_environment(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(["db-smoke", "--start", "2026-01-01", "--end", "2026-01-05", "--limit", "1"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_factor_smoke_requires_db_url_or_environment(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "factor-smoke",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-05",
            "--logical-name",
            "rsi_2",
            "--target",
            "factors.stock_daily_momentum_close.rsi_2",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_benchmark_smoke_requires_db_url_or_environment(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "benchmark-smoke",
            "--table",
            "public.index_daily",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-05",
            "--codes",
            "000300.SH",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_benchmark_smoke_prints_data_availability(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_benchmark_bars(self, table_name, ts_codes, start, end, fields, limit=None):
            assert table_name == "public.index_daily"
            assert ts_codes == ["000300.SH"]
            assert fields == ["close"]
            assert limit == 10
            return pd.DataFrame(
                {
                    "ts_code": ["000300.SH", "000300.SH", "000300.SH"],
                    "trade_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"]),
                    "close": [1000.0, 1010.0, None],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "benchmark-smoke",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--table",
            "public.index_daily",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-05",
            "--codes",
            "000300.SH",
            "--value-column",
            "close",
            "--limit",
            "10",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "loaded_rows=3" in captured.out
    assert "date_min=2026-01-01" in captured.out
    assert "date_max=2026-01-05" in captured.out
    assert "non_null_close=2" in captured.out
    assert "return_observations=1" in captured.out


def test_cli_metadata_smoke_requires_db_url_or_environment(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(["metadata-smoke", "--limit", "1"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_eval_smoke_requires_db_url_or_environment(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "eval-smoke",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-05",
            "--logical-name",
            "rsi_2",
            "--target",
            "factors.stock_daily_momentum_close.rsi_2",
            "--signal",
            "rsi_2 < 10",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_eval_config_requires_db_url_or_environment(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-05",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_eval_config_prints_ic_and_quantile_tables(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "c", "d", "a", "b", "c", "d"],
                    "trade_date": pd.to_datetime(
                        [
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-06",
                            "2026-01-06",
                            "2026-01-06",
                            "2026-01-06",
                        ]
                    ),
                    "open": [10.0] * 8,
                    "high": [10.0] * 8,
                    "low": [10.0] * 8,
                    "close": [10.0, 10.0, 10.0, 10.0, 9.0, 10.0, 11.0, 12.0],
                    "pre_close": [10.0] * 8,
                    "vol": [1.0] * 8,
                    "amount": [100.0] * 8,
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "c", "d", "a", "b", "c", "d"],
                    "trade_date": pd.to_datetime(
                        [
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-06",
                            "2026-01-06",
                            "2026-01-06",
                            "2026-01-06",
                        ]
                    ),
                    "rsi_2": [1.0, 2.0, 3.0, 4.0, 1.0, 1.0, 1.0, 1.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "a",
            "b",
            "c",
            "d",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "ic_summary" in captured.out
    assert "factor,horizon,observation_dates,mean_ic" in captured.out
    assert "quantile_summary" in captured.out
    assert "factor,horizon,quantile,row_count,mean_forward_return" in captured.out


def test_cli_eval_config_accepts_round_trip_cost_rate(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "open": [10.0, 10.0],
                    "high": [10.0, 10.0],
                    "low": [10.0, 10.0],
                    "close": [10.0, 11.0],
                    "pre_close": [10.0, 10.0],
                    "vol": [1.0, 1.0],
                    "amount": [100.0, 100.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "rsi_2": [5.0, 5.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--round-trip-cost-rate",
            "0.02",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "round_trip_cost_rate,mean_adjusted_forward_return" in captured.out
    assert "0.02,0.08000000000000008" in captured.out


def test_cli_eval_config_can_estimate_round_trip_cost_from_market_profile(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "open": [10.0, 10.0],
                    "high": [10.0, 10.0],
                    "low": [10.0, 10.0],
                    "close": [10.0, 11.0],
                    "pre_close": [10.0, 10.0],
                    "vol": [1.0, 1.0],
                    "amount": [100.0, 100.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "rsi_2": [5.0, 5.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--market-profile",
            "configs/market_profiles/ashare_daily_default.yaml",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "round_trip_cost_rate" in captured.out
    assert "0.00212" in captured.out


def test_cli_eval_config_group_by_prints_group_summary(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06", "2026-01-07"]
                    ),
                    "open": [10.0, 10.0, 20.0, 20.0, 20.0],
                    "high": [10.0, 10.0, 20.0, 20.0, 20.0],
                    "low": [10.0, 10.0, 20.0, 20.0, 20.0],
                    "close": [10.0, 11.0, 20.0, 18.0, 19.8],
                    "pre_close": [10.0, 10.0, 20.0, 20.0, 20.0],
                    "vol": [1.0, 1.0, 1.0, 1.0, 1.0],
                    "amount": [100.0, 100.0, 100.0, 100.0, 100.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06", "2026-01-07"]
                    ),
                    "rsi_2": [5.0, 15.0, 12.0, 6.0, 8.0],
                }
            )

        def load_security_metadata(self, ts_codes=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "board": ["main_board", "star_market"],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "000002.SZ",
            "--group-by",
            "board",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "group_summary" in captured.out
    assert "board" in captured.out
    assert "main_board" in captured.out
    assert "star_market" in captured.out


def test_cli_eval_config_group_by_missing_column_raises_error(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "open": [10.0, 10.0],
                    "high": [10.0, 10.0],
                    "low": [10.0, 10.0],
                    "close": [10.0, 11.0],
                    "pre_close": [10.0, 10.0],
                    "vol": [1.0, 1.0],
                    "amount": [100.0, 100.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "rsi_2": [5.0, 15.0],
                }
            )

        def load_security_metadata(self, ts_codes=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "board": ["main_board"],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--group-by",
            "missing_column",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "missing requested group columns" in captured.err


def test_cli_eval_config_output_dir_writes_artifacts(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "c", "d", "a", "b", "c", "d"],
                    "trade_date": pd.to_datetime(
                        [
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-06",
                            "2026-01-06",
                            "2026-01-06",
                            "2026-01-06",
                        ]
                    ),
                    "open": [10.0] * 8,
                    "high": [10.0] * 8,
                    "low": [10.0] * 8,
                    "close": [10.0, 10.0, 10.0, 10.0, 9.0, 10.0, 11.0, 12.0],
                    "pre_close": [10.0] * 8,
                    "vol": [1.0] * 8,
                    "amount": [100.0] * 8,
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "c", "d", "a", "b", "c", "d"],
                    "trade_date": pd.to_datetime(
                        [
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-05",
                            "2026-01-06",
                            "2026-01-06",
                            "2026-01-06",
                            "2026-01-06",
                        ]
                    ),
                    "rsi_2": [1.0, 2.0, 3.0, 4.0, 1.0, 1.0, 1.0, 1.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_dir = tmp_path / "eval_output"

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "a",
            "b",
            "c",
            "d",
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0

    # Core artifacts always present
    assert (output_dir / "events.csv").is_file()
    assert (output_dir / "run_manifest.json").is_file()
    assert (output_dir / "report_manifest.json").is_file()

    # Non-empty result tables
    assert (output_dir / "summary.csv").is_file()
    assert (output_dir / "ic_summary.csv").is_file()
    assert (output_dir / "quantile_summary.csv").is_file()

    # group_summary.csv not written when --group-by is omitted
    assert not (output_dir / "group_summary.csv").is_file()

    # stdout preserved
    assert "ic_summary" in captured.out
    assert "quantile_summary" in captured.out

    # run_manifest.json structure
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["schema_version"] == 1
    assert run_manifest["kind"] == "evaluation_run_manifest"
    assert run_manifest["command"] == "eval-config"
    assert run_manifest["start"] == "2026-01-05"
    assert run_manifest["end"] == "2026-01-06"
    assert run_manifest["codes"] == ["a", "b", "c", "d"]
    assert run_manifest["market_profile"] is None
    assert "events" in run_manifest["artifacts"]
    assert "run_manifest" not in run_manifest["artifacts"]  # run_manifest not in itself

    # report_manifest.json loads via ReportManifest
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    manifest = ReportManifest.from_path(output_dir / "report_manifest.json")
    assert manifest.kind == "evaluation_report_manifest"
    assert len(manifest.files()) > 0

    # validate_contents passes
    issues = manifest.validate_contents()
    assert len(issues) == 0


def test_cli_eval_config_output_dir_with_group_by_and_market_profile(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06", "2026-01-07"]
                    ),
                    "open": [10.0, 10.0, 20.0, 20.0, 20.0],
                    "high": [10.0, 10.0, 20.0, 20.0, 20.0],
                    "low": [10.0, 10.0, 20.0, 20.0, 20.0],
                    "close": [10.0, 11.0, 20.0, 18.0, 19.8],
                    "pre_close": [10.0, 10.0, 20.0, 20.0, 20.0],
                    "vol": [1.0, 1.0, 1.0, 1.0, 1.0],
                    "amount": [100.0, 100.0, 100.0, 100.0, 100.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06", "2026-01-07"]
                    ),
                    "rsi_2": [5.0, 15.0, 12.0, 6.0, 8.0],
                }
            )

        def load_security_metadata(self, ts_codes=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "board": ["main_board", "star_market"],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_dir = tmp_path / "eval_output"

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-07",
            "--codes",
            "000001.SZ",
            "000002.SZ",
            "--group-by",
            "board",
            "--market-profile",
            "configs/market_profiles/ashare_daily_default.yaml",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0

    assert (output_dir / "events.csv").is_file()
    assert (output_dir / "group_summary.csv").is_file()
    assert (output_dir / "run_manifest.json").is_file()
    assert (output_dir / "report_manifest.json").is_file()

    # run_manifest records group_by and market_profile provenance
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["group_by"] == ["board"]
    assert run_manifest["round_trip_cost_rate"] is None
    assert run_manifest["market_profile"] == "configs/market_profiles/ashare_daily_default.yaml"
    assert "group_summary" in run_manifest["artifacts"]

    # report manifest validates with no issues
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    manifest = ReportManifest.from_path(output_dir / "report_manifest.json")
    assert manifest.kind == "evaluation_report_manifest"
    issues = manifest.validate_contents()
    assert len(issues) == 0

    # events.csv has expected columns
    events = pd.read_csv(output_dir / "events.csv")
    assert "ts_code" in events.columns
    assert "trade_date" in events.columns
    assert "board" in events.columns  # preserved from group_by


def test_cli_eval_config_random_baseline_prints_summary(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06"]
                    ),
                    "open": [10.0, 10.0, 20.0, 20.0],
                    "high": [10.0, 10.0, 20.0, 20.0],
                    "low": [10.0, 10.0, 20.0, 20.0],
                    "close": [10.0, 11.0, 20.0, 18.0],
                    "pre_close": [10.0, 10.0, 20.0, 20.0],
                    "vol": [1.0, 1.0, 1.0, 1.0],
                    "amount": [100.0, 100.0, 100.0, 100.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06"]
                    ),
                    "rsi_2": [5.0, 15.0, 12.0, 6.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "000002.SZ",
            "--random-baseline-seed",
            "42",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "random_baseline_summary" in captured.out
    assert "horizon,event_count,mean_forward_return" in captured.out


def test_cli_eval_config_random_baseline_persists_to_output_dir(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06"]
                    ),
                    "open": [10.0, 10.0, 20.0, 20.0],
                    "high": [10.0, 10.0, 20.0, 20.0],
                    "low": [10.0, 10.0, 20.0, 20.0],
                    "close": [10.0, 11.0, 20.0, 18.0],
                    "pre_close": [10.0, 10.0, 20.0, 20.0],
                    "vol": [1.0, 1.0, 1.0, 1.0],
                    "amount": [100.0, 100.0, 100.0, 100.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-06", "2026-01-05", "2026-01-06"]
                    ),
                    "rsi_2": [5.0, 15.0, 12.0, 6.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_dir = tmp_path / "eval_out"

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "000002.SZ",
            "--random-baseline-seed",
            "42",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert (output_dir / "random_baseline_summary.csv").is_file()

    # manifest validates
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    manifest = ReportManifest.from_path(output_dir / "report_manifest.json")
    issues = manifest.validate_contents()
    assert len(issues) == 0

    # run manifest records seed
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["random_baseline_seed"] == 42
    assert "random_baseline_summary" in run_manifest["artifacts"]


def test_cli_eval_config_factor_decay_printed_and_persisted(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "c", "a", "b", "c"] * 3,
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-05", "2026-01-05",
                         "2026-01-06", "2026-01-06", "2026-01-06"] * 3
                    ),
                    "open": [10.0] * 18,
                    "high": [10.0] * 18,
                    "low": [10.0] * 18,
                    "close": [10.0] * 18,
                    "pre_close": [10.0] * 18,
                    "vol": [1.0] * 18,
                    "amount": [100.0] * 18,
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "c", "a", "b", "c"] * 3,
                    "trade_date": pd.to_datetime(
                        ["2026-01-05", "2026-01-05", "2026-01-05",
                         "2026-01-06", "2026-01-06", "2026-01-06"] * 3
                    ),
                    "rsi_2": [1.0, 2.0, 3.0, 1.0, 2.0, 3.0] * 3,
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_dir = tmp_path / "eval_decay"

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-07",
            "--codes",
            "a",
            "b",
            "c",
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0

    # Printed to stdout
    assert "factor_decay_summary" in captured.out

    # Persisted
    assert (output_dir / "factor_decay_summary.csv").is_file()
    decay = pd.read_csv(output_dir / "factor_decay_summary.csv")
    assert "factor" in decay.columns
    assert "horizon" in decay.columns
    assert "base_horizon" in decay.columns
    assert "ic_decay_from_base" in decay.columns
    assert "rank_ic_decay_from_base" in decay.columns

    # run_manifest records artifact
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert "factor_decay_summary" in run_manifest["artifacts"]

    # report_manifest validates
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    manifest = ReportManifest.from_path(output_dir / "report_manifest.json")
    issues = manifest.validate_contents()
    assert len(issues) == 0


def test_cli_preflight_prints_read_only_report(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def table_exists(self, table_name, *, engine=None):
            return table_name == "factors.stock_daily_momentum_close"

        def get_table_columns(self, table_name, *, engine=None):
            return ["ts_code", "trade_date", "rsi_2"]

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "open": [10.0],
                    "close": [10.5],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "rsi_2": [8.0],
                }
            )

        def load_security_metadata(self, ts_codes=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                    "is_st": [False],
                    "is_risk_warning": [False],
                    "is_suspended": [False],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "preflight",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-05",
            "--codes",
            "000001.SZ",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "status=ok" in captured.out
    assert "market_rows=1" in captured.out
    assert "latest_market_date=2026-01-05" in captured.out
    assert "factor_rsi_2_coverage_ratio=1.0" in captured.out
    assert "join_coverage_ratio=1.0" in captured.out


def test_cli_backtest_single_requires_db_url_or_environment(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "backtest-single",
            "examples/rsi2_reversal_research.yaml",
            "--symbol",
            "000001.SZ",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-20",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_backtest_batch_requires_db_url_or_environment(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "backtest-batch",
            "examples/rsi2_reversal_research.yaml",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-20",
            "--codes",
            "000001.SZ",
            "000002.SZ",
            "--group-by",
            "board",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_backtest_shared_requires_db_url_or_environment(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "backtest-shared",
            "examples/rsi2_reversal_research.yaml",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-20",
            "--codes",
            "000001.SZ",
            "000002.SZ",
            "--max-positions",
            "2",
            "--weight-model",
            "score_weight",
            "--score-column",
            "rsi_2",
            "--stop-loss-pct",
            "0.08",
            "--take-profit-pct",
            "0.12",
            "--trailing-stop-pct",
            "0.10",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_backtest_shared_accepts_yaml_risk_controls(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "backtest-shared",
            "examples/rsi2_reversal_with_risk.yaml",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-20",
            "--codes",
            "000001.SZ",
            "--max-positions",
            "1",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_backtest_shared_prints_benchmark_relative_summary(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_benchmark_bars(self, table_name, ts_codes, start, end, fields, limit=None):
            assert table_name == "public.stock_daily"
            assert ts_codes == ["000002.SZ"]
            assert fields == ["close"]
            return pd.DataFrame(
                {
                    "ts_code": ["000002.SZ", "000002.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                    "close": [100.0, 105.0, 110.25],
                }
            )

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            return pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"])})

    class FakeSharedEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return SharedCashBacktestResult(
                orders=pd.DataFrame(),
                trades=pd.DataFrame(),
                failed_orders=pd.DataFrame(),
                equity_curve=pd.DataFrame(
                    {
                        "trade_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                        "total_equity": [100.0, 110.0, 121.0],
                    }
                ),
                summary={"initial_cash": 100.0, "final_equity": 121.0, "total_return": 0.21},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "SharedCashBacktestEngine", FakeSharedEngine)

    exit_code = main(
        [
            "backtest-shared",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--codes",
            "000001.SZ",
            "--max-positions",
            "1",
            "--benchmark-table",
            "public.stock_daily",
            "--benchmark-code",
            "000002.SZ",
            "--benchmark-value-column",
            "close",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "benchmark_code=000002.SZ" in captured.out
    assert "benchmark_aligned_period_count=3" in captured.out
    assert "benchmark_total_return=0.1025" in captured.out
    assert "benchmark_excess_total_return=" in captured.out
    assert "benchmark_up_capture=2.0" in captured.out


def test_cli_backtest_shared_can_print_markdown_summary(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            return pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"])})

    class FakeSharedEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return SharedCashBacktestResult(
                orders=pd.DataFrame(),
                trades=pd.DataFrame(),
                failed_orders=pd.DataFrame(),
                equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"]), "total_equity": [100.0]}),
                summary={
                    "initial_cash": 100.0,
                    "final_equity": 105.0,
                    "total_return": 0.05,
                    "rebalance_order_count": 0,
                    "benchmark_code": "000002.SZ",
                    "benchmark_benchmark_total_return": 0.03,
                },
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "SharedCashBacktestEngine", FakeSharedEngine)

    exit_code = main(
        [
            "backtest-shared",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--codes",
            "000001.SZ",
            "--max-positions",
            "1",
            "--print-summary-md",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "# Shared Cash Backtest Summary" in captured.out
    assert "## Benchmark" in captured.out
    assert "| Benchmark total return | 0.03 |" in captured.out


def test_cli_backtest_shared_metadata_columns_persisted_to_output_dir(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            return pd.DataFrame({
                "trade_date": pd.to_datetime(["2026-01-05"]),
                "ts_code": ["000001.SZ"],
                "open": [10.0],
                "close": [10.1],
                "sector": ["Finance"],
            })

    class FakeSharedEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return SharedCashBacktestResult(
                orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"], "sector": ["Finance"]}),
                trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0], "sector": ["Finance"]}),
                failed_orders=pd.DataFrame(),
                equity_curve=pd.DataFrame(
                    {"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [100.0]}
                ),
                summary={"initial_cash": 100.0, "final_equity": 105.0, "total_return": 0.05},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "SharedCashBacktestEngine", FakeSharedEngine)

    output_dir = tmp_path / "output"
    exit_code = main(
        [
            "backtest-shared",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--codes",
            "000001.SZ",
            "--max-positions",
            "1",
            "--metadata-columns",
            "sector",
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "orders_path=" in captured.out
    orders_csv = pd.read_csv(output_dir / "orders.csv")
    assert "sector" in orders_csv.columns
    trades_csv = pd.read_csv(output_dir / "trades.csv")
    assert "sector" in trades_csv.columns
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["request"]["metadata_columns"] == ["sector"]


def test_cli_backtest_shared_group_by_writes_grouped_artifacts(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            return pd.DataFrame({
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                "ts_code": ["000001.SZ", "000002.SZ"],
                "open": [10.0, 20.0],
                "close": [10.1, 20.2],
                "board": ["main_board", "star_market"],
            })

    class FakeSharedEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return SharedCashBacktestResult(
                orders=pd.DataFrame({
                    "symbol": ["000001.SZ", "000002.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-06", "2026-01-07"]),
                    "side": ["buy", "sell"],
                    "quantity": [100, 50],
                    "price": [10.0, 20.0],
                    "notional": [1000.0, 1000.0],
                    "cost": [5.0, 5.0],
                    "reason": ["entry", "exit"],
                    "board": ["main_board", "star_market"],
                }),
                trades=pd.DataFrame({
                    "symbol": ["000001.SZ", "000002.SZ"],
                    "entry_date": pd.to_datetime(["2026-01-06", "2026-01-07"]),
                    "exit_date": pd.to_datetime(["2026-01-09", "2026-01-10"]),
                    "quantity": [100, 50],
                    "entry_price": [10.0, 20.0],
                    "exit_price": [11.0, 25.0],
                    "gross_pnl": [100.0, 250.0],
                    "cost": [10.0, 5.0],
                    "net_pnl": [90.0, 245.0],
                    "exit_reason": ["holding_days", "holding_days"],
                    "board": ["main_board", "star_market"],
                }),
                failed_orders=pd.DataFrame({
                    "symbol": ["000002.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-07"]),
                    "side": ["buy"],
                    "quantity": [100],
                    "price": [30.0],
                    "notional": [3000.0],
                    "reason": [None],
                    "failure_reason": ["limit_up_buy_blocked"],
                    "board": ["star_market"],
                }),
                equity_curve=pd.DataFrame(
                    {"trade_date": pd.date_range("2026-01-30", periods=21, freq="B"), "total_equity": [100.0] * 21}
                ),
                summary={"initial_cash": 100.0, "final_equity": 105.0, "total_return": 0.05},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "SharedCashBacktestEngine", FakeSharedEngine)

    output_dir = tmp_path / "output"
    exit_code = main(
        [
            "backtest-shared",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--codes",
            "000001.SZ",
            "000002.SZ",
            "--max-positions",
            "2",
            "--group-by",
            "board",
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "orders_by_board" in captured.out
    assert "trades_by_board" in captured.out
    assert "failed_orders_by_board" in captured.out

    assert (output_dir / "orders_by_board.csv").exists()
    assert (output_dir / "trades_by_board.csv").exists()
    assert (output_dir / "failed_orders_by_board.csv").exists()

    orders_grouped = pd.read_csv(output_dir / "orders_by_board.csv")
    assert orders_grouped["group_value"].tolist() == ["main_board", "star_market"]
    assert orders_grouped["order_count"].tolist() == [1, 1]

    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["request"]["group_by"] == ["board"]

    report_manifest = json.loads((output_dir / "report_manifest.json").read_text(encoding="utf-8"))
    manifest_by_key = {item["key"]: item for item in report_manifest["files"]}
    assert manifest_by_key["orders_by_board"]["group_by"] == "board"
    assert manifest_by_key["orders_by_board"]["role"] == "shared_orders_group_summary"


def test_cli_backtest_batch_can_print_markdown_summary(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            return pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"])})

    class FakeBatchEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return BatchBacktestResult(
                symbols=["000001.SZ"],
                results={},
                summary=pd.DataFrame(
                    {
                        "symbol": ["000001.SZ"],
                        "trade_count": [1],
                        "board": ["main_board"],
                        "total_return": [0.05],
                        "win_rate": [1.0],
                        "total_cost": [10.0],
                        "failed_order_count": [0],
                    }
                ),
                summary_metrics={"symbol_count": 1, "mean_total_return": 0.05, "total_trades": 1},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "BatchBacktestEngine", FakeBatchEngine)

    exit_code = main(
        [
            "backtest-batch",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--codes",
            "000001.SZ",
            "--group-by",
            "board",
            "--group-rank-top-n",
            "2",
            "--print-summary-md",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "# Batch Backtest Summary" in captured.out
    assert "## Aggregate Metrics" in captured.out
    assert "| Symbol count | 1 |" in captured.out
    assert "## Top Symbols" in captured.out
    assert "| 000001.SZ | 0.05 | 1 | 1.0 | 10.0 |" in captured.out
    assert "| Monthly window summary | window_summary_M.csv |" in captured.out
    assert "| Quarterly window summary | window_summary_Q.csv |" in captured.out
    assert "| Yearly window summary | window_summary_Y.csv |" in captured.out
    assert "| Report manifest | report_manifest.json |" in captured.out
    assert "| Group by board | group_by_board.csv |" in captured.out
    assert "| Group by board ranked symbols | group_by_board_ranked_symbols.csv |" in captured.out
    assert "| Window summary M by board | window_summary_M_by_board.csv |" in captured.out
    assert "| Window summary Q by board | window_summary_Q_by_board.csv |" in captured.out
    assert "| Window summary Y by board | window_summary_Y_by_board.csv |" in captured.out
    assert "| Window summary M by board ranked symbols | window_summary_M_by_board_ranked_symbols.csv |" in captured.out
    assert "| Window summary Q by board ranked symbols | window_summary_Q_by_board_ranked_symbols.csv |" in captured.out
    assert "| Window summary Y by board ranked symbols | window_summary_Y_by_board_ranked_symbols.csv |" in captured.out


def test_cli_backtest_batch_group_by_passthrough_column(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            return pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"])})

    class FakeBatchEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return BatchBacktestResult(
                symbols=["000001.SZ", "000002.SZ"],
                results={},
                summary=pd.DataFrame(
                    {
                        "symbol": ["000001.SZ", "000002.SZ"],
                        "trade_count": [2, 1],
                        "board": ["main_board", "chinext"],
                        "sector": ["Finance", "Tech"],
                        "total_return": [0.05, 0.03],
                        "win_rate": [1.0, 0.5],
                        "total_cost": [10.0, 5.0],
                        "failed_order_count": [0, 0],
                    }
                ),
                summary_metrics={"symbol_count": 2, "mean_total_return": 0.04, "total_trades": 3},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "BatchBacktestEngine", FakeBatchEngine)

    exit_code = main(
        [
            "backtest-batch",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--codes",
            "000001.SZ",
            "000002.SZ",
            "--group-by",
            "sector",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "group_by=sector" in captured.out
    assert "Finance" in captured.out
    assert "Tech" in captured.out


def test_cli_report_files_filters_manifest_paths(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
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

    exit_code = main(
        [
            "report-files",
            str(manifest_path),
            "--role",
            "window_ranked_symbols",
            "--window",
            "M",
            "--group-by",
            "board",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == str(tmp_path / "window_summary_M_by_board_ranked_symbols.csv")


def test_cli_report_files_can_print_keys(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "000001.SZ_orders",
                        "path": "000001.SZ/orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                        "symbol": "000001.SZ",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--role", "orders", "--symbol", "000001.SZ", "--keys"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "000001.SZ_orders"


def test_cli_report_files_reports_invalid_manifest(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(json.dumps({"kind": "other", "files": []}), encoding="utf-8")

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "batch_backtest_report_manifest" in captured.err


def test_cli_report_files_reports_unsupported_schema_version(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "unsupported manifest schema_version" in captured.err


def test_cli_report_files_reports_string_schema_version(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "v1",
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

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "unsupported manifest schema_version" in captured.err


def test_cli_report_files_reports_boolean_schema_version(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "unsupported manifest schema_version" in captured.err


def test_cli_report_files_reports_missing_file_entry_field(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "missing required field" in captured.err


def test_cli_report_audit_reports_invalid_manifest(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(json.dumps({"kind": "other", "files": []}), encoding="utf-8")

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "batch_backtest_report_manifest" in captured.err


def test_cli_report_audit_reports_unsupported_schema_version(capsys, tmp_path):
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

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "unsupported manifest schema_version" in captured.err


def test_cli_report_audit_reports_string_schema_version(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "v1",
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

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "unsupported manifest schema_version" in captured.err


def test_cli_report_audit_reports_boolean_schema_version(capsys, tmp_path):
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

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "unsupported manifest schema_version" in captured.err


def test_cli_report_audit_reports_missing_file_entry_field(capsys, tmp_path):
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

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "missing required field" in captured.err


def test_cli_report_files_check_exists_passes_when_files_exist(capsys, tmp_path):
    output_path = tmp_path / "summary.csv"
    output_path.write_text("symbol,total_return\n000001.SZ,0.1\n", encoding="utf-8")
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

    exit_code = main(["report-files", str(manifest_path), "--role", "summary", "--check-exists"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == str(output_path)
    assert captured.err == ""


def test_cli_report_files_check_exists_reports_missing_paths(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path), "--role", "summary", "--check-exists"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert str(tmp_path / "summary.csv") in captured.err


def test_cli_report_files_validate_contents_passes_when_report_files_are_valid(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,trade_date,side\n000001.SZ,2026-01-05,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--role", "orders", "--validate-contents"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == str(output_path)
    assert captured.err == ""


def test_cli_report_files_validate_contents_reports_structural_issues(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,side\n000001.SZ,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--role", "orders", "--validate-contents"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "orders" in captured.err
    assert "missing_columns" in captured.err
    assert str(output_path) in captured.err
    assert "trade_date" in captured.err


def test_cli_report_audit_summarizes_valid_manifest(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,trade_date,side\n000001.SZ,2026-01-05,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path), "--role", "orders"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "manifest_kind=shared_cash_backtest_report_manifest" in captured.out
    assert "matched_files=1" in captured.out
    assert "missing_files=0" in captured.out
    assert "validation_issues=0" in captured.out
    assert "status=ok" in captured.out
    assert captured.err == ""


def test_cli_report_audit_reports_missing_and_invalid_files(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,side\n000001.SZ,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    },
                    {
                        "key": "trades",
                        "path": "trades.csv",
                        "filename": "trades.csv",
                        "role": "trades",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "matched_files=2" in captured.out
    assert "missing_files=1" in captured.out
    assert "validation_issues=2" in captured.out
    assert "status=failed" in captured.out
    assert "orders" in captured.err
    assert "missing_columns" in captured.err
    assert str(output_path) in captured.err
    assert "trades" in captured.err
    assert "missing_file" in captured.err


def test_cli_report_audit_allows_zero_matches_by_default(capsys, tmp_path):
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

    exit_code = main(["report-audit", str(manifest_path), "--role", "rolling_ranked_symbols"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "matched_files=0" in captured.out
    assert "status=ok" in captured.out
    assert captured.err == ""


def test_cli_report_audit_require_match_fails_zero_matches(capsys, tmp_path):
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

    exit_code = main(
        [
            "report-audit",
            str(manifest_path),
            "--role",
            "rolling_ranked_symbols",
            "--require-match",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "matched_files=0" in captured.out
    assert "status=failed" in captured.out
    assert "no manifest entries matched filters" in captured.err


def test_cli_report_audit_json_outputs_valid_object(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,trade_date,side\n000001.SZ,2026-01-05,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path), "--role", "orders", "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["manifest_kind"] == "shared_cash_backtest_report_manifest"
    assert payload["schema_version"] is None
    assert payload["matched_files"] == 1
    assert payload["missing_files"] == 0
    assert payload["validation_issues"] == 0
    assert payload["status"] == "ok"
    assert payload["issues"] == []


def test_cli_report_audit_json_includes_issues_for_failures(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,side\n000001.SZ,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    },
                    {
                        "key": "trades",
                        "path": "trades.csv",
                        "filename": "trades.csv",
                        "role": "trades",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path), "--json"])

    captured = capsys.readouterr()

    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 2
    assert payload["schema_version"] is None
    assert payload["missing_files"] == 1
    assert payload["validation_issues"] == 2
    assert payload["status"] == "failed"
    assert len(payload["issues"]) == 2
    codes = {issue["code"] for issue in payload["issues"]}
    assert "missing_columns" in codes
    assert "missing_file" in codes

    missing_file_issue = next(i for i in payload["issues"] if i["code"] == "missing_file")
    assert missing_file_issue["code"] == "missing_file"
    assert missing_file_issue["key"] == "trades"
    assert missing_file_issue["path"] == str(tmp_path / "trades.csv")
    assert missing_file_issue["message"] == f"missing file: {tmp_path / 'trades.csv'}"

    missing_columns_issue = next(i for i in payload["issues"] if i["code"] == "missing_columns")
    assert missing_columns_issue["code"] == "missing_columns"
    assert missing_columns_issue["key"] == "orders"
    assert missing_columns_issue["path"] == str(output_path)
    assert "missing column" in missing_columns_issue["message"]
    assert "trade_date" in missing_columns_issue["message"]


def test_cli_report_audit_json_require_match_zero_matches(capsys, tmp_path):
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

    exit_code = main(
        [
            "report-audit",
            str(manifest_path),
            "--role",
            "rolling_ranked_symbols",
            "--json",
            "--require-match",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "no manifest entries matched filters" in captured.err
    payload = json.loads(captured.out)
    assert payload["schema_version"] is None
    assert payload["matched_files"] == 0
    assert payload["status"] == "failed"
    assert payload["issues"] == [
        {
            "key": "manifest",
            "code": "no_matches",
            "path": str(manifest_path),
            "message": "no manifest entries matched filters",
        }
    ]
    spec = StrategySpec.from_yaml("examples/rsi2_reversal_with_risk.yaml")
    args = Namespace(stop_loss_pct=None, take_profit_pct=None, trailing_stop_pct=None)

    controls = resolve_risk_controls(args, spec)

    assert controls == {
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.12,
        "trailing_stop_pct": 0.10,
    }


def test_resolve_risk_controls_prefers_cli_values_over_yaml():
    spec = StrategySpec.from_yaml("examples/rsi2_reversal_with_risk.yaml")
    args = Namespace(stop_loss_pct=0.05, take_profit_pct=None, trailing_stop_pct=0.07)

    controls = resolve_risk_controls(args, spec)

    assert controls == {
        "stop_loss_pct": 0.05,
        "take_profit_pct": 0.12,
        "trailing_stop_pct": 0.07,
    }


def test_resolve_weight_controls_uses_yaml_when_cli_is_absent():
    spec = StrategySpec.from_yaml("examples/rsi2_reversal_with_risk_and_weight.yaml")
    args = Namespace(weight_model=None, score_column=None, volatility_column=None)

    controls = resolve_weight_controls(args, spec)

    assert controls == {
        "weight_model": "score_weight",
        "score_column": "rsi_2",
        "volatility_column": None,
    }


def test_resolve_weight_controls_prefers_cli_values_over_yaml():
    spec = StrategySpec.from_yaml("examples/rsi2_reversal_with_risk_and_weight.yaml")
    args = Namespace(weight_model="inverse_volatility", score_column=None, volatility_column="vol_20")

    controls = resolve_weight_controls(args, spec)

    assert controls == {
        "weight_model": "inverse_volatility",
        "score_column": "rsi_2",
        "volatility_column": "vol_20",
    }


def test_resolve_weight_controls_defaults_to_equal_weight_when_unspecified():
    spec = StrategySpec.from_yaml("examples/rsi2_reversal_research.yaml")
    args = Namespace(weight_model=None, score_column=None, volatility_column=None)

    controls = resolve_weight_controls(args, spec)

    assert controls == {
        "weight_model": "equal_weight",
        "score_column": None,
        "volatility_column": None,
    }


def test_resolve_rebalance_controls_uses_yaml_when_cli_is_absent():
    spec = StrategySpec.from_mapping(
        {
            "experiment": {"name": "rebalance_test"},
            "data": {"factor_fields": {"rsi_2": "factors.stock_daily_momentum_close.rsi_2"}},
            "signal": {"entry": "rsi_2 < 10"},
            "evaluation": {"forward_return_horizons": [1]},
            "holding": {"max_holding_days": 5},
            "portfolio": {"rebalance_interval_days": 5},
        }
    )
    args = Namespace(rebalance_interval_days=None)

    controls = resolve_rebalance_controls(args, spec)

    assert controls == {"rebalance_interval_days": 5}


def test_resolve_rebalance_controls_prefers_cli_values_over_yaml():
    spec = StrategySpec.from_mapping(
        {
            "experiment": {"name": "rebalance_test"},
            "data": {"factor_fields": {"rsi_2": "factors.stock_daily_momentum_close.rsi_2"}},
            "signal": {"entry": "rsi_2 < 10"},
            "evaluation": {"forward_return_horizons": [1]},
            "holding": {"max_holding_days": 5},
            "portfolio": {"rebalance_interval_days": 5},
        }
    )
    args = Namespace(rebalance_interval_days=3)

    controls = resolve_rebalance_controls(args, spec)

    assert controls == {"rebalance_interval_days": 3}


def test_cli_backtest_single_accepts_output_dir_argument(capsys, monkeypatch, tmp_path):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "backtest-single",
            "examples/rsi2_reversal_research.yaml",
            "--symbol",
            "000001.SZ",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-20",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_backtest_single_accepts_market_profile_argument(capsys, monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    exit_code = main(
        [
            "backtest-single",
            "examples/rsi2_reversal_research.yaml",
            "--symbol",
            "000001.SZ",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-20",
            "--market-profile",
            "configs/market_profiles/ashare_daily_default.yaml",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "QRE_MARKET_DB_URL" in captured.err


def test_cli_report_audit_passes_for_valid_failed_orders_csv(capsys, tmp_path):
    output_path = tmp_path / "failed_orders.csv"
    output_path.write_text(
        "symbol,trade_date,side,quantity,price,notional,reason\n"
        "000001.SZ,2026-01-06,buy,100,10.0,1000.0,\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "failed_orders",
                        "path": "failed_orders.csv",
                        "filename": "failed_orders.csv",
                        "role": "failed_orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path), "--role", "failed_orders"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "validation_issues=0" in captured.out
    assert "status=ok" in captured.out
    assert captured.err == ""


def test_cli_report_audit_fails_for_malformed_failed_orders_csv(capsys, tmp_path):
    output_path = tmp_path / "failed_orders.csv"
    output_path.write_text(
        "symbol,side\n000001.SZ,buy\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "failed_orders",
                        "path": "failed_orders.csv",
                        "filename": "failed_orders.csv",
                        "role": "failed_orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path), "--role", "failed_orders"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "validation_issues=1" in captured.out
    assert "status=failed" in captured.out
    assert "failed_orders" in captured.err
    assert "missing_columns" in captured.err
    assert str(output_path) in captured.err


def test_cli_report_files_require_match_returns_zero_when_absent(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--role", "orders"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_cli_report_files_require_match_errors_when_no_entries_match(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        ["report-files", str(manifest_path), "--role", "orders", "--require-match"]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "no manifest entries matched filters" in captured.err


def test_cli_report_files_require_match_prints_paths_when_entries_match(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,trade_date\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        ["report-files", str(manifest_path), "--role", "orders", "--require-match"]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert str(output_path) in captured.out
    assert captured.err == ""


def test_cli_report_files_json_outputs_matched_entries(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,trade_date\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--role", "orders", "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["manifest_kind"] == "shared_cash_backtest_report_manifest"
    assert payload["schema_version"] is None
    assert payload["matched_files"] == 1
    assert len(payload["files"]) == 1
    entry = payload["files"][0]
    assert entry["key"] == "orders"
    assert entry["path"] == str(output_path)
    assert entry["filename"] == "orders.csv"
    assert entry["role"] == "orders"


def test_cli_report_files_json_includes_optional_metadata(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "window_summary_M_by_board_ranked_symbols",
                        "path": "window_summary_M_by_board_ranked_symbols.csv",
                        "filename": "window_summary_M_by_board_ranked_symbols.csv",
                        "role": "window_ranked_symbols",
                        "window": "M",
                        "group_by": "board",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["schema_version"] is None
    assert payload["matched_files"] == 1
    entry = payload["files"][0]
    assert entry["window"] == "M"
    assert entry["group_by"] == "board"
    assert "symbol" not in entry


def test_cli_report_files_json_zero_matches_exits_zero(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--role", "orders", "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 0
    assert payload["files"] == []


def test_cli_report_files_json_require_match_errors_on_zero_matches(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        ["report-files", str(manifest_path), "--role", "orders", "--json", "--require-match"]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "no manifest entries matched filters" in captured.err
    payload = json.loads(captured.out)
    assert payload["manifest_kind"] == "shared_cash_backtest_report_manifest"
    assert payload["schema_version"] is None
    assert payload["matched_files"] == 0
    assert payload["files"] == []


def test_cli_report_files_json_includes_schema_version_when_present(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,trade_date\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--role", "orders", "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["schema_version"] == 1
    assert payload["manifest_kind"] == "shared_cash_backtest_report_manifest"
    assert payload["matched_files"] == 1
    assert len(payload["files"]) == 1


def test_cli_report_audit_json_includes_schema_version_when_present(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,trade_date,side\n000001.SZ,2026-01-05,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path), "--role", "orders", "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["schema_version"] == 1
    assert payload["manifest_kind"] == "shared_cash_backtest_report_manifest"
    assert payload["matched_files"] == 1
    assert payload["status"] == "ok"


def test_cli_report_files_reports_missing_kind(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"files": []}),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest missing top-level 'kind' field" in captured.err


def test_cli_report_files_reports_missing_files(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"kind": "batch_backtest_report_manifest"}),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest missing top-level 'files' field" in captured.err


def test_cli_report_audit_reports_missing_kind(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"files": []}),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest missing top-level 'kind' field" in captured.err


def test_cli_report_audit_reports_missing_files(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"kind": "batch_backtest_report_manifest"}),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest missing top-level 'files' field" in captured.err


def test_cli_report_files_reports_non_string_kind(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"kind": 123, "files": []}),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest 'kind' must be a string" in captured.err


def test_cli_report_files_reports_non_list_files(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"kind": "batch_backtest_report_manifest", "files": "not-a-list"}),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest 'files' must be a list" in captured.err


def test_cli_report_audit_reports_non_string_kind(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"kind": 123, "files": []}),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest 'kind' must be a string" in captured.err


def test_cli_report_audit_reports_non_list_files(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps({"kind": "batch_backtest_report_manifest", "files": "not-a-list"}),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest 'files' must be a list" in captured.err


def test_cli_report_files_reports_invalid_json_text(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text("not-json", encoding="utf-8")

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest contains invalid JSON" in captured.err


def test_cli_report_files_reports_non_object_root(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text("[]", encoding="utf-8")

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest root must be an object" in captured.err


def test_cli_report_audit_reports_invalid_json_text(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text("not-json", encoding="utf-8")

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest contains invalid JSON" in captured.err


def test_cli_report_audit_reports_non_object_root(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text("[]", encoding="utf-8")

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest root must be an object" in captured.err


def test_cli_report_files_reports_non_object_file_entry(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": ["not-an-object"],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry 0 must be an object" in captured.err


def test_cli_report_files_reports_non_string_file_entry_field(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "summary",
                        "path": 123,
                        "filename": "summary.csv",
                        "role": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry field 'path' must be a string" in captured.err


def test_cli_report_audit_reports_non_object_file_entry(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": ["not-an-object"],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry 0 must be an object" in captured.err


def test_cli_report_audit_reports_non_string_file_entry_field(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "summary",
                        "path": 123,
                        "filename": "summary.csv",
                        "role": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry field 'path' must be a string" in captured.err


def test_cli_report_files_reports_non_string_optional_symbol(capsys, tmp_path):
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
                        "symbol": 123,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry field 'symbol' must be a string or null" in captured.err


def test_cli_report_files_reports_non_string_optional_window(capsys, tmp_path):
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
                        "window": 456,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry field 'window' must be a string or null" in captured.err


def test_cli_report_audit_reports_non_string_optional_symbol(capsys, tmp_path):
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
                        "symbol": 123,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry field 'symbol' must be a string or null" in captured.err


def test_cli_report_audit_reports_non_string_optional_window(capsys, tmp_path):
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
                        "window": 456,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry field 'window' must be a string or null" in captured.err


def test_cli_report_files_reports_non_string_optional_group_by(capsys, tmp_path):
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
                        "group_by": 789,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry field 'group_by' must be a string or null" in captured.err


def test_cli_report_audit_reports_non_string_optional_group_by(capsys, tmp_path):
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
                        "group_by": 789,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "manifest file entry field 'group_by' must be a string or null" in captured.err


def test_cli_report_files_json_accepts_null_optional_metadata(capsys, tmp_path):
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
                        "symbol": None,
                        "window": None,
                        "group_by": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    entry = payload["files"][0]
    assert entry["key"] == "summary"
    assert entry["role"] == "summary"
    assert "symbol" not in entry
    assert "window" not in entry
    assert "group_by" not in entry


def test_cli_report_audit_json_accepts_null_optional_metadata(capsys, tmp_path):
    output_path = tmp_path / "summary.csv"
    output_path.write_text("symbol,total_return\n000001.SZ,0.1\n", encoding="utf-8")
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
                        "symbol": None,
                        "window": None,
                        "group_by": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-audit", str(manifest_path), "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["status"] == "ok"
    assert payload["matched_files"] == 1
    assert payload["missing_files"] == 0
    assert payload["validation_issues"] == 0


def test_cli_report_files_json_accepts_null_schema_version(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": None,
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

    exit_code = main(["report-files", str(manifest_path), "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["schema_version"] is None
    assert payload["matched_files"] == 1


def test_cli_report_audit_json_accepts_null_schema_version(capsys, tmp_path):
    output_path = tmp_path / "summary.csv"
    output_path.write_text("symbol,total_return\n000001.SZ,0.1\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": None,
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

    exit_code = main(["report-audit", str(manifest_path), "--json"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["schema_version"] is None
    assert payload["status"] == "ok"


def test_cli_report_files_json_check_exists_passes_when_files_exist(capsys, tmp_path):
    output_path = tmp_path / "summary.csv"
    output_path.write_text("symbol,total_return\n000001.SZ,0.1\n", encoding="utf-8")
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

    exit_code = main(["report-files", str(manifest_path), "--json", "--check-exists"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert len(payload["files"]) == 1
    assert payload["files"][0]["key"] == "summary"
    assert payload["files"][0]["path"] == str(output_path)


def test_cli_report_files_json_check_exists_reports_missing_paths(capsys, tmp_path):
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
    missing_path = tmp_path / "summary.csv"

    exit_code = main(["report-files", str(manifest_path), "--json", "--check-exists"])

    captured = capsys.readouterr()

    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert len(payload["files"]) == 1
    assert payload["files"][0]["key"] == "summary"
    assert str(missing_path) in captured.err


def test_cli_report_files_json_validate_contents_passes_when_files_are_valid(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,trade_date,side\n000001.SZ,2026-01-05,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--role", "orders", "--json", "--validate-contents"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert len(payload["files"]) == 1
    assert payload["files"][0]["key"] == "orders"
    assert payload["files"][0]["path"] == str(output_path)


def test_cli_report_files_json_validate_contents_reports_structural_issues(capsys, tmp_path):
    output_path = tmp_path / "orders.csv"
    output_path.write_text("symbol,side\n000001.SZ,buy\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {
                        "key": "orders",
                        "path": "orders.csv",
                        "filename": "orders.csv",
                        "role": "orders",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["report-files", str(manifest_path), "--role", "orders", "--json", "--validate-contents"])

    captured = capsys.readouterr()

    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert len(payload["files"]) == 1
    assert payload["files"][0]["key"] == "orders"
    assert "orders" in captured.err
    assert "missing_columns" in captured.err
    assert str(output_path) in captured.err
    assert "trade_date" in captured.err


def test_cli_eval_config_run_id_in_run_manifest(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "a", "b"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-05", "2026-01-06", "2026-01-06"]),
                    "open": [10.0] * 4,
                    "high": [10.0] * 4,
                    "low": [10.0] * 4,
                    "close": [10.0, 10.0, 11.0, 12.0],
                    "pre_close": [10.0] * 4,
                    "vol": [1.0] * 4,
                    "amount": [100.0] * 4,
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "a", "b"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-05", "2026-01-06", "2026-01-06"]),
                    "rsi_2": [1.0, 2.0, 1.0, 1.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_dir = tmp_path / "eval_output"

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "a",
            "b",
            "--output-dir",
            str(output_dir),
            "--run-id",
            "research-run-42",
        ]
    )

    assert exit_code == 0
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["run_id"] == "research-run-42"


def test_cli_eval_config_run_id_omitted_is_null(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "a", "b"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-05", "2026-01-06", "2026-01-06"]),
                    "open": [10.0] * 4,
                    "high": [10.0] * 4,
                    "low": [10.0] * 4,
                    "close": [10.0, 10.0, 11.0, 12.0],
                    "pre_close": [10.0] * 4,
                    "vol": [1.0] * 4,
                    "amount": [100.0] * 4,
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["a", "b", "a", "b"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-05", "2026-01-06", "2026-01-06"]),
                    "rsi_2": [1.0, 2.0, 1.0, 1.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_dir = tmp_path / "eval_output"

    exit_code = main(
        [
            "eval-config",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "a",
            "b",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["run_id"] is None


def test_cli_preflight_run_id_in_output_json(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def table_exists(self, table_name, *, engine=None):
            return table_name == "factors.stock_daily_momentum_close"

        def get_table_columns(self, table_name, *, engine=None):
            return ["ts_code", "trade_date", "rsi_2"]

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "open": [10.0],
                    "close": [10.5],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "rsi_2": [8.0],
                }
            )

        def load_security_metadata(self, ts_codes=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                    "is_st": [False],
                    "is_risk_warning": [False],
                    "is_suspended": [False],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_json_path = tmp_path / "preflight_output.json"

    exit_code = main(
        [
            "preflight",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-05",
            "--codes",
            "000001.SZ",
            "--output-json",
            str(output_json_path),
            "--run-id",
            "research-run-42",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "research-run-42"


def test_cli_preflight_run_id_omitted_is_null(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def table_exists(self, table_name, *, engine=None):
            return table_name == "factors.stock_daily_momentum_close"

        def get_table_columns(self, table_name, *, engine=None):
            return ["ts_code", "trade_date", "rsi_2"]

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "open": [10.0],
                    "close": [10.5],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "rsi_2": [8.0],
                }
            )

        def load_security_metadata(self, ts_codes=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "list_date": pd.to_datetime(["1991-04-03"]),
                    "board": ["main_board"],
                    "is_st": [False],
                    "is_risk_warning": [False],
                    "is_suspended": [False],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_json_path = tmp_path / "preflight_output.json"

    exit_code = main(
        [
            "preflight",
            "examples/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-05",
            "--codes",
            "000001.SZ",
            "--output-json",
            str(output_json_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_json_path.read_text(encoding="utf-8"))
    assert payload["run_id"] is None
