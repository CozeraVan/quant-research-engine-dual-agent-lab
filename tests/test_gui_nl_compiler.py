from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_research_engine.gui.nl_compiler import (
    ENV_API_KEY,
    ENV_BASE_URL,
    ENV_MODEL,
    NOT_CONFIGURED_ERROR,
    build_system_prompt,
    compile_nl,
    nl_config,
    strip_yaml_fence,
)


def _llm_env() -> dict[str, str]:
    return {
        ENV_BASE_URL: "http://llm.local/v1",
        ENV_API_KEY: "test-key",
        ENV_MODEL: "test-model",
    }


def _http_ok(content: str):
    def http_post(url, headers, payload, timeout):
        assert url == "http://llm.local/v1/chat/completions"
        assert headers["Authorization"] == "Bearer test-key"
        assert payload["model"] == "test-model"
        assert payload["messages"][-1]["role"] == "user"
        return {"choices": [{"message": {"content": content}}]}

    return http_post


_VALID_YAML = (
    "experiment:\n  name: nl_demo\n  market_profile: ashare_daily_default\n  frequency: daily\n"
    "data:\n  market_fields: [open, high, low, close, pre_close, vol, amount]\n"
    "  factor_fields:\n    rsi_14: factors.stock_daily_momentum_close.rsi_14\n"
    "signal:\n  entry: rsi_14 > 30\n  exit: rsi_14 > 60\n"
    "holding:\n  max_holding_days: 5\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5]\n"
)


# --- config / prompt / fence ---


def test_nl_config_missing():
    assert nl_config({}) is None
    assert nl_config({ENV_BASE_URL: "http://x"}) is None


def test_nl_config_present():
    cfg = nl_config(_llm_env())
    assert cfg == {"base_url": "http://llm.local/v1", "api_key": "test-key", "model": "test-model"}


def test_build_system_prompt_contains_dsl_and_catalog():
    prompt = build_system_prompt()
    assert "factor_fields" in prompt
    assert "只输出 YAML" in prompt
    assert "rsi" in prompt  # indicator catalog injected
    assert "示例 1" in prompt


def test_strip_yaml_fence():
    assert strip_yaml_fence("```yaml\na: 1\n```") == "a: 1"
    assert strip_yaml_fence("```\na: 1\n```\n") == "a: 1"
    assert strip_yaml_fence("a: 1") == "a: 1"


# --- compile_nl flows ---


def test_compile_not_configured():
    result = compile_nl("RSI 超卖买入", env={})
    assert result["ok"] is False
    assert result["code"] == "not_configured"
    assert "未配置 LLM" in result["error"]
    assert result["error"] == NOT_CONFIGURED_ERROR


def test_compile_empty_description():
    result = compile_nl("   ", env=_llm_env())
    assert result["ok"] is False
    assert result["code"] == "empty"


def test_compile_success_roundtrip_with_fence():
    fenced = "```yaml\n" + _VALID_YAML + "```\n"
    result = compile_nl(
        "RSI(14) 站回 30 买入，大于 60 卖出",
        env=_llm_env(),
        http_post=_http_ok(fenced),
        column_lookup=lambda table: {"rsi_14"},
    )
    assert result["ok"] is True
    assert "rsi_14" in result["yaml"]
    assert "```" not in result["yaml"]


def test_compile_defaults_missing_holding_to_unlimited_and_preserves_explicit_days():
    without_holding = _VALID_YAML.replace("holding:\n  max_holding_days: 5\n", "")
    result = compile_nl(
        "RSI 超卖买入，超买卖出",
        env=_llm_env(),
        http_post=_http_ok(without_holding),
        column_lookup=lambda table: {"rsi_14"},
    )
    assert result["ok"] is True
    assert "holding:\n  max_holding_days: 0\n" in result["yaml"]

    explicit = compile_nl(
        "RSI 超卖买入，超买卖出，最长持仓 5 天",
        env=_llm_env(),
        http_post=_http_ok(_VALID_YAML),
        column_lookup=lambda table: {"rsi_14"},
    )
    assert explicit["ok"] is True
    assert "max_holding_days: 5" in explicit["yaml"]

    invented = compile_nl(
        "MACD 金叉买入，死叉卖出",
        env=_llm_env(),
        http_post=_http_ok(_VALID_YAML.replace("max_holding_days: 5", "max_holding_days: 999")),
        column_lookup=lambda table: {"rsi_14"},
    )
    assert invented["ok"] is True
    assert "max_holding_days: 0" in invented["yaml"]
    assert "max_holding_days: 999" not in invented["yaml"]


def test_compile_llm_http_error():
    def http_post(url, headers, payload, timeout):
        raise TimeoutError("timed out")

    result = compile_nl("x", env=_llm_env(), http_post=http_post)
    assert result["ok"] is False
    assert result["code"] == "llm_error"
    assert "LLM 调用失败" in result["error"]


def test_compile_invalid_yaml_returns_draft():
    result = compile_nl(
        "x",
        env=_llm_env(),
        http_post=_http_ok("name: nope\n# missing required sections\n"),
    )
    assert result["ok"] is False
    assert result["code"] == "invalid_yaml"
    assert "未通过策略规格校验" in result["error"]
    assert result["yaml"]  # draft returned for user editing


def test_compile_non_yaml_llm_output():
    result = compile_nl(
        "x",
        env=_llm_env(),
        http_post=_http_ok("对不起，我无法理解这个策略。"),
    )
    assert result["ok"] is False
    assert result["code"] == "invalid_yaml"


def test_compile_missing_factors_enqueued(tmp_path):
    queue_path = tmp_path / "handoff" / "missing_factor_requests.json"
    result = compile_nl(
        "需要 rsi_99 因子",
        env=_llm_env(),
        http_post=_http_ok(_VALID_YAML),
        column_lookup=lambda table: set(),  # nothing exists
        queue_path=queue_path,
    )
    assert result["ok"] is False
    assert result["code"] == "missing_factors"
    assert "已搁置" in result["error"]
    assert "rsi_14" in result["error"]
    assert result["missing_factors"] == ["rsi_14"]
    assert result["yaml"]  # draft kept

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert len(queue) == 1
    entry = queue[0]
    assert entry["alias"] == "rsi_14"
    assert entry["expected_table"] == "factors.stock_daily_momentum_close"
    assert entry["expected_column"] == "rsi_14"
    assert entry["status"] == "pending"


def test_compile_db_unavailable_falls_back_to_catalog_snapshot():
    """2026-10-10 起：DB 不可用不再跳过检查——回退 configs/factor_catalog_llm.json
    快照 lookup（ECS 无行情库，纠错/重试层照常工作）。有效 YAML 正常通过且无
    「跳过因子存在性检查」警告。"""
    result = compile_nl(
        "x",
        env=_llm_env(),
        http_post=_http_ok(_VALID_YAML),
        column_lookup=None,
        db_url="postgresql+psycopg:///definitely_not_exists_db",
    )
    assert result["ok"] is True
    assert not any("跳过因子存在性检查" in w for w in result.get("warnings", []))


# --- route ---


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_route_empty_description(app_client):
    resp = app_client.post("/api/nl_compile", json={"description": "  "})
    assert resp.status_code == 400


def test_route_not_configured_returns_503(app_client, monkeypatch):
    for var in (ENV_BASE_URL, ENV_API_KEY, ENV_MODEL):
        monkeypatch.delenv(var, raising=False)
    resp = app_client.post("/api/nl_compile", json={"description": "RSI 超卖买入"})
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["code"] == "not_configured"
    assert "未配置 LLM" in data["error"]


def test_route_success_200(app_client, monkeypatch):
    for key, value in _llm_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        "quant_research_engine.gui.nl_compiler._default_column_lookup",
        lambda db_url=None: (lambda table: {"rsi_14"}),
    )

    import urllib.request

    class _FakeResponse:
        def __init__(self, body: dict):
            self._body = json.dumps(body).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self._body

    def fake_urlopen(request, timeout=None):
        return _FakeResponse({"choices": [{"message": {"content": _VALID_YAML}}]})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    resp = app_client.post("/api/nl_compile", json={"description": "RSI(14) 站回 30 买入"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "rsi_14" in data["yaml"]


def test_index_page_nl_channel_moved(app_client):
    # QRE-GUI-CONSOL-039：8080 首页退役为引导页；NL 通道在 8081（test_gui_lab.py 覆盖）
    resp = app_client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "已迁移至回测台" in html
    assert "btn-nl-compile" not in html
