# CR-2026-11-16 · 微信 Native 真实渠道适配层

- wechat_native.py：API v3 商户 RSA 签名、Native 下单、查单、平台回调验签、AES-GCM 解密。
- payments.py：配置齐全才走 native，返回 code_url；真实回调/查单校验商户、订单、金额、SUCCESS，并复用幂等履约事务。
- 配置键仅文档记录：QRE_WECHAT_MCHID/APPID/SERIAL_NUMBER/PRIVATE_KEY_PATH/PLATFORM_PUBLIC_KEY_PATH/NOTIFY_URL/API_V3_KEY；密钥只在受控环境，未读取或写入仓库。
- 241 项相关测试通过/14 skipped；生产无配置时回调404，商品200，未发真实交易。
- 平台证书轮换目前需运维更新平台公钥；真实支付前必须补小额支付/退款/对账验收。
