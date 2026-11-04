"""阿里云短信通道（SmsSender）与发码通道路由测试（2026-11-04）。

覆盖：自定义验证码请求构造、非 OK 响应报错、缺配置可读错误、
_get_sender 按 target 类型分流（邮箱 SMTP / 手机阿里云 / stub 优先）。
不触发真实发送：SDK Client 以 fake 替换。
"""

from __future__ import annotations

import json

import pytest
from flask import Flask

from quant_research_engine.gui.saas import app as saas_app_mod
from quant_research_engine.gui.saas.app import SmsSender, _get_sender


class _FakeBody:
    def __init__(self, code="OK", message=""):
        self.code = code
        self.message = message


class _FakeResponse:
    def __init__(self, code="OK", message=""):
        self.body = _FakeBody(code, message)


class FakeClient:
    sent = []

    def __init__(self, config):
        self.config = config

    def send_sms_verify_code(self, request):
        FakeClient.sent.append(request)
        return FakeClient.resp


@pytest.fixture(autouse=True)
def _fake_sdk(monkeypatch):
    import alibabacloud_dypnsapi20170525.client as client_mod

    FakeClient.sent = []
    FakeClient.resp = _FakeResponse()
    monkeypatch.setattr(client_mod, "Client", FakeClient)
    yield


def _configure(monkeypatch):
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "sk")
    monkeypatch.setenv("ALIYUN_SMS_SIGN_NAME", "赠送签名")
    monkeypatch.setenv("ALIYUN_SMS_TEMPLATE_CODE", "SMS_123456")


def test_missing_config_raises(monkeypatch):
    for key in ("ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
                "ALIYUN_SMS_SIGN_NAME", "ALIYUN_SMS_TEMPLATE_CODE"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="未配置"):
        SmsSender().send("13800000000", "123456")


def test_send_uses_custom_code_request(monkeypatch):
    _configure(monkeypatch)
    SmsSender().send("13800000000", "203582")
    assert len(FakeClient.sent) == 1
    req = FakeClient.sent[0]
    assert req.phone_number == "13800000000"
    # 自定义验证码经模板变量 ${code} 下发：QRE 自生成自校验
    assert json.loads(req.template_param) == {"code": "203582"}
    assert req.code_length == 6
    assert req.sign_name == "赠送签名"
    assert req.template_code == "SMS_123456"


def test_send_non_ok_raises(monkeypatch):
    _configure(monkeypatch)
    FakeClient.resp = _FakeResponse(code="isv.SIGN_NOT_MATCH", message="签名不匹配")
    with pytest.raises(RuntimeError, match="签名不匹配"):
        SmsSender().send("13800000000", "123456")


def _app(channel):
    app = Flask(__name__)
    app.config["SAAS_AUTH_CHANNEL"] = channel
    return app


def test_sender_routes_email_and_sms(monkeypatch):
    _configure(monkeypatch)
    app = _app("auto")
    assert isinstance(_get_sender(app, "user@example.com"), saas_app_mod.EmailSender)
    assert isinstance(_get_sender(app, "13800000000"), SmsSender)


def test_sender_stub_wins_over_routing():
    app = _app("stub")
    assert isinstance(_get_sender(app, "user@example.com"), saas_app_mod.StubSender)
    assert isinstance(_get_sender(app, "13800000000"), saas_app_mod.StubSender)


def test_sender_sms_channel_email_target_still_email(monkeypatch):
    # 全局 channel=sms 时，邮箱 target 也必须走 SMTP（否则邮箱验证码会被短信通道吃掉）
    app = _app("sms")
    assert isinstance(_get_sender(app, "user@example.com"), saas_app_mod.EmailSender)
