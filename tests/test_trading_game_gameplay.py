"""游戏性优化 S1 回归：自选时长/资金透传 + 收益率/回撤统计（2026-11-12 用户批准切片）。

设计见 .tmp/game-windows-dev/gameplay-design.md（Windows 本地证据，不同步 WSL）。
默认基线不变（1250 / 1,000,000）；配置 additive；warmup 固定 250 保护 ema_250。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "win"))

from game_preview_sample import SampleGameStore  # noqa: E402

from quant_research_engine.game.data import PostgresGameDataProvider  # noqa: E402
from quant_research_engine.game.engine import GameRuleError  # noqa: E402
from quant_research_engine.game.web import create_game_app  # noqa: E402


@pytest.fixture()
def provider():
    return PostgresGameDataProvider(SampleGameStore())


def test_session_defaults_unchanged(provider):
    session = provider.create_session(seed=7)
    assert session.game_bars == 1250 and session.warmup_bars == 250
    assert session.engine.initial_cash == 1_000_000.0
    assert session.equity_curve == [1_000_000.0]


def test_session_options_plumb_through(provider):
    session = provider.create_session(seed=7, game_bars=250, initial_cash=100_000)
    assert session.game_bars == 250 and session.warmup_bars == 250
    assert session.engine.initial_cash == 100_000.0
    assert session.engine.cash == 100_000.0


def test_game_bars_beyond_candidate_data_rejected(provider):
    # 样本 1600 根：250 预热 + 1350 对局 = 1600 刚好；1351 越界必须拒绝
    provider.create_session(seed=7, game_bars=1350)
    with pytest.raises(GameRuleError):
        provider.create_session(seed=7, game_bars=1351)


def test_configured_length_finishes(provider):
    session = provider.create_session(seed=7, game_bars=250, initial_cash=500_000)
    for _ in range(250):
        session.advance()
        session.close_day()
    assert session.finished is True
    assert len(session.equity_curve) == 251
    assert session.return_pct == pytest.approx(0.0)
    assert session.max_drawdown == pytest.approx(0.0)


def test_return_and_drawdown_math(provider):
    session = provider.create_session(seed=7, initial_cash=100_000)
    # 直接注入曲线单测回撤公式（与既有 corrupted-factor 单测同手法）；
    # 真实曲线累积由 test_configured_length_finishes 覆盖。
    session.equity_curve = [100_000.0, 120_000.0, 90_000.0, 110_000.0]
    assert session.max_drawdown == pytest.approx(0.25)
    session.engine.cash = 110_000.0  # 无持仓 equity==cash
    assert session.return_pct == pytest.approx(0.10)


def test_api_options_validation_and_state():
    app = create_game_app(PostgresGameDataProvider(SampleGameStore()), testing=True)
    client = app.test_client()
    ok = client.post("/game/api/sessions", json={"game_bars": 250, "initial_cash": 500_000})
    assert ok.status_code == 200
    state = ok.get_json()
    assert state["game_bars"] == 250 and state["initial_cash"] == 500_000
    assert state["return_pct"] == 0.0 and state["max_drawdown"] == 0.0
    assert client.post("/game/api/sessions", json={"game_bars": 999}).status_code == 400
    assert client.post("/game/api/sessions", json={"initial_cash": 42}).status_code == 400
    default = client.post("/game/api/sessions")
    assert default.status_code == 200
    d = default.get_json()
    assert d["game_bars"] == 1250 and d["initial_cash"] == 1_000_000


def test_decision_shortcuts_present_in_template():
    """S2 纯前端快捷：结构守卫（沿用 disabled-visual 模板正则手法）。"""
    html = (REPO / "src/quant_research_engine/game/templates/game.html").read_text(encoding="utf-8")
    for marker in ('id="pos-25"', 'id="pos-50"', 'id="pos-100"',
                   'id="btn-fill-open"', 'id="btn-wait"'):
        assert marker in html, f"缺少快捷控件 {marker}"
    assert "currentPositionQty" in html, "缺少仓位百分比计算函数"


def test_playback_animation_present_in_template():
    """S3 单根播放动画 + 倍速：结构守卫。"""
    html = (REPO / "src/quant_research_engine/game/templates/game.html").read_text(encoding="utf-8")
    for marker in ('id="anim-speed"', 'id="btn-anim-pause"', 'id="btn-anim-skip"'):
        assert marker in html, f"缺少播放控件 {marker}"
    assert "startBarAnimation" in html, "缺少单根动画入口"
    assert "dataset.anim" in html, "缺少可测试的动画状态反射"