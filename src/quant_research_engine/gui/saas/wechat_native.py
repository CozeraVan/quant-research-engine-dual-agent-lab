"""微信支付 API v3 Native 最小适配；未配置商户资料时保持不可用。"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API_ROOT = "https://api.mch.weixin.qq.com"


@dataclass(frozen=True)
class NativeConfig:
    mchid: str
    appid: str
    serial_number: str
    private_key_path: str
    platform_public_key_path: str
    notify_url: str
    platform_public_key_next_path: str = ""

    @classmethod
    def from_env(cls) -> "NativeConfig | None":
        values = {
            "mchid": os.environ.get("QRE_WECHAT_MCHID", ""),
            "appid": os.environ.get("QRE_WECHAT_APPID", ""),
            "serial_number": os.environ.get("QRE_WECHAT_SERIAL_NUMBER", ""),
            "private_key_path": os.environ.get("QRE_WECHAT_PRIVATE_KEY_PATH", ""),
            "platform_public_key_path": os.environ.get("QRE_WECHAT_PLATFORM_PUBLIC_KEY_PATH", ""),
            "notify_url": os.environ.get("QRE_WECHAT_NOTIFY_URL", ""),
        }
        if not all(values.values()):
            return None
        return cls(
            **values,
            platform_public_key_next_path=os.environ.get("QRE_WECHAT_PLATFORM_PUBLIC_KEY_NEXT_PATH", ""),
        )


class NativeClient:
    def __init__(self, config: NativeConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()

    def _private_key(self):
        return serialization.load_pem_private_key(
            Path(self.config.private_key_path).read_bytes(), password=None,
        )

    def _authorization(self, method: str, path: str, body: str) -> str:
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        message = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body}\n"
        signature = base64.b64encode(self._private_key().sign(
            message.encode(), padding.PKCS1v15(), hashes.SHA256(),
        )).decode()
        return (
            f'WECHATPAY2-SHA256-RSA2048 mchid="{self.config.mchid}",'
            f'nonce_str="{nonce}",timestamp="{timestamp}",serial_no="{self.config.serial_number}",'
            f'signature="{signature}"'
        )

    def _call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) if payload is not None else ""
        response = self.session.request(
            method, API_ROOT + path, data=body,
            headers={"Authorization": self._authorization(method, path, body),
                     "Content-Type": "application/json", "Accept": "application/json"},
            timeout=30,
        )
        data = response.json()
        if response.status_code >= 400:
            raise RuntimeError(f"微信支付请求失败（HTTP {response.status_code}）")
        return data

    def create_order(self, *, order_id: str, description: str, price_cents: int) -> str:
        result = self._call("POST", "/v3/pay/transactions/native", {
            "appid": self.config.appid, "mchid": self.config.mchid,
            "description": description, "out_trade_no": order_id,
            "notify_url": self.config.notify_url,
            "amount": {"total": price_cents, "currency": "CNY"},
        })
        code_url = result.get("code_url")
        if not code_url:
            raise RuntimeError("微信支付未返回 code_url")
        return code_url

    def query_order(self, order_id: str) -> dict[str, Any]:
        return self._call("GET", f"/v3/pay/transactions/out-trade-no/{order_id}?mchid={self.config.mchid}")

    def verify_callback(self, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        """验证时间戳、平台签名并解密 resource；业务字段由路由负责。"""
        try:
            callback_time = int(headers.get("Wechatpay-Timestamp", ""))
        except ValueError as exc:
            raise ValueError("微信支付通知时间戳无效") from exc
        if abs(time.time() - callback_time) > 300:
            raise ValueError("微信支付通知时间戳超出允许窗口")
        message = (
            headers.get("Wechatpay-Timestamp", "") + "\n"
            + headers.get("Wechatpay-Nonce", "") + "\n" + body.decode() + "\n"
        )
        signature = base64.b64decode(headers.get("Wechatpay-Signature", ""))
        paths = [self.config.platform_public_key_path]
        if self.config.platform_public_key_next_path:
            paths.append(self.config.platform_public_key_next_path)
        for index, path in enumerate(paths):
            public_key = serialization.load_pem_public_key(Path(path).read_bytes())
            try:
                public_key.verify(signature, message.encode(), padding.PKCS1v15(), hashes.SHA256())
                break
            except Exception:
                # 仅在还有轮换备用证书时继续；两者均失败则由最后一次验签异常拒绝。
                if index == len(paths) - 1:
                    raise
        event = json.loads(body)
        resource = event.get("resource") or {}
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        api_v3_key = os.environ.get("QRE_WECHAT_API_V3_KEY", "").encode()
        if len(api_v3_key) != 32:
            raise RuntimeError("微信 API v3 密钥未正确配置")
        plaintext = AESGCM(api_v3_key).decrypt(
            base64.b64decode(resource["nonce"]),
            base64.b64decode(resource["ciphertext"]),
            resource.get("associated_data", "").encode(),
        )
        result = json.loads(plaintext)
        if event.get("id"):
            result["_event_id"] = str(event["id"])
        return result
