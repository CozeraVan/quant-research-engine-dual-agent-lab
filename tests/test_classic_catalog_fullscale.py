import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "classic_catalog" / "fullscale.py"
sys.path.insert(0, str(_SCRIPT.parent))
_SPEC = importlib.util.spec_from_file_location("classic_catalog_fullscale", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_fullscale_numbering_is_stable_and_complete():
    rows = _MODULE.numbered_strategies()
    assert len(rows) == 118
    assert rows[0]["cf_id"] == "CF-001"
    assert rows[-1]["cf_id"] == "CF-118"
    assert len({row["strategy_id"] for row in rows}) == 118


def test_fullscale_submission_uses_unlimited_positions():
    row = _MODULE.numbered_strategies()[0]

    class FakeBrowser:
        def evaluate(self, code):
            assert '"max_positions": 0' in code
            return {"status": 200, "data": {"job_id": 123}}

    result = _MODULE.submit(FakeBrowser(), row)
    assert result["job_id"] == 123


def test_submit_uses_custom_key_version():
    """重跑必须换幂等键：服务端同键只会返回旧的失败 job。"""
    row = _MODULE.numbered_strategies()[0]
    seen = {}

    class FakeBrowser:
        def evaluate(self, code):
            seen["code"] = code
            return {"status": 200, "data": {"job_id": 299}}

    result = _MODULE.submit(FakeBrowser(), row, "v2")
    assert result["job_id"] == 299
    assert f'"{row["cf_id"]}-{row["strategy_id"]}-v2"' in seen["code"]
    assert f'"{row["cf_id"]}-{row["strategy_id"]}-v1"' not in seen["code"]


def test_prepare_retry_bumps_version_and_drops_stale_job_mapping():
    job_ids = {"CF-001": 227, "CF-063": 298}
    retry_counts = {}

    job_ids, retry_counts = _MODULE.prepare_retry(["CF-063"], job_ids, retry_counts)

    assert "CF-063" not in job_ids          # 旧映射摘除，强制重新提交
    assert job_ids["CF-001"] == 227         # 其他 CF 不受影响
    assert retry_counts == {"CF-063": 1}
    assert _MODULE.retry_key_version(retry_counts, "CF-063") == "v2"
    assert _MODULE.retry_key_version(retry_counts, "CF-001") == "v1"

    # 二次重跑继续累加，键版本单调递增（v3），不会退回到失败键
    _, retry_counts = _MODULE.prepare_retry(["CF-063"], job_ids, retry_counts)
    assert _MODULE.retry_key_version(retry_counts, "CF-063") == "v3"


def test_assign_owner_checks_backup_and_updates_all_owned_rows():
    calls = []

    class Result:
        stdout = "1\n"

    def runner(command, **kwargs):
        calls.append(command)
        return Result()

    _MODULE.assign_owner(228, runner=runner)

    assert len(calls) == 2
    precheck, mutation = calls
    assert "SELECT count(*) FROM jobs WHERE id = 228" in precheck[-1]
    sql = mutation[-1]
    assert "BEGIN" in sql and "COMMIT" in sql
    assert "classic_owner_backup_job_228_jobs" in sql
    assert "classic_owner_backup_job_228_results" in sql
    assert "classic_owner_backup_job_228_strategies" in sql
    assert "UPDATE jobs SET user_id = 6 WHERE id = 228" in sql
    assert "UPDATE results SET user_id = 6 WHERE job_id = 228" in sql
    assert "UPDATE strategies SET user_id = 6" in sql


def test_wait_owner_reads_terminal_status_without_browser_session():
    calls = []

    class Result:
        stdout = '{"status":"completed","error_class":null,"error":null,"summary":{"total_trade_count":7}}\n'

    def runner(command, **kwargs):
        calls.append(command)
        return Result()

    result = _MODULE.wait_owner(228, runner=runner, sleep=lambda _: None)
    assert result["status"] == "completed"
    assert result["summary"]["total_trade_count"] == 7
    assert len(calls) == 1
    assert "json_build_object" in calls[0][-1]
