from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

DEFAULT_STOCK_BASIC_FIELDS = "ts_code,symbol,name,area,industry,list_date"

# Canonical columns for a normalized security snapshot. These match the
# fixed columns expected by PostgresDataStore._normalize_security_metadata.
SNAPSHOT_FIXED_COLUMNS: list[str] = [
    "ts_code",
    "list_date",
    "board",
    "is_st",
    "is_risk_warning",
    "is_suspended",
]


@dataclass(slots=True)
class SmokeResult:
    name: str
    ok: bool
    message: str


@dataclass(slots=True)
class SecuritySnapshot:
    """Canonical security metadata snapshot from Tushare sources.

    Passthrough carries any extra source columns that are not part of the
    fixed set. Future bulk ingestion can use this shape without inventing
    semantics or touching PostgreSQL.
    """

    ts_code: str
    list_date: str | None = None
    board: str | None = None
    is_st: bool = False
    is_risk_warning: bool = False
    is_suspended: bool = False
    passthrough: dict[str, object] = field(default_factory=dict)


class TushareProClient(Protocol):
    def stock_basic(self, **kwargs: object) -> pd.DataFrame: ...

    def suspend_d(self, **kwargs: object) -> pd.DataFrame: ...

    def stock_st(self, **kwargs: object) -> pd.DataFrame: ...

    def stk_alert(self, **kwargs: object) -> pd.DataFrame: ...


def format_frame(frame: pd.DataFrame, *, head: int) -> str:
    rows = len(frame)
    columns = list(frame.columns)
    preview = frame.head(head).to_string(index=False) if rows else "<empty>"
    return f"rows={rows} cols={columns}\n{preview}"


def derive_board(ts_code: str) -> str:
    """Infer A-share board from ts_code patterns."""
    suffix = ts_code.rsplit(".", maxsplit=1)[-1].upper() if "." in ts_code else ""
    if suffix == "BJ":
        return "beijing"
    symbol = ts_code.split(".", maxsplit=1)[0]
    if symbol.startswith("688"):
        return "star_market"
    if symbol.startswith(("300", "301")):
        return "chinext"
    return "main_board"


def normalize_snapshot_frame(
    source: TushareSecuritySource,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Build a canonical security snapshot DataFrame from Tushare sources.

    Merges stock_basic with suspend_d for the given trade_date. ST and
    risk-warning endpoints are probed but treated as optional — when
    permission-blocked, the corresponding boolean columns default to False.

    Returns a DataFrame with SNAPSHOT_FIXED_COLUMNS followed by any
    passthrough columns from the source frames (e.g. symbol, name, area,
    industry from stock_basic).
    """
    basic = source.fetch_stock_basic()
    if basic.empty:
        return pd.DataFrame(columns=SNAPSHOT_FIXED_COLUMNS)

    snapshot = pd.DataFrame()
    snapshot["ts_code"] = basic["ts_code"]
    snapshot["list_date"] = basic.get("list_date", pd.NA)
    snapshot["board"] = snapshot["ts_code"].map(derive_board)

    # Suspension status: True when a row exists in suspend_d for this trade_date.
    try:
        susp = source.fetch_suspend_d(trade_date=trade_date)
    except Exception:
        susp = pd.DataFrame()
    if not susp.empty and "ts_code" in susp.columns:
        suspended_codes = set(susp["ts_code"].dropna().unique())
        snapshot["is_suspended"] = snapshot["ts_code"].isin(suspended_codes)
    else:
        snapshot["is_suspended"] = False

    # ST and risk-warning are optional — permission-blocked endpoints raise.
    snapshot["is_st"] = _probe_bool_endpoint(
        source, "fetch_stock_st", trade_date, snapshot["ts_code"]
    )
    snapshot["is_risk_warning"] = _probe_bool_endpoint(
        source, "fetch_stk_alert", trade_date, snapshot["ts_code"]
    )

    # Preserve passthrough columns from stock_basic.
    fixed_set = set(SNAPSHOT_FIXED_COLUMNS)
    passthrough_cols = sorted(c for c in basic.columns if c not in fixed_set)
    for col in passthrough_cols:
        snapshot[col] = basic[col]

    return snapshot.sort_values("ts_code").reset_index(drop=True)


def _probe_bool_endpoint(
    source: TushareSecuritySource,
    method: str,
    trade_date: str,
    ts_codes: pd.Series,
) -> pd.Series:
    try:
        frame = getattr(source, method)(trade_date=trade_date)
    except Exception:
        return pd.Series(False, index=ts_codes.index)
    if frame.empty or "ts_code" not in frame.columns:
        return pd.Series(False, index=ts_codes.index)
    flagged = set(frame["ts_code"].dropna().unique())
    return ts_codes.isin(flagged)


class TushareSecuritySource:
    def __init__(self, pro: TushareProClient) -> None:
        self.pro = pro

    def fetch_stock_basic(self) -> pd.DataFrame:
        return self.pro.stock_basic(
            exchange="SSE",
            list_status="L",
            fields=DEFAULT_STOCK_BASIC_FIELDS,
        )

    def fetch_suspend_d(self, *, trade_date: str) -> pd.DataFrame:
        return self.pro.suspend_d(trade_date=trade_date)

    def fetch_stock_st(self, *, trade_date: str) -> pd.DataFrame:
        return self.pro.stock_st(trade_date=trade_date)

    def fetch_stk_alert(self, *, trade_date: str) -> pd.DataFrame:
        return self.pro.stk_alert(trade_date=trade_date)

    def probe(self, *, trade_date: str, head: int) -> list[SmokeResult]:
        return [
            self._try_call("stock_basic", self.fetch_stock_basic, head=head),
            self._try_call(
                "suspend_d",
                lambda: self.fetch_suspend_d(trade_date=trade_date),
                head=head,
            ),
            self._try_call(
                "stock_st",
                lambda: self.fetch_stock_st(trade_date=trade_date),
                head=head,
            ),
            self._try_call(
                "stk_alert",
                lambda: self.fetch_stk_alert(trade_date=trade_date),
                head=head,
            ),
        ]

    @staticmethod
    def _try_call(name: str, func, *, head: int) -> SmokeResult:
        try:
            frame = func()
        except Exception as exc:  # pragma: no cover - smoke path
            return SmokeResult(name=name, ok=False, message=repr(exc))
        return SmokeResult(name=name, ok=True, message=format_frame(frame, head=head))
