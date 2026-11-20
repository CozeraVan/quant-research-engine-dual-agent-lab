from __future__ import annotations

import pytest

from quant_research_engine.scheduling import RefreshInProgress, refresh_lock


def test_shared_backtests_can_run_together(tmp_path):
    path = tmp_path / "schedule.lock"
    with refresh_lock(path, exclusive=False):
        with refresh_lock(path, exclusive=False):
            pass


def test_refresh_waits_for_backtest_and_backtest_waits_for_refresh(tmp_path):
    path = tmp_path / "schedule.lock"
    with refresh_lock(path, exclusive=False):
        with pytest.raises(RefreshInProgress):
            with refresh_lock(path, exclusive=True, blocking=False):
                pass
    with refresh_lock(path, exclusive=True):
        with pytest.raises(RefreshInProgress):
            with refresh_lock(path, exclusive=False, blocking=False):
                pass


def test_automatic_refresh_units_use_same_exclusive_lock():
    from pathlib import Path
    root = Path("deploy/scheduling")
    for name in ("quant-ts-daily", "indicators-tushare-daily", "alpha191-daily", "panel-factors-daily"):
        text = (root / f"{name}.conf").read_text()
        assert "ExecStart=" in text
        assert "/usr/bin/flock /tmp/qre-market-refresh.lock" in text
