from __future__ import annotations

import json

import pytest

from quant_research_engine.mcp_server.auth import credentials_path, load_credentials, login, logout
from quant_research_engine.mcp_server.client import AgentAPIClient, AgentAPIConfig


class Response:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


class Session:
    def __init__(self):
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers))
        if url.endswith('/auth/code'):
            return Response({'ok': True})
        if url.endswith('/auth/login'):
            return Response({'ok': True, 'token': 'session-secret'})
        return Response({'ok': True, 'token': {
            'id': 8, 'plaintext': 'agent-secret', 'expires_at': '2026-12-16T00:00:00Z',
        }})


def test_cli_login_saves_restricted_credentials_without_sms(tmp_path, monkeypatch):
    session = Session()
    # requests 在 login 函数内导入，patch 其本地工厂。
    import requests
    monkeypatch.setattr(requests, 'Session', lambda: session)
    target = tmp_path / 'credentials.json'
    result = login('13800000001', '123456', base_url='https://example.test', path=target)
    saved = json.loads(target.read_text())
    assert result['saved_to'] == str(target)
    assert target.stat().st_mode & 0o777 == 0o600
    assert saved['agent_token'] == 'agent-secret'
    assert '123456' not in target.read_text()
    assert session.calls[2][2]['Authorization'] == 'Bearer session-secret'
    monkeypatch.setenv('QRE_MCP_CREDENTIALS', str(target))
    monkeypatch.delenv('QRE_AGENT_TOKEN', raising=False)
    config = AgentAPIConfig.from_user()
    assert config.base_url == 'https://example.test/api/agent/v1'
    assert config.token == 'agent-secret'


def test_logout_revokes_then_deletes_credentials(tmp_path, monkeypatch):
    target = tmp_path / 'credentials.json'
    target.write_text(json.dumps({
        'schema': 'qre-mcp-credentials-v1', 'base_url': 'https://example.test',
        'agent_token': 'agent-secret', 'agent_token_id': 8, 'session_token': 'session-secret',
    }))
    calls = []
    monkeypatch.setattr(AgentAPIClient, 'request', lambda self, method, path, payload=None: calls.append((path, self.config.token)) or {'ok': True})
    assert logout(path=target) is True
    assert calls == [('/tokens/8/revoke', 'session-secret')]
    assert not target.exists()
    assert logout(path=target) is False


def test_missing_credentials_give_actionable_error(tmp_path, monkeypatch):
    monkeypatch.setenv('QRE_MCP_CREDENTIALS', str(tmp_path / 'missing.json'))
    monkeypatch.delenv('QRE_AGENT_TOKEN', raising=False)
    with pytest.raises(ValueError, match='qre-mcp-login'):
        AgentAPIConfig.from_user()
