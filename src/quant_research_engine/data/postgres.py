from __future__ import annotations

from collections import defaultdict
from datetime import date
import re

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.data.settings import DatabaseSettings


class PostgresDataStore:
    _IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self.market_engine = create_engine(settings.market_db_url)
        self.factor_engine = create_engine(settings.factor_db_url or settings.market_db_url)
        self.reference_engine = create_engine(settings.reference_db_url or settings.market_db_url)

    def ping(self) -> bool:
        with self.market_engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        return True

    def table_exists(self, table_name: str, *, engine: Engine | None = None) -> bool:
        schema, table = self.split_table_name(table_name)
        query = text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            LIMIT 1
            """
        )
        with (engine or self.market_engine).begin() as conn:
            return conn.execute(query, {"schema_name": schema, "table_name": table}).scalar_one_or_none() is not None

    def get_table_columns(self, table_name: str, *, engine: Engine | None = None) -> list[str]:
        schema, table = self.split_table_name(table_name)
        query = text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            ORDER BY ordinal_position
            """
        )
        with (engine or self.market_engine).begin() as conn:
            rows = conn.execute(query, {"schema_name": schema, "table_name": table}).fetchall()
        return [str(row[0]) for row in rows]

    def load_daily_bars(
        self,
        ts_codes: list[str] | None,
        start: date,
        end: date,
        fields: list[str] | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        self._validate_date_range(start, end)
        fields = fields or ["open", "high", "low", "close", "pre_close", "vol", "amount"]
        return self._load_table_frame(
            engine=self.market_engine,
            table_name=self.settings.tables.market_daily_table,
            source_columns=["ts_code", "trade_date", *fields],
            start=start,
            end=end,
            ts_codes=ts_codes,
            limit=limit,
        )

    def load_benchmark_bars(
        self,
        table_name: str,
        ts_codes: list[str] | None,
        start: date,
        end: date,
        fields: list[str] | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        self._validate_date_range(start, end)
        fields = fields or ["close"]
        return self._load_table_frame(
            engine=self.market_engine,
            table_name=table_name,
            source_columns=["ts_code", "trade_date", *fields],
            start=start,
            end=end,
            ts_codes=ts_codes,
            limit=limit,
        )

    def load_factor_history(
        self,
        ts_codes: list[str] | None,
        field_requests: list[FactorFieldRequest],
        start: date,
        end: date,
    ) -> pd.DataFrame:
        self._validate_date_range(start, end)
        if not field_requests:
            return pd.DataFrame(columns=["ts_code", "trade_date"])

        grouped: dict[str, list[FactorFieldRequest]] = defaultdict(list)
        for request in field_requests:
            grouped[request.qualified_table].append(request)

        merged: pd.DataFrame | None = None
        for table_name, requests in grouped.items():
            columns = ["ts_code", "trade_date", *[request.source_column for request in requests]]
            rename_map = {
                request.source_column: request.logical_name
                for request in requests
                if request.source_column != request.logical_name
            }
            chunk = self._load_table_frame(
                engine=self.factor_engine,
                table_name=table_name,
                source_columns=columns,
                start=start,
                end=end,
                ts_codes=ts_codes,
            )
            if rename_map:
                chunk = chunk.rename(columns=rename_map)
            merged = chunk if merged is None else merged.merge(chunk, on=["ts_code", "trade_date"], how="outer")

        if merged is None:
            return pd.DataFrame(columns=["ts_code", "trade_date"])
        return self._normalize_frame(merged)

    def load_calendar(self, start: date, end: date) -> pd.DataFrame:
        self._validate_date_range(start, end)
        query = f"""
            SELECT DISTINCT trade_date
            FROM {self.qualified_table(self.settings.tables.market_daily_table)}
            WHERE trade_date BETWEEN :start_date AND :end_date
            ORDER BY trade_date
        """
        frame = pd.read_sql_query(
            sql=text(query),
            con=self.reference_engine,
            params={"start_date": start, "end_date": end},
        )
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        return frame

    def load_security_metadata(self, ts_codes: list[str] | None = None) -> pd.DataFrame:
        table_name = self.settings.tables.security_metadata_table
        if table_name:
            frame = self._load_security_metadata_table(table_name, ts_codes)
        else:
            frame = self._derive_security_metadata_from_daily(ts_codes)
        return self._normalize_security_metadata(frame)

    @staticmethod
    def derive_board(ts_code: str) -> str:
        symbol = ts_code.split(".", maxsplit=1)[0]
        suffix = ts_code.rsplit(".", maxsplit=1)[-1].upper() if "." in ts_code else ""
        if suffix == "BJ":
            return "beijing"
        if symbol.startswith("688"):
            return "star_market"
        if symbol.startswith(("300", "301")):
            return "chinext"
        return "main_board"

    def split_table_name(self, table_name: str) -> tuple[str, str]:
        parts = table_name.split(".")
        if len(parts) == 1:
            schema, table = "public", parts[0]
        elif len(parts) == 2:
            schema, table = parts
        else:
            raise ValueError(f"Unsafe SQL identifier: {table_name}")
        self.validate_identifier(schema)
        self.validate_identifier(table)
        return schema, table

    def qualified_table(self, table_name: str) -> str:
        schema, table = self.split_table_name(table_name)
        return f"{schema}.{table}"

    def validate_identifier(self, identifier: str) -> str:
        if not self._IDENTIFIER.match(identifier):
            raise ValueError(f"Unsafe SQL identifier: {identifier}")
        return identifier

    def validate_columns(self, columns: list[str]) -> list[str]:
        return [self.validate_identifier(column) for column in columns]

    def _load_security_metadata_table(self, table_name: str, ts_codes: list[str] | None) -> pd.DataFrame:
        expected_columns = [
            "ts_code",
            "list_date",
            "board",
            "is_st",
            "is_risk_warning",
            "is_suspended",
        ]
        available_columns = set(self.get_table_columns(table_name, engine=self.reference_engine))
        selected_columns = [column for column in expected_columns if column in available_columns]
        passthrough_columns = sorted(available_columns - set(expected_columns))
        selected_columns.extend(passthrough_columns)
        if "ts_code" not in selected_columns:
            raise ValueError(f"{table_name} must include ts_code")

        query = f"""
            SELECT {", ".join(self.validate_columns(selected_columns))}
            FROM {self.qualified_table(table_name)}
        """
        params: dict[str, object] = {}
        if ts_codes:
            placeholders = []
            for index, ts_code in enumerate(ts_codes):
                key = f"ts_code_{index}"
                placeholders.append(f":{key}")
                params[key] = ts_code
            query += f" WHERE ts_code IN ({', '.join(placeholders)})"
        query += " ORDER BY ts_code"
        return pd.read_sql_query(sql=text(query), con=self.reference_engine, params=params)

    def _derive_security_metadata_from_daily(self, ts_codes: list[str] | None) -> pd.DataFrame:
        query = f"""
            SELECT ts_code, MIN(trade_date) AS list_date
            FROM {self.qualified_table(self.settings.tables.market_daily_table)}
        """
        params: dict[str, object] = {}
        if ts_codes:
            placeholders = []
            for index, ts_code in enumerate(ts_codes):
                key = f"ts_code_{index}"
                placeholders.append(f":{key}")
                params[key] = ts_code
            query += f" WHERE ts_code IN ({', '.join(placeholders)})"
        query += " GROUP BY ts_code ORDER BY ts_code"
        frame = pd.read_sql_query(sql=text(query), con=self.reference_engine, params=params)
        if frame.empty:
            return pd.DataFrame(
                columns=[
                    "ts_code",
                    "list_date",
                    "board",
                    "is_st",
                    "is_risk_warning",
                    "is_suspended",
                ]
            )
        frame["board"] = frame["ts_code"].map(self.derive_board)
        frame["is_st"] = False
        frame["is_risk_warning"] = False
        frame["is_suspended"] = False
        return frame

    def _normalize_security_metadata(self, frame: pd.DataFrame) -> pd.DataFrame:
        fixed_columns = [
            "ts_code",
            "list_date",
            "board",
            "is_st",
            "is_risk_warning",
            "is_suspended",
        ]
        for column in fixed_columns:
            if column not in frame.columns:
                frame[column] = pd.NA
        if "list_date" in frame.columns:
            frame["list_date"] = pd.to_datetime(frame["list_date"])
        if frame["board"].isna().any():
            frame["board"] = frame["board"].fillna(frame["ts_code"].map(self.derive_board))
        for column in ["is_st", "is_risk_warning", "is_suspended"]:
            frame[column] = frame[column].fillna(False).astype(bool)
        passthrough = sorted(c for c in frame.columns if c not in set(fixed_columns))
        return frame[fixed_columns + passthrough].sort_values("ts_code").reset_index(drop=True)

    def _load_table_frame(
        self,
        *,
        engine: Engine,
        table_name: str,
        source_columns: list[str],
        start: date,
        end: date,
        ts_codes: list[str] | None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        validated_columns = self.validate_columns(source_columns)
        query = f"""
            SELECT {", ".join(validated_columns)}
            FROM {self.qualified_table(table_name)}
            WHERE trade_date BETWEEN :start_date AND :end_date
        """
        params: dict[str, object] = {"start_date": start, "end_date": end}
        if ts_codes:
            placeholders = []
            for index, ts_code in enumerate(ts_codes):
                key = f"ts_code_{index}"
                placeholders.append(f":{key}")
                params[key] = ts_code
            query += f" AND ts_code IN ({', '.join(placeholders)})"
        query += " ORDER BY ts_code, trade_date"
        if limit is not None:
            query += " LIMIT :limit"
            params["limit"] = limit

        frame = pd.read_sql_query(sql=text(query), con=engine, params=params)
        return self._normalize_frame(frame)

    def _normalize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if "trade_date" in frame.columns:
            frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        if {"ts_code", "trade_date"}.issubset(frame.columns):
            frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
        return frame

    def _validate_date_range(self, start: date, end: date) -> None:
        if start > end:
            raise ValueError("start must be <= end")
