from __future__ import annotations

from quant_research_engine.gui.saas.metering import (
    FULL_SCALE_REFERENCE_SU,
    calculate_su,
    record_shadow_usage,
    usage_from_result,
)


def test_single_factor_stock_year_is_one_su():
    assert calculate_su(1, 1, 1, 1, 0) == 1


def test_cf022_current_maximum_reference():
    actual = calculate_su(5201, 17.8, 4, 2, 2_693_401)
    assert actual == FULL_SCALE_REFERENCE_SU == 470_493


def test_partial_task_is_proportional():
    assert calculate_su(100, 2, 1, 1, 0) == 200


def test_invalid_inputs_are_rejected():
    import pytest
    with pytest.raises(ValueError):
        calculate_su(0, 1)
    with pytest.raises(ValueError):
        calculate_su(1, -1)


def test_usage_from_result_and_idempotent_upsert():
    yaml_text = """data:
  factor_fields:
    a: factors.table_a.x
    b: factors.table_a.y
    c: factors.table_b.z
    d: factors.table_b.w
"""
    job = {"id": 22, "user_id": 6, "params": {}}
    summary = {
        "symbol_count": 5201, "date_start": "2009-01-05", "date_end": "2026-10-30",
        "total_trade_count": 2_693_401,
    }
    usage = usage_from_result(job, summary, yaml_text)
    assert usage["factor_fields"] == 4 and usage["factor_tables"] == 2
    assert usage["actual_su"] == 470_596  # 实际日期天数/365.25，区别于17.8年参考值
    assert usage["estimated_su"] < usage["actual_su"]
    assert usage["mode"] == "shadow"

    class Conn:
        calls = []
        def execute(self, sql, params):
            self.calls.append((str(sql), params))
    conn = Conn()
    record_shadow_usage(conn, job, summary, yaml_text)
    assert "ON CONFLICT (job_id) DO UPDATE" in conn.calls[0][0]
    assert conn.calls[0][1]["job_id"] == 22
    assert conn.calls[0][1]["mode"] == "shadow"


def test_period_windows_and_allowances():
    from datetime import date
    from quant_research_engine.gui.saas.metering import allowance_su, period_window

    assert period_window('guest', date(2026, 11, 16)) == (date(2026, 11, 16), date(2026, 11, 16))
    assert period_window('member', date(2026, 11, 16)) == (date(2026, 11, 1), date(2026, 12, 1))
    assert period_window('starter', date(2026, 12, 16), date(2026, 11, 16)) == (
        date(2026, 12, 16), date(2027, 1, 16))  # 到期日当天进入下一周期
    assert period_window('diamond', date(2027, 1, 16), date(2026, 11, 30)) == (
        date(2026, 12, 30), date(2027, 1, 30))
    assert allowance_su('starter') == 3 * FULL_SCALE_REFERENCE_SU
    assert allowance_su('advanced') == 10 * FULL_SCALE_REFERENCE_SU
    assert allowance_su('diamond') == 30 * FULL_SCALE_REFERENCE_SU
    assert allowance_su('member') == 0


def test_cycle_usage_reads_real_aggregate():
    from datetime import date
    from quant_research_engine.gui.saas.metering import cycle_usage

    class Result:
        def mappings(self): return self
        def one(self): return {'jobs': 2, 'estimated': 100, 'actual': 150, 'allowance': 1000}
    class Conn:
        def execute(self, sql, params):
            assert params == {'uid': 6, 'start': date(2026, 11, 1), 'end': date(2026, 12, 1)}
            assert "mode='shadow'" in str(sql)
            return Result()
    assert cycle_usage(Conn(), 6, date(2026, 11, 1), date(2026, 12, 1)) == {
        'jobs': 2, 'estimated_su': 100, 'actual_su': 150, 'allowance_su': 1000}
