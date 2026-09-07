# QRE-SAAS-005 因子代码沙箱镜像
# 用途：在禁网/限资源/只读容器内执行 NL 生成的因子 Python 代码（冒烟计算）。
# 构建：python -c "from quant_research_engine.worker.sandbox import build_image; build_image()"
#   或 docker build -t qre-factor-sandbox:3.12 -f deploy/saas/sandbox.Dockerfile deploy/saas
# 依赖面按 pyproject.toml 因子计算所需最小集：pandas / numpy / pandas_ta。
FROM python:3.12-slim

RUN pip install --no-cache-dir pandas numpy pandas_ta \
    && useradd --create-home sandbox
USER sandbox
WORKDIR /work

# 容器入口由 worker.sandbox.run_sandboxed 指定（python main.py），
# 网络/资源/只读限制在 docker run 参数侧强制（worker/sandbox.py CONTAINER_LIMITS）。
