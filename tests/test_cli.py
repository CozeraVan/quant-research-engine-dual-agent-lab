from argparse import Namespace
from datetime import date
import json
from pathlib import Path

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
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestResult
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
    assert (output_dir / "group_summary_by_board.csv").is_file()
    assert (output_dir / "run_manifest.json").is_file()
    assert (output_dir / "report_manifest.json").is_file()

    # run_manifest records group_by and market_profile provenance
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["group_by"] == ["board"]
    assert run_manifest["round_trip_cost_rate"] is None
    assert run_manifest["market_profile"] == "configs/market_profiles/ashare_daily_default.yaml"
    assert "group_summary" in run_manifest["artifacts"]
    assert "group_summary_by_board" in run_manifest["artifacts"]

    # report manifest validates with no issues
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    manifest = ReportManifest.from_path(output_dir / "report_manifest.json")
    assert manifest.kind == "evaluation_report_manifest"
    issues = manifest.validate_contents()
    assert len(issues) == 0

    # per-column grouped file has expected manifest entry with group_by metadata
    by_key = {e.key: {"role": e.role, "group_by": e.group_by} for e in manifest.files_}
    assert by_key["group_summary"]["role"] == "evaluation_group_summary"
    assert by_key["group_summary"]["group_by"] is None  # combined file has no group_by metadata
    assert by_key["group_summary_by_board"]["role"] == "evaluation_group_summary"
    assert by_key["group_summary_by_board"]["group_by"] == "board"

    # per-column file is discoverable and auditable via --group-by
    matches = manifest.files(role="evaluation_group_summary", group_by="board")
    assert len(matches) == 1
    assert matches[0].key == "group_summary_by_board"

    # report-audit --require-match works on the per-column file
    audit_issues = manifest.validate_contents(role="evaluation_group_summary", group_by="board")
    assert len(audit_issues) == 0

    # events.csv has expected columns
    events = pd.read_csv(output_dir / "events.csv")
    assert "ts_code" in events.columns
    assert "trade_date" in events.columns
    assert "board" in events.columns  # preserved from group_by


def test_cli_eval_config_output_dir_multi_group_by_writes_per_column_files(capsys, monkeypatch, tmp_path):
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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000002.SZ"],
                    "board": ["main_board", "star_market"],
                    "sector": ["Finance", "Technology"],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_dir = tmp_path / "eval_output"

    exit_code = main(
        [
            "eval-config",
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "sector",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0

    # Combined file still written
    assert (output_dir / "group_summary.csv").is_file()

    # Per-column files for both group-by columns
    assert (output_dir / "group_summary_by_board.csv").is_file()
    board_group = pd.read_csv(output_dir / "group_summary_by_board.csv")
    assert (board_group["group_by"] == "board").all()

    assert (output_dir / "group_summary_by_sector.csv").is_file()
    sector_group = pd.read_csv(output_dir / "group_summary_by_sector.csv")
    assert (sector_group["group_by"] == "sector").all()

    # report manifest entries have correct group_by metadata
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    manifest = ReportManifest.from_path(output_dir / "report_manifest.json")
    by_key = {e.key: e.group_by for e in manifest.files_}
    assert by_key["group_summary"] is None
    assert by_key["group_summary_by_board"] == "board"
    assert by_key["group_summary_by_sector"] == "sector"

    # Filtering by group_by matches only the per-column file
    board_matches = manifest.files(role="evaluation_group_summary", group_by="board")
    assert len(board_matches) == 1
    assert board_matches[0].key == "group_summary_by_board"

    sector_matches = manifest.files(role="evaluation_group_summary", group_by="sector")
    assert len(sector_matches) == 1
    assert sector_matches[0].key == "group_summary_by_sector"


def test_cli_report_files_eval_group_by_filter(capsys, monkeypatch, tmp_path):
    """report-files --role evaluation_group_summary --group-by <col> matches per-column file."""
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    output_dir = tmp_path / "eval_output"
    output_dir.mkdir(parents=True)

    # Write a minimal combined group_summary.csv
    group_csv = output_dir / "group_summary.csv"
    group_csv.write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nboard,chinext,1,30\nsector,Tech,1,40\n",
        encoding="utf-8",
    )
    # Write per-column files
    by_board = output_dir / "group_summary_by_board.csv"
    by_board.write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nboard,chinext,1,30\n",
        encoding="utf-8",
    )
    by_sector = output_dir / "group_summary_by_sector.csv"
    by_sector.write_text(
        "group_by,group_value,horizon,event_count\nsector,Tech,1,40\n",
        encoding="utf-8",
    )

    # Write manifest
    manifest_path = output_dir / "report_manifest.json"
    manifest_payload = {
        "schema_version": 1,
        "kind": "evaluation_report_manifest",
        "files": [
            {"key": "group_summary", "path": "group_summary.csv", "filename": "group_summary.csv",
             "role": "evaluation_group_summary"},
            {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
             "filename": "group_summary_by_board.csv", "role": "evaluation_group_summary",
             "group_by": "board"},
            {"key": "group_summary_by_sector", "path": "group_summary_by_sector.csv",
             "filename": "group_summary_by_sector.csv", "role": "evaluation_group_summary",
             "group_by": "sector"},
        ],
    }
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    exit_code = main([
        "report-files", str(manifest_path),
        "--role", "evaluation_group_summary",
        "--group-by", "board",
    ])
    assert exit_code == 0
    output_lines = [l for l in capsys.readouterr().out.strip().split("\n") if l]
    assert len(output_lines) == 1
    assert output_lines[0].endswith("group_summary_by_board.csv")

    # Without group_by filter: all 3 files matched
    exit_code2 = main([
        "report-files", str(manifest_path),
        "--role", "evaluation_group_summary",
    ])
    assert exit_code2 == 0
    all_lines = [l for l in capsys.readouterr().out.strip().split("\n") if l]
    assert len(all_lines) == 3
    filenames = [l.rsplit("/", 1)[-1] for l in all_lines]
    assert "group_summary.csv" in filenames
    assert "group_summary_by_board.csv" in filenames
    assert "group_summary_by_sector.csv" in filenames


def test_cli_report_audit_eval_group_by_filter(capsys, monkeypatch, tmp_path):
    """report-audit --role evaluation_group_summary --group-by <col> audits per-column file."""
    output_dir = tmp_path / "eval_output"
    output_dir.mkdir(parents=True)

    # Write valid per-column grouped CSV
    by_board = output_dir / "group_summary_by_board.csv"
    by_board.write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nboard,chinext,1,30\n",
        encoding="utf-8",
    )
    by_sector = output_dir / "group_summary_by_sector.csv"
    by_sector.write_text(
        "group_by,group_value,horizon,event_count\nsector,Tech,1,40\n",
        encoding="utf-8",
    )

    manifest_path = output_dir / "report_manifest.json"
    manifest_payload = {
        "schema_version": 1,
        "kind": "evaluation_report_manifest",
        "files": [
            {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
             "filename": "group_summary_by_board.csv", "role": "evaluation_group_summary",
             "group_by": "board"},
            {"key": "group_summary_by_sector", "path": "group_summary_by_sector.csv",
             "filename": "group_summary_by_sector.csv", "role": "evaluation_group_summary",
             "group_by": "sector"},
        ],
    }
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    # report-audit --group-by board --require-match exits 0 (all matched files valid)
    exit_code = main([
        "report-audit", str(manifest_path),
        "--role", "evaluation_group_summary",
        "--group-by", "board",
        "--require-match",
    ])
    assert exit_code == 0

    # report-audit --json --group-by board only audits the board file
    capsys.readouterr()  # consume previous output
    exit_code2 = main([
        "report-audit", str(manifest_path),
        "--role", "evaluation_group_summary",
        "--group-by", "board",
        "--json",
    ])
    assert exit_code2 == 0
    audit_payload = json.loads(capsys.readouterr().out.strip())
    assert audit_payload["matched_files"] == 1
    assert audit_payload["validation_issues"] == 0
    assert audit_payload["status"] == "ok"


def test_cli_report_audit_eval_group_by_missing_file(capsys, tmp_path):
    """report-audit on a missing per-column grouped file reports the issue."""
    output_dir = tmp_path / "eval_output"
    output_dir.mkdir(parents=True)

    manifest_path = output_dir / "report_manifest.json"
    manifest_payload = {
        "schema_version": 1,
        "kind": "evaluation_report_manifest",
        "files": [
            {"key": "group_summary_by_board", "path": "group_summary_by_board.csv",
             "filename": "group_summary_by_board.csv", "role": "evaluation_group_summary",
             "group_by": "board"},
        ],
    }
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    # File not written

    exit_code = main([
        "report-audit", str(manifest_path),
        "--role", "evaluation_group_summary",
        "--group-by", "board",
        "--require-match",
    ])
    assert exit_code == 2

    capsys.readouterr()  # consume previous output
    exit_code2 = main([
        "report-audit", str(manifest_path),
        "--role", "evaluation_group_summary",
        "--group-by", "board",
        "--json",
    ])
    assert exit_code2 == 2
    audit_payload = json.loads(capsys.readouterr().out.strip())
    assert audit_payload["status"] == "failed"
    assert audit_payload["missing_files"] == 1


def test_cli_report_audit_group_by_mismatch(capsys, tmp_path):
    """report-audit catches group_by mismatch when CSV content disagrees with manifest."""
    output_dir = tmp_path / "eval_output"
    output_dir.mkdir(parents=True)

    # CSV has 'sector' rows but manifest claims group_by=board
    (output_dir / "group_summary_by_board.csv").write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nsector,Tech,1,40\n",
        encoding="utf-8",
    )
    manifest_path = output_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
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

    # report-audit exits 2 on mismatch
    exit_code = main([
        "report-audit", str(manifest_path),
        "--role", "evaluation_group_summary",
        "--group-by", "board",
        "--require-match",
    ])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "group_by_mismatch" in captured.err
    assert "sector" in captured.err


def test_cli_report_audit_group_by_mismatch_json(capsys, tmp_path):
    """report-audit --json surfaces group_by_mismatch with correct issue payload."""
    output_dir = tmp_path / "eval_output"
    output_dir.mkdir(parents=True)

    (output_dir / "group_summary_by_board.csv").write_text(
        "group_by,group_value,horizon,event_count\nboard,main,1,50\nsector,Tech,1,40\n",
        encoding="utf-8",
    )
    manifest_path = output_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
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

    exit_code = main([
        "report-audit", str(manifest_path),
        "--role", "evaluation_group_summary",
        "--group-by", "board",
        "--json",
    ])
    assert exit_code == 2
    audit_payload = json.loads(capsys.readouterr().out.strip())
    assert audit_payload["status"] == "failed"
    assert audit_payload["validation_issues"] == 1
    issue = audit_payload["issues"][0]
    assert issue["code"] == "group_by_mismatch"
    assert issue["key"] == "group_summary_by_board"
    assert "board" in issue["message"]
    assert "sector" in issue["message"]


def test_cli_report_audit_batch_header_mismatch(capsys, tmp_path):
    """report-audit catches group_by_header_mismatch when batch CSV header disagrees with manifest."""
    output_dir = tmp_path / "batch_output"
    output_dir.mkdir(parents=True)

    # CSV has 'sector' column but manifest claims group_by=board
    (output_dir / "group_summary_by_board.csv").write_text(
        "symbol_count,sector\n10,Technology\n",
        encoding="utf-8",
    )
    manifest_path = output_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
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

    exit_code = main([
        "report-audit", str(manifest_path),
        "--role", "group_summary",
        "--group-by", "board",
        "--require-match",
    ])
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "group_by_header_mismatch" in captured.err
    assert "board" in captured.err
    assert "sector" in captured.err


def test_cli_report_audit_batch_header_mismatch_json(capsys, tmp_path):
    """report-audit --json surfaces group_by_header_mismatch with correct issue payload."""
    output_dir = tmp_path / "batch_output"
    output_dir.mkdir(parents=True)

    (output_dir / "group_summary_by_board.csv").write_text(
        "symbol_count,sector\n10,Technology\n",
        encoding="utf-8",
    )
    manifest_path = output_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
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

    exit_code = main([
        "report-audit", str(manifest_path),
        "--role", "group_summary",
        "--group-by", "board",
        "--json",
    ])
    assert exit_code == 2
    audit_payload = json.loads(capsys.readouterr().out.strip())
    assert audit_payload["status"] == "failed"
    assert audit_payload["validation_issues"] == 1
    issue = audit_payload["issues"][0]
    assert issue["code"] == "group_by_header_mismatch"
    assert issue["key"] == "group_summary_by_board"
    assert "board" in issue["message"]
    assert "sector" in issue["message"]


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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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


def test_cli_eval_smoke_with_benchmark_args_loads_and_merges_benchmark_bars(capsys, monkeypatch):
    """eval-smoke --benchmark-table --benchmark-code should load and merge benchmark bars."""
    benchmark_loaded: list[dict] = []

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "close": [10.5],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "rsi_2": [3.0],
                }
            )

        def load_benchmark_bars(self, table_name, ts_codes, start, end, fields=None, limit=None):
            benchmark_loaded.append(
                {
                    "table_name": table_name,
                    "ts_codes": ts_codes,
                    "fields": fields,
                }
            )
            return pd.DataFrame(
                {
                    "ts_code": [ts_codes[0]],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "close": [3200.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "eval-smoke",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-05",
            "--logical-name",
            "rsi_2",
            "--target",
            "factors.stock_daily_momentum_close.rsi_2",
            "--signal",
            "rsi_2 < 10",
            "--benchmark-table",
            "public.index_daily",
            "--benchmark-code",
            "000300.SH",
            "--benchmark-value-column",
            "close",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert len(benchmark_loaded) == 1
    assert benchmark_loaded[0]["table_name"] == "public.index_daily"
    assert benchmark_loaded[0]["ts_codes"] == ["000300.SH"]
    assert benchmark_loaded[0]["fields"] == ["close"]
    # benchmark columns should be in frame (printed as research_rows >= 1)
    assert "research_rows=1" in captured.out


def test_cli_eval_smoke_benchmark_args_optional_noop_when_omitted(capsys, monkeypatch):
    """eval-smoke without benchmark args should not load benchmark bars."""
    benchmark_called = []

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "close": [10.5],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05"]),
                    "rsi_2": [3.0],
                }
            )

        def load_benchmark_bars(self, table_name, ts_codes, start, end, fields=None, limit=None):
            benchmark_called.append(1)
            return pd.DataFrame()

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "eval-smoke",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
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
    assert exit_code == 0
    assert len(benchmark_called) == 0
    assert "research_rows=1" in captured.out


def test_cli_eval_config_with_benchmark_args_threads_to_assembler(capsys, monkeypatch, tmp_path):
    """eval-config --benchmark-table --benchmark-code should thread benchmark params."""
    assembler_calls: list[dict] = []

    # Write a minimal strategy YAML so the test does not depend on file-system files.
    strategy_yaml = tmp_path / "strategy.yaml"
    strategy_yaml.write_text(
        "experiment:\n"
        "  name: test_bench\n"
        "  market_profile: ashare_daily_default\n"
        "  frequency: daily\n"
        "  objective: screen_then_validate\n"
        "data:\n"
        "  market_table: public.stock_daily\n"
        "  factor_schema: factors\n"
        "  market_fields:\n"
        "    - close\n"
        "  factor_fields:\n"
        "    rsi_2: factors.stock_daily_momentum_close.rsi_2\n"
        "universe:\n"
        "  market: ashare\n"
        "signal:\n"
        "  type: expression\n"
        "  entry: close > 0\n"
        "execution:\n"
        "  signal_date: t\n"
        "  entry_execution: t_plus_1_open\n"
        "holding:\n"
        "  max_holding_days: 5\n"
        "  direction: long_only\n"
        "evaluation:\n"
        "  forward_return_horizons: [1, 3, 5]\n"
        "  quantiles: 5\n"
    )

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
                    "close": [10.5, 11.2],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ", "000001.SZ"],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "rsi_2": [1.0, 2.0],
                }
            )

        def load_benchmark_bars(self, table_name, ts_codes, start, end, fields=None, limit=None):
            assembler_calls.append(
                {
                    "table_name": table_name,
                    "ts_codes": ts_codes,
                    "fields": fields,
                }
            )
            return pd.DataFrame(
                {
                    "ts_code": [ts_codes[0], ts_codes[0]],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "close": [3200.0, 3210.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)

    exit_code = main(
        [
            "eval-config",
            str(strategy_yaml),
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--benchmark-table",
            "public.index_daily",
            "--benchmark-code",
            "000300.SH",
            "--benchmark-value-column",
            "close",
        ]
    )

    captured = capsys.readouterr()
    if exit_code != 0:
        import sys as _sys

        _sys.stderr.write(f"STDERR: {captured.err}\n")
        _sys.stderr.write(f"STDOUT: {captured.out}\n")
    assert exit_code == 0
    assert len(assembler_calls) == 1
    assert assembler_calls[0]["table_name"] == "public.index_daily"
    assert assembler_calls[0]["ts_codes"] == ["000300.SH"]
    assert assembler_calls[0]["fields"] == ["close"]
    assert "research_rows=2" in captured.out


def test_cli_eval_smoke_rejects_benchmark_table_without_code(capsys, monkeypatch):
    """eval-smoke --benchmark-table without --benchmark-code should exit 2."""
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

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

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    exit_code = main(
        [
            "eval-smoke",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--logical-name",
            "rsi_2",
            "--target",
            "factors.table.rsi_2",
            "--signal",
            "rsi_2 < 10",
            "--benchmark-table",
            "public.index_daily",
        ]
    )
    assert exit_code == 2


def test_cli_eval_smoke_rejects_benchmark_code_without_table(capsys, monkeypatch):
    """eval-smoke --benchmark-code without --benchmark-table should exit 2."""
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

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

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    exit_code = main(
        [
            "eval-smoke",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--logical-name",
            "rsi_2",
            "--target",
            "factors.table.rsi_2",
            "--signal",
            "rsi_2 < 10",
            "--benchmark-code",
            "000300.SH",
        ]
    )
    assert exit_code == 2


def test_cli_eval_config_rejects_benchmark_table_without_code(capsys, monkeypatch, tmp_path):
    """eval-config --benchmark-table without --benchmark-code should exit 2."""
    strategy_yaml = tmp_path / "strategy.yaml"
    strategy_yaml.write_text(
        "experiment:\n"
        "  name: test_bench\n"
        "  market_profile: ashare_daily_default\n"
        "  frequency: daily\n"
        "  objective: screen_then_validate\n"
        "data:\n"
        "  market_table: public.stock_daily\n"
        "  factor_schema: factors\n"
        "  market_fields:\n"
        "    - close\n"
        "  factor_fields:\n"
        "    rsi_2: factors.stock_daily_momentum_close.rsi_2\n"
        "universe:\n"
        "  market: ashare\n"
        "signal:\n"
        "  type: expression\n"
        "  entry: close > 0\n"
        "execution:\n"
        "  signal_date: t\n"
        "  entry_execution: t_plus_1_open\n"
        "holding:\n"
        "  max_holding_days: 5\n"
        "  direction: long_only\n"
        "evaluation:\n"
        "  forward_return_horizons: [1]\n"
        "  quantiles: 5\n"
    )

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "open": [10.0] * 2,
                    "high": [10.0] * 2,
                    "low": [10.0] * 2,
                    "close": [10.0, 11.0],
                    "pre_close": [10.0] * 2,
                    "vol": [1.0] * 2,
                    "amount": [100.0] * 2,
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    exit_code = main(
        [
            "eval-config",
            str(strategy_yaml),
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--benchmark-table",
            "public.index_daily",
        ]
    )
    assert exit_code == 2


def test_cli_eval_config_rejects_benchmark_code_without_table(capsys, monkeypatch, tmp_path):
    """eval-config --benchmark-code without --benchmark-table should exit 2."""
    strategy_yaml = tmp_path / "strategy.yaml"
    strategy_yaml.write_text(
        "experiment:\n"
        "  name: test_bench\n"
        "  market_profile: ashare_daily_default\n"
        "  frequency: daily\n"
        "  objective: screen_then_validate\n"
        "data:\n"
        "  market_table: public.stock_daily\n"
        "  factor_schema: factors\n"
        "  market_fields:\n"
        "    - close\n"
        "  factor_fields:\n"
        "    rsi_2: factors.stock_daily_momentum_close.rsi_2\n"
        "universe:\n"
        "  market: ashare\n"
        "signal:\n"
        "  type: expression\n"
        "  entry: close > 0\n"
        "execution:\n"
        "  signal_date: t\n"
        "  entry_execution: t_plus_1_open\n"
        "holding:\n"
        "  max_holding_days: 5\n"
        "  direction: long_only\n"
        "evaluation:\n"
        "  forward_return_horizons: [1]\n"
        "  quantiles: 5\n"
    )

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "open": [10.0] * 2,
                    "high": [10.0] * 2,
                    "low": [10.0] * 2,
                    "close": [10.0, 11.0],
                    "pre_close": [10.0] * 2,
                    "vol": [1.0] * 2,
                    "amount": [100.0] * 2,
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    exit_code = main(
        [
            "eval-config",
            str(strategy_yaml),
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--benchmark-code",
            "000300.SH",
        ]
    )
    assert exit_code == 2


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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_with_risk.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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


def test_cli_backtest_batch_prints_benchmark_relative_summary(capsys, monkeypatch):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_benchmark_bars(self, table_name, ts_codes, start, end, fields, limit=None):
            assert table_name == "public.index_daily"
            assert ts_codes == ["000300.SH"]
            assert fields == ["close"]
            return pd.DataFrame(
                {
                    "ts_code": ["000300.SH", "000300.SH", "000300.SH"],
                    "trade_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                    "close": [100.0, 105.0, 110.25],
                }
            )

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            return pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"])})

    class FakeBatchEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            r1 = SingleSymbolBacktestResult(
                orders=pd.DataFrame(),
                trades=pd.DataFrame(),
                equity_curve=pd.DataFrame(
                    {
                        "trade_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                        "cash": [5000.0, 5000.0, 5000.0],
                        "position_quantity": [0, 0, 0],
                        "market_value": [5000.0, 5500.0, 6050.0],
                        "total_equity": [10000.0, 10500.0, 11050.0],
                    }
                ),
                failed_orders=pd.DataFrame(),
                summary={"initial_cash": 10000.0, "final_equity": 11050.0, "total_return": 0.105, "trade_count": 1, "win_rate": 1.0, "total_cost": 10.0, "buy_hold_return": 0.05, "excess_return_vs_buy_hold": 0.055},
            )
            return BatchBacktestResult(
                symbols=["000001.SZ"],
                results={"000001.SZ": r1},
                summary=pd.DataFrame(
                    {
                        "symbol": ["000001.SZ"],
                        "trade_count": [1],
                        "board": ["main_board"],
                        "total_return": [0.105],
                        "win_rate": [1.0],
                        "total_cost": [10.0],
                        "failed_order_count": [0],
                        "buy_hold_return": [0.05],
                        "excess_return_vs_buy_hold": [0.055],
                    }
                ),
                summary_metrics={"symbol_count": 1, "mean_total_return": 0.105, "total_trades": 1},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "BatchBacktestEngine", FakeBatchEngine)

    exit_code = main(
        [
            "backtest-batch",
            "strategies/low_level/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--codes",
            "000001.SZ",
            "--benchmark-table",
            "public.index_daily",
            "--benchmark-code",
            "000300.SH",
            "--benchmark-value-column",
            "close",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "benchmark_code=000300.SH" in captured.out
    assert "benchmark_aligned_period_count=3" in captured.out
    assert "benchmark_benchmark_total_return=0.1025" in captured.out
    assert "benchmark_excess_total_return=" in captured.out


def test_cli_backtest_batch_metadata_as_of_threaded_to_assembler(capsys, monkeypatch):
    """backtest-batch --metadata-as-of is passed to assembler.build()."""
    captured_kwargs = {}

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            captured_kwargs.update(kwargs)
            return pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"])})

    class FakeBatchEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return BatchBacktestResult(
                symbols=["000001.SZ"],
                results={},
                summary=pd.DataFrame({"symbol": ["000001.SZ"], "trade_count": [1], "board": ["main_board"], "total_return": [0.05], "win_rate": [1.0], "total_cost": [10.0], "failed_order_count": [0]}),
                summary_metrics={"symbol_count": 1, "mean_total_return": 0.05, "total_trades": 1},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "BatchBacktestEngine", FakeBatchEngine)

    exit_code = main(
        [
            "backtest-batch",
            "strategies/low_level/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--codes",
            "000001.SZ",
            "--metadata-as-of",
            "2025-12-31",
        ]
    )

    assert exit_code == 0
    assert captured_kwargs.get("metadata_as_of") == date(2025, 12, 31)


def test_cli_backtest_batch_metadata_as_of_none_when_omitted(capsys, monkeypatch):
    """backtest-batch without --metadata-as-of passes None to assembler.build()."""
    captured_kwargs = {}

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            captured_kwargs.update(kwargs)
            return pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"])})

    class FakeBatchEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return BatchBacktestResult(
                symbols=["000001.SZ"],
                results={},
                summary=pd.DataFrame({"symbol": ["000001.SZ"], "trade_count": [1], "board": ["main_board"], "total_return": [0.05], "win_rate": [1.0], "total_cost": [10.0], "failed_order_count": [0]}),
                summary_metrics={"symbol_count": 1, "mean_total_return": 0.05, "total_trades": 1},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "BatchBacktestEngine", FakeBatchEngine)

    exit_code = main(
        [
            "backtest-batch",
            "strategies/low_level/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--codes",
            "000001.SZ",
        ]
    )

    assert exit_code == 0
    assert captured_kwargs.get("metadata_as_of") is None


def test_cli_backtest_shared_metadata_as_of_threaded_to_assembler(capsys, monkeypatch):
    """backtest-shared --metadata-as-of is passed to assembler.build()."""
    captured_kwargs = {}

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            captured_kwargs.update(kwargs)
            return pd.DataFrame({
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                "ts_code": ["000001.SZ", "000002.SZ"],
                "open": [10.0, 20.0],
                "close": [10.1, 20.2],
            })

    class FakeSharedEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return SharedCashBacktestResult(
                orders=pd.DataFrame(),
                trades=pd.DataFrame(),
                failed_orders=pd.DataFrame(),
                equity_curve=pd.DataFrame({"trade_date": pd.date_range("2026-01-30", periods=21, freq="B"), "total_equity": [100.0] * 21}),
                summary={"initial_cash": 100.0, "final_equity": 105.0, "total_return": 0.05},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "SharedCashBacktestEngine", FakeSharedEngine)

    exit_code = main(
        [
            "backtest-shared",
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "--metadata-as-of",
            "2025-12-31",
        ]
    )

    assert exit_code == 0
    assert captured_kwargs.get("metadata_as_of") == date(2025, 12, 31)


def test_cli_backtest_shared_metadata_as_of_none_when_omitted(capsys, monkeypatch):
    """backtest-shared without --metadata-as-of passes None to assembler.build()."""
    captured_kwargs = {}

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            captured_kwargs.update(kwargs)
            return pd.DataFrame({
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                "ts_code": ["000001.SZ", "000002.SZ"],
                "open": [10.0, 20.0],
                "close": [10.1, 20.2],
            })

    class FakeSharedEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return SharedCashBacktestResult(
                orders=pd.DataFrame(),
                trades=pd.DataFrame(),
                failed_orders=pd.DataFrame(),
                equity_curve=pd.DataFrame({"trade_date": pd.date_range("2026-01-30", periods=21, freq="B"), "total_equity": [100.0] * 21}),
                summary={"initial_cash": 100.0, "final_equity": 105.0, "total_return": 0.05},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "SharedCashBacktestEngine", FakeSharedEngine)

    exit_code = main(
        [
            "backtest-shared",
            "strategies/low_level/rsi2_reversal_research.yaml",
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
        ]
    )

    assert exit_code == 0
    assert captured_kwargs.get("metadata_as_of") is None


def test_cli_backtest_single_metadata_as_of_threaded_to_assembler(capsys, monkeypatch):
    """backtest-single --metadata-as-of is passed to assembler.build()."""
    captured_kwargs = {}

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            captured_kwargs.update(kwargs)
            return pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"]), "ts_code": ["000001.SZ"], "open": [10.0], "close": [10.1]})

    class FakeSingleEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return SingleSymbolBacktestResult(
                orders=pd.DataFrame(),
                trades=pd.DataFrame(),
                equity_curve=pd.DataFrame(),
                failed_orders=pd.DataFrame(),
                summary={"initial_cash": 100000.0, "final_equity": 101000.0, "total_return": 0.01},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "SingleSymbolBacktestEngine", FakeSingleEngine)

    exit_code = main(
        [
            "backtest-single",
            "strategies/low_level/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--symbol",
            "000001.SZ",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
            "--metadata-as-of",
            "2025-12-31",
        ]
    )

    assert exit_code == 0
    assert captured_kwargs.get("metadata_as_of") == date(2025, 12, 31)


def test_cli_backtest_single_metadata_as_of_none_when_omitted(capsys, monkeypatch):
    """backtest-single without --metadata-as-of passes None to assembler.build()."""
    captured_kwargs = {}

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

    class FakeAssembler:
        def __init__(self, store):
            self.store = store

        def build(self, **kwargs):
            captured_kwargs.update(kwargs)
            return pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-01"]), "ts_code": ["000001.SZ"], "open": [10.0], "close": [10.1]})

    class FakeSingleEngine:
        def __init__(self, market_profile):
            self.market_profile = market_profile

        def run(self, frame, request):
            return SingleSymbolBacktestResult(
                orders=pd.DataFrame(),
                trades=pd.DataFrame(),
                equity_curve=pd.DataFrame(),
                failed_orders=pd.DataFrame(),
                summary={"initial_cash": 100000.0, "final_equity": 101000.0, "total_return": 0.01},
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    monkeypatch.setattr(cli_module, "ResearchFrameAssembler", FakeAssembler)
    monkeypatch.setattr(cli_module, "SingleSymbolBacktestEngine", FakeSingleEngine)

    exit_code = main(
        [
            "backtest-single",
            "strategies/low_level/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--symbol",
            "000001.SZ",
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-03",
        ]
    )

    assert exit_code == 0
    assert captured_kwargs.get("metadata_as_of") is None


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
    spec = StrategySpec.from_yaml("strategies/low_level/rsi2_reversal_with_risk.yaml")
    args = Namespace(stop_loss_pct=None, take_profit_pct=None, trailing_stop_pct=None)

    controls = resolve_risk_controls(args, spec)

    assert controls == {
        "stop_loss_pct": 0.08,
        "take_profit_pct": 0.12,
        "trailing_stop_pct": 0.10,
    }


def test_resolve_risk_controls_prefers_cli_values_over_yaml():
    spec = StrategySpec.from_yaml("strategies/low_level/rsi2_reversal_with_risk.yaml")
    args = Namespace(stop_loss_pct=0.05, take_profit_pct=None, trailing_stop_pct=0.07)

    controls = resolve_risk_controls(args, spec)

    assert controls == {
        "stop_loss_pct": 0.05,
        "take_profit_pct": 0.12,
        "trailing_stop_pct": 0.07,
    }


def test_resolve_weight_controls_uses_yaml_when_cli_is_absent():
    spec = StrategySpec.from_yaml("strategies/low_level/rsi2_reversal_with_risk_and_weight.yaml")
    args = Namespace(weight_model=None, score_column=None, volatility_column=None)

    controls = resolve_weight_controls(args, spec)

    assert controls == {
        "weight_model": "score_weight",
        "score_column": "rsi_2",
        "volatility_column": None,
    }


def test_resolve_weight_controls_prefers_cli_values_over_yaml():
    spec = StrategySpec.from_yaml("strategies/low_level/rsi2_reversal_with_risk_and_weight.yaml")
    args = Namespace(weight_model="inverse_volatility", score_column=None, volatility_column="vol_20")

    controls = resolve_weight_controls(args, spec)

    assert controls == {
        "weight_model": "inverse_volatility",
        "score_column": "rsi_2",
        "volatility_column": "vol_20",
    }


def test_resolve_weight_controls_defaults_to_equal_weight_when_unspecified():
    spec = StrategySpec.from_yaml("strategies/low_level/rsi2_reversal_research.yaml")
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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


def test_cli_eval_config_benchmark_fields_in_run_manifest(capsys, monkeypatch, tmp_path):
    """eval-config --benchmark-table --benchmark-code write benchmark fields to run_manifest.json."""
    strategy_yaml = tmp_path / "strategy.yaml"
    strategy_yaml.write_text(
        "experiment:\n"
        "  name: test_bench\n"
        "  market_profile: ashare_daily_default\n"
        "  frequency: daily\n"
        "  objective: screen_then_validate\n"
        "data:\n"
        "  market_table: public.stock_daily\n"
        "  factor_schema: factors\n"
        "  market_fields:\n"
        "    - close\n"
        "  factor_fields:\n"
        "    rsi_2: factors.stock_daily_momentum_close.rsi_2\n"
        "universe:\n"
        "  market: ashare\n"
        "signal:\n"
        "  type: expression\n"
        "  entry: close > 0\n"
        "execution:\n"
        "  signal_date: t\n"
        "  entry_execution: t_plus_1_open\n"
        "holding:\n"
        "  max_holding_days: 5\n"
        "  direction: long_only\n"
        "evaluation:\n"
        "  forward_return_horizons: [1]\n"
        "  quantiles: 5\n"
    )

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "open": [10.0] * 2,
                    "high": [10.0] * 2,
                    "low": [10.0] * 2,
                    "close": [10.0, 11.0],
                    "pre_close": [10.0] * 2,
                    "vol": [1.0] * 2,
                    "amount": [100.0] * 2,
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "rsi_2": [8.0, 9.0],
                }
            )

        def load_benchmark_bars(self, table_name, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": [ts_codes[0], ts_codes[0]],
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "close": [100.0, 101.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_dir = tmp_path / "eval_output"

    exit_code = main(
        [
            "eval-config",
            str(strategy_yaml),
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--output-dir",
            str(output_dir),
            "--benchmark-table",
            "public.index_daily",
            "--benchmark-code",
            "000300.SH",
            "--benchmark-value-column",
            "close",
        ]
    )

    assert exit_code == 0
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["benchmark_table"] == "public.index_daily"
    assert run_manifest["benchmark_code"] == "000300.SH"
    assert run_manifest["benchmark_value_column"] == "close"


def test_cli_eval_config_benchmark_fields_null_when_omitted(capsys, monkeypatch, tmp_path):
    """eval-config without benchmark args writes null benchmark fields to run_manifest.json."""
    strategy_yaml = tmp_path / "strategy.yaml"
    strategy_yaml.write_text(
        "experiment:\n"
        "  name: test_bench\n"
        "  market_profile: ashare_daily_default\n"
        "  frequency: daily\n"
        "  objective: screen_then_validate\n"
        "data:\n"
        "  market_table: public.stock_daily\n"
        "  factor_schema: factors\n"
        "  market_fields:\n"
        "    - close\n"
        "  factor_fields:\n"
        "    rsi_2: factors.stock_daily_momentum_close.rsi_2\n"
        "universe:\n"
        "  market: ashare\n"
        "signal:\n"
        "  type: expression\n"
        "  entry: close > 0\n"
        "execution:\n"
        "  signal_date: t\n"
        "  entry_execution: t_plus_1_open\n"
        "holding:\n"
        "  max_holding_days: 5\n"
        "  direction: long_only\n"
        "evaluation:\n"
        "  forward_return_horizons: [1]\n"
        "  quantiles: 5\n"
    )

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "close": [10.0, 11.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "rsi_2": [8.0, 9.0],
                }
            )

    monkeypatch.setattr(cli_module, "PostgresDataStore", FakeStore)
    output_dir = tmp_path / "eval_output"

    exit_code = main(
        [
            "eval-config",
            str(strategy_yaml),
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    run_manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["benchmark_table"] is None
    assert run_manifest["benchmark_code"] is None
    assert run_manifest["benchmark_value_column"] == "close"


def test_cli_eval_config_metadata_as_of_threaded_to_assembler(capsys, monkeypatch, tmp_path):
    """eval-config --metadata-as-of is passed to the assembler's load_security_metadata."""
    strategy_yaml = tmp_path / "strategy.yaml"
    strategy_yaml.write_text(
        "experiment:\n"
        "  name: test_asof\n"
        "  market_profile: ashare_daily_default\n"
        "  frequency: daily\n"
        "  objective: screen_then_validate\n"
        "data:\n"
        "  market_table: public.stock_daily\n"
        "  factor_schema: factors\n"
        "  market_fields:\n"
        "    - close\n"
        "  factor_fields:\n"
        "    rsi_2: factors.stock_daily_momentum_close.rsi_2\n"
        "universe:\n"
        "  market: ashare\n"
        "signal:\n"
        "  type: expression\n"
        "  entry: close > 0\n"
        "execution:\n"
        "  signal_date: t\n"
        "  entry_execution: t_plus_1_open\n"
        "holding:\n"
        "  max_holding_days: 5\n"
        "  direction: long_only\n"
        "evaluation:\n"
        "  forward_return_horizons: [1]\n"
        "  quantiles: 5\n"
    )

    captured_as_of = []

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "close": [10.0, 11.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "rsi_2": [8.0, 9.0],
                }
            )

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
            captured_as_of.append(as_of)
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
    output_dir = tmp_path / "eval_output"

    exit_code = main(
        [
            "eval-config",
            str(strategy_yaml),
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--output-dir",
            str(output_dir),
            "--group-by",
            "board",
            "--metadata-as-of",
            "2025-12-31",
        ]
    )

    assert exit_code == 0
    assert captured_as_of == [date(2025, 12, 31)]


def test_cli_eval_config_metadata_as_of_none_when_omitted(capsys, monkeypatch, tmp_path):
    """eval-config without --metadata-as-of passes None to load_security_metadata."""
    strategy_yaml = tmp_path / "strategy.yaml"
    strategy_yaml.write_text(
        "experiment:\n"
        "  name: test_asof\n"
        "  market_profile: ashare_daily_default\n"
        "  frequency: daily\n"
        "  objective: screen_then_validate\n"
        "data:\n"
        "  market_table: public.stock_daily\n"
        "  factor_schema: factors\n"
        "  market_fields:\n"
        "    - close\n"
        "  factor_fields:\n"
        "    rsi_2: factors.stock_daily_momentum_close.rsi_2\n"
        "universe:\n"
        "  market: ashare\n"
        "signal:\n"
        "  type: expression\n"
        "  entry: close > 0\n"
        "execution:\n"
        "  signal_date: t\n"
        "  entry_execution: t_plus_1_open\n"
        "holding:\n"
        "  max_holding_days: 5\n"
        "  direction: long_only\n"
        "evaluation:\n"
        "  forward_return_horizons: [1]\n"
        "  quantiles: 5\n"
    )

    captured_as_of = []

    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def load_daily_bars(self, ts_codes, start, end, fields=None, limit=None):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "close": [10.0, 11.0],
                }
            )

        def load_factor_history(self, ts_codes, field_requests, start, end):
            return pd.DataFrame(
                {
                    "ts_code": ["000001.SZ"] * 2,
                    "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
                    "rsi_2": [8.0, 9.0],
                }
            )

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
            captured_as_of.append(as_of)
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
    output_dir = tmp_path / "eval_output"

    exit_code = main(
        [
            "eval-config",
            str(strategy_yaml),
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-06",
            "--codes",
            "000001.SZ",
            "--output-dir",
            str(output_dir),
            "--group-by",
            "board",
        ]
    )

    assert exit_code == 0
    assert captured_as_of == [None]


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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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


def test_cli_report_audit_validate_contents_reports_malformed_run_manifest(capsys, tmp_path):
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"kind": "portfolio_backtest_run_manifest"}),
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

    exit_code = main(["report-audit", str(manifest_path), "--role", "run_manifest", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["status"] == "failed"
    assert payload["validation_issues"] > 0
    issue_codes = {issue["code"] for issue in payload["issues"]}
    assert "missing_run_manifest_field" in issue_codes


def test_cli_report_audit_validate_contents_accepts_valid_run_manifest(capsys, tmp_path):
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

    exit_code = main(["report-audit", str(manifest_path), "--role", "run_manifest", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["status"] == "ok"
    assert payload["validation_issues"] == 0


# --- window_size CLI filtering ---


def test_cli_report_files_window_size_filter(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path), "--window-size", "20"])

    captured = capsys.readouterr()
    assert exit_code == 0
    lines = captured.out.strip().split("\n")
    assert len(lines) == 1
    assert "rolling_summary_20" in lines[0]


def test_cli_report_audit_window_size_filter(capsys, tmp_path):
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

    exit_code = main(["report-audit", str(manifest_path), "--window-size", "20"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "matched_files=1" in captured.out


def test_cli_report_files_json_includes_window_size(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    entry = payload["files"][0]
    assert entry["window_size"] == 20


def test_cli_report_files_json_omits_window_size_when_absent(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    entry = payload["files"][0]
    assert "window_size" not in entry


def test_cli_report_files_json_includes_window_size_null(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    entry = payload["files"][0]
    assert "window_size" not in entry


# --- window_size CLI malformed-manifest regression ---


def test_cli_report_files_reports_string_window_size(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "must be an integer or null" in captured.err
    assert "window_size" in captured.err


def test_cli_report_files_reports_boolean_window_size(capsys, tmp_path):
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

    exit_code = main(["report-files", str(manifest_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "must be an integer or null" in captured.err
    assert "window_size" in captured.err


def test_cli_report_audit_reports_string_window_size(capsys, tmp_path):
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

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "must be an integer or null" in captured.err
    assert "window_size" in captured.err


def test_cli_report_audit_reports_boolean_window_size(capsys, tmp_path):
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

    exit_code = main(["report-audit", str(manifest_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "must be an integer or null" in captured.err
    assert "window_size" in captured.err


# --- window_size --json --require-match parity ---


def test_cli_report_files_window_size_json_require_match_matched_entry(capsys, tmp_path):
    (tmp_path / "rolling_summary_20.csv").write_text(
        "window_size,end_date,symbol_count\n20,2026-01-05,50\n",
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

    exit_code = main(
        ["report-files", str(manifest_path), "--window-size", "20", "--json", "--require-match"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert payload["files"][0]["window_size"] == 20
    assert payload["files"][0]["key"] == "rolling_summary_20"


def test_cli_report_files_window_size_json_require_match_zero_matches(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_60",
                        "path": "rolling_summary_60.csv",
                        "filename": "rolling_summary_60.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        ["report-files", str(manifest_path), "--window-size", "20", "--json", "--require-match"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no manifest entries matched filters" in captured.err
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 0
    assert payload["files"] == []


def test_cli_report_audit_window_size_json_require_match_matched_entry(capsys, tmp_path):
    (tmp_path / "rolling_summary_20.csv").write_text(
        "window_size,end_date,symbol_count\n20,2026-01-05,50\n",
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

    exit_code = main(
        ["report-audit", str(manifest_path), "--window-size", "20", "--json", "--require-match"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert payload["status"] == "ok"
    assert payload["validation_issues"] == 0


def test_cli_report_audit_window_size_json_require_match_zero_matches(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_60",
                        "path": "rolling_summary_60.csv",
                        "filename": "rolling_summary_60.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        ["report-audit", str(manifest_path), "--window-size", "20", "--json", "--require-match"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no manifest entries matched filters" in captured.err
    payload = json.loads(captured.out)
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


# --- window_size + group_by combined selector parity ---


def test_cli_report_files_window_size_group_by_json_require_match_matched_entry(capsys, tmp_path):
    (tmp_path / "rolling_summary_20_by_board.csv").write_text(
        "window_size,end_date,symbol_count,board\n20,2026-01-05,50,main\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_20_by_board",
                        "path": "rolling_summary_20_by_board.csv",
                        "filename": "rolling_summary_20_by_board.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                        "group_by": "board",
                    },
                    {
                        "key": "rolling_summary_60_by_board",
                        "path": "rolling_summary_60_by_board.csv",
                        "filename": "rolling_summary_60_by_board.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                        "group_by": "board",
                    },
                    {
                        "key": "rolling_summary_20_by_sector",
                        "path": "rolling_summary_20_by_sector.csv",
                        "filename": "rolling_summary_20_by_sector.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                        "group_by": "sector",
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
            "--window-size", "20",
            "--group-by", "board",
            "--json",
            "--require-match",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    entry = payload["files"][0]
    assert entry["window_size"] == 20
    assert entry["group_by"] == "board"
    assert entry["key"] == "rolling_summary_20_by_board"


def test_cli_report_files_window_size_group_by_json_require_match_zero_matches(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_20_by_sector",
                        "path": "rolling_summary_20_by_sector.csv",
                        "filename": "rolling_summary_20_by_sector.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                        "group_by": "sector",
                    },
                    {
                        "key": "rolling_summary_60_by_board",
                        "path": "rolling_summary_60_by_board.csv",
                        "filename": "rolling_summary_60_by_board.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                        "group_by": "board",
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
            "--window-size", "20",
            "--group-by", "board",
            "--json",
            "--require-match",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no manifest entries matched filters" in captured.err
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 0
    assert payload["files"] == []


def test_cli_report_audit_window_size_group_by_json_require_match_matched_entry(capsys, tmp_path):
    (tmp_path / "rolling_summary_20_by_board.csv").write_text(
        "window_size,end_date,symbol_count,board\n20,2026-01-05,50,main\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_20_by_board",
                        "path": "rolling_summary_20_by_board.csv",
                        "filename": "rolling_summary_20_by_board.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                        "group_by": "board",
                    },
                    {
                        "key": "rolling_summary_60_by_board",
                        "path": "rolling_summary_60_by_board.csv",
                        "filename": "rolling_summary_60_by_board.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                        "group_by": "board",
                    },
                    {
                        "key": "rolling_summary_20_by_sector",
                        "path": "rolling_summary_20_by_sector.csv",
                        "filename": "rolling_summary_20_by_sector.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                        "group_by": "sector",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "report-audit",
            str(manifest_path),
            "--window-size", "20",
            "--group-by", "board",
            "--json",
            "--require-match",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert payload["status"] == "ok"
    assert payload["validation_issues"] == 0


def test_cli_report_audit_window_size_group_by_json_require_match_zero_matches(capsys, tmp_path):
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "batch_backtest_report_manifest",
                "files": [
                    {
                        "key": "rolling_summary_20_by_sector",
                        "path": "rolling_summary_20_by_sector.csv",
                        "filename": "rolling_summary_20_by_sector.csv",
                        "role": "rolling_summary",
                        "window_size": 20,
                        "group_by": "sector",
                    },
                    {
                        "key": "rolling_summary_60_by_board",
                        "path": "rolling_summary_60_by_board.csv",
                        "filename": "rolling_summary_60_by_board.csv",
                        "role": "rolling_summary",
                        "window_size": 60,
                        "group_by": "board",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "report-audit",
            str(manifest_path),
            "--window-size", "20",
            "--group-by", "board",
            "--json",
            "--require-match",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no manifest entries matched filters" in captured.err
    payload = json.loads(captured.out)
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


# ---------------------------------------------------------------------------
# preflight --output-dir: missing-factor request emission
# ---------------------------------------------------------------------------


def test_cli_preflight_output_dir_emits_empty_when_no_missing_factors(capsys, monkeypatch, tmp_path):
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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
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
    out_dir = tmp_path / "mf_output"

    exit_code = main(
        [
            "preflight",
            "strategies/low_level/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-05",
            "--codes",
            "000001.SZ",
            "--output-dir",
            str(out_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "missing_factor_count=0" in captured.out
    assert "missing_factor_status=ok" in captured.out

    mf_path = out_dir / "missing_factor_requests.json"
    assert mf_path.exists()
    data = json.loads(mf_path.read_text(encoding="utf-8"))
    assert data == []


def test_cli_preflight_output_dir_emits_requests_when_table_missing(capsys, monkeypatch, tmp_path):
    class FakeStore:
        def __init__(self, settings):
            self.settings = settings

        def ping(self):
            return True

        def table_exists(self, table_name, *, engine=None):
            return False

        def get_table_columns(self, table_name, *, engine=None):
            return []

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
            return pd.DataFrame(columns=["ts_code", "trade_date"])

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
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
    out_dir = tmp_path / "mf_output"

    exit_code = main(
        [
            "preflight",
            "strategies/low_level/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-05",
            "--codes",
            "000001.SZ",
            "--output-dir",
            str(out_dir),
        ]
    )

    captured = capsys.readouterr()
    assert "missing_factor_status=pending" in captured.out
    assert "missing_factor_count=1" in captured.out
    assert "missing_factor=rsi_2" in captured.out

    mf_path = out_dir / "missing_factor_requests.json"
    assert mf_path.exists()
    data = json.loads(mf_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["alias"] == "rsi_2"
    assert data[0]["strategy_id"] == "rsi2_reversal_research_mvp"
    assert data[0]["expected_table"] == "factors.stock_daily_momentum_close"
    assert data[0]["expected_column"] == "rsi_2"
    assert data[0]["required"] is True
    assert data[0]["date_range"] == {"start": "2026-01-05", "end": "2026-01-05"}


def test_cli_preflight_no_output_dir_prints_status_but_no_file(capsys, monkeypatch):
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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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
    assert "missing_factor_count=0" in captured.out
    assert "missing_factor_status=ok" in captured.out


def test_cli_preflight_metadata_as_of_threaded(capsys, monkeypatch, tmp_path):
    """preflight --metadata-as-of passes the as-of date to load_security_metadata."""
    captured_as_of = []

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
                    "amount": [500.0],
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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
            captured_as_of.append(as_of)
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
            "strategies/low_level/rsi2_reversal_research.yaml",
            "--db-url",
            "postgresql+psycopg://user:pass@localhost/db",
            "--start",
            "2026-01-05",
            "--end",
            "2026-01-05",
            "--codes",
            "000001.SZ",
            "--metadata-as-of",
            "2025-12-31",
        ]
    )

    assert exit_code == 0
    assert captured_as_of == [date(2025, 12, 31)]


def test_cli_preflight_metadata_as_of_none_when_omitted(capsys, monkeypatch, tmp_path):
    """preflight without --metadata-as-of passes None to load_security_metadata."""
    captured_as_of = []

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
                    "amount": [500.0],
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

        def load_security_metadata(self, ts_codes=None, *, benchmark_code=None, as_of=None):
            captured_as_of.append(as_of)
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
            "strategies/low_level/rsi2_reversal_research.yaml",
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

    assert exit_code == 0
    assert captured_as_of == [None]


# ---------------------------------------------------------------------------
# compile command
# ---------------------------------------------------------------------------

RSI2_HIGH_LEVEL_YAML = """\
strategy:
  id: rsi2_oversold_reversal
  name: RSI2 Oversold Reversal
  family: mean_reversion
  direction: long_only
  version: "1.0.0"

factor_requirements:
  - alias: rsi_fast
    indicator: rsi
    source: close
    period: 2
    required: true
    reason: entry and exit threshold signal

rules:
  entry:
    all:
      - alias: rsi_fast
        operator: "<"
        value: 10
  exit:
    any:
      - alias: rsi_fast
        operator: ">"
        value: 70
  risk:
    stop_loss_pct: 0.08
    max_holding_days: 5

experiment:
  id: rsi2_smoke
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-02-01
  universe:
    include: all_a
    exclude_st: true
  execution:
    signal_date: t
    entry_execution: t_plus_1_open
    exit_execution: t_plus_1_open
    market_profile: ashare_daily_default
  capital:
    initial_cash: 1000000
  output:
    dir: outputs/rsi2_smoke/
"""


def test_cli_compile_rsi2_success(capsys, tmp_path):
    path = tmp_path / "rsi2.yaml"
    path.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    exit_code = main(["compile", str(path)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "compile_status=ok" in captured.out
    assert "strategy_id=rsi2_oversold_reversal" in captured.out
    assert "factor_target_count=1" in captured.out
    assert "factor_target_rsi_fast=factors.stock_daily_momentum_close.rsi_2" in captured.out
    assert "signal_expression=" in captured.out


def test_cli_compile_invalid_yaml_returns_2(capsys, tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("strategy:\n  id: 42\n", encoding="utf-8")
    exit_code = main(["compile", str(path)])
    assert exit_code == 2


def test_cli_compile_with_output_dir_writes_spec(capsys, tmp_path):
    path = tmp_path / "rsi2.yaml"
    path.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    out_dir = tmp_path / "compile_output"
    exit_code = main(["compile", str(path), "--output-dir", str(out_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "compiled_spec=" in captured.out
    compiled_path = out_dir / "compiled_strategy_spec.json"
    assert compiled_path.exists()
    spec_data = json.loads(compiled_path.read_text(encoding="utf-8"))
    assert spec_data["experiment"]["name"] == "rsi2_oversold_reversal"
    assert "rsi_fast" in spec_data["data"]["factor_fields"]
    assert spec_data["signal"]["entry"] is not None


def test_cli_compile_preflight_without_dates_returns_2(capsys, tmp_path):
    path = tmp_path / "rsi2.yaml"
    path.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    exit_code = main(["compile", str(path), "--preflight"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--start" in captured.err


# ---------------------------------------------------------------------------
# strategy-smoke CLI tests
# ---------------------------------------------------------------------------

def test_cli_strategy_smoke_no_db_succeeds(capsys, tmp_path):
    """In a no-DB environment, strategy-smoke exit code is 0 with explicit skips."""
    rsi2 = tmp_path / "rsi2.yaml"
    rsi2.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    ema200 = tmp_path / "ema200.yaml"
    ema200.write_text("""\
strategy:
  id: ema200_bollinger_reversal
  name: EMA200 BB
  family: mean_reversion
  direction: long_only
rules:
  entry:
    all:
      - alias: close
        operator: ">"
        alias_b: ema_200
  risk:
    stop_loss_pct: 0.10
factor_requirements:
  - alias: ema_200
    indicator: ema
    source: close
    period: 200
    required: true
    reason: filter
experiment:
  id: smk
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-02-01
  universe:
    include: all_a
""")
    macd = tmp_path / "macd.yaml"
    macd.write_text("""\
strategy:
  id: macd_zero_cross_momentum
  name: MACD
  family: momentum
  direction: long_only
rules:
  entry:
    all:
      - alias: macd_line
        operator: ">"
        alias_b: macd_signal
  risk:
    stop_loss_pct: 0.08
factor_requirements:
  - alias: macd_line
    indicator: macd
    source: close
    params:
      fast: 12
      slow: 26
      signal: 9
    output: macd
    required: true
    reason: macd line
  - alias: macd_signal
    indicator: macd
    source: close
    params:
      fast: 12
      slow: 26
      signal: 9
    output: signal
    required: true
    reason: macd signal
experiment:
  id: smk
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-02-01
  universe:
    include: all_a
""")
    out_dir = tmp_path / "smoke_out"

    exit_code = main([
        "strategy-smoke",
        "--strategies", str(rsi2), str(ema200), str(macd),
        "--output-dir", str(out_dir),
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "overall_status=pass" in captured.out
    assert "compile=pass" in captured.out
    assert "preflight=skip" in captured.out
    assert "backtest_smoke=skip" in captured.out
    assert "database" in captured.out.lower() or "db" in captured.out.lower()

    # smoke_summary.json must exist
    summary_path = out_dir / "smoke_summary.json"
    assert summary_path.exists()
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data["overall_status"] == "pass"
    assert len(data["strategies"]) == 3


def test_cli_strategy_smoke_default_strategies_use_current_paths(capsys, tmp_path):
    """Default strategy-smoke should use repo-local strategies/high_level entries."""
    out_dir = tmp_path / "default-smoke"

    exit_code = main([
        "strategy-smoke",
        "--no-preflight",
        "--no-backtest",
        "--output-dir", str(out_dir),
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "overall_status=pass" in captured.out
    for strategy_id in (
        "rsi2_oversold_reversal",
        "ema200_bollinger_reversal",
        "macd_zero_cross_momentum",
    ):
        assert f"strategy={strategy_id} compile=pass" in captured.out
        assert (out_dir / strategy_id / "compiled_strategy_spec.json").exists()


def test_cli_strategy_smoke_custom_output_dir(capsys, tmp_path):
    """--output-dir places smoke_summary.json and per-strategy dirs there."""
    rsi2 = tmp_path / "rsi2.yaml"
    rsi2.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    out_dir = tmp_path / "custom-out"

    exit_code = main([
        "strategy-smoke",
        "--strategies", str(rsi2),
        "--output-dir", str(out_dir),
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert (out_dir / "smoke_summary.json").exists()
    assert (out_dir / "rsi2_oversold_reversal" / "compiled_strategy_spec.json").exists()


def test_cli_strategy_smoke_compile_failure(capsys, tmp_path):
    """A strategy YAML that can't compile sets overall_status=fail and exit code 2."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("strategy: [invalid yaml", encoding="utf-8")
    out_dir = tmp_path / "fail_out"

    exit_code = main([
        "strategy-smoke",
        "--strategies", str(bad),
        "--output-dir", str(out_dir),
    ])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "overall_status=fail" in captured.out
    assert "compile=fail" in captured.out


def test_cli_strategy_smoke_no_preflight_flag(capsys, tmp_path):
    """--no-preflight forces preflight skip even if DB were available."""
    rsi2 = tmp_path / "rsi2.yaml"
    rsi2.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    out_dir = tmp_path / "np_out"

    exit_code = main([
        "strategy-smoke",
        "--strategies", str(rsi2),
        "--output-dir", str(out_dir),
        "--no-preflight",
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "preflight=skip" in captured.out


def test_cli_strategy_smoke_no_backtest_flag(capsys, tmp_path):
    """--no-backtest forces backtest_smoke skip."""
    rsi2 = tmp_path / "rsi2.yaml"
    rsi2.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    out_dir = tmp_path / "nb_out"

    exit_code = main([
        "strategy-smoke",
        "--strategies", str(rsi2),
        "--output-dir", str(out_dir),
        "--no-backtest",
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "backtest_smoke=skip" in captured.out


def test_cli_strategy_smoke_prints_smoke_summary_path(capsys, tmp_path):
    """The smoke_summary.json file path is printed in stdout."""
    rsi2 = tmp_path / "rsi2.yaml"
    rsi2.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    out_dir = tmp_path / "smoke_out"

    exit_code = main([
        "strategy-smoke",
        "--strategies", str(rsi2),
        "--output-dir", str(out_dir),
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "smoke_summary=" in captured.out
    assert "smoke_summary.json" in captured.out


def test_cli_strategy_smoke_prints_artifact_paths(capsys, tmp_path):
    """Each strategy's artifact paths and counts appear in stdout."""
    rsi2 = tmp_path / "rsi2.yaml"
    rsi2.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    out_dir = tmp_path / "smoke_out"

    exit_code = main([
        "strategy-smoke",
        "--strategies", str(rsi2),
        "--output-dir", str(out_dir),
        "--no-preflight",
        "--no-backtest",
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "artifact_count=" in captured.out
    assert "artifact.compiled_strategy_spec=" in captured.out
    assert "compiled_strategy_spec.json" in captured.out
    assert "durations:" in captured.out
    assert "compile=" in captured.out  # timing key


def test_cli_strategy_smoke_prints_manifest_path(capsys, tmp_path):
    """The smoke_report_manifest.json file path is printed in stdout."""
    rsi2 = tmp_path / "rsi2.yaml"
    rsi2.write_text(RSI2_HIGH_LEVEL_YAML, encoding="utf-8")
    out_dir = tmp_path / "smoke_out"

    exit_code = main([
        "strategy-smoke",
        "--strategies", str(rsi2),
        "--output-dir", str(out_dir),
        "--no-preflight",
        "--no-backtest",
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "smoke_report_manifest=" in captured.out
    assert "smoke_report_manifest.json" in captured.out


# ---------------------------------------------------------------------------
# Smoke manifest filter parity — report-files
# ---------------------------------------------------------------------------

SMOKE_MANIFEST_JSON = json.dumps({
    "schema_version": 1,
    "kind": "strategy_smoke_report_manifest",
    "files": [
        {
            "key": "smoke_summary",
            "path": "smoke_summary.json",
            "filename": "smoke_summary.json",
            "role": "smoke_summary",
        },
        {
            "key": "compiled_strategy_spec_rsi2_oversold_reversal",
            "path": "rsi2_oversold_reversal/compiled_strategy_spec.json",
            "filename": "compiled_strategy_spec.json",
            "role": "compiled_strategy_spec",
            "symbol": "rsi2_oversold_reversal",
        },
        {
            "key": "compiled_strategy_spec_ema200_bollinger_reversal",
            "path": "ema200_bollinger_reversal/compiled_strategy_spec.json",
            "filename": "compiled_strategy_spec.json",
            "role": "compiled_strategy_spec",
            "symbol": "ema200_bollinger_reversal",
        },
        {
            "key": "backtest_smoke_summary_rsi2_oversold_reversal",
            "path": "rsi2_oversold_reversal/backtest_smoke_summary.csv",
            "filename": "backtest_smoke_summary.csv",
            "role": "backtest_smoke_summary",
            "symbol": "rsi2_oversold_reversal",
        },
    ],
})


def _write_smoke_manifest(tmp_path: Path) -> Path:
    p = tmp_path / "smoke_report_manifest.json"
    p.write_text(SMOKE_MANIFEST_JSON, encoding="utf-8")
    # Create the actual files so report-audit passes existence checks.
    (tmp_path / "smoke_summary.json").write_text("{}", encoding="utf-8")
    (tmp_path / "rsi2_oversold_reversal").mkdir(exist_ok=True)
    (tmp_path / "rsi2_oversold_reversal" / "compiled_strategy_spec.json").write_text("{}", encoding="utf-8")
    (tmp_path / "rsi2_oversold_reversal" / "backtest_smoke_summary.csv").write_text("symbol\n", encoding="utf-8")
    (tmp_path / "ema200_bollinger_reversal").mkdir(exist_ok=True)
    (tmp_path / "ema200_bollinger_reversal" / "compiled_strategy_spec.json").write_text("{}", encoding="utf-8")
    return p


# --- report-files ---

def test_cli_report_files_smoke_manifest_role_smoke_summary(capsys, tmp_path):
    """--role smoke_summary returns only the run-level smoke_summary path."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main(["report-files", str(mp), "--role", "smoke_summary"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == str(tmp_path / "smoke_summary.json")


def test_cli_report_files_smoke_manifest_role_compiled_strategy_spec(capsys, tmp_path):
    """--role compiled_strategy_spec returns all matching spec paths."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main(["report-files", str(mp), "--role", "compiled_strategy_spec"])
    captured = capsys.readouterr()
    assert exit_code == 0
    lines = captured.out.strip().split("\n")
    assert len(lines) == 2
    assert all("compiled_strategy_spec.json" in ln for ln in lines)


def test_cli_report_files_smoke_manifest_symbol_filter(capsys, tmp_path):
    """--symbol filters to only the given strategy_id."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main(["report-files", str(mp), "--symbol", "rsi2_oversold_reversal"])
    captured = capsys.readouterr()
    assert exit_code == 0
    lines = captured.out.strip().split("\n")
    assert len(lines) == 2  # compiled_strategy_spec + backtest_smoke_summary
    assert all("rsi2_oversold_reversal" in ln for ln in lines)


def test_cli_report_files_smoke_manifest_role_symbol_combined(capsys, tmp_path):
    """--role + --symbol narrows to exactly one entry."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main([
        "report-files", str(mp),
        "--role", "compiled_strategy_spec",
        "--symbol", "rsi2_oversold_reversal",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    lines = captured.out.strip().split("\n")
    assert len(lines) == 1
    assert "rsi2_oversold_reversal" in lines[0]
    assert "compiled_strategy_spec.json" in lines[0]


def test_cli_report_files_smoke_manifest_role_symbol_no_match(capsys, tmp_path):
    """--role + --symbol that match nothing produces no output with exit 0."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main([
        "report-files", str(mp),
        "--role", "backtest_smoke_summary",
        "--symbol", "ema200_bollinger_reversal",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""


def test_cli_report_files_smoke_manifest_json_output(capsys, tmp_path):
    """--json outputs valid JSON with paths list."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main(["report-files", str(mp), "--role", "smoke_summary", "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert payload["manifest_kind"] == "strategy_smoke_report_manifest"
    assert isinstance(payload["files"], list)
    assert len(payload["files"]) == 1


def test_cli_report_files_smoke_manifest_require_match_success(capsys, tmp_path):
    """--require-match exits 0 when entries match the filter."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main([
        "report-files", str(mp),
        "--role", "compiled_strategy_spec",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    lines = captured.out.strip().split("\n")
    assert len(lines) == 2


def test_cli_report_files_smoke_manifest_require_match_zero(capsys, tmp_path):
    """--require-match exits 2 when no entries match the filter."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main([
        "report-files", str(mp),
        "--role", "missing_factor_requests",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no manifest entries matched filters" in captured.err


def test_cli_report_files_smoke_manifest_json_require_match_zero(capsys, tmp_path):
    """--json --require-match exits 2 with structured error on zero matches."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main([
        "report-files", str(mp),
        "--role", "missing_factor_requests",
        "--json",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 0
    assert payload["manifest_kind"] == "strategy_smoke_report_manifest"
    assert len(payload["files"]) == 0


# --- report-audit ---

def test_cli_report_audit_smoke_manifest_role_filter(capsys, tmp_path):
    """report-audit with --role filters smoke manifest entries."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main(["report-audit", str(mp), "--role", "smoke_summary"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "matched_files=1" in captured.out
    assert "status=ok" in captured.out


def test_cli_report_audit_smoke_manifest_role_symbol_combined(capsys, tmp_path):
    """report-audit with --role + --symbol narrows to one entry."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main([
        "report-audit", str(mp),
        "--role", "compiled_strategy_spec",
        "--symbol", "rsi2_oversold_reversal",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "matched_files=1" in captured.out


def test_cli_report_audit_smoke_manifest_require_match_success(capsys, tmp_path):
    """report-audit --require-match exits 0 when filter matches entries."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main([
        "report-audit", str(mp),
        "--role", "smoke_summary",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "matched_files=1" in captured.out
    assert "status=ok" in captured.out


def test_cli_report_audit_smoke_manifest_require_match_zero(capsys, tmp_path):
    """report-audit --require-match exits 2 with matched_files=0 on no match."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main([
        "report-audit", str(mp),
        "--role", "missing_factor_requests",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "matched_files=0" in captured.out
    assert "status=failed" in captured.out
    assert "no manifest entries matched filters" in captured.err


def test_cli_report_audit_smoke_manifest_json_output(capsys, tmp_path):
    """report-audit --json for smoke manifest returns structured payload."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main(["report-audit", str(mp), "--role", "smoke_summary", "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert payload["manifest_kind"] == "strategy_smoke_report_manifest"


def test_cli_report_audit_smoke_manifest_json_require_match_zero(capsys, tmp_path):
    """report-audit --json --require-match exits 2 with structured error on zero matches."""
    mp = _write_smoke_manifest(tmp_path)
    exit_code = main([
        "report-audit", str(mp),
        "--role", "missing_factor_requests",
        "--json",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 0
    assert payload["manifest_kind"] == "strategy_smoke_report_manifest"


# ---------------------------------------------------------------------------
# Smoke discovery CLI — smoke-files
# ---------------------------------------------------------------------------

SMOKE_SUMMARY_JSON = json.dumps({
    "run_id": "test-run-001",
    "generated_at": "2026-05-22T00:00:00Z",
    "environment": {"db_configured": False},
    "strategies": [
        {
            "strategy_id": "rsi2_oversold_reversal",
            "compile": "pass",
            "preflight": "skip",
            "missing_factor": "skip",
            "backtest_smoke": "skip",
            "reason": "No DB available",
            "artifacts": {"compiled_strategy_spec": "rsi2/compiled_strategy_spec.json"},
            "durations_s": {"compile": 0.042},
        },
        {
            "strategy_id": "ema200_bollinger_reversal",
            "compile": "pass",
            "preflight": "skip",
            "missing_factor": "skip",
            "backtest_smoke": "skip",
            "reason": "No DB available",
            "artifacts": {"compiled_strategy_spec": "ema200/compiled_strategy_spec.json"},
            "durations_s": {"compile": 0.051},
        },
    ],
    "overall_status": "ok",
})

SMOKE_DISCOVERY_MANIFEST_JSON = json.dumps({
    "schema_version": 1,
    "kind": "strategy_smoke_report_manifest",
    "files": [
        {"key": "smoke_summary", "path": "smoke_summary.json", "filename": "smoke_summary.json", "role": "smoke_summary"},
        {"key": "compiled_strategy_spec_rsi2", "path": "rsi2/compiled_strategy_spec.json", "filename": "compiled_strategy_spec.json", "role": "compiled_strategy_spec", "symbol": "rsi2_oversold_reversal"},
        {"key": "compiled_strategy_spec_ema200", "path": "ema200/compiled_strategy_spec.json", "filename": "compiled_strategy_spec.json", "role": "compiled_strategy_spec", "symbol": "ema200_bollinger_reversal"},
    ],
})


def _write_smoke_discovery_fixture(tmp_path: Path) -> Path:
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    (tmp_path / "smoke_report_manifest.json").write_text(SMOKE_DISCOVERY_MANIFEST_JSON, encoding="utf-8")
    return tmp_path


def test_cli_smoke_files_default_output(capsys, tmp_path):
    """qre smoke-files prints run_id, overall_status, strategy_count, and artifact_role_summary."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main(["smoke-files", "--output-dir", str(out_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "run_id=test-run-001" in captured.out
    assert "resolved_output_dir=" in captured.out
    assert "source_mode=manifest" in captured.out
    assert "overall_status=ok" in captured.out
    assert "strategy_count=2" in captured.out
    assert "strategy=rsi2_oversold_reversal" in captured.out
    assert "strategy=ema200_bollinger_reversal" in captured.out
    assert "artifact_role_summary:" in captured.out
    assert "compiled_strategy_spec: 2" in captured.out
    assert "smoke_summary: 1" in captured.out


def test_cli_smoke_files_json_output(capsys, tmp_path):
    """qre smoke-files --json emits valid JSON payload."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main(["smoke-files", "--output-dir", str(out_dir), "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["run_id"] == "test-run-001"
    assert payload["overall_status"] == "ok"
    assert "resolved_output_dir" in payload
    assert payload["source_mode"] == "manifest"
    assert payload["strategy_count"] == 2
    assert payload["artifact_role_counts"]["smoke_summary"] == 1
    assert payload["artifact_role_counts"]["compiled_strategy_spec"] == 2


def test_cli_smoke_files_strategy_filter(capsys, tmp_path):
    """qre smoke-files --strategy filters to a single strategy."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main(["smoke-files", "--output-dir", str(out_dir), "--strategy", "rsi2_oversold_reversal"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "strategy_count=1" in captured.out
    assert "strategy=rsi2_oversold_reversal" in captured.out
    assert "ema200_bollinger_reversal" not in captured.out


def test_cli_smoke_files_strategy_json(capsys, tmp_path):
    """qre smoke-files --json --strategy includes per-strategy detail."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main(["smoke-files", "--output-dir", str(out_dir), "--json", "--strategy", "rsi2_oversold_reversal"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["strategy_count"] == 1
    assert payload["strategy"]["strategy_id"] == "rsi2_oversold_reversal"
    assert payload["strategy"]["compile"] == "pass"


def test_cli_smoke_files_role_filter(capsys, tmp_path):
    """qre smoke-files --role filters artifact_role_summary to a single role."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main(["smoke-files", "--output-dir", str(out_dir), "--role", "compiled_strategy_spec"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "compiled_strategy_spec: 2" in captured.out
    assert "smoke_summary" not in captured.out


def test_cli_smoke_files_role_json(capsys, tmp_path):
    """qre smoke-files --json --role returns only the matching role count."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main(["smoke-files", "--output-dir", str(out_dir), "--json", "--role", "smoke_summary"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["artifact_role_counts"] == {"smoke_summary": 1}


def test_cli_smoke_files_missing_summary_json(capsys, tmp_path):
    """qre smoke-files exits 2 and prints error when smoke_summary.json is missing."""
    exit_code = main(["smoke-files", "--output-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "not found" in captured.err


def test_cli_smoke_files_fail_status(capsys, tmp_path):
    """qre smoke-files exits 2 when overall_status is fail."""
    fail_summary = json.dumps({**json.loads(SMOKE_SUMMARY_JSON), "overall_status": "fail"})
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    exit_code = main(["smoke-files", "--output-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "overall_status=fail" in captured.out


def test_cli_smoke_files_latest_discovery_success(capsys, tmp_path, monkeypatch):
    """qre smoke-files discovers the latest run when multiple run dirs exist."""
    # Create a fake __file__ so that 4 parents up = tmp_path
    fake_cli = tmp_path / "src" / "quant_research_engine" / "apps" / "cli.py"
    fake_cli.parent.mkdir(parents=True)
    fake_cli.write_text("")
    monkeypatch.setattr("quant_research_engine.apps.cli.__file__", str(fake_cli))

    root = tmp_path / "outputs" / "strategy-entry-smoke"
    run_old = root / "run-old"
    run_new = root / "run-new"
    run_old.mkdir(parents=True)
    run_new.mkdir(parents=True)
    old_summary = json.dumps({**json.loads(SMOKE_SUMMARY_JSON), "run_id": "old-run"})
    new_summary = json.dumps({**json.loads(SMOKE_SUMMARY_JSON), "run_id": "new-run"})
    (run_old / "smoke_summary.json").write_text(old_summary)
    (run_new / "smoke_summary.json").write_text(new_summary)
    # Ensure run_new is more recent
    (run_new / "smoke_summary.json").touch()

    exit_code = main(["smoke-files"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "run_id=new-run" in captured.out
    assert "resolved_output_dir=" in captured.out
    assert str(run_new.resolve()) in captured.out


def test_cli_smoke_files_latest_no_runs(capsys, tmp_path, monkeypatch):
    """qre smoke-files exits 2 when no smoke run dirs exist under default root."""
    fake_cli = tmp_path / "src" / "quant_research_engine" / "apps" / "cli.py"
    fake_cli.parent.mkdir(parents=True)
    fake_cli.write_text("")
    monkeypatch.setattr("quant_research_engine.apps.cli.__file__", str(fake_cli))

    root = tmp_path / "outputs" / "strategy-entry-smoke"
    root.mkdir(parents=True)
    # No subdirectories with smoke_summary.json

    exit_code = main(["smoke-files"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "No smoke runs found" in captured.err


def test_cli_smoke_files_output_dir_precedence(capsys, tmp_path, monkeypatch):
    """Explicit --output-dir takes precedence over --latest / auto-discovery."""
    # Create a newer run that should be ignored when --output-dir is explicit
    root = tmp_path / "outputs" / "strategy-entry-smoke"
    run_auto = root / "run-auto"
    run_auto.mkdir(parents=True)
    auto_summary = json.dumps({**json.loads(SMOKE_SUMMARY_JSON), "run_id": "auto-run"})
    (run_auto / "smoke_summary.json").write_text(auto_summary)

    # Create explicit output_dir with a different run_id
    explicit_dir = tmp_path / "explicit-output"
    explicit_dir.mkdir(parents=True)
    explicit_summary = json.dumps({**json.loads(SMOKE_SUMMARY_JSON), "run_id": "explicit-run"})
    (explicit_dir / "smoke_summary.json").write_text(explicit_summary)

    exit_code = main(["smoke-files", "--output-dir", str(explicit_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "run_id=explicit-run" in captured.out
    assert "auto-run" not in captured.out


def test_cli_smoke_files_deterministic_strategy_order(capsys, tmp_path):
    """qre smoke-files lists strategies in deterministic order by strategy_id."""
    summary_reversed = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "strategies": [
            {
                "strategy_id": "ema200_bollinger_reversal",
                "compile": "pass",
                "preflight": "skip",
                "missing_factor": "skip",
                "backtest_smoke": "skip",
                "reason": "No DB available",
                "artifacts": {"compiled_strategy_spec": "ema200/compiled_strategy_spec.json"},
                "durations_s": {"compile": 0.051},
            },
            {
                "strategy_id": "rsi2_oversold_reversal",
                "compile": "pass",
                "preflight": "skip",
                "missing_factor": "skip",
                "backtest_smoke": "skip",
                "reason": "No DB available",
                "artifacts": {"compiled_strategy_spec": "rsi2/compiled_strategy_spec.json"},
                "durations_s": {"compile": 0.042},
            },
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(summary_reversed, encoding="utf-8")
    exit_code = main(["smoke-files", "--output-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == 0
    # After sorting by strategy_id, ema200 comes before rsi2
    ema_idx = captured.out.index("strategy=ema200_bollinger_reversal")
    rsi_idx = captured.out.index("strategy=rsi2_oversold_reversal")
    assert ema_idx < rsi_idx, "strategies must be sorted by strategy_id"


def test_cli_smoke_files_source_mode_manifest_text(capsys, tmp_path):
    """qre smoke-files prints source_mode=manifest when manifest is present."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main(["smoke-files", "--output-dir", str(out_dir)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "source_mode=manifest" in captured.out


def test_cli_smoke_files_source_mode_fallback_text(capsys, tmp_path):
    """qre smoke-files prints source_mode=artifacts_fallback when manifest is missing."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    # No manifest file — fallback mode
    exit_code = main(["smoke-files", "--output-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "source_mode=artifacts_fallback" in captured.out


def test_cli_smoke_files_manifest_fallback_count_parity(capsys, tmp_path):
    """Artifact role counts are identical from manifest vs fallback when per-strategy data matches."""
    # Build a manifest and a summary where per-strategy artifacts are aligned.
    # The fallback counts only per-strategy artifacts, so the manifest must not include
    # run-level artifacts (like smoke_summary) for the parity test to be valid.
    aligned_summary = json.dumps({
        "run_id": "test-parity",
        "generated_at": "2026-05-22T00:00:00Z",
        "environment": {"db_configured": False},
        "strategies": [
            {
                "strategy_id": "alpha",
                "compile": "pass",
                "preflight": "skip",
                "missing_factor": "skip",
                "backtest_smoke": "skip",
                "reason": "No DB",
                "artifacts": {"compiled_strategy_spec": "alpha/c.json", "backtest_smoke_summary": "alpha/s.csv"},
                "durations_s": {},
            },
            {
                "strategy_id": "beta",
                "compile": "pass",
                "preflight": "skip",
                "missing_factor": "skip",
                "backtest_smoke": "skip",
                "reason": "No DB",
                "artifacts": {"compiled_strategy_spec": "beta/c.json", "backtest_smoke_summary": "beta/s.csv"},
                "durations_s": {},
            },
        ],
        "overall_status": "ok",
    })
    aligned_manifest = json.dumps({
        "schema_version": 1,
        "kind": "strategy_smoke_report_manifest",
        "files": [
            {"key": "a1", "path": "alpha/c.json", "filename": "c.json", "role": "compiled_strategy_spec", "symbol": "alpha"},
            {"key": "a2", "path": "alpha/s.csv", "filename": "s.csv", "role": "backtest_smoke_summary", "symbol": "alpha"},
            {"key": "b1", "path": "beta/c.json", "filename": "c.json", "role": "compiled_strategy_spec", "symbol": "beta"},
            {"key": "b2", "path": "beta/s.csv", "filename": "s.csv", "role": "backtest_smoke_summary", "symbol": "beta"},
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(aligned_summary)
    (tmp_path / "smoke_report_manifest.json").write_text(aligned_manifest)

    # Get counts via manifest
    exit_code = main(["smoke-files", "--output-dir", str(tmp_path), "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    manifest_payload = json.loads(captured.out)
    assert manifest_payload["source_mode"] == "manifest"

    # Remove manifest and get counts via fallback
    (tmp_path / "smoke_report_manifest.json").unlink()
    exit_code = main(["smoke-files", "--output-dir", str(tmp_path), "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    fallback_payload = json.loads(captured.out)
    assert fallback_payload["source_mode"] == "artifacts_fallback"

    # Counts must be identical when per-strategy artifacts match
    assert manifest_payload["artifact_role_counts"] == fallback_payload["artifact_role_counts"]


def test_cli_smoke_files_details_text(capsys, tmp_path):
    """qre smoke-files --details prints per-strategy block with stage statuses and artifact keys."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main(["smoke-files", "--output-dir", str(out_dir), "--details"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "run_id=test-run-001" in captured.out
    assert "source_mode=manifest" in captured.out
    # Per-strategy detail blocks
    assert "  strategy_id=ema200_bollinger_reversal" in captured.out
    assert "    compile=pass" in captured.out
    assert "    preflight=skip" in captured.out
    assert "    missing_factor=skip" in captured.out
    assert "    backtest_smoke=skip" in captured.out
    assert "    artifacts=['compiled_strategy_spec']" in captured.out
    assert "  strategy_id=rsi2_oversold_reversal" in captured.out
    # Summary still present
    assert "artifact_role_summary:" in captured.out
    assert "compiled_strategy_spec: 2" in captured.out


def test_cli_smoke_files_details_json(capsys, tmp_path):
    """qre smoke-files --json --details includes strategies array with per-strategy details."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main(["smoke-files", "--output-dir", str(out_dir), "--json", "--details"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["strategies"] == [
        {
            "strategy_id": "ema200_bollinger_reversal",
            "compile": "pass",
            "preflight": "skip",
            "missing_factor": "skip",
            "backtest_smoke": "skip",
            "artifacts": ["compiled_strategy_spec"],
        },
        {
            "strategy_id": "rsi2_oversold_reversal",
            "compile": "pass",
            "preflight": "skip",
            "missing_factor": "skip",
            "backtest_smoke": "skip",
            "artifacts": ["compiled_strategy_spec"],
        },
    ]
    # Summary still present
    assert payload["artifact_role_counts"]["compiled_strategy_spec"] == 2


def test_cli_smoke_files_details_with_strategy_filter(capsys, tmp_path):
    """qre smoke-files --details --strategy filters per-strategy details."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--details", "--strategy", "rsi2_oversold_reversal",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "strategy_count=1" in captured.out
    assert "  strategy_id=rsi2_oversold_reversal" in captured.out
    assert "  strategy_id=ema200_bollinger_reversal" not in captured.out


def test_cli_smoke_files_details_role_still_filters_summary(capsys, tmp_path):
    """qre smoke-files --details --role filters artifact_role_summary but still shows full details."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--details", "--role", "smoke_summary",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    # Role filter applies to summary
    assert "smoke_summary: 1" in captured.out
    assert "compiled_strategy_spec" not in captured.out or "compiled_strategy_spec:" not in captured.out.split("artifact_role_summary:")[-1]
    # Details still show both strategies
    assert "  strategy_id=ema200_bollinger_reversal" in captured.out
    assert "  strategy_id=rsi2_oversold_reversal" in captured.out


def test_cli_smoke_files_output_file_text_export(capsys, tmp_path):
    """qre smoke-files --output-file <path> writes text output to file, stdout unchanged."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    output_file = tmp_path / "export.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--output-file", str(output_file),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    # Stdout unchanged
    assert "run_id=test-run-001" in captured.out
    assert "source_mode=manifest" in captured.out
    # File written with matching content
    assert output_file.exists()
    file_content = output_file.read_text(encoding="utf-8")
    assert file_content == captured.out


def test_cli_smoke_files_output_file_json_export(capsys, tmp_path):
    """qre smoke-files --json --output-file <path> writes JSON to file, stdout unchanged."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    output_file = tmp_path / "export.json"
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--json", "--output-file", str(output_file),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    # Stdout contains JSON
    stdout_data = json.loads(captured.out)
    assert stdout_data["run_id"] == "test-run-001"
    # File written with matching JSON
    assert output_file.exists()
    file_data = json.loads(output_file.read_text(encoding="utf-8"))
    assert file_data == stdout_data


def test_cli_smoke_files_output_file_parent_dir_auto_create(capsys, tmp_path):
    """qre smoke-files --output-file <path> creates parent directories automatically."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    output_file = tmp_path / "nested" / "subdir" / "export.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--output-file", str(output_file),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    # File exists under nested path
    assert output_file.exists()
    assert "run_id=test-run-001" in output_file.read_text(encoding="utf-8")
    # Stdout unchanged
    assert "run_id=test-run-001" in captured.out


def test_cli_smoke_files_output_file_write_failure(capsys, tmp_path):
    """qre smoke-files --output-file returns 2 on write failure with stderr message."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    # Create a directory at the target path to force write failure
    output_file = tmp_path / "is_a_directory"
    output_file.mkdir()
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--output-file", str(output_file),
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Failed to write output file" in captured.err
    # Stdout still produced (text output printed before file write attempt)
    assert "run_id=test-run-001" in captured.out


def test_cli_smoke_files_check_exists_success(capsys, tmp_path):
    """qre smoke-files --check-exists exits 0 when all referenced artifacts exist."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    # Create the actual artifact files referenced in the manifest
    (out_dir / "rsi2" / "compiled_strategy_spec.json").parent.mkdir(parents=True, exist_ok=True)
    (out_dir / "rsi2" / "compiled_strategy_spec.json").write_text("{}", encoding="utf-8")
    (out_dir / "ema200" / "compiled_strategy_spec.json").parent.mkdir(parents=True, exist_ok=True)
    (out_dir / "ema200" / "compiled_strategy_spec.json").write_text("{}", encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--check-exists",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "run_id=test-run-001" in captured.out
    assert "Missing artifact:" not in captured.err


def test_cli_smoke_files_check_exists_missing_artifact(capsys, tmp_path):
    """qre smoke-files --check-exists exits 2 and prints missing artifacts to stderr."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--check-exists",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    # Stderr reports missing artifact paths
    assert "Missing artifact:" in captured.err
    assert "compiled_strategy_spec.json" in captured.err
    # Stdout still produced
    assert "run_id=test-run-001" in captured.out


def test_cli_smoke_files_check_exists_json(capsys, tmp_path):
    """qre smoke-files --json --check-exists includes missing_artifact_count and missing_artifacts."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--json", "--check-exists",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["missing_artifact_count"] > 0
    assert isinstance(payload["missing_artifacts"], list)
    assert len(payload["missing_artifacts"]) == payload["missing_artifact_count"]
    # Missing artifact paths are sorted
    assert payload["missing_artifacts"] == sorted(payload["missing_artifacts"])


def test_cli_smoke_files_check_exists_backward_compat(capsys, tmp_path):
    """qre smoke-files without --check-exists does not include missing-artifact fields."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    # Text mode
    exit_code_text = main([
        "smoke-files", "--output-dir", str(out_dir),
    ])
    captured_text = capsys.readouterr()
    assert exit_code_text == 0
    assert "Missing artifact:" not in captured_text.err

    # JSON mode
    exit_code_json = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--json",
    ])
    captured_json = capsys.readouterr()
    assert exit_code_json == 0
    payload = json.loads(captured_json.out)
    assert "missing_artifact_count" not in payload
    assert "missing_artifacts" not in payload


def test_cli_smoke_files_require_match_strategy_success(capsys, tmp_path):
    """qre smoke-files --strategy <match> --require-match exits 0 when strategy matches."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--strategy", "rsi2_oversold_reversal",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "strategy=rsi2_oversold_reversal" in captured.out


def test_cli_smoke_files_require_match_strategy_no_match(capsys, tmp_path):
    """qre smoke-files --strategy <no-match> --require-match returns 2 with stderr."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--strategy", "nonexistent_strategy",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "No matching strategy: nonexistent_strategy" in captured.err
    # Stdout still produced
    assert "run_id=test-run-001" in captured.out
    assert "strategy_count=0" in captured.out


def test_cli_smoke_files_require_match_role_no_match(capsys, tmp_path):
    """qre smoke-files --role <no-match> --require-match returns 2 with stderr."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--role", "nonexistent_role",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "No matching role: nonexistent_role" in captured.err
    # Stdout still produced
    assert "run_id=test-run-001" in captured.out


def test_cli_smoke_files_require_match_backward_compat(capsys, tmp_path):
    """qre smoke-files --strategy no-match without --require-match exits 0."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--strategy", "nonexistent_strategy",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "No matching strategy:" not in captured.err
    assert "strategy_count=0" in captured.out


def test_cli_smoke_files_list_missing_without_check_exists(capsys, tmp_path):
    """qre smoke-files --list-missing without --check-exists exits 2 with stderr."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--list-missing",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--list-missing requires --check-exists" in captured.err
    # Normal output should NOT be printed (early exit before output)
    assert "run_id=" not in captured.out


def test_cli_smoke_files_list_missing_with_missing_artifacts(capsys, tmp_path):
    """qre smoke-files --check-exists --list-missing prints missing paths to stdout."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--check-exists", "--list-missing",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    # stderr has "Missing artifact:" lines
    assert "Missing artifact:" in captured.err
    # stdout has text output + missing paths (one per line)
    assert "run_id=" in captured.out
    assert "overall_status=" in captured.out
    # Paths should appear in stdout after normal output
    lines = captured.out.strip().split("\n")
    # Last lines should be the artifact paths
    assert len(lines) > 5  # normal output + path lines
    path_lines = [l for l in lines if l.startswith("smoke_") or l.startswith("backtest_") or "compiled" in l]
    assert len(path_lines) > 0


def test_cli_smoke_files_list_missing_json_with_missing_artifacts(capsys, tmp_path):
    """qre smoke-files --json --check-exists --list-missing emits JSON then paths."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--json", "--check-exists", "--list-missing",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    # JSON is multi-line with indent=2; paths follow after closing brace line
    out_lines = captured.out.split("\n")
    # Find the JSON block: lines from first "{" to the single "}" line
    json_end = None
    for i, line in enumerate(out_lines):
        if line == "}":
            json_end = i
            break
    assert json_end is not None, f"Could not find end of JSON in: {captured.out}"
    json_str = "\n".join(out_lines[: json_end + 1])
    payload = json.loads(json_str)
    assert "missing_artifact_count" in payload
    assert "missing_artifacts" in payload
    assert payload["missing_artifact_count"] > 0
    # Remaining non-empty lines are missing artifact relative paths
    path_lines = [l for l in out_lines[json_end + 1 :] if l.strip()]
    if payload["missing_artifact_count"] > 0:
        assert len(path_lines) > 0
        for path in path_lines:
            assert path in payload["missing_artifacts"]


def test_cli_smoke_files_list_missing_backward_compat(capsys, tmp_path):
    """qre smoke-files without --list-missing does not print paths to stdout."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--check-exists",
    ])
    captured = capsys.readouterr()
    # exit 2 because artifacts are missing (no files on disk)
    assert exit_code == 2
    assert "Missing artifact:" in captured.err
    # Stdout should NOT contain raw artifact paths (list-missing not present).
    # Path lines are unindented lines with .json/.csv extensions — not the
    # indented summary lines like "  compiled_strategy_spec: 2".
    out_lines = captured.out.strip().split("\n")
    path_lines = [
        l for l in out_lines
        if not l.startswith(" ") and (l.endswith(".json") or l.endswith(".csv"))
    ]
    assert len(path_lines) == 0


def test_cli_smoke_files_quiet_suppresses_stdout_text(capsys, tmp_path):
    """qre smoke-files --quiet emits no stdout in text mode."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--quiet",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    # stderr should also be empty for a normal success case
    assert captured.err.strip() == ""


def test_cli_smoke_files_quiet_preserves_stderr_and_exit_code(capsys, tmp_path):
    """qre smoke-files --quiet --check-exists keeps stderr diagnostics and exit 2."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--quiet", "--check-exists",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out.strip() == ""
    assert "Missing artifact:" in captured.err


def test_cli_smoke_files_quiet_json_suppresses_stdout(capsys, tmp_path):
    """qre smoke-files --json --quiet emits no stdout."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--json", "--quiet",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""


def test_cli_smoke_files_quiet_backward_compat(capsys, tmp_path):
    """qre smoke-files without --quiet still emits normal stdout."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "run_id=" in captured.out
    assert "overall_status=" in captured.out


def test_cli_smoke_files_status_only_text_output(capsys, tmp_path):
    """qre smoke-files --status-only emits only overall_status in text mode."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--status-only",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "ok"
    assert "run_id=" not in captured.out
    assert "strategy_count=" not in captured.out


def test_cli_smoke_files_status_only_json_output(capsys, tmp_path):
    """qre smoke-files --json --status-only emits minimal JSON with overall_status + run_id."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--json", "--status-only",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out.strip())
    assert set(payload.keys()) == {"overall_status", "run_id"}
    assert payload["overall_status"] == "ok"
    assert payload["run_id"] == "test-run-001"


def test_cli_smoke_files_status_only_quiet_suppresses(capsys, tmp_path):
    """qre smoke-files --status-only --quiet suppresses stdout."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--status-only", "--quiet",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""


def test_cli_smoke_files_status_only_backward_compat(capsys, tmp_path):
    """qre smoke-files without --status-only still emits full text output."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "run_id=" in captured.out
    assert "overall_status=" in captured.out
    assert "strategy_count=" in captured.out


def test_cli_smoke_files_status_file_text(capsys, tmp_path):
    """qre smoke-files --status-file writes full text output to file."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--status-file", str(status_path),
    ])
    assert exit_code == 0
    content = status_path.read_text(encoding="utf-8")
    assert "run_id=test-run-001" in content
    assert "overall_status=ok" in content
    assert "strategy_count=2" in content


def test_cli_smoke_files_status_file_json(capsys, tmp_path):
    """qre smoke-files --json --status-file writes full JSON to file."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    status_path = tmp_path / "status.json"
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--json", "--status-file", str(status_path),
    ])
    assert exit_code == 0
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["overall_status"] == "ok"
    assert payload["run_id"] == "test-run-001"
    assert "strategy_count" in payload


def test_cli_smoke_files_status_file_parent_dir_create(capsys, tmp_path):
    """qre smoke-files --status-file auto-creates parent directories."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    status_path = tmp_path / "nested" / "subdir" / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--status-file", str(status_path),
    ])
    assert exit_code == 0
    assert status_path.is_file()
    content = status_path.read_text(encoding="utf-8")
    assert "run_id=test-run-001" in content


def test_cli_smoke_files_status_file_write_failure(capsys, tmp_path):
    """qre smoke-files --status-file write failure returns exit 2 with stderr."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    # Create a regular file where a directory would need to be created
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("block", encoding="utf-8")
    status_path = tmp_path / "blocker.txt" / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Failed to write status file" in captured.err


def test_cli_smoke_files_status_file_with_quiet(capsys, tmp_path):
    """qre smoke-files --quiet --status-file suppresses stdout but writes file."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--quiet", "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8")
    assert "run_id=test-run-001" in content
    assert "overall_status=ok" in content


def test_cli_smoke_files_status_format_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-format text emits plain status line."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--status-only", "--status-format", "text",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "ok"
    # Verify no JSON payload in output
    assert "{" not in captured.out


def test_cli_smoke_files_status_format_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-format json emits minimal JSON."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--status-only", "--status-format", "json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out.strip())
    assert payload["overall_status"] == "ok"
    assert payload["run_id"] == "test-run-001"
    # Status-only JSON should not have full payload fields
    assert "strategy_count" not in payload


def test_cli_smoke_files_status_format_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-format without --status-only returns 2 with stderr."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--status-format", "text",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-format requires --status-only" in captured.err


def test_cli_smoke_files_status_format_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-format json --status-file writes file, suppresses stdout."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    status_path = tmp_path / "status.json"
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--quiet", "--status-only", "--status-format", "json",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["overall_status"] == "ok"
    assert payload["run_id"] == "test-run-001"


def test_cli_smoke_files_status_reason_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-reason emits status<TAB>reason in text mode."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][0], "compile": "fail", "reason": "compile error"},
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][1],
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-reason",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2  # fail status returns 2
    assert captured.out.strip() == "fail\trsi2_oversold_reversal: compile=fail"


def test_cli_smoke_files_status_reason_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-reason --json includes reason key."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][0], "backtest_smoke": "fail", "reason": "backtest error"},
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][1],
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-reason", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out.strip())
    assert payload["overall_status"] == "fail"
    assert payload["run_id"] == "test-run-001"
    assert payload["reason"] == "rsi2_oversold_reversal: backtest_smoke=fail"


def test_cli_smoke_files_status_reason_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-reason without --status-only returns 2 with stderr."""
    out_dir = _write_smoke_discovery_fixture(tmp_path)
    exit_code = main([
        "smoke-files", "--output-dir", str(out_dir),
        "--status-reason",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-reason requires --status-only" in captured.err


def test_cli_smoke_files_status_reason_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-reason --status-file writes reason, suppresses stdout."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][0], "compile": "fail", "reason": "compile failure"},
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][1],
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-reason",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 2  # fail status
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert content == "fail\trsi2_oversold_reversal: compile=fail"


def test_cli_smoke_files_status_code_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-code emits numeric code (0) in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-code",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "0"


def test_cli_smoke_files_status_code_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-code --json emits status_code in JSON payload."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][0], "compile": "fail", "reason": "compile failure"},
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][1],
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-code", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2  # fail status
    payload = json.loads(captured.out)
    assert payload["overall_status"] == "fail"
    assert payload["status_code"] == 1


def test_cli_smoke_files_status_code_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-code without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-code",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-code requires --status-only" in captured.err


def test_cli_smoke_files_status_code_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-code --status-file writes code, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-code",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert content == "0"


def test_cli_smoke_files_status_meta_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-meta emits status with metadata in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-meta",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    out = captured.out.strip()
    assert out.startswith("ok\t")
    assert "run_id=test-run-001" in out
    assert "source_mode=artifacts_fallback" in out


def test_cli_smoke_files_status_meta_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-meta --json includes source_mode in JSON payload."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-meta", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["overall_status"] == "ok"
    assert payload["run_id"] == "test-run-001"
    assert "source_mode" in payload


def test_cli_smoke_files_status_meta_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-meta without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-meta",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-meta requires --status-only" in captured.err


def test_cli_smoke_files_status_meta_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-meta --status-file writes metadata, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-meta",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "run_id=test-run-001" in content
    assert "source_mode=artifacts_fallback" in content


def test_cli_smoke_files_status_summary_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-summary emits status with count fields in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-summary",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    out = captured.out.strip()
    assert out.startswith("ok\t")
    assert "total=2" in out
    assert "pass=2" in out
    assert "fail=0" in out
    assert "skip=0" in out


def test_cli_smoke_files_status_summary_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-summary --json includes count fields in JSON payload."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][0], "compile": "fail", "reason": "compile failure"},
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][1],
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-summary", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["overall_status"] == "fail"
    assert payload["strategy_total"] == 2
    assert payload["strategy_pass"] == 1
    assert payload["strategy_fail"] == 1
    assert payload["strategy_skip"] == 0


def test_cli_smoke_files_status_summary_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-summary without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-summary",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-summary requires --status-only" in captured.err


def test_cli_smoke_files_status_summary_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-summary --status-file writes counts, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-summary",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "total=2" in content
    assert "pass=2" in content
    assert "fail=0" in content
    assert "skip=0" in content


def test_cli_smoke_files_status_fail_key_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-fail-key emits fail_key in text mode."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][0],
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][1], "compile": "fail", "reason": "compile failure"},
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-fail-key",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    out = captured.out.strip()
    assert out.startswith("fail")
    assert "fail_key=ema200_bollinger_reversal" in out


def test_cli_smoke_files_status_fail_key_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-fail-key --json includes fail_key in JSON payload."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][0], "compile": "fail", "reason": "compile failure"},
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][1],
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-fail-key", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["overall_status"] == "fail"
    assert payload["fail_key"] == "rsi2_oversold_reversal"


def test_cli_smoke_files_status_fail_key_json_no_failure(capsys, tmp_path):
    """qre smoke-files --status-only --status-fail-key --json returns null when no strategy fails."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-fail-key", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["fail_key"] is None


def test_cli_smoke_files_status_fail_key_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-fail-key without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-fail-key",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-fail-key requires --status-only" in captured.err


def test_cli_smoke_files_status_fail_key_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-fail-key --status-file writes fail_key, suppresses stdout."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][0], "compile": "fail", "reason": "compile failure"},
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][1],
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-fail-key",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "fail_key=rsi2_oversold_reversal" in content


def test_cli_smoke_files_status_fail_stage_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-fail-stage emits fail_stage in text mode."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][0], "compile": "fail", "reason": "compile failure"},
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][1],
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-fail-stage",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    out = captured.out.strip()
    assert out.startswith("fail")
    assert "fail_stage=compile" in out


def test_cli_smoke_files_status_fail_stage_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-fail-stage --json includes fail_stage in JSON payload."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][0],
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][1], "backtest_smoke": "fail", "reason": "backtest failure"},
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-fail-stage", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["overall_status"] == "fail"
    assert payload["fail_stage"] == "backtest_smoke"


def test_cli_smoke_files_status_fail_stage_json_no_failure(capsys, tmp_path):
    """qre smoke-files --status-only --status-fail-stage --json returns null when no stage fails."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-fail-stage", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["fail_stage"] is None


def test_cli_smoke_files_status_fail_stage_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-fail-stage without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-fail-stage",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-fail-stage requires --status-only" in captured.err


def test_cli_smoke_files_status_fail_stage_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-fail-stage --status-file writes fail_stage, suppresses stdout."""
    fail_summary = json.dumps({
        **json.loads(SMOKE_SUMMARY_JSON),
        "overall_status": "fail",
        "strategies": [
            {**json.loads(SMOKE_SUMMARY_JSON)["strategies"][0], "preflight": "fail", "reason": "preflight failure"},
            json.loads(SMOKE_SUMMARY_JSON)["strategies"][1],
        ],
    })
    (tmp_path / "smoke_summary.json").write_text(fail_summary, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-fail-stage",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "fail_stage=preflight" in content


def test_cli_smoke_files_status_timestamp_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-timestamp emits timestamp in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-timestamp",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    out = captured.out.strip()
    assert out.startswith("ok")
    assert "timestamp=2026-05-22T00:00:00Z" in out


def test_cli_smoke_files_status_timestamp_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-timestamp --json includes timestamp in JSON payload."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-timestamp", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["overall_status"] == "ok"
    assert payload["timestamp"] == "2026-05-22T00:00:00Z"


def test_cli_smoke_files_status_timestamp_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-timestamp without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-timestamp",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-timestamp requires --status-only" in captured.err


def test_cli_smoke_files_status_timestamp_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-timestamp --status-file writes timestamp, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-timestamp",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "timestamp=2026-05-22T00:00:00Z" in content


def test_cli_smoke_files_status_output_dir_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-output-dir emits output_dir in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-output-dir",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    out = captured.out.strip()
    assert out.startswith("ok")
    assert f"output_dir={tmp_path.resolve()}" in out


def test_cli_smoke_files_status_output_dir_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-output-dir --json includes output_dir in JSON payload."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-output-dir", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["overall_status"] == "ok"
    assert payload["output_dir"] == str(tmp_path.resolve())


def test_cli_smoke_files_status_output_dir_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-output-dir without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-output-dir",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-output-dir requires --status-only" in captured.err


def test_cli_smoke_files_status_output_dir_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-output-dir --status-file writes output_dir, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-output-dir",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert f"output_dir={tmp_path.resolve()}" in content


def test_cli_smoke_files_status_manifest_path_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-manifest-path emits manifest_path in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-manifest-path",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    out = captured.out.strip()
    assert out.startswith("ok")
    expected_manifest = str(tmp_path / "smoke_report_manifest.json")
    assert f"manifest_path={expected_manifest}" in out


def test_cli_smoke_files_status_manifest_path_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-manifest-path --json emits manifest_path in JSON mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-manifest-path", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["overall_status"] == "ok"
    assert payload["manifest_path"] == str(tmp_path / "smoke_report_manifest.json")


def test_cli_smoke_files_status_manifest_path_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-manifest-path without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-manifest-path",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-manifest-path requires --status-only" in captured.err


def test_cli_smoke_files_status_manifest_path_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-manifest-path --status-file writes manifest_path, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-manifest-path",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    expected_manifest = str(tmp_path / "smoke_report_manifest.json")
    assert f"manifest_path={expected_manifest}" in content


def test_cli_smoke_files_status_manifest_exists_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-manifest-exists emits manifest_exists=true in text mode when manifest exists."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    (tmp_path / "smoke_report_manifest.json").write_text("{}", encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-manifest-exists",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    out = captured.out.strip()
    assert out.startswith("ok")
    assert "manifest_exists=true" in out


def test_cli_smoke_files_status_manifest_exists_json(capsys, tmp_path):
    """qre smoke-files --status-only --status-manifest-exists --json emits manifest_exists in JSON mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    (tmp_path / "smoke_report_manifest.json").write_text("{}", encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-manifest-exists", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["overall_status"] == "ok"
    assert payload["manifest_exists"] is True


def test_cli_smoke_files_status_manifest_exists_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-manifest-exists without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-manifest-exists",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-manifest-exists requires --status-only" in captured.err


def test_cli_smoke_files_status_manifest_exists_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-manifest-exists --status-file writes manifest_exists=false, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-manifest-exists",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "manifest_exists=false" in content


def test_cli_smoke_files_status_artifact_count_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-artifact-count emits artifact_count in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-artifact-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "ok\tartifact_count=2"


def test_cli_smoke_files_status_artifact_count_json(capsys, tmp_path):
    """qre smoke-files --json --status-only --status-artifact-count adds artifact_count integer to JSON payload."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--json", "--status-only", "--status-artifact-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out.strip())
    assert payload["overall_status"] == "ok"
    assert payload["artifact_count"] == 2
    assert isinstance(payload["artifact_count"], int)


def test_cli_smoke_files_status_artifact_count_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-artifact-count without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-artifact-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-artifact-count requires --status-only" in captured.err


def test_cli_smoke_files_status_artifact_count_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-artifact-count --status-file writes artifact_count, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-artifact-count",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "artifact_count=2" in content


def test_cli_smoke_files_status_strategy_count_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-strategy-count emits strategy_count in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-strategy-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "ok\tstrategy_count=2"


def test_cli_smoke_files_status_strategy_count_json(capsys, tmp_path):
    """qre smoke-files --json --status-only --status-strategy-count adds strategy_count integer to JSON payload."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--json", "--status-only", "--status-strategy-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out.strip())
    assert payload["overall_status"] == "ok"
    assert payload["strategy_count"] == 2
    assert isinstance(payload["strategy_count"], int)


def test_cli_smoke_files_status_strategy_count_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-strategy-count without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-strategy-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-strategy-count requires --status-only" in captured.err


def test_cli_smoke_files_status_strategy_count_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-strategy-count --status-file writes strategy_count, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-strategy-count",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "strategy_count=2" in content


def test_cli_smoke_files_status_fail_count_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-fail-count emits fail_count in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-fail-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "ok\tfail_count=0"


def test_cli_smoke_files_status_fail_count_json(capsys, tmp_path):
    """qre smoke-files --json --status-only --status-fail-count adds fail_count integer to JSON payload."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--json", "--status-only", "--status-fail-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out.strip())
    assert payload["overall_status"] == "ok"
    assert payload["fail_count"] == 0
    assert isinstance(payload["fail_count"], int)


def test_cli_smoke_files_status_fail_count_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-fail-count without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-fail-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-fail-count requires --status-only" in captured.err


def test_cli_smoke_files_status_fail_count_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-fail-count --status-file writes fail_count, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-fail-count",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "fail_count=0" in content


def test_cli_smoke_files_status_skip_count_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-skip-count emits skip_count in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-skip-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "ok\tskip_count=0"


def test_cli_smoke_files_status_skip_count_json(capsys, tmp_path):
    """qre smoke-files --json --status-only --status-skip-count adds skip_count integer to JSON payload."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--json", "--status-only", "--status-skip-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out.strip())
    assert payload["overall_status"] == "ok"
    assert payload["skip_count"] == 0
    assert isinstance(payload["skip_count"], int)


def test_cli_smoke_files_status_skip_count_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-skip-count without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-skip-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-skip-count requires --status-only" in captured.err


def test_cli_smoke_files_status_skip_count_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-skip-count --status-file writes skip_count, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-skip-count",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "skip_count=0" in content


def test_cli_smoke_files_status_pass_count_text(capsys, tmp_path):
    """qre smoke-files --status-only --status-pass-count emits pass_count in text mode."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-only", "--status-pass-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "ok\tpass_count=2"


def test_cli_smoke_files_status_pass_count_json(capsys, tmp_path):
    """qre smoke-files --json --status-only --status-pass-count adds pass_count integer to JSON payload."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--json", "--status-only", "--status-pass-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out.strip())
    assert payload["overall_status"] == "ok"
    assert payload["pass_count"] == 2
    assert isinstance(payload["pass_count"], int)


def test_cli_smoke_files_status_pass_count_requires_status_only(capsys, tmp_path):
    """qre smoke-files --status-pass-count without --status-only returns exit 2."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--status-pass-count",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--status-pass-count requires --status-only" in captured.err


def test_cli_smoke_files_status_pass_count_quiet_status_file(capsys, tmp_path):
    """qre smoke-files --quiet --status-only --status-pass-count --status-file writes pass_count, suppresses stdout."""
    (tmp_path / "smoke_summary.json").write_text(SMOKE_SUMMARY_JSON, encoding="utf-8")
    status_path = tmp_path / "status.txt"
    exit_code = main([
        "smoke-files", "--output-dir", str(tmp_path),
        "--quiet", "--status-only", "--status-pass-count",
        "--status-file", str(status_path),
    ])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == ""
    content = status_path.read_text(encoding="utf-8").strip()
    assert "pass_count=2" in content


# --- qre research-run CLI tests ---


def test_cli_research_run_help_includes_command(capsys):
    """qre research-run --help shows the command description."""
    import pytest as _pytest
    with _pytest.raises(SystemExit) as exc_info:
        main(["research-run", "--help"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "research-run" in captured.out
    assert "preflight" in captured.out.lower()
    assert "eval" in captured.out.lower()
    assert "backtest" in captured.out.lower()


def test_cli_research_run_missing_required_args(capsys):
    """qre research-run without --start, --end, --output-dir fails with usage error."""
    import pytest as _pytest
    with _pytest.raises(SystemExit) as exc_info:
        main(["research-run", "strategy.yaml"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "required" in captured.err


def test_cli_research_run_no_db_returns_error(capsys, tmp_path):
    """qre research-run without a database configuration returns exit 2 with stderr."""
    strat_path = tmp_path / "strategy.yaml"
    strat_path.write_text("""
name: test
signal:
  entry: (close > ema_200) and (close < bb_lower)
factor_fields:
  - factors.stock_daily_basic.ema_200
  - factors.stock_daily_basic.bb_lower
""", encoding="utf-8")
    output_dir = tmp_path / "output"
    exit_code = main([
        "research-run", str(strat_path),
        "--start", "2024-01-01",
        "--end", "2024-02-01",
        "--output-dir", str(output_dir),
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err != ""


def test_cli_research_run_rejects_benchmark_table_without_code(capsys, tmp_path):
    """research-run --benchmark-table without --benchmark-code should exit 2."""
    strat_path = tmp_path / "strategy.yaml"
    strat_path.write_text(
        "name: test\n"
        "signal:\n"
        "  entry: close > 0\n"
        "factor_fields: []\n"
    )
    output_dir = tmp_path / "output"
    exit_code = main([
        "research-run", str(strat_path),
        "--start", "2024-01-01",
        "--end", "2024-02-01",
        "--output-dir", str(output_dir),
        "--benchmark-table", "public.index_daily",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "must be provided together" in captured.err


def test_cli_research_run_rejects_benchmark_code_without_table(capsys, tmp_path):
    """research-run --benchmark-code without --benchmark-table should exit 2."""
    strat_path = tmp_path / "strategy.yaml"
    strat_path.write_text(
        "name: test\n"
        "signal:\n"
        "  entry: close > 0\n"
        "factor_fields: []\n"
    )
    output_dir = tmp_path / "output"
    exit_code = main([
        "research-run", str(strat_path),
        "--start", "2024-01-01",
        "--end", "2024-02-01",
        "--output-dir", str(output_dir),
        "--benchmark-code", "000300.SH",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "must be provided together" in captured.err


def test_cli_research_run_success_prints_stage_paths(capsys, monkeypatch, tmp_path):
    """Successful research-run prints stage manifest paths to stdout."""
    from quant_research_engine.orchestration import research_run as rr_module

    strat_path = tmp_path / "strategy.yaml"
    strat_path.write_text("name: test\nsignal:\n  entry: close > 0\n", encoding="utf-8")
    output_dir = tmp_path / "run_output"
    output_dir.mkdir()

    # Build fake spec
    spec = StrategySpec(
        name="test_strategy",
        signal_expression="close > 0",
        exit_signal_expression=None,
        market_fields=["open", "high", "low", "close", "vol", "amount"],
        factor_fields=[],
        forward_horizons=[1, 3, 5],
        holding_days=5,
        quantiles=None,
    )

    monkeypatch.setattr(rr_module, "_build_db_store", lambda db_url=None: _FakeStore())
    monkeypatch.setattr(
        rr_module.StrategySpec,
        "from_yaml",
        staticmethod(lambda path: spec),
    )

    # Preflight mock
    preflight_report = type("FakeReport", (), {
        "status": "ok",
        "summary": "All good",
        "missing_factor_requests": None,
        "missing_factors": None,
        "details": None,
        "market_fields_available": None,
        "factor_fields_available": None,
        "universe_size": None,
        "factor_coverage": None,
        "calendar_range": None,
    })()
    monkeypatch.setattr(rr_module, "_run_preflight", lambda *a, **kw: ("ok", preflight_report))

    # Eval mock
    eval_df = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [pd.Timestamp("2024-01-05")]})
    empty_df = pd.DataFrame()
    eval_result = type("FakeEvalResult", (), {
        "events": eval_df,
        "summary": empty_df,
        "ic_summary": empty_df,
        "quantile_summary": empty_df,
        "group_summary": empty_df,
        "random_baseline_summary": empty_df,
        "factor_decay_summary": empty_df,
        "regime_summary": empty_df,
    })()
    monkeypatch.setattr(rr_module, "_run_eval", lambda *a, **kw: ("ok", eval_result))

    # Backtest mock — write files under output_dir/backtest/
    bt_dir = output_dir / "backtest"
    bt_dir.mkdir(parents=True)
    summary_csv = bt_dir / "summary.csv"
    summary_csv.write_text("col1\n1")
    bt_rm = bt_dir / "report_manifest.json"
    bt_rm.write_text("{}")
    monkeypatch.setattr(
        rr_module,
        "_run_backtest",
        lambda *a, **kw: ("ok", {"summary_csv": summary_csv, "report_manifest": bt_rm}),
    )

    exit_code = main([
        "research-run", str(strat_path),
        "--start", "2024-01-01",
        "--end", "2024-02-01",
        "--output-dir", str(output_dir),
        "--run-id", "cli-test-001",
        "--db-url", "postgresql://localhost/test",
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "run_id=cli-test-001" in captured.out
    assert "preflight_status=ok" in captured.out
    assert "eval_status=ok" in captured.out
    assert "backtest_status=ok" in captured.out
    assert "research_manifest=" in captured.out
    assert "report_manifest=" in captured.out
    assert "preflight_preflight_report=" in captured.out
    assert "eval_report_manifest=" in captured.out
    assert "eval_run_manifest=" in captured.out
    assert "backtest_summary_csv=" in captured.out
    assert str(output_dir) in captured.out


def test_cli_research_run_prints_preflight_error(capsys, monkeypatch, tmp_path):
    """Research-run with preflight error prints error to stderr and exits 2."""
    from quant_research_engine.orchestration import research_run as rr_module

    strat_path = tmp_path / "strategy.yaml"
    strat_path.write_text("name: test\nsignal:\n  entry: close > 0\n", encoding="utf-8")
    output_dir = tmp_path / "run_output"
    output_dir.mkdir()

    spec = StrategySpec(
        name="test_strategy",
        signal_expression="close > 0",
        exit_signal_expression=None,
        market_fields=["open", "high", "low", "close", "vol", "amount"],
        factor_fields=[],
        forward_horizons=[1, 3, 5],
        holding_days=5,
        quantiles=None,
    )

    monkeypatch.setattr(rr_module, "_build_db_store", lambda db_url=None: _FakeStore())
    monkeypatch.setattr(
        rr_module.StrategySpec,
        "from_yaml",
        staticmethod(lambda path: spec),
    )
    monkeypatch.setattr(
        rr_module,
        "_run_preflight",
        lambda *a, **kw: ("error", type("FakeReport", (), {"status": "error"})()),
    )

    exit_code = main([
        "research-run", str(strat_path),
        "--start", "2024-01-01",
        "--end", "2024-02-01",
        "--output-dir", str(output_dir),
        "--db-url", "postgresql://localhost/test",
    ])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "preflight_status=error" in captured.out
    assert "error=" in captured.err
    assert "Preflight failed" in captured.err


def test_cli_report_files_research_run_report_manifest(capsys, tmp_path):
    """report-files on a research_run_report_manifest with --check-exists --validate-contents exits 0."""
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                     "run_id": "r1", "command": "research-run",
                     "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "research_run_manifest", "path": "research_run_manifest.json",
                 "filename": "research_run_manifest.json", "role": "run_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-files", str(tmp_path / "report_manifest.json"),
        "--check-exists", "--validate-contents",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0, f"stderr: {captured.err}"
    assert "research_run_manifest.json" in captured.out


def test_cli_report_audit_research_run_report_manifest_role_run_manifest(capsys, tmp_path):
    """report-audit on research_run_report_manifest --role run_manifest --require-match exits 0."""
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                     "run_id": "r1", "command": "research-run",
                     "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "research_run_manifest", "path": "research_run_manifest.json",
                 "filename": "research_run_manifest.json", "role": "run_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "run_manifest",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0, f"stderr: {captured.err}"
    assert "matched_files=1" in captured.out
    assert "status=ok" in captured.out


def test_cli_report_audit_json_includes_nested_issue_details(capsys, tmp_path):
    """report-audit --json surfaces recursive nested stage manifest issues."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main(["report-audit", str(tmp_path / "report_manifest.json"), "--json"])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert payload["validation_issues"] >= 1
    assert len(payload["issues"]) >= 1
    codes = {i["code"] for i in payload["issues"]}
    assert "invalid_nested_report_manifest" in codes
    nested_issue = next(i for i in payload["issues"] if i["code"] == "invalid_nested_report_manifest")
    assert nested_issue["key"] == "eval_report_manifest"
    assert "eval_report_manifest" in nested_issue["message"]


def test_cli_report_files_json_validate_contents_includes_nested_issue_details(capsys, tmp_path):
    """report-files --validate-contents --json surfaces recursive nested stage manifest issues."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-files", str(tmp_path / "report_manifest.json"),
        "--validate-contents", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert len(payload["files"]) == 1
    assert "invalid_nested_report_manifest" in captured.err


def test_cli_report_audit_role_run_manifest_skips_nested_validation(capsys, tmp_path):
    """--role run_manifest does not trigger recursive nested stage validation."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                     "run_id": "r1", "command": "research-run",
                     "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    (tmp_path / "report_manifest.json").write_text(
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
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "run_manifest",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0, f"stderr: {captured.err}"
    assert "status=ok" in captured.out


def test_cli_report_audit_role_eval_report_manifest_triggers_nested_validation(capsys, tmp_path):
    """--role eval_report_manifest triggers recursive validation of the nested eval manifest."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "eval_report_manifest",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2, f"stderr: {captured.err}"
    assert "status=failed" in captured.out


def test_cli_report_audit_json_role_preflight_report_surfaces_issue(capsys, tmp_path):
    """report-audit --json --role preflight_report surfaces preflight content issues."""
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "preflight_report",
        "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    codes = {i["code"] for i in payload["issues"]}
    assert "invalid_preflight_report_json" in codes


def test_cli_report_files_json_validate_contents_role_preflight_surfaces_issue(capsys, tmp_path):
    """report-files --validate-contents --json --role preflight_report surfaces issue."""
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-files", str(tmp_path / "report_manifest.json"),
        "--role", "preflight_report",
        "--validate-contents", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "invalid_preflight_report_json" in captured.err


def test_cli_report_audit_role_run_manifest_skips_preflight_validation(capsys, tmp_path):
    """--role run_manifest does not validate a malformed preflight report."""
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                     "run_id": "r1", "command": "research-run",
                     "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "research_run_manifest", "path": "research_run_manifest.json",
                 "filename": "research_run_manifest.json", "role": "run_manifest"},
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "run_manifest",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0, f"stderr: {captured.err}"
    assert "status=ok" in captured.out


def test_cli_report_audit_json_role_preflight_surfaces_check_item_issue(capsys, tmp_path):
    """report-audit --json --role preflight_report surfaces a check-item shape issue."""
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text(
        json.dumps({"status": "ok", "checks": [123]}),
        encoding="utf-8",
    )
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "preflight_report",
        "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    codes = {i["code"] for i in payload["issues"]}
    assert "invalid_preflight_report_check" in codes


def test_cli_report_audit_json_role_preflight_surfaces_missing_factor_item_issue(capsys, tmp_path):
    """report-audit --json --role preflight_report surfaces a missing-factor item shape issue."""
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text(
        json.dumps({"status": "ok", "missing_factor_requests": [123]}),
        encoding="utf-8",
    )
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "preflight_report",
        "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    codes = {i["code"] for i in payload["issues"]}
    assert "invalid_preflight_report_missing_factor_request" in codes


# --- research_run_report_manifest role selector parity ---


def test_cli_report_audit_json_role_backtest_surfaces_nested_issue(capsys, tmp_path):
    """report-audit --json --role backtest_report_manifest surfaces nested manifest issues."""
    bt_dir = tmp_path / "backtest"
    bt_dir.mkdir()
    (bt_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "backtest_report_manifest", "path": "backtest/report_manifest.json",
                 "filename": "report_manifest.json", "role": "backtest_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "backtest_report_manifest",
        "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    codes = {i["code"] for i in payload["issues"]}
    assert "invalid_nested_report_manifest" in codes


def test_cli_report_files_json_role_backtest_surfaces_nested_issue(capsys, tmp_path):
    """report-files --validate-contents --json --role backtest_report_manifest surfaces nested issues."""
    bt_dir = tmp_path / "backtest"
    bt_dir.mkdir()
    (bt_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "backtest_report_manifest", "path": "backtest/report_manifest.json",
                 "filename": "report_manifest.json", "role": "backtest_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-files", str(tmp_path / "report_manifest.json"),
        "--role", "backtest_report_manifest",
        "--validate-contents", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "invalid_nested_report_manifest" in captured.err


def test_cli_report_audit_json_role_eval_does_not_validate_sibling_backtest(capsys, tmp_path):
    """--role eval_report_manifest does not validate a malformed sibling backtest_report_manifest."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text(
        json.dumps({"kind": "evaluation_report_manifest", "files": []}),
        encoding="utf-8",
    )
    bt_dir = tmp_path / "backtest"
    bt_dir.mkdir()
    (bt_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
                {"key": "backtest_report_manifest", "path": "backtest/report_manifest.json",
                 "filename": "report_manifest.json", "role": "backtest_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "eval_report_manifest",
        "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0, f"stderr: {captured.err}"
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert len(payload["issues"]) == 0


def test_cli_report_audit_json_role_preflight_does_not_validate_nested_stage(capsys, tmp_path):
    """--role preflight_report does not validate a malformed nested stage manifest."""
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text(
        json.dumps({"status": "ok"}),
        encoding="utf-8",
    )
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "preflight_report",
        "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0, f"stderr: {captured.err}"
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert len(payload["issues"]) == 0


def test_cli_report_audit_json_role_run_manifest_does_not_validate_preflight_or_nested(capsys, tmp_path):
    """--role run_manifest does not validate malformed preflight or nested stage manifests."""
    (tmp_path / "research_run_manifest.json").write_text(
        json.dumps({"schema_version": 1, "kind": "research_run_manifest",
                     "run_id": "r1", "command": "research-run",
                     "strategy_path": "strategy.yaml", "artifacts": []}),
        encoding="utf-8",
    )
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text("not valid json", encoding="utf-8")
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "report_manifest.json").write_text("not valid json", encoding="utf-8")
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "research_run_manifest", "path": "research_run_manifest.json",
                 "filename": "research_run_manifest.json", "role": "run_manifest"},
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
                {"key": "eval_report_manifest", "path": "eval/report_manifest.json",
                 "filename": "report_manifest.json", "role": "eval_report_manifest"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "run_manifest",
        "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0, f"stderr: {captured.err}"
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1
    assert len(payload["issues"]) == 0


def test_cli_report_files_json_role_preflight_require_match_exits_0(capsys, tmp_path):
    """report-files --json --role preflight_report --require-match exits 0 with matched_files=1."""
    preflight_dir = tmp_path / "preflight"
    preflight_dir.mkdir()
    (preflight_dir / "preflight_report.json").write_text(
        json.dumps({"status": "ok"}),
        encoding="utf-8",
    )
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-files", str(tmp_path / "report_manifest.json"),
        "--role", "preflight_report",
        "--require-match", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 0, f"stderr: {captured.err}"
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 1


def test_cli_report_files_json_role_missing_require_match_exits_2(capsys, tmp_path):
    """report-files --json --role missing_role --require-match exits 2 with matched_files=0."""
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-files", str(tmp_path / "report_manifest.json"),
        "--role", "missing_role",
        "--require-match", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2, f"stdout: {captured.out}"
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 0


def test_cli_report_audit_json_role_missing_require_match_exits_2(capsys, tmp_path):
    """report-audit --json --role missing_role --require-match exits 2 with matched_files=0."""
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "missing_role",
        "--require-match", "--json",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2, f"stdout: {captured.out}"
    payload = json.loads(captured.out)
    assert payload["matched_files"] == 0


def test_cli_report_files_text_role_missing_require_match_exits_2(capsys, tmp_path):
    """report-files --role missing_role --require-match exits 2 with no-match diagnostic (text mode)."""
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-files", str(tmp_path / "report_manifest.json"),
        "--role", "missing_role",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2, f"stdout: {captured.out}"
    assert "no manifest entries matched filters" in captured.err.lower()


def test_cli_report_audit_text_role_missing_require_match_exits_2(capsys, tmp_path):
    """report-audit --role missing_role --require-match exits 2 with no-match diagnostic (text mode)."""
    (tmp_path / "report_manifest.json").write_text(
        json.dumps({
            "kind": "research_run_report_manifest",
            "files": [
                {"key": "preflight_report", "path": "preflight/preflight_report.json",
                 "filename": "preflight_report.json", "role": "preflight_report"},
            ],
        }),
        encoding="utf-8",
    )
    exit_code = main([
        "report-audit", str(tmp_path / "report_manifest.json"),
        "--role", "missing_role",
        "--require-match",
    ])
    captured = capsys.readouterr()
    assert exit_code == 2, f"stdout: {captured.out}"
    assert "no manifest entries matched filters" in captured.err.lower()


class _FakeStore:
    def __init__(self, settings=None):
        self.settings = settings

    def ping(self):
        return True
