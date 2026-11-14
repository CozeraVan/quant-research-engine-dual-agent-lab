"""快进连播与 K 线两位小数的前端结构守卫。"""

from pathlib import Path

HTML = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "quant_research_engine"
    / "game"
    / "templates"
    / "game.html"
)


def _html() -> str:
    return HTML.read_text(encoding="utf-8")


def test_decimal_display_present():
    html = _html()

    assert "function chartTooltip" in html, "缺少图表 tooltip 格式化函数"
    assert "tooltip: {trigger: 'axis', formatter: chartTooltip}" in html, (
        "tooltip 未挂 formatter"
    )
    assert "formatter: v => Number(v).toFixed(2)" in html, "主图价格轴未统一 2 位小数"


def test_autoplay_present():
    html = _html()

    for marker in (
        'id="btn-autoplay"',
        'id="autoplay-status"',
        "dataset.autoplay",
        "function startAutoplay",
        "function stopAutoplay",
        "function autoplayStep",
        "function ffCadence",
        "function toggleAutoplay",
        "function renderAutoplayControls",
    ):
        assert marker in html, f"缺少连播控件/函数 {marker}"


def test_single_bar_invariant_preserved():
    html = _html()

    for marker in (
        'id="anim-speed"',
        'id="btn-anim-pause"',
        'id="btn-anim-skip"',
        "startBarAnimation",
        "dataset.anim",
    ):
        assert marker in html, f"单根动画 marker 被破坏 {marker}"
    assert "!ff.active) startBarAnimation" in html, "连播未与单根动画解耦"
