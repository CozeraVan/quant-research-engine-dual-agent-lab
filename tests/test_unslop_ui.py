"""UNSlOP： quiet chrome / 内容承载色彩，而非装饰承载色彩。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = (ROOT / "src/quant_research_engine/gui/static/lab-theme.css").read_text(encoding="utf-8")
CARDS = (ROOT / "src/quant_research_engine/gui/static/card-class.css").read_text(encoding="utf-8")
BASE = (ROOT / "src/quant_research_engine/gui/saas/templates/base.html").read_text(encoding="utf-8")
ACCOUNT = (ROOT / "src/quant_research_engine/gui/static/account.css").read_text(encoding="utf-8")
SKILL = ROOT / ".agents/skills/unslop/SKILL.md"


def test_unslop_skill_is_installed_with_attribution():
    assert SKILL.is_file()
    text = SKILL.read_text(encoding="utf-8")
    assert "heydamir" in text
    assert "CC BY 4.0" in text


def test_quiet_chrome_contract():
    assert "QRE-UNSLOP-QUIET-CHROME" in THEME
    assert "--card-radius:12px" in THEME
    assert "body::before{display:none}" in THEME
    assert "QRE-UNSLOP-QUIET-CHROME" in CARDS
    assert "backdrop-filter:none" in THEME.replace(" ", "")
    assert "backdrop-filter:none" in CARDS.replace(" ", "")
    assert "/static/card-fx.js" not in BASE
    assert ".btn-primary::after{display:none}" in THEME



def test_auth_workspace_avoids_marketing_hero_slop():
    assert "QRE-UNSLOP-ACCOUNT" in ACCOUNT
    assert "font-size: clamp(32px, 3.2vw, 44px)" in ACCOUNT
    assert "font-weight: 700" in ACCOUNT
    assert "box-shadow: none" in ACCOUNT
