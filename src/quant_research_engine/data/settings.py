from __future__ import annotations

from dataclasses import dataclass
import os


def _get_env(primary: str, fallback: str | None = None, default: str | None = None) -> str | None:
    value = os.environ.get(primary, "").strip()
    if value:
        return value
    if fallback:
        fallback_value = os.environ.get(fallback, "").strip()
        if fallback_value:
            return fallback_value
    return default


@dataclass(frozen=True)
class DatabaseTableConfig:
    market_daily_table: str = "public.stock_daily"
    security_metadata_table: str | None = None
    trade_calendar_table: str | None = None
    benchmark_daily_table: str | None = None


@dataclass(frozen=True)
class DatabaseSettings:
    market_db_url: str
    factor_db_url: str | None = None
    reference_db_url: str | None = None
    benchmark_db_url: str | None = None
    research_db_url: str | None = None
    tables: DatabaseTableConfig = DatabaseTableConfig()

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        market_db_url = _get_env("QRE_MARKET_DB_URL", "SR_MARKET_DB_URL")
        if not market_db_url:
            raise ValueError("QRE_MARKET_DB_URL or SR_MARKET_DB_URL is required")

        tables = DatabaseTableConfig(
            market_daily_table=_get_env("QRE_MARKET_DAILY_TABLE", "SR_MARKET_DAILY_TABLE", "public.stock_daily")
            or "public.stock_daily",
            security_metadata_table=_get_env("QRE_SECURITY_METADATA_TABLE", "SR_SECURITY_METADATA_TABLE"),
            trade_calendar_table=_get_env("QRE_TRADE_CALENDAR_TABLE", "SR_TRADE_CALENDAR_TABLE"),
            benchmark_daily_table=_get_env("QRE_BENCHMARK_DAILY_TABLE", "SR_BENCHMARK_DAILY_TABLE"),
        )
        return cls(
            market_db_url=market_db_url,
            factor_db_url=_get_env("QRE_FACTOR_DB_URL", "SR_FACTOR_DB_URL"),
            reference_db_url=_get_env("QRE_REFERENCE_DB_URL", "SR_REFERENCE_DB_URL"),
            benchmark_db_url=_get_env("QRE_BENCHMARK_DB_URL", "SR_BENCHMARK_DB_URL"),
            research_db_url=_get_env("QRE_RESEARCH_DB_URL", "SR_RESEARCH_DB_URL"),
            tables=tables,
        )
