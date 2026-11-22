from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src" / "quant_research_engine" / "gui"


def test_strategy_and_symbol_equity_charts_share_viewport_height() -> None:
    css = (GUI / "static" / "lab-theme.css").read_text(encoding="utf-8")
    job = (GUI / "saas" / "templates" / "job.html").read_text(encoding="utf-8")
    symbol = (GUI / "saas" / "templates" / "symbol.html").read_text(encoding="utf-8")

    assert (
        ".equity-chart-viewport{height:clamp(480px,calc(100dvh - 300px),1200px)}"
        in css
    )
    assert (
        "@media(max-width:640px){.equity-chart-viewport"
        "{height:clamp(360px,calc(100dvh - 340px),900px)}}" in css
    )
    assert '<div id="chart-main" class="equity-chart-viewport"></div>' in job
    assert '<div id="chart-equity" class="equity-chart-viewport"></div>' in symbol
