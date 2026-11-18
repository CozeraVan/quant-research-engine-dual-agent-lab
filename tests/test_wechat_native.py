from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from quant_research_engine.gui.saas.wechat_native import NativeClient, NativeConfig


def _config(tmp_path, private_key, public_key):
    private_path = tmp_path / 'private.pem'
    public_path = tmp_path / 'platform.pem'
    private_path.write_bytes(private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public_path.write_bytes(public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return NativeConfig('mch-1', 'app-1', 'serial-1', str(private_path), str(public_path),
                        'https://example.test/notify')


def test_native_sign_create_and_query(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = NativeClient(_config(tmp_path, key, key.public_key()))

    class Response:
        status_code = 200
        def json(self): return {'code_url': 'weixin://test'}
    class Session:
        def __init__(self): self.calls = []
        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            return Response()
    session = Session()
    client.session = session
    assert client.create_order(order_id='qre-1', description='初级会员', price_cents=2990) == 'weixin://test'
    auth = session.calls[0][2]['headers']['Authorization']
    assert auth.startswith('WECHATPAY2-SHA256-RSA2048')
    assert 'mch-1' in auth and 'serial-1' in auth
    assert json.loads(session.calls[0][2]['data'])['amount']['total'] == 2990
    client.query_order('qre-1')
    assert session.calls[1][0] == 'GET'
    assert 'out-trade-no/qre-1?mchid=mch-1' in session.calls[1][1]


def test_native_callback_signature_and_decrypt(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = _config(tmp_path, key, key.public_key())
    client = NativeClient(config)
    plaintext = json.dumps({'out_trade_no': 'qre-1', 'trade_state': 'SUCCESS'}).encode()
    api_key = b'x' * 32
    monkeypatch.setenv('QRE_WECHAT_API_V3_KEY', api_key.decode())
    encrypted = AESGCM(api_key).encrypt(b'nonce-test-1', plaintext, b'associated')
    event = {'resource': {'nonce': base64.b64encode(b'nonce-test-1').decode(),
                          'ciphertext': base64.b64encode(encrypted).decode(),
                          'associated_data': 'associated'}}
    body = json.dumps(event).encode()
    timestamp = str(int(__import__('time').time()))
    headers = {'Wechatpay-Timestamp': timestamp, 'Wechatpay-Nonce': 'nonce'}
    message = f"{timestamp}\nnonce\n{body.decode()}\n"
    signature = key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    headers['Wechatpay-Signature'] = base64.b64encode(signature).decode()
    result = client.verify_callback(body, headers)
    assert result['out_trade_no'] == 'qre-1'
    headers['Wechatpay-Nonce'] = 'tampered'
    try:
        client.verify_callback(body, headers)
        assert False
    except Exception:
        assert True


def test_native_callback_accepts_next_certificate_during_rotation(tmp_path, monkeypatch):
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    next_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = _config(tmp_path, old_key, old_key.public_key())
    next_path = tmp_path / 'platform-next.pem'
    next_path.write_bytes(next_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    config = __import__('dataclasses').replace(config, platform_public_key_next_path=str(next_path))
    client = NativeClient(config)
    plaintext = json.dumps({'out_trade_no': 'qre-rotate', 'trade_state': 'SUCCESS'}).encode()
    api_key = b'x' * 32
    monkeypatch.setenv('QRE_WECHAT_API_V3_KEY', api_key.decode())
    encrypted = AESGCM(api_key).encrypt(b'nonce-rotate', plaintext, b'associated')
    body = json.dumps({'resource': {'nonce': base64.b64encode(b'nonce-rotate').decode(),
                                    'ciphertext': base64.b64encode(encrypted).decode(),
                                    'associated_data': 'associated'}}).encode()
    timestamp = str(int(__import__('time').time()))
    message = f"{timestamp}\nnonce\n{body.decode()}\n"
    signature = next_key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    headers = {'Wechatpay-Timestamp': timestamp, 'Wechatpay-Nonce': 'nonce',
               'Wechatpay-Signature': base64.b64encode(signature).decode()}
    assert client.verify_callback(body, headers)['out_trade_no'] == 'qre-rotate'


def test_native_callback_rejects_stale_timestamp_before_signature(tmp_path):
    config = NativeConfig('mch-1', 'app-1', 'serial', 'missing-private',
                          str(tmp_path / 'missing-public'), 'https://example.test/notify')
    try:
        NativeClient(config).verify_callback(b'{}', {'Wechatpay-Timestamp': '1'})
        assert False
    except Exception as exc:
        assert '时间戳' in str(exc)


def test_native_config_disabled_without_credentials(monkeypatch):
    for key in list(os.environ):
        if key.startswith('QRE_WECHAT_'):
            monkeypatch.delenv(key)
    assert NativeConfig.from_env() is None
