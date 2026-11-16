from quant_research_engine.gui.saas import create_saas_app


def test_membership_center_page_and_navigation():
    client = create_saas_app().test_client()
    response = client.get('/saas/membership')
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    for marker in ('会员中心', '当前权益', '订单记录', '尚未开放购买', '每支付周期30次'):
        assert marker in text
    from pathlib import Path
    base = Path('src/quant_research_engine/gui/saas/templates/base.html').read_text(encoding='utf-8')
    assert 'href="/saas/membership"' in base
