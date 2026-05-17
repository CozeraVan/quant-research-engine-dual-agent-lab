import pytest

from quant_research_engine.data.settings import DatabaseSettings


def test_database_settings_reads_qre_environment(monkeypatch):
    monkeypatch.setenv("QRE_MARKET_DB_URL", "postgresql+psycopg://user:pass@localhost:5432/tushare_data")
    monkeypatch.setenv("QRE_FACTOR_DB_URL", "postgresql+psycopg://user:pass@localhost:5432/tushare_data")
    monkeypatch.setenv("QRE_MARKET_DAILY_TABLE", "public.stock_daily")

    settings = DatabaseSettings.from_env()

    assert settings.market_db_url == "postgresql+psycopg://user:pass@localhost:5432/tushare_data"
    assert settings.factor_db_url == "postgresql+psycopg://user:pass@localhost:5432/tushare_data"
    assert settings.tables.market_daily_table == "public.stock_daily"


def test_database_settings_accepts_sr_environment_fallback(monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.setenv("SR_MARKET_DB_URL", "postgresql+psycopg://user:pass@localhost:5432/tushare_data")

    settings = DatabaseSettings.from_env()

    assert settings.market_db_url == "postgresql+psycopg://user:pass@localhost:5432/tushare_data"


def test_database_settings_requires_market_db_url(monkeypatch):
    monkeypatch.delenv("QRE_MARKET_DB_URL", raising=False)
    monkeypatch.delenv("SR_MARKET_DB_URL", raising=False)

    with pytest.raises(ValueError, match="QRE_MARKET_DB_URL"):
        DatabaseSettings.from_env()
