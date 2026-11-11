import importlib.util
import json
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


def test_poll_jobs_batches_ids_into_single_query():
    """多路并发用一条 IN 查询批量取状态，不按并发数放大 SSH 往返。"""
    calls = []

    class Result:
        stdout = ('{"id":301,"status":"running","error_class":null,"error":null,"summary":null}\n'
                  '{"id":302,"status":"completed","error_class":null,"error":null,'
                  '"summary":{"total_trade_count":5}}\n')

    def runner(command, **kwargs):
        calls.append(command)
        return Result()

    statuses = _MODULE.poll_jobs([302, 301], runner=runner)

    assert set(statuses) == {301, 302}
    assert statuses[302]["summary"]["total_trade_count"] == 5
    assert len(calls) == 1
    assert "IN (301,302)" in calls[0][-1]


def test_run_queue_keeps_two_jobs_in_flight(tmp_path, monkeypatch):
    """concurrency=2 时流水线提交：第一个完成立刻补位，最多同时两个在飞。"""
    monkeypatch.setattr(_MODULE, "STATE", tmp_path / "results.jsonl")
    monkeypatch.setattr(_MODULE, "JOB_IDS", tmp_path / "job_ids.json")
    rows = _MODULE.numbered_strategies()[:3]

    class FakeBrowser:
        def __init__(self):
            self.submitted = []

        def evaluate(self, code):
            job_id = 400 + len(self.submitted)
            self.submitted.append(job_id)
            return {"status": 200, "data": {"job_id": job_id}}

    polls = [
        {400: {"id": 400, "status": "running"},
         401: {"id": 401, "status": "running"}},
        {400: {"id": 400, "status": "completed", "summary": {"total_trade_count": 1}},
         401: {"id": 401, "status": "running"},
         402: {"id": 402, "status": "running"}},
        {401: {"id": 401, "status": "completed", "summary": {"total_trade_count": 2}},
         402: {"id": 402, "status": "completed", "summary": {"total_trade_count": 3}}},
    ]
    poll_snapshots = []

    class Result:
        stdout = "1\n"

    def runner(command, **kwargs):
        result = Result()
        if "json_build_object" in command[-1]:
            snapshot = polls.pop(0)
            poll_snapshots.append(sorted(snapshot))
            result.stdout = "\n".join(json.dumps(v) for v in snapshot.values()) + "\n"
        return result

    browser = FakeBrowser()
    code = _MODULE.run_queue(rows, browser, {}, {}, concurrency=2,
                             runner=runner, sleep=lambda _seconds: None)

    assert code == 0
    assert browser.submitted == [400, 401, 402]
    # 第一个 job 完成后才补第三个：证明是流水线而不是一次性全提交
    assert poll_snapshots == [[400, 401], [400, 401, 402], [401, 402]]
    recorded = [json.loads(line) for line in (tmp_path / "results.jsonl").read_text().splitlines()]
    assert [row["cf_id"] for row in recorded] == [rows[0]["cf_id"], rows[1]["cf_id"], rows[2]["cf_id"]]
    assert all(row["status"] == "completed" for row in recorded)


def test_is_infra_failure_classification():
    """基础设施失败才自动重跑；策略/因子类失败必须停下来修。"""
    assert _MODULE.is_infra_failure({"error_class": "result_upload_http_429"}) is True
    assert _MODULE.is_infra_failure({"error_class": "result_upload_error"}) is True
    assert _MODULE.is_infra_failure(
        {"error_class": "engine_error",
         "error": "RuntimeError: 回测失败：(psycopg.OperationalError) ... "
                  "FATAL:  the database system is starting up"}) is True
    # 非基础设施：必须停下等人工，不能被自动重跑掩盖
    assert _MODULE.is_infra_failure({"error_class": "engine_error",
                                     "error": "因子 f_missing 不存在"}) is False
    assert _MODULE.is_infra_failure({"error_class": "yaml_invalid", "error": "语法错误"}) is False
    assert _MODULE.is_infra_failure({}) is False


def test_run_queue_auto_retries_infra_failure(tmp_path, monkeypatch):
    """回传 429 这类基础设施失败：自动换键重跑，不再把整个队列停住。

    回归 2026-11-09：CF-083 因 429 失败后驱动连退 3 次、监管 HALT，空转 17.8h。
    """
    monkeypatch.setattr(_MODULE, "STATE", tmp_path / "results.jsonl")
    monkeypatch.setattr(_MODULE, "JOB_IDS", tmp_path / "job_ids.json")
    monkeypatch.setattr(_MODULE, "RETRY_COUNTS", tmp_path / "retry_counts.json")
    rows = _MODULE.numbered_strategies()[:1]

    class FakeBrowser:
        def __init__(self):
            self.submitted = []

        def evaluate(self, code):
            job_id = 500 + len(self.submitted)
            self.submitted.append(job_id)
            return {"status": 200, "data": {"job_id": job_id}}

    polls = [
        {500: {"id": 500, "status": "failed", "error_class": "result_upload_http_429",
               "error": "产物回传被云端拒绝（HTTP 429）"}},
        {501: {"id": 501, "status": "completed",
               "summary": {"total_trade_count": 7}}},
    ]

    class Result:
        stdout = "1\n"

    def runner(command, **kwargs):
        result = Result()
        if "json_build_object" in command[-1]:
            snapshot = polls.pop(0)
            result.stdout = "\n".join(json.dumps(v) for v in snapshot.values()) + "\n"
        return result

    browser = FakeBrowser()
    retry_counts: dict = {}
    job_ids: dict = {}
    code = _MODULE.run_queue(rows, browser, job_ids, retry_counts, concurrency=1,
                             runner=runner, sleep=lambda _seconds: None)

    assert code == 0                       # 自动重跑成功 ⇒ 队列继续推进
    assert browser.submitted == [500, 501]  # 换新 job 重跑一次
    assert retry_counts == {rows[0]["cf_id"]: 1}
    assert job_ids[rows[0]["cf_id"]] == 501
    recorded = [json.loads(line) for line in (tmp_path / "results.jsonl").read_text().splitlines()]
    assert [row["status"] for row in recorded] == ["failed", "completed"]


def test_run_queue_stops_on_strategy_failure(tmp_path, monkeypatch):
    """策略/因子类失败仍然立刻停（交给主 Agent 修因），不得自动重跑掩盖。"""
    monkeypatch.setattr(_MODULE, "STATE", tmp_path / "results.jsonl")
    monkeypatch.setattr(_MODULE, "JOB_IDS", tmp_path / "job_ids.json")
    monkeypatch.setattr(_MODULE, "RETRY_COUNTS", tmp_path / "retry_counts.json")
    rows = _MODULE.numbered_strategies()[:1]

    class FakeBrowser:
        def __init__(self):
            self.submitted = []

        def evaluate(self, code):
            job_id = 600 + len(self.submitted)
            self.submitted.append(job_id)
            return {"status": 200, "data": {"job_id": job_id}}

    class Result:
        stdout = "1\n"

    def runner(command, **kwargs):
        result = Result()
        if "json_build_object" in command[-1]:
            result.stdout = ('{"id":600,"status":"failed","error_class":"engine_error",'
                             '"error":"因子 f_missing 不存在","summary":null}\n')
        return result

    browser = FakeBrowser()
    retry_counts: dict = {}
    code = _MODULE.run_queue(rows, browser, {}, retry_counts, concurrency=1,
                             runner=runner, sleep=lambda _seconds: None)

    assert code == 1
    assert browser.submitted == [600]       # 不重跑
    assert retry_counts == {}


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


def test_pending_rows_keeps_explicitly_retried_completed_cf():
    """--resume + --retry 同一已完成 CF：必须保留下来重跑，不能被 completed 过滤吃掉。

    回归 2026-11-11：CF-018/074 修复后重跑，进程 0.19s 退出、零建单，
    因为 --resume 先把它们滤掉了。
    """
    rows = _MODULE.numbered_strategies()
    done = {"CF-001", "CF-018", "CF-074"}
    pending = _MODULE.pending_rows(rows, done, ["CF-018", "CF-074"])
    ids = [row["cf_id"] for row in pending]
    assert "CF-018" in ids and "CF-074" in ids
    assert "CF-001" not in ids
    assert len(pending) == 117  # 118 - 3 完成 + 2 重跑

    # 不带 retry 时行为不变
    assert len(_MODULE.pending_rows(rows, done, [])) == 115
