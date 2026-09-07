"""SaaS 版入口（CR-0004 M1：QRE-SAAS-002 任务队列协议 + QRE-SAAS-004 骨架）。

`create_saas_app()` 是独立的 Flask app（8081 四功能入口的云侧 API），
与既有 gui/app.py（8080 管理台）/ lab*.py（8081 冻结页）完全隔离，
全部路由挂 /api/saas/ 前缀。云小库连接用环境变量 SAAS_DB_URL（PG）。
"""

from quant_research_engine.gui.saas.app import create_saas_app

__all__ = ["create_saas_app"]
