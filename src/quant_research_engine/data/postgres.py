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
        self.benchmark_engine = create_engine(
            settings.benchmark_db_url or settings.reference_db_url or settings.market_db_url
        )

    def ping(self) -> bool:
        with self.market_engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        return True

    def list_symbols_with_bars(self, start: date, end: date) -> list[str]:
        """Distinct ts_codes having daily bars in [start, end] (index scan)."""
        query = text(
            f"""
            SELECT DISTINCT ts_code
            FROM {self.qualified_table(self.settings.tables.market_daily_table)}
            WHERE trade_date BETWEEN :start_date AND :end_date
            ORDER BY ts_code
            """
        )
        with self.market_engine.begin() as conn:
            rows = conn.execute(query, {"start_date": start, "end_date": end}).fetchall()
        return [str(row[0]) for row in rows]

    def close(self) -> None:
        """Dispose all DB engines, returning connections to the database."""
        seen: set[int] = set()
        for engine in (self.market_engine, self.factor_engine, self.reference_engine, self.benchmark_engine):
            if id(engine) in seen:
                continue
            seen.add(id(engine))
            engine.dispose()

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
            engine=self.benchmark_engine,
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

    def load_security_metadata(
        self, ts_codes: list[str] | None = None, *, benchmark_code: str | None = None, as_of: date | None = None
    ) -> pd.DataFrame:
        table_name = self.settings.tables.security_metadata_table
        if table_name:
            frame = self._load_security_metadata_table(table_name, ts_codes)
        elif self.table_exists("reference.stock_basic", engine=self.reference_engine):
            frame = self._load_reference_security_metadata(ts_codes, as_of=as_of)
        else:
            frame = self._derive_security_metadata_from_daily(ts_codes)

        if not table_name:
            daily_basic = self._load_reference_daily_basic_snapshot(ts_codes, as_of=as_of)
            if not daily_basic.empty:
                frame = frame.merge(daily_basic, on="ts_code", how="left")
                if "total_mv" in frame.columns:
                    frame["market_cap_bucket"] = self._compute_market_cap_bucket(frame["total_mv"])
                if "turnover_rate_f" in frame.columns:
                    frame["liquidity_bucket"] = self._compute_liquidity_bucket(frame["turnover_rate_f"])

            if benchmark_code:
                index_weight = self._load_reference_index_weight_snapshot(benchmark_code, ts_codes, as_of=as_of)
                if not index_weight.empty:
                    frame = frame.merge(index_weight, on="ts_code", how="left")
                    frame["is_benchmark_member"] = frame["is_benchmark_member"].fillna(False).astype(bool)
                    frame["benchmark_code"] = frame["benchmark_code"].fillna(benchmark_code)

        if "industry" in frame.columns:
            frame["industry_group"] = self._compute_industry_group(frame["industry"])

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

    def _load_reference_security_metadata(self, ts_codes: list[str] | None, *, as_of: date | None = None) -> pd.DataFrame:
        stock_basic_table = "reference.stock_basic"
        available_columns = set(self.get_table_columns(stock_basic_table, engine=self.reference_engine))
        if "ts_code" not in available_columns:
            return self._derive_security_metadata_from_daily(ts_codes)

        fixed_columns = ["ts_code", "list_date", "board"]
        passthrough_candidates = ["name", "area", "industry", "market"]
        selected = [c for c in fixed_columns if c in available_columns]
        selected.extend(c for c in passthrough_candidates if c in available_columns)

        query = f"""
            SELECT {", ".join(self.validate_columns(selected))}
            FROM {self.qualified_table(stock_basic_table)}
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
        frame = pd.read_sql_query(sql=text(query), con=self.reference_engine, params=params)

        frame_ts_codes = frame["ts_code"]
        frame["is_suspended"] = frame_ts_codes.isin(
            self._query_status_ts_codes("reference.stock_suspend", ts_codes, mode="latest_trade_date", as_of=as_of)
        )
        frame["is_st"] = frame_ts_codes.isin(
            self._query_status_ts_codes("reference.stock_st", ts_codes, mode="latest_trade_date", as_of=as_of)
        )
        frame["is_risk_warning"] = frame_ts_codes.isin(
            self._query_status_ts_codes("reference.stock_risk_warning", ts_codes, mode="active_range", as_of=as_of)
        )
        return frame

    def _query_status_ts_codes(
        self, table_name: str, ts_codes: list[str] | None, *, mode: str, as_of: date | None = None
    ) -> set[str]:
        if not self.table_exists(table_name, engine=self.reference_engine):
            return set()
        columns = set(self.get_table_columns(table_name, engine=self.reference_engine))
        if "ts_code" not in columns:
            return set()

        if mode == "latest_trade_date":
            if "trade_date" not in columns:
                return set()
            as_of_clause = ""
            if as_of is not None:
                as_of_clause = " AND trade_date <= :as_of_date"
            query = f"""
                SELECT DISTINCT ts_code
                FROM {self.qualified_table(table_name)}
                WHERE trade_date = (SELECT MAX(trade_date) FROM {self.qualified_table(table_name)} WHERE 1=1{as_of_clause})
            """
        elif mode == "active_range":
            if "start_date" not in columns:
                return set()
            date_expr = ":as_of_date" if as_of is not None else "CURRENT_DATE"
            where_parts = [f"start_date <= {date_expr}"]
            if "end_date" in columns:
                where_parts.append(f"(end_date IS NULL OR end_date >= {date_expr})")
            query = f"""
                SELECT DISTINCT ts_code
                FROM {self.qualified_table(table_name)}
                WHERE {' AND '.join(where_parts)}
            """
        else:
            return set()

        params: dict[str, object] = {}
        if as_of is not None:
            params["as_of_date"] = as_of
        if ts_codes:
            placeholders = []
            for index, ts_code in enumerate(ts_codes):
                key = f"ts_code_{index}"
                placeholders.append(f":{key}")
                params[key] = ts_code
            query += f" AND ts_code IN ({', '.join(placeholders)})"

        result = pd.read_sql_query(sql=text(query), con=self.reference_engine, params=params)
        return set(result["ts_code"].tolist())

    def _load_reference_daily_basic_snapshot(
        self, ts_codes: list[str] | None, *, as_of: date | None = None
    ) -> pd.DataFrame:
        table_name = "reference.daily_basic"
        if not self.table_exists(table_name, engine=self.reference_engine):
            return pd.DataFrame()

        available_columns = set(self.get_table_columns(table_name, engine=self.reference_engine))
        candidates = ["total_mv", "circ_mv", "turnover_rate", "turnover_rate_f", "volume_ratio"]
        selected = [c for c in candidates if c in available_columns]
        if not selected:
            return pd.DataFrame()

        as_of_clause = ""
        params: dict[str, object] = {}
        if as_of is not None:
            as_of_clause = " AND trade_date <= :as_of_date"
            params["as_of_date"] = as_of

        query = f"""
            SELECT db.ts_code, {", ".join(f"db.{self.validate_identifier(c)}" for c in selected)}
            FROM {self.qualified_table(table_name)} db
            INNER JOIN (
                SELECT ts_code, MAX(trade_date) AS max_date
                FROM {self.qualified_table(table_name)}
                WHERE 1=1{as_of_clause}
                GROUP BY ts_code
            ) latest ON db.ts_code = latest.ts_code AND db.trade_date = latest.max_date
        """
        if ts_codes:
            placeholders = []
            for index, ts_code in enumerate(ts_codes):
                key = f"ts_code_{index}"
                placeholders.append(f":{key}")
                params[key] = ts_code
            query += f" WHERE db.ts_code IN ({', '.join(placeholders)})"
        query += " ORDER BY db.ts_code"
        return pd.read_sql_query(sql=text(query), con=self.reference_engine, params=params)

    @staticmethod
    def _compute_market_cap_bucket(series: pd.Series) -> pd.Series:
        """total_mv in 万元 (10k RMB): small < 50亿, mid 50-500亿, large >= 500亿."""
        buckets = pd.Series("small", index=series.index)
        buckets[series >= 5_000_000] = "mid"
        buckets[series >= 50_000_000] = "large"
        buckets[series.isna()] = pd.NA
        return buckets

    @staticmethod
    def _compute_liquidity_bucket(series: pd.Series) -> pd.Series:
        """turnover_rate_f in %: low < 1%, mid 1-5%, high >= 5%."""
        buckets = pd.Series("low", index=series.index)
        buckets[series >= 1.0] = "mid"
        buckets[series >= 5.0] = "high"
        buckets[series.isna()] = pd.NA
        return buckets

    @staticmethod
    def _compute_industry_group(series: pd.Series) -> pd.Series:
        """Normalize raw industry: trim whitespace, empty string -> NA."""
        result = series.astype(str).str.strip()
        result[result == ""] = pd.NA
        result[series.isna()] = pd.NA
        return result

    def _load_reference_index_weight_snapshot(
        self, index_code: str, ts_codes: list[str] | None, *, as_of: date | None = None
    ) -> pd.DataFrame:
        table_name = "reference.index_weight"
        if not self.table_exists(table_name, engine=self.reference_engine):
            return pd.DataFrame()

        columns = set(self.get_table_columns(table_name, engine=self.reference_engine))
        if "con_code" not in columns:
            return pd.DataFrame()

        weight_col = "weight" if "weight" in columns else None
        if weight_col is None:
            return pd.DataFrame()

        self.validate_identifier(weight_col)

        as_of_clause = ""
        params: dict[str, object] = {"index_code": index_code}
        if as_of is not None:
            as_of_clause = " AND trade_date <= :as_of_date"
            params["as_of_date"] = as_of

        query = f"""
            SELECT iw.con_code AS ts_code, :index_code AS benchmark_code,
                   iw.{weight_col} AS benchmark_weight
            FROM {self.qualified_table(table_name)} iw
            INNER JOIN (
                SELECT con_code, MAX(trade_date) AS max_date
                FROM {self.qualified_table(table_name)}
                WHERE index_code = :index_code{as_of_clause}
                GROUP BY con_code
            ) latest ON iw.con_code = latest.con_code AND iw.trade_date = latest.max_date
            WHERE iw.index_code = :index_code
        """
        if ts_codes:
            placeholders = []
            for i, ts_code in enumerate(ts_codes):
                key = f"ts_code_{i}"
                placeholders.append(f":{key}")
                params[key] = ts_code
            query += f" AND iw.con_code IN ({', '.join(placeholders)})"
        query += " ORDER BY iw.con_code"

        frame = pd.read_sql_query(sql=text(query), con=self.reference_engine, params=params)
        frame["benchmark_code"] = frame["benchmark_code"].astype(str)
        frame["is_benchmark_member"] = True
        return frame[["ts_code", "benchmark_code", "benchmark_weight", "is_benchmark_member"]]

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
