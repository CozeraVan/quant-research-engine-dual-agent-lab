import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "classic_catalog" / "driver.py"
_SPEC = importlib.util.spec_from_file_location("classic_catalog_driver", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_wizard_converts_simple_conditions_and_constant_cross():
    state = _MODULE.wizard_state(
        "(rsi_14 < 30) and (close > sma_200)",
        "(macd_12_26_9 < 0) and (macd_12_26_9.shift(1) >= 0)",
    )

    assert state["entry"]["groups"][0]["conds"] == [
        {"left": "rsi_14", "op": "<", "fixed": "30", "right": None},
        {"left": "close", "op": ">", "fixed": None, "right": "sma_200"},
    ]
    assert state["exit"]["groups"][0]["conds"] == [
        {"left": "macd_12_26_9", "op": "crosses_below", "fixed": "0", "right": None},
    ]


def test_wizard_rejects_arithmetic_and_unsupported_methods():
    with pytest.raises(ValueError):
        _MODULE.wizard_state("close / sma_20 > 1.05", "rsi_14 > 60")
    with pytest.raises(ValueError):
        _MODULE.wizard_state("close > close.shift(1).rolling(20).max()", "rsi_14 > 60")


def test_semantic_equal_ignores_parentheses_but_not_cross_semantics():
    assert _MODULE.semantic_equal("(rsi_14 < 30)", "rsi_14 < 30")
    assert not _MODULE.semantic_equal(
        "macd > macds",
        "(macd > macds) and (macd.shift(1) <= macds.shift(1))",
    )


def test_entry_assignment_is_stratified_and_deterministic():
    payload = json.loads(Path("docs/agent/classic_catalog/inventory.json").read_text())
    strategies = payload["strategies"]
    first = _MODULE.assign_entries(strategies)
    second = _MODULE.assign_entries(strategies)

    assert first == second
    assert set(first.values()) == {"nl", "wizard", "yaml"}
    assert len(first) == 118


def test_all_legacy_catalog_yamls_pass_public_schema_after_normalization():
    from quant_research_engine.security.yaml_guard import validate_strategy_yaml

    failures = {}
    for path in Path("strategies/catalog").rglob("*.yaml"):
        normalized = _MODULE.public_yaml(path.read_text())
        result = validate_strategy_yaml(normalized)
        if result["issues"]:
            failures[path.stem] = result["issues"]
    assert failures == {}


# ---------------------------------------------------------------------------
# WebBridge 瞬断重试（CF-001 首跑因 502 Bad Gateway 终止；浏览器驱动/代理的瞬断
# 不应杀死整个 CF）。只重试传输层错误与 502/503/504；命令级错误（payload ok=false，
# 页面 JS 异常）与 4xx 是确定性失败，不重试。提交重试安全由幂等键保证。
# ---------------------------------------------------------------------------

import io  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://127.0.0.1:10086/command", code,
                                  f"HTTP {code}", {}, io.BytesIO(b""))


class _FlakyTransport:
    """前 failures 次调袖珍瞬断（按 error_factory），之后返回固定 payload。"""

    def __init__(self, failures: int, error_factory, payload: dict):
        self.failures = failures
        self.error_factory = error_factory
        self.payload = payload
        self.calls = 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error_factory()
        return _FakeResponse(self.payload)


def _browser(sleep_recorder=None):
    return _MODULE.Browser(session="classic-catalog-smoke",
                           sleep=(sleep_recorder.append if sleep_recorder is not None
                                  else (lambda s: None)))


def _ok_payload(value):
    return {"ok": True, "data": {"type": "object", "value": value}}


class TestWebBridgeRetry:
    def test_transient_502_then_success(self, monkeypatch):
        transport = _FlakyTransport(2, lambda: _http_error(502), _ok_payload({"yaml": "x"}))
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        delays: list[float] = []
        browser = _browser(delays)
        assert browser.evaluate("1+1") == {"yaml": "x"}
        assert transport.calls == 3
        assert delays == sorted(delays) and delays[0] > 0  # 退避递增

    def test_transient_503_then_success(self, monkeypatch):
        transport = _FlakyTransport(1, lambda: _http_error(503), _ok_payload(42))
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        assert _browser().evaluate("1+1") == 42
        assert transport.calls == 2

    def test_connection_reset_then_success(self, monkeypatch):
        transport = _FlakyTransport(2, lambda: urllib.error.URLError("Connection reset by peer"),
                                    _ok_payload("v"))
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        assert _browser().evaluate("1+1") == "v"
        assert transport.calls == 3

    def test_timeout_then_success(self, monkeypatch):
        transport = _FlakyTransport(1, lambda: TimeoutError("timed out"), _ok_payload("v"))
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        assert _browser().evaluate("1+1") == "v"
        assert transport.calls == 2

    def test_gives_up_after_max_attempts_with_clear_error(self, monkeypatch):
        transport = _FlakyTransport(99, lambda: _http_error(502), _ok_payload("never"))
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        browser = _browser()
        with pytest.raises(RuntimeError, match="WebBridge") as excinfo:
            browser.evaluate("1+1")
        assert transport.calls == _MODULE.WEBBRIDGE_MAX_ATTEMPTS
        assert "502" in str(excinfo.value)
        assert str(_MODULE.WEBBRIDGE_MAX_ATTEMPTS) in str(excinfo.value)

    def test_command_level_failure_not_retried(self, monkeypatch):
        """payload ok=false（页面 JS 异常等确定性失败）：不重试，立即抛。"""
        transport = _FlakyTransport(0, lambda: _http_error(502),
                                    {"ok": False, "error": "no tab"})
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        with pytest.raises(RuntimeError):
            _browser().evaluate("1+1")
        assert transport.calls == 1

    def test_4xx_not_retried(self, monkeypatch):
        transport = _FlakyTransport(99, lambda: _http_error(400), _ok_payload("never"))
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        with pytest.raises(RuntimeError, match="400"):
            _browser().evaluate("1+1")
        assert transport.calls == 1

    def test_backoff_bounded(self, monkeypatch):
        """退避递增且有界：5 次尝试的总睡眠 ≤ 0.5+1+2+4 + jitter 上界。"""
        transport = _FlakyTransport(99, lambda: _http_error(503), _ok_payload("never"))
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        delays: list[float] = []
        with pytest.raises(RuntimeError):
            _browser(delays).evaluate("1+1")
        assert len(delays) == _MODULE.WEBBRIDGE_MAX_ATTEMPTS - 1
        assert delays == sorted(delays)
        assert sum(delays) <= 0.5 + 1 + 2 + 4 + 4 * 0.25


class TestSubmitRetryKeepsIdempotencyKey:
    def test_submit_retry_sends_identical_idempotency_key(self, monkeypatch):
        """提交重试不得重复建单：传输层 502 后重发同一 payload（幂等键不变），
        服务端按 (user_id, idempotency_key) 去重返回同一 job。
        这里在 urlopen 层注入一次 502，走真实 evaluate 重试路径。"""
        inventory = json.loads(Path("docs/agent/classic_catalog/inventory.json").read_text())
        sample = inventory["strategies"][0]
        row = {
            "strategy_id": sample["strategy_id"], "entry_mode": "yaml",
            "yaml_path": sample["yaml_path"], "description": "d",
            "entry": "close > open", "exit": "close < open",
            "declared_entry": "", "declared_exit": "",
        }
        params = {"start": "2024-11-01", "end": "2026-10-30", "mode": "batch"}
        bodies: list[bytes] = []

        class _SubmitTransport:
            def __init__(self):
                self.calls = 0

            def __call__(self, request, timeout=None):
                self.calls += 1
                bodies.append(request.data)
                if self.calls == 1:
                    raise _http_error(502)
                return _FakeResponse({"ok": True, "data": {"type": "object", "value": {
                    "status": 200, "data": {"ok": True, "job_id": 777}}}})

        transport = _SubmitTransport()
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        browser = _browser()
        result = browser.submit(row, params)
        assert result["job_id"] == 777
        assert transport.calls == 2  # 第一次 502 重试，第二次成功
        keys = [b.decode().split('\\"idempotency_key\\": \\"')[1].split('\\"')[0]
                for b in bodies]
        assert keys[0] == keys[1] == f"classic-20261103-{sample['strategy_id']}-v4"
        # 重试前后请求体逐字节一致（幂等从客户端侧即可证）
        assert bodies[0] == bodies[1]


# ---------------------------------------------------------------------------
# 命令级瞬断重试（CF-001/job227 回归：等待 ~2.6h 后 WebBridge 命令级
# extension_error——页面 apiFetch 收到网关 HTML 错误页，r.json() 抛
# SyntaxError: Unexpected token '<'）。这类「网关/HTML/网络」瞬态与传输层瞬断
# 同罪：有限重试；确定性命令错误（JS 逻辑/业务拒绝）不重试。
# ---------------------------------------------------------------------------

_TRANSIENT_HTML_MESSAGE = (
    'evaluate: SyntaxError: Unexpected token \'<\', '
    '"<html><body>502 Bad Gateway</body></html>..." is not valid JSON'
)


class _PayloadTransport:
    """按队列依次返回 payload（最后一个重复）；记录调用次数。"""

    def __init__(self, payloads: list[dict]):
        self.payloads = list(payloads)
        self.calls = 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        index = min(self.calls - 1, len(self.payloads) - 1)
        return _FakeResponse(self.payloads[index])


class _RawTransport:
    """返回非 JSON 原始 body（模拟 daemon/代理层 HTML 错误页）。"""

    def __init__(self, raw: bytes, ok_after: int, payload: dict):
        self.raw = raw
        self.ok_after = ok_after
        self.payload = payload
        self.calls = 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        if self.calls <= self.ok_after:
            return _FakeResponse.__new__(_FakeResponse) if False else _RawBody(self.raw)
        return _FakeResponse(self.payload)


class _RawBody:
    def __init__(self, raw: bytes):
        self._raw = raw

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _transient_payload(message: str) -> dict:
    return {"ok": False, "error": "extension_error", "message": message}


class TestTransientCommandErrorRetry:
    def test_html_json_syntax_error_then_success(self, monkeypatch):
        """job227 回归：HTML 错误页导致 r.json() SyntaxError → 重试恢复。"""
        transport = _PayloadTransport([
            _transient_payload(_TRANSIENT_HTML_MESSAGE),
            _transient_payload(_TRANSIENT_HTML_MESSAGE),
            _ok_payload({"status": "completed"}),
        ])
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        delays: list[float] = []
        browser = _browser(delays)
        assert browser.evaluate("poll") == {"status": "completed"}
        assert transport.calls == 3
        assert len(delays) == 2  # 两次瞬断两次退避

    def test_failed_to_fetch_then_success(self, monkeypatch):
        transport = _PayloadTransport([
            _transient_payload("evaluate: TypeError: Failed to fetch"),
            _ok_payload({"status": "running"}),
        ])
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        assert _browser().evaluate("poll") == {"status": "running"}
        assert transport.calls == 2

    def test_gateway_message_then_success(self, monkeypatch):
        transport = _PayloadTransport([
            _transient_payload("evaluate: Error 502 Bad Gateway"),
            _transient_payload("evaluate: Error 503 Service Unavailable"),
            _ok_payload({"status": "running"}),
        ])
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        assert _browser().evaluate("poll") == {"status": "running"}
        assert transport.calls == 3

    def test_transient_command_error_exhausts_with_clear_error(self, monkeypatch):
        transport = _PayloadTransport([_transient_payload(_TRANSIENT_HTML_MESSAGE)])
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        browser = _browser()
        with pytest.raises(RuntimeError, match="WebBridge") as excinfo:
            browser.evaluate("poll")
        assert transport.calls == _MODULE.WEBBRIDGE_MAX_ATTEMPTS
        assert "Unexpected token" in str(excinfo.value)
        assert str(_MODULE.WEBBRIDGE_MAX_ATTEMPTS) in str(excinfo.value)

    def test_non_transient_command_error_not_retried(self, monkeypatch):
        """确定性命令错误（页面 JS 逻辑异常）：不重试，立即抛。"""
        transport = _PayloadTransport([
            _transient_payload("evaluate: ReferenceError: apiFetch is not defined"),
        ])
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        with pytest.raises(RuntimeError, match="ReferenceError"):
            _browser().evaluate("poll")
        assert transport.calls == 1

    def test_non_transient_business_error_not_retried(self, monkeypatch):
        transport = _PayloadTransport([
            {"ok": False, "error": "任务非当前 worker 持有"},
        ])
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        with pytest.raises(RuntimeError):
            _browser().evaluate("poll")
        assert transport.calls == 1

    def test_html_body_from_daemon_layer_retried(self, monkeypatch):
        """daemon/代理层直接返回 HTML（非 JSON body）：瞬断，重试后恢复。"""
        transport = _RawTransport(b"<html><body>502 Bad Gateway</body></html>", 2,
                                  _ok_payload("v"))
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        assert _browser().evaluate("poll") == "v"
        assert transport.calls == 3

    def test_html_body_from_daemon_layer_exhausts(self, monkeypatch):
        transport = _RawTransport(b"<html>gateway</html>", 99, _ok_payload("never"))
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        with pytest.raises(RuntimeError, match="瞬断重试耗尽") as excinfo:
            _browser().evaluate("poll")
        assert transport.calls == _MODULE.WEBBRIDGE_MAX_ATTEMPTS
        assert str(_MODULE.WEBBRIDGE_MAX_ATTEMPTS) in str(excinfo.value)


class TestWaitPollingRecovery:
    def test_wait_survives_transient_poll_error(self, monkeypatch):
        """job227 回归：wait 轮询期的瞬断（HTML/JSON 命令级错误）不杀死等待，
        恢复后拿到终态。"""
        transport = _PayloadTransport([
            _transient_payload(_TRANSIENT_HTML_MESSAGE),
            _ok_payload({"status": "running"}),
            _ok_payload({"status": "completed", "summary": {"total_trade_count": 12}}),
        ])
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        browser = _browser()
        result = browser.wait(227, timeout_s=30, sleep=lambda s: None)
        assert result["status"] == "completed"
        assert result["summary"]["total_trade_count"] == 12
        assert transport.calls == 3

    def test_wait_timeout_still_raises(self, monkeypatch):
        transport = _PayloadTransport([_ok_payload({"status": "running"})])
        monkeypatch.setattr(urllib.request, "urlopen", transport)
        browser = _browser()
        with pytest.raises(TimeoutError):
            browser.wait(227, timeout_s=0.2, sleep=lambda s: None)
