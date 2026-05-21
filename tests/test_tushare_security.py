from __future__ import annotations

import pandas as pd
import pytest

from quant_research_engine.data.tushare_security import (
    TushareSecuritySource,
    SecuritySnapshot,
    SNAPSHOT_FIXED_COLUMNS,
    derive_board,
    format_frame,
    normalize_snapshot_frame,
)


class FakeTusharePro:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def stock_basic(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("stock_basic", kwargs))
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "300001.SZ", "688001.SH", "830001.BJ"],
                "symbol": ["000001", "300001", "688001", "830001"],
                "name": [
                    "Ping An Bank",
                    "Chinext Example",
                    "STAR Example",
                    "Beijing Example",
                ],
                "area": ["Shenzhen", "Beijing", "Shanghai", "Beijing"],
                "industry": ["Banking", "Tech", "Semicon", "Manufacturing"],
                "list_date": ["1991-04-03", "2015-06-01", "2020-01-15", "2022-03-01"],
            }
        )

    def suspend_d(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("suspend_d", kwargs))
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": [kwargs.get("trade_date", "20200312")],
                "suspend_timing": ["A"],
                "suspend_type": ["trade"],
            }
        )

    def stock_st(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("stock_st", kwargs))
        raise RuntimeError("permission denied")

    def stk_alert(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("stk_alert", kwargs))
        raise RuntimeError("permission denied")


class FakeTushareProEmptySuspend:
    """suspend_d returns an empty frame."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def stock_basic(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("stock_basic", kwargs))
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH"],
                "list_date": ["1991-04-03", "2000-01-01"],
            }
        )

    def suspend_d(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("suspend_d", kwargs))
        return pd.DataFrame(columns=["ts_code", "trade_date", "suspend_timing", "suspend_type"])

    def stock_st(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("stock_st", kwargs))
        raise RuntimeError("permission denied")

    def stk_alert(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("stk_alert", kwargs))
        raise RuntimeError("permission denied")


class FakeTushareProAllAvailable:
    """All endpoints return data (no permission blocks)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def stock_basic(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("stock_basic", kwargs))
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "600000.SH", "300001.SZ"],
                "list_date": ["1991-04-03", "2000-01-01", "2015-06-01"],
                "industry": ["Banking", "Finance", "Tech"],
            }
        )

    def suspend_d(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("suspend_d", kwargs))
        return pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "trade_date": [kwargs.get("trade_date", "20200312")],
                "suspend_timing": ["A"],
                "suspend_type": ["trade"],
            }
        )

    def stock_st(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("stock_st", kwargs))
        return pd.DataFrame(
            {
                "ts_code": ["600000.SH"],
                "trade_date": [kwargs.get("trade_date", "20200312")],
                "name": ["ST Example"],
            }
        )

    def stk_alert(self, **kwargs: object) -> pd.DataFrame:
        self.calls.append(("stk_alert", kwargs))
        return pd.DataFrame(
            {
                "ts_code": ["300001.SZ"],
                "trade_date": [kwargs.get("trade_date", "20200312")],
                "name": ["Risk Warn Example"],
            }
        )


# --- format_frame ---


def test_format_frame_includes_rows_columns_and_preview():
    frame = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": ["20200312"]})

    rendered = format_frame(frame, head=1)

    assert "rows=1" in rendered
    assert "ts_code" in rendered
    assert "000001.SZ" in rendered


# --- probe ---


def test_probe_uses_shared_source_wrapper():
    source = TushareSecuritySource(FakeTusharePro())

    results = source.probe(trade_date="20200312", head=1)

    assert [result.name for result in results] == [
        "stock_basic",
        "suspend_d",
        "stock_st",
        "stk_alert",
    ]
    assert results[0].ok is True
    assert results[1].ok is True
    assert results[2].ok is False
    assert results[3].ok is False
    assert "permission denied" in results[2].message
    assert "permission denied" in results[3].message


# --- derive_board ---


def test_derive_board_main_board():
    assert derive_board("000001.SZ") == "main_board"
    assert derive_board("600000.SH") == "main_board"
    assert derive_board("002001.SZ") == "main_board"


def test_derive_board_chinext():
    assert derive_board("300001.SZ") == "chinext"
    assert derive_board("301001.SZ") == "chinext"


def test_derive_board_star_market():
    assert derive_board("688001.SH") == "star_market"


def test_derive_board_beijing():
    assert derive_board("830001.BJ") == "beijing"


# --- SecuritySnapshot ---


def test_security_snapshot_defaults():
    snap = SecuritySnapshot(ts_code="000001.SZ")

    assert snap.ts_code == "000001.SZ"
    assert snap.list_date is None
    assert snap.board is None
    assert snap.is_st is False
    assert snap.is_risk_warning is False
    assert snap.is_suspended is False
    assert snap.passthrough == {}


def test_security_snapshot_with_passthrough():
    snap = SecuritySnapshot(
        ts_code="000001.SZ",
        board="main_board",
        passthrough={"industry": "Banking", "area": "Shenzhen"},
    )

    assert snap.passthrough == {"industry": "Banking", "area": "Shenzhen"}


# --- normalize_snapshot_frame ---


def test_normalize_snapshot_frame_produces_fixed_columns():
    source = TushareSecuritySource(FakeTushareProEmptySuspend())

    frame = normalize_snapshot_frame(source, trade_date="20200312")

    for col in SNAPSHOT_FIXED_COLUMNS:
        assert col in frame.columns


def test_normalize_snapshot_frame_board_inference():
    source = TushareSecuritySource(FakeTusharePro())

    frame = normalize_snapshot_frame(source, trade_date="20200312")

    boards = dict(zip(frame["ts_code"], frame["board"]))
    assert boards["000001.SZ"] == "main_board"
    assert boards["300001.SZ"] == "chinext"
    assert boards["688001.SH"] == "star_market"
    assert boards["830001.BJ"] == "beijing"


def test_normalize_snapshot_frame_sets_suspension_true_for_flagged_code():
    source = TushareSecuritySource(FakeTusharePro())

    frame = normalize_snapshot_frame(source, trade_date="20200312")

    # 000001.SZ is in suspend_d output → suspended
    row = frame[frame["ts_code"] == "000001.SZ"].iloc[0]
    assert bool(row["is_suspended"]) is True
    # Others not in suspend_d → not suspended
    others = frame[frame["ts_code"] != "000001.SZ"]
    assert (others["is_suspended"] == False).all()


def test_normalize_snapshot_frame_empty_suspend_all_false():
    source = TushareSecuritySource(FakeTushareProEmptySuspend())

    frame = normalize_snapshot_frame(source, trade_date="20200312")

    assert (frame["is_suspended"] == False).all()


def test_normalize_snapshot_frame_st_and_risk_warning_default_false_when_blocked():
    source = TushareSecuritySource(FakeTusharePro())

    frame = normalize_snapshot_frame(source, trade_date="20200312")

    assert (frame["is_st"] == False).all()
    assert (frame["is_risk_warning"] == False).all()


def test_normalize_snapshot_frame_st_and_risk_warning_when_available():
    source = TushareSecuritySource(FakeTushareProAllAvailable())

    frame = normalize_snapshot_frame(source, trade_date="20200312")

    # 600000.SH is in stock_st output
    row_st = frame[frame["ts_code"] == "600000.SH"].iloc[0]
    assert bool(row_st["is_st"]) is True
    assert bool(row_st["is_risk_warning"]) is False

    # 300001.SZ is in stk_alert output
    row_rw = frame[frame["ts_code"] == "300001.SZ"].iloc[0]
    assert bool(row_rw["is_st"]) is False
    assert bool(row_rw["is_risk_warning"]) is True

    # 000001.SZ is in neither
    row_clean = frame[frame["ts_code"] == "000001.SZ"].iloc[0]
    assert bool(row_clean["is_st"]) is False
    assert bool(row_clean["is_risk_warning"]) is False


def test_normalize_snapshot_frame_preserves_passthrough_columns():
    source = TushareSecuritySource(FakeTusharePro())

    frame = normalize_snapshot_frame(source, trade_date="20200312")

    # Passthrough columns from stock_basic (not in fixed set) should be present.
    assert "symbol" in frame.columns
    assert "name" in frame.columns
    assert "area" in frame.columns
    assert "industry" in frame.columns
    row = frame[frame["ts_code"] == "000001.SZ"].iloc[0]
    assert row["symbol"] == "000001"
    assert row["name"] == "Ping An Bank"
    assert row["industry"] == "Banking"


def test_normalize_snapshot_frame_sorted_by_ts_code():
    source = TushareSecuritySource(FakeTusharePro())

    frame = normalize_snapshot_frame(source, trade_date="20200312")

    assert list(frame["ts_code"]) == sorted(frame["ts_code"])


def test_normalize_snapshot_frame_empty_stock_basic():
    class EmptyBasic:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def stock_basic(self, **kwargs: object) -> pd.DataFrame:
            self.calls.append(("stock_basic", kwargs))
            return pd.DataFrame()

        def suspend_d(self, **kwargs: object) -> pd.DataFrame:
            return pd.DataFrame()

        def stock_st(self, **kwargs: object) -> pd.DataFrame:
            raise RuntimeError("permission denied")

        def stk_alert(self, **kwargs: object) -> pd.DataFrame:
            raise RuntimeError("permission denied")

    source = TushareSecuritySource(EmptyBasic())

    frame = normalize_snapshot_frame(source, trade_date="20200312")

    assert frame.empty
    assert list(frame.columns) == SNAPSHOT_FIXED_COLUMNS
