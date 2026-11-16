from quant_research_engine.gui.saas import create_saas_app


def test_mcp_guide_page_is_public_and_complete():
    client = create_saas_app().test_client()
    response = client.get('/saas/mcp-guide')
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    for marker in (
        'MCP 使用说明', 'https://aguhuice.com/mcp', '/saas/profile#mcp',
        'submit_backtest', 'qre-mcp-export', 'qre-mcp-login', 'SHA-256',
        '不构成投资建议',
    ):
        assert marker in text


def test_mcp_guide_linked_from_profile_dropdown():
    from pathlib import Path
    base = Path('src/quant_research_engine/gui/saas/templates/base.html').read_text(encoding='utf-8')
    assert 'href="/saas/mcp-guide"' in base
