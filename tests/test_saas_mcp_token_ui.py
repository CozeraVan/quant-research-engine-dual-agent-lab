from pathlib import Path


def test_profile_has_mcp_token_self_service():
    text = Path("src/quant_research_engine/gui/saas/templates/profile.html").read_text(encoding="utf-8")
    for marker in (
        'data-profile-view-link="mcp"', 'data-profile-view="mcp"',
        'id="mcp-token-form"', 'id="mcp-token-list"', 'id="mcp-token-value"',
        "'/api/agent/v1/tokens'", "+ '/revoke'", 'loadMcpTokens();',
    ):
        assert marker in text
    assert "'shares', 'mcp'" in text
    assert "allow_full_market:false" in text


def test_mcp_token_list_does_not_render_plaintext_or_hash():
    text = Path("src/quant_research_engine/gui/saas/templates/profile.html").read_text(encoding="utf-8")
    assert "d.token.plaintext" in text  # 仅创建成功响应
    assert "it.plaintext" not in text
    assert "it.token_hash" not in text
