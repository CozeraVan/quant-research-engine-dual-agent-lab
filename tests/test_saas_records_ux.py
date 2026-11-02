"""个人策略库删除 UX 静态回归：有关联回测的策略禁用删除，并页面内显示原因。"""

from pathlib import Path


def test_delete_disabled_when_job_count_positive():
    js = Path("src/quant_research_engine/gui/saas/templates/_records_scripts.html").read_text(encoding="utf-8")
    assert "s.job_count > 0" in js
    assert "为保证历史可溯不允许删除" in js
    assert 'class="btn-sm" disabled data-tip=' in js


def test_inline_error_box_exists_and_is_used():
    body = Path("src/quant_research_engine/gui/saas/templates/_records_body.html").read_text(encoding="utf-8")
    js = Path("src/quant_research_engine/gui/saas/templates/_records_scripts.html").read_text(encoding="utf-8")
    assert 'id="strat-error"' in body
    assert "errBox.textContent = d.error" in js
    assert "errBox.textContent = ''" in js
