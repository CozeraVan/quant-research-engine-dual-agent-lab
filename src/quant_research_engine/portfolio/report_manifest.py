from __future__ import annotations

import json
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_VALID_PREFLIGHT_STATUSES = {"ok", "warning", "error"}

_SUPPORTED_MANIFEST_KINDS = {
    "batch_backtest_report_manifest",
    "shared_cash_backtest_report_manifest",
    "evaluation_report_manifest",
    "strategy_smoke_report_manifest",
    "research_run_report_manifest",
    "strategy_fit_report_manifest",
    "strategy_refresh_delta_manifest",
}

_RUN_MANIFEST_KINDS = {
    "portfolio_backtest_run_manifest",
    "evaluation_run_manifest",
    "research_run_manifest",
}

_BATCH_GROUPED_ROLES = {
    "group_summary",
    "group_ranked_symbols",
    "window_summary",
    "window_ranked_symbols",
    "rolling_summary",
    "rolling_ranked_symbols",
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
    "events": {"ts_code", "trade_date"},
    "evaluation_summary": {"horizon", "event_count"},
    "ic_summary": {"factor", "horizon", "observation_dates"},
    "quantile_summary": {"factor", "horizon", "quantile", "row_count"},
    "evaluation_group_summary": {"group_by", "group_value", "horizon", "event_count"},
    "random_baseline_summary": {"horizon", "event_count"},
    "factor_decay_summary": {"factor", "horizon", "base_horizon"},
    "regime_summary": {"regime", "horizon", "event_count"},
    "shared_orders_group_summary": {"group_by", "group_value", "order_count"},
    "shared_trades_group_summary": {"group_by", "group_value", "trade_count"},
    "shared_failed_orders_group_summary": {"group_by", "group_value", "failed_order_count"},
    "trades_ledger": {"symbol", "trade_date", "side"},
    "round_trips": {"symbol", "entry_date", "exit_date"},
    "symbol_performance": {"symbol", "trade_count"},
    "full_market_equity_curve": {"trade_date", "total_equity"},
    "drawdown_curve": {"trade_date", "total_equity"},
    "full_market_report_workbook": set(),
    "strategy_performance": set(),
    "trade_analysis": set(),
    "capital_usage": set(),
    "equity_curve_chart": set(),
    "drawdown_curve_chart": set(),
    "html_report": set(),
    "strategy_fit_summary": {"strategy_id", "eligible_symbols", "meta_tier"},
    "strategy_fit_stocks": {"strategy_id", "symbol", "tier", "binomial_p", "total_return", "buy_hold_return", "excess_return_vs_buy_hold"},
    "strategy_fit_classes": {"strategy_id", "dimension", "class_value", "p_value", "q_value"},
    "strategy_fit_report": set(),
    "refresh_delta_report": set(),
    "refresh_delta_markdown": set(),
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
    window_size: int | None = None

    _REQUIRED_FIELDS = ("key", "path", "filename", "role")

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> ReportFile:
        for field in cls._REQUIRED_FIELDS:
            if field not in mapping:
                entry_key = mapping.get("key", "<missing key>")
                raise ValueError(
                    f"manifest file entry missing required field {field!r} (entry key: {entry_key!r})"
                )
        entry_key = mapping["key"]
        if not isinstance(entry_key, str):
            raise ValueError(
                f"manifest file entry field 'key' must be a string, got {type(entry_key).__name__}"
            )
        for field in ("path", "filename", "role"):
            value = mapping[field]
            if not isinstance(value, str):
                raise ValueError(
                    f"manifest file entry field {field!r} must be a string, got {type(value).__name__} (entry key: {entry_key!r})"
                )
        for field in ("symbol", "window", "group_by"):
            value = mapping.get(field)
            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"manifest file entry field {field!r} must be a string or null, got {type(value).__name__} (entry key: {entry_key!r})"
                )
        window_size_value = mapping.get("window_size")
        if window_size_value is not None and type(window_size_value) is not int:
            raise ValueError(
                f"manifest file entry field 'window_size' must be an integer or null, "
                f"got {type(window_size_value).__name__} (entry key: {entry_key!r})"
            )
        return cls(
            key=entry_key,
            path=mapping["path"],
            filename=mapping["filename"],
            role=mapping["role"],
            symbol=_optional_string(mapping.get("symbol")),
            window=_optional_string(mapping.get("window")),
            group_by=_optional_string(mapping.get("group_by")),
            window_size=window_size_value,
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
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"manifest contains invalid JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(
                f"manifest root must be an object, got {type(payload).__name__}"
            )
        if "kind" not in payload:
            raise ValueError("manifest missing top-level 'kind' field")
        kind = payload["kind"]
        if not isinstance(kind, str):
            raise ValueError(
                f"manifest 'kind' must be a string, got {type(kind).__name__}"
            )
        if kind not in _SUPPORTED_MANIFEST_KINDS:
            supported = ", ".join(sorted(_SUPPORTED_MANIFEST_KINDS))
            raise ValueError(f"manifest kind must be one of: {supported}")
        schema_version = payload.get("schema_version")
        if schema_version is not None and not (type(schema_version) is int and schema_version == 1):
            raise ValueError(
                f"unsupported manifest schema_version: {schema_version!r} (expected 1 or absent)"
            )
        if "files" not in payload:
            raise ValueError("manifest missing top-level 'files' field")
        raw_files = payload["files"]
        if not isinstance(raw_files, list):
            raise ValueError(
                f"manifest 'files' must be a list, got {type(raw_files).__name__}"
            )
        for idx, item in enumerate(raw_files):
            if not isinstance(item, dict):
                raise ValueError(
                    f"manifest file entry {idx} must be an object, got {type(item).__name__}"
                )
        return cls(
            kind=kind,
            files_=tuple(ReportFile.from_mapping(item) for item in raw_files),
            base_dir=manifest_path.parent,
            schema_version=schema_version,
        )

    def files(
        self,
        role: str | None = None,
        symbol: str | None = None,
        window: str | None = None,
        group_by: str | None = None,
        window_size: int | None = None,
    ) -> list[ReportFile]:
        return [
            entry
            for entry in self.files_
            if _matches(entry.role, role)
            and _matches(entry.symbol, symbol)
            and _matches(entry.window, window)
            and _matches(entry.group_by, group_by)
            and _matches_int(entry.window_size, window_size)
        ]

    def paths(
        self,
        role: str | None = None,
        symbol: str | None = None,
        window: str | None = None,
        group_by: str | None = None,
        window_size: int | None = None,
    ) -> list[Path]:
        return [self.base_dir / entry.path for entry in self.files(role, symbol, window, group_by, window_size=window_size)]

    def validate_contents(
        self,
        role: str | None = None,
        symbol: str | None = None,
        window: str | None = None,
        group_by: str | None = None,
        window_size: int | None = None,
    ) -> list[ReportValidationIssue]:
        issues: list[ReportValidationIssue] = []
        for entry in self.files(role=role, symbol=symbol, window=window, group_by=group_by, window_size=window_size):
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
            if self.kind == "research_run_report_manifest" and entry.role in {"eval_report_manifest", "backtest_report_manifest"}:
                issues.extend(_validate_nested_report_manifest(entry, path))
                continue
            if self.kind == "research_run_report_manifest" and entry.role == "preflight_report":
                issues.extend(_validate_preflight_report(entry, path))
                continue
            if path.suffix == ".json" and entry.role == "summary":
                issues.extend(_validate_json_object(entry, path))
                continue
            if path.suffix == ".json" and entry.role == "run_manifest":
                issues.extend(_validate_run_manifest(entry, path))
                continue
            required_columns = _REQUIRED_COLUMNS_BY_ROLE.get(entry.role)
            if required_columns is not None and path.suffix == ".csv":
                column_issues = _validate_csv_columns(entry, path, required_columns)
                issues.extend(column_issues)
                if not column_issues and entry.group_by is not None:
                    if entry.role in _BATCH_GROUPED_ROLES:
                        issues.extend(_validate_csv_batch_group_by_header(entry, path))
                    else:
                        issues.extend(_validate_csv_group_by_consistency(entry, path))
        return issues


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _matches(value: str | None, expected: str | None) -> bool:
    return expected is None or value == expected


def _matches_int(value: int | None, expected: int | None) -> bool:
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


def _validate_run_manifest(entry: ReportFile, path: Path) -> list[ReportValidationIssue]:
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
                message="run manifest must be an object",
            )
        ]

    issues: list[ReportValidationIssue] = []

    required_fields = {
        "schema_version": "schema_version",
        "kind": "kind",
        "run_id": "run_id",
        "command": "command",
        "strategy_path": "strategy_path",
        "artifacts": "artifacts",
    }
    for field_key, field_label in required_fields.items():
        if field_key not in payload:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="missing_run_manifest_field",
                    message=f"run manifest missing required field {field_label!r}",
                )
            )

    # Validate schema_version (must be integer 1, not null)
    if "schema_version" in payload:
        schema_version = payload["schema_version"]
        if schema_version is None:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message="run manifest schema_version must be 1, got null",
                )
            )
        elif type(schema_version) is not int or schema_version != 1:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message=f"run manifest schema_version must be 1, got {schema_version!r}",
                )
            )

    # Validate kind (must be a string and one of the supported run-manifest kinds, not null)
    if "kind" in payload:
        kind = payload["kind"]
        if kind is None:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message="run manifest kind must be a string, got null",
                )
            )
        elif not isinstance(kind, str):
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message=f"run manifest kind must be a string, got {type(kind).__name__}",
                )
            )
        elif kind not in _RUN_MANIFEST_KINDS:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message=f"unsupported run manifest kind: {kind!r}",
                )
            )

    # Validate run_id (must be string or null)
    if "run_id" in payload:
        run_id = payload["run_id"]
        if run_id is not None and not isinstance(run_id, str):
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message=f"run manifest run_id must be a string or null, got {type(run_id).__name__}",
                )
            )

    # Validate command (must be string, not null)
    if "command" in payload:
        command = payload["command"]
        if command is None:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message="run manifest command must be a string, got null",
                )
            )
        elif not isinstance(command, str):
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message=f"run manifest command must be a string, got {type(command).__name__}",
                )
            )

    # Validate strategy_path (must be string, not null)
    if "strategy_path" in payload:
        strategy_path = payload["strategy_path"]
        if strategy_path is None:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message="run manifest strategy_path must be a string, got null",
                )
            )
        elif not isinstance(strategy_path, str):
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message=f"run manifest strategy_path must be a string, got {type(strategy_path).__name__}",
                )
            )

    # Validate artifacts (must be a list of strings, not null)
    if "artifacts" in payload:
        artifacts = payload["artifacts"]
        if artifacts is None:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message="run manifest artifacts must be a list, got null",
                )
            )
        elif not isinstance(artifacts, list):
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_run_manifest_field",
                    message=f"run manifest artifacts must be a list, got {type(artifacts).__name__}",
                )
            )
        else:
            for idx, item in enumerate(artifacts):
                if not isinstance(item, str):
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="invalid_run_manifest_field",
                            message=f"run manifest artifacts[{idx}] must be a string, got {type(item).__name__}",
                        )
                    )

    return issues


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


def _validate_csv_group_by_consistency(entry: ReportFile, path: Path) -> list[ReportValidationIssue]:
    mismatched_values: set[str] = set()
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            if "group_by" not in header:
                return []
            group_by_idx = header.index("group_by")
            for row in reader:
                if len(row) <= group_by_idx:
                    continue
                cell = row[group_by_idx].strip()
                if cell and cell != entry.group_by:
                    mismatched_values.add(cell)
    except Exception:
        return []

    if mismatched_values:
        return [
            ReportValidationIssue(
                key=entry.key,
                path=path,
                code="group_by_mismatch",
                message=(
                    f"manifest group_by={entry.group_by!r} but CSV contains "
                    f"group_by value(s): {', '.join(sorted(mismatched_values))}"
                ),
            )
        ]
    return []


def _validate_csv_batch_group_by_header(entry: ReportFile, path: Path) -> list[ReportValidationIssue]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
    except Exception:
        return []

    if entry.group_by in header:
        return []

    return [
        ReportValidationIssue(
            key=entry.key,
            path=path,
            code="group_by_header_mismatch",
            message=(
                f"manifest group_by={entry.group_by!r} but CSV header "
                f"does not contain column {entry.group_by!r} "
                f"(columns: {', '.join(header) if header else '<empty>'})"
            ),
        )
    ]


def _validate_nested_report_manifest(entry: ReportFile, path: Path) -> list[ReportValidationIssue]:
    """Recursively validate a nested stage report manifest referenced by a research-run root manifest.

    Called when ``ReportManifest.kind == "research_run_report_manifest"`` and a root
    entry has role ``eval_report_manifest`` or ``backtest_report_manifest``.
    """
    try:
        nested = ReportManifest.from_path(path)
    except (ValueError, json.JSONDecodeError) as exc:
        return [
            ReportValidationIssue(
                key=entry.key,
                path=path,
                code="invalid_nested_report_manifest",
                message=f"nested report manifest (key={entry.key!r}) could not be parsed: {exc}",
            )
        ]
    nested_issues = nested.validate_contents()
    return [
        ReportValidationIssue(
            key=entry.key,
            path=issue.path,
            code="nested_report_manifest_issue",
            message=f"[{entry.key}] {issue.key}: [{issue.code}] {issue.message}",
        )
        for issue in nested_issues
    ]


def _validate_preflight_report(entry: ReportFile, path: Path) -> list[ReportValidationIssue]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [
            ReportValidationIssue(
                key=entry.key,
                path=path,
                code="invalid_preflight_report_json",
                message=f"invalid JSON: {exc}",
            )
        ]
    if not isinstance(payload, dict):
        return [
            ReportValidationIssue(
                key=entry.key,
                path=path,
                code="invalid_preflight_report_object",
                message="preflight report must be an object",
            )
        ]

    issues: list[ReportValidationIssue] = []

    # Root status: required, must be a non-empty string in the accepted set.
    if "status" not in payload:
        issues.append(
            ReportValidationIssue(
                key=entry.key,
                path=path,
                code="missing_preflight_report_field",
                message="preflight report missing required field 'status'",
            )
        )
    else:
        status = payload["status"]
        if not isinstance(status, str) or not status:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_preflight_report_field",
                    message=f"preflight report 'status' must be a non-empty string, got {type(status).__name__}",
                )
            )
        elif status not in _VALID_PREFLIGHT_STATUSES:
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_preflight_report_field",
                    message=f"preflight report 'status' must be one of {sorted(_VALID_PREFLIGHT_STATUSES)}, got {status!r}",
                )
            )

    # checks: optional list of well-shaped check objects.
    if "checks" in payload:
        checks = payload["checks"]
        if not isinstance(checks, list):
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_preflight_report_field",
                    message=f"preflight report 'checks' must be a list, got {type(checks).__name__}",
                )
            )
        else:
            for idx, item in enumerate(checks):
                if not isinstance(item, dict):
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="invalid_preflight_report_check",
                            message=f"preflight report checks[{idx}] must be an object, got {type(item).__name__}",
                        )
                    )
                    continue
                # name: required, non-empty string
                if "name" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_check_field",
                            message=f"preflight report checks[{idx}] missing required field 'name'",
                        )
                    )
                else:
                    if not isinstance(item["name"], str) or not item["name"]:
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_check",
                                message=f"preflight report checks[{idx}] 'name' must be a non-empty string, got {type(item['name']).__name__}",
                            )
                        )
                # status: required, must be ok/warning/error
                if "status" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_check_field",
                            message=f"preflight report checks[{idx}] missing required field 'status'",
                        )
                    )
                else:
                    check_status = item["status"]
                    if not isinstance(check_status, str):
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_check",
                                message=f"preflight report checks[{idx}] 'status' must be a string, got {type(check_status).__name__}",
                            )
                        )
                    elif check_status not in _VALID_PREFLIGHT_STATUSES:
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_check",
                                message=f"preflight report checks[{idx}] 'status' must be one of {sorted(_VALID_PREFLIGHT_STATUSES)}, got {check_status!r}",
                            )
                        )
                # message: required string
                if "message" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_check_field",
                            message=f"preflight report checks[{idx}] missing required field 'message'",
                        )
                    )
                else:
                    if not isinstance(item["message"], str):
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_check",
                                message=f"preflight report checks[{idx}] 'message' must be a string, got {type(item['message']).__name__}",
                            )
                        )

    # missing_factor_requests: optional list of well-shaped request objects.
    if "missing_factor_requests" in payload:
        requests = payload["missing_factor_requests"]
        if not isinstance(requests, list):
            issues.append(
                ReportValidationIssue(
                    key=entry.key,
                    path=path,
                    code="invalid_preflight_report_field",
                    message=f"preflight report 'missing_factor_requests' must be a list, got {type(requests).__name__}",
                )
            )
        else:
            for idx, item in enumerate(requests):
                if not isinstance(item, dict):
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="invalid_preflight_report_missing_factor_request",
                            message=f"preflight report missing_factor_requests[{idx}] must be an object, got {type(item).__name__}",
                        )
                    )
                    continue
                # strategy_id: required, non-empty string
                if "strategy_id" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_missing_factor_field",
                            message=f"preflight report missing_factor_requests[{idx}] missing required field 'strategy_id'",
                        )
                    )
                else:
                    if not isinstance(item["strategy_id"], str) or not item["strategy_id"]:
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_missing_factor_request",
                                message=f"preflight report missing_factor_requests[{idx}] 'strategy_id' must be a non-empty string, got {type(item['strategy_id']).__name__}",
                            )
                        )
                # alias: required, non-empty string
                if "alias" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_missing_factor_field",
                            message=f"preflight report missing_factor_requests[{idx}] missing required field 'alias'",
                        )
                    )
                else:
                    if not isinstance(item["alias"], str) or not item["alias"]:
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_missing_factor_request",
                                message=f"preflight report missing_factor_requests[{idx}] 'alias' must be a non-empty string, got {type(item['alias']).__name__}",
                            )
                        )
                # indicator: required, non-empty string
                if "indicator" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_missing_factor_field",
                            message=f"preflight report missing_factor_requests[{idx}] missing required field 'indicator'",
                        )
                    )
                else:
                    if not isinstance(item["indicator"], str) or not item["indicator"]:
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_missing_factor_request",
                                message=f"preflight report missing_factor_requests[{idx}] 'indicator' must be a non-empty string, got {type(item['indicator']).__name__}",
                            )
                        )
                # expected_table: required, non-empty string
                if "expected_table" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_missing_factor_field",
                            message=f"preflight report missing_factor_requests[{idx}] missing required field 'expected_table'",
                        )
                    )
                else:
                    if not isinstance(item["expected_table"], str) or not item["expected_table"]:
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_missing_factor_request",
                                message=f"preflight report missing_factor_requests[{idx}] 'expected_table' must be a non-empty string, got {type(item['expected_table']).__name__}",
                            )
                        )
                # expected_column: required, non-empty string
                if "expected_column" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_missing_factor_field",
                            message=f"preflight report missing_factor_requests[{idx}] missing required field 'expected_column'",
                        )
                    )
                else:
                    if not isinstance(item["expected_column"], str) or not item["expected_column"]:
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_missing_factor_request",
                                message=f"preflight report missing_factor_requests[{idx}] 'expected_column' must be a non-empty string, got {type(item['expected_column']).__name__}",
                            )
                        )
                # date_range: required object with start/end string fields
                if "date_range" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_missing_factor_field",
                            message=f"preflight report missing_factor_requests[{idx}] missing required field 'date_range'",
                        )
                    )
                else:
                    date_range = item["date_range"]
                    if not isinstance(date_range, dict):
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_missing_factor_request",
                                message=f"preflight report missing_factor_requests[{idx}] 'date_range' must be an object, got {type(date_range).__name__}",
                            )
                        )
                    else:
                        if "start" not in date_range or not isinstance(date_range.get("start"), str) or not date_range.get("start"):
                            issues.append(
                                ReportValidationIssue(
                                    key=entry.key,
                                    path=path,
                                    code="invalid_preflight_report_missing_factor_request",
                                    message=f"preflight report missing_factor_requests[{idx}] 'date_range' must contain a non-empty string 'start'",
                                )
                            )
                        if "end" not in date_range or not isinstance(date_range.get("end"), str) or not date_range.get("end"):
                            issues.append(
                                ReportValidationIssue(
                                    key=entry.key,
                                    path=path,
                                    code="invalid_preflight_report_missing_factor_request",
                                    message=f"preflight report missing_factor_requests[{idx}] 'date_range' must contain a non-empty string 'end'",
                                )
                            )
                # reason: required, non-empty string
                if "reason" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_missing_factor_field",
                            message=f"preflight report missing_factor_requests[{idx}] missing required field 'reason'",
                        )
                    )
                else:
                    if not isinstance(item["reason"], str) or not item["reason"]:
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_missing_factor_request",
                                message=f"preflight report missing_factor_requests[{idx}] 'reason' must be a non-empty string, got {type(item['reason']).__name__}",
                            )
                        )
                # required: must be a boolean
                if "required" not in item:
                    issues.append(
                        ReportValidationIssue(
                            key=entry.key,
                            path=path,
                            code="missing_preflight_report_missing_factor_field",
                            message=f"preflight report missing_factor_requests[{idx}] missing required field 'required'",
                        )
                    )
                else:
                    if type(item["required"]) is not bool:
                        issues.append(
                            ReportValidationIssue(
                                key=entry.key,
                                path=path,
                                code="invalid_preflight_report_missing_factor_request",
                                message=f"preflight report missing_factor_requests[{idx}] 'required' must be a boolean, got {type(item['required']).__name__}",
                            )
                        )

    return issues
