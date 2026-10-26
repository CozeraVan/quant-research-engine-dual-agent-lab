#!/usr/bin/env bash
# QRE-SAAS-PUBLIC-BETA-OPS：一次性干净跑关键公网路径真实 Chromium 验收。
# 每次全量重跑前重建临时库 + 重启 staging（seed 的 DROP DATABASE 会掐断在服连接）。
# 复用项目既有测试资产：.tmp/browser-venv（Playwright）+ .tmp/ms-playwright（Chromium）。
# Playwright 仅为测试工具，不进生产依赖；不启动真实 worker、不跑真实回测，
# LLM 由下方内联 bootstrap 以桩替换（不触真实 DeepSeek）。
set -euo pipefail
cd "$(dirname "$0")/../../.."
PID=$(ss -ltnp 2>/dev/null | grep :8099 | grep -oP 'pid=\K[0-9]+' | head -1 || true)
[ -n "${PID}" ] && kill "${PID}" && sleep 1
.venv/bin/python deploy/saas/public-beta-audit/seed.py
SAAS_DB_URL="postgresql+psycopg:///qre_public_beta_audit" \
SAAS_WORKER_TOKEN="public-beta-ops-token" SAAS_AUTH_CHANNEL="stub" SAAS_STUB_ECHO=1 \
SAAS_UPLOAD_DIR="$(pwd)/.tmp/public-beta-ops/uploads" \
  setsid nohup .venv/bin/python - <<'PYEOF' > .tmp/public-beta-ops/server.log 2>&1 &
import os
os.environ.update({"QRE_NL_LLM_BASE_URL": "https://llm.test",
                   "QRE_NL_LLM_API_KEY": "k", "QRE_NL_LLM_MODEL": "m"})
import sys
sys.path.insert(0, "src")
from quant_research_engine.gui import nl_compiler
nl_compiler.call_llm = lambda d, c, **kw: (
    "experiment:\n  name: audit\ndata:\n  market_fields: [close]\n"
    "signal:\n  entry: close > 0\n  exit: close < 0\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5, 10, 20]\n  quantiles: 5\n"
    "holding:\n  max_holding_days: 20\n")
nl_compiler._default_column_lookup = lambda db_url=None: None
from quant_research_engine.gui.saas import create_saas_app
app = create_saas_app()
app.config["SAAS_DB_URL"] = "postgresql+psycopg:///qre_public_beta_audit"
app.config["SAAS_WORKER_TOKEN"] = "public-beta-ops-token"
app.config["SAAS_DEV_AUTH"] = "1"
app.run(host="127.0.0.1", port=8099)
PYEOF
disown
sleep 5
PLAYWRIGHT_BROWSERS_PATH=.tmp/ms-playwright \
  .tmp/browser-venv/bin/python deploy/saas/public-beta-audit/browser_audit.py
