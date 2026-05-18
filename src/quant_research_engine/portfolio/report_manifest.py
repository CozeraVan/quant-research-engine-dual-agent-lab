from __future__ import annotations

import json
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SUPPORTED_MANIFEST_KINDS = {
    "batch_backtest_report_manifest",
    "shared_cash_backtest_report_manifest",
}

_REQUIRED_COLUMNS_BY_ROLE = {
    "orders": {"symbol", "trade_date"},
    "trades": {"symbol"},
    "failed_orders": {"symbol", "trade_date", "side", "quantity", "price", "notional", "reason"},
    "equity_curve": {"trade_date"},
    "window_metrics": {"window", "total_return"},
    "rolling_metrics": {"window_size", "end_date", "total_return"},
    "rolling_summary": {"window_size", "end_date", "symbol_count"},
    "window_summary": {"window", "symbol_count"},
    "group_summary": {"symbol_count"},
    "window_ranked_symbols": {"window", "rank_type", "rank", "symbol", "total_return"},
    "group_ranked_symbols": {"rank_type", "rank", "symbol", "total_return"},
    "rolling_ranked_symbols": {"window_size", "end_date", "rank_type", "rank", "symbol", "total_return"},
}


@dataclass(frozen=True)
class ReportFile:
    key: str
    path: str
    filename: str
    role: str
    symbol: str | None = None
    window: str | None = None
    group_by: str | None = None

    _REQUIRED_FIELDS = ("key", "path", "filename", "role")

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> ReportFile:
        for field in cls._REQUIRED_FIELDS:
            if field not in mapping:
                entry_key = mapping.get("key", "<missing key>")
                raise ValueError(
                    f"manifest file entry missing required field {field!r} (entry key: {entry_key!r})"
                )
        return cls(
            key=str(mapping["key"]),
            path=str(mapping["path"]),
            filename=str(mapping["filename"]),
            role=str(mapping["role"]),
            symbol=_optional_string(mapping.get("symbol")),
            window=_optional_string(mapping.get("window")),
            group_by=_optional_string(mapping.get("group_by")),
        )


@dataclass(frozen=True)
class ReportValidationIssue:
    key: str
    path: Path
    code: str
    message: str


@dataclass(frozen=True)
class ReportManifest:
    kind: str
    files_: tuple[ReportFile, ...]
    base_dir: Path
    schema_version: int | None = None

    @classmethod
    def from_path(cls, path: str | Path) -> ReportManifest:
        manifest_path = Path(path)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        kind = payload.get("kind")
        if kind not in _SUPPORTED_MANIFEST_KINDS:
            supported = ", ".join(sorted(_SUPPORTED_MANIFEST_KINDS))
            raise ValueError(f"manifest kind must be one of: {supported}")
        schema_version = payload.get("schema_version")
        if schema_version is not None and not (type(schema_version) is int and schema_version == 1):
            raise ValueError(
                f"unsupported manifest schema_version: {schema_version!r} (expected 1 or absent)"
            )
        return cls(
            kind=kind,
            files_=tuple(ReportFile.from_mapping(item) for item in payload.get("files", [])),
            base_dir=manifest_path.parent,
            schema_version=schema_version,
        )

    def files(
        self,
        role: str | None = None,
        symbol: str | None = None,
        window: str | None = None,
        group_by: str | None = None,
    ) -> list[ReportFile]:
        return [
            entry
            for entry in self.files_
            if _matches(entry.role, role)
            and _matches(entry.symbol, symbol)
            and _matches(entry.window, window)
            and _matches(entry.group_by, group_by)
        ]

    def paths(
        self,
        role: str | None = None,
        symbol: str | None = None,
        window: str | None = None,
        group_by: str | None = None,
    ) -> list[Path]:
        return [self.base_dir / entry.path for entry in self.files(role, symbol, window, group_by)]

    def validate_contents(
        self,
        role: str | None = None,
        symbol: str | None = None,
        window: str | None = None,
        group_by: str | None = None,
    ) -> list[ReportValidationIssue]:
        issues: list[ReportValidationIssue] = []
        for entry in self.files(role=role, symbol=symbol, window=window, group_by=group_by):
            path = self.base_dir / entry.path
            if not path.exists():
                issues.append(
                    ReportValidationIssue(
                        key=entry.key,
                        path=path,
                        code="missing_file",
                        message=f"missing file: {path}",
                    )
                )
                continue
            if entry.role == "summary" and path.suffix == ".json":
                issues.extend(_validate_json_object(entry, path))
                continue
            required_columns = _REQUIRED_COLUMNS_BY_ROLE.get(entry.role)
            if required_columns is not None and path.suffix == ".csv":
                issues.extend(_validate_csv_columns(entry, path, required_columns))
        return issues


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _matches(value: str | None, expected: str | None) -> bool:
    return expected is None or value == expected


def _validate_json_object(entry: ReportFile, path: Path) -> list[ReportValidationIssue]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [
            ReportValidationIssue(
                key=entry.key,
                path=path,
                code="invalid_json",
                message=f"invalid JSON: {exc}",
            )
        ]
    if not isinstance(payload, dict):
        return [
            ReportValidationIssue(
                key=entry.key,
                path=path,
                code="invalid_json_object",
                message="summary JSON must be an object",
            )
        ]
    return []


def _validate_csv_columns(entry: ReportFile, path: Path, required_columns: set[str]) -> list[ReportValidationIssue]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
    except Exception as exc:
        return [
            ReportValidationIssue(
                key=entry.key,
                path=path,
                code="invalid_csv",
                message=f"invalid CSV: {exc}",
            )
        ]
    missing = sorted(required_columns.difference(header))
    if missing:
        return [
            ReportValidationIssue(
                key=entry.key,
                path=path,
                code="missing_columns",
                message=f"missing columns: {', '.join(missing)}",
            )
        ]
    return []
