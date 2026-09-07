"""新因子代码的 Docker 隔离执行器（QRE-SAAS-005）。

威胁模型：factor-create 路径 B（NL 生成因子 Python 类）最终要 import/exec
生成的代码做冒烟计算——这是 NL 链路里**唯一真正执行任意代码**的点
（策略 YAML 是声明式，由 security.yaml_guard 前置把关）。即便
``factor_nl_compiler.check_code_safety`` 已做 AST 白名单，公网开放前仍要
执行隔离兜底（防御纵深）：容器禁网 + 资源上限 + 只读根文件系统 + 降权。

容器参数：--network none --memory 512m --cpus 1 --pids-limit 100
--read-only --cap-drop ALL --security-opt no-new-privileges --user 65534
超时 120s 强杀（--rm + timeout 后 docker kill），stdout/stderr 限 1MB。

docker 命令前缀可注入：默认 ['docker']（van 在 docker 组）；
env SANDBOX_DOCKER_SUDO=1 时用 ['sudo', '-n', 'docker']（如 systemd 服务
账号不在 docker 组的场景）。

镜像：deploy/saas/sandbox.Dockerfile（python:3.12-slim + pandas/numpy/
pandas_ta），build_image() 封构建命令；容器内禁网故因子冒烟所需数据
须以只读挂载/文件形式传入（M4 接入时定），本执行器只管隔离运行。

注意：--network none 下容器无法连本地 PG，因子冒烟的 DB 输入须预先导出
挂载——这是 factor-create 沙箱化的既有设计前提（本切片只交付隔离执行器）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_IMAGE = "qre-factor-sandbox:3.12"
DEFAULT_TIMEOUT_SECONDS = 120
MAX_OUTPUT_BYTES = 1_000_000
DOCKERFILE_DIR = Path(__file__).resolve().parents[3] / "deploy" / "saas"

# 容器硬限制（单一事实来源，测试断言引用）
CONTAINER_LIMITS = {
    "network": "none",
    "memory": "512m",
    "cpus": "1",
    "pids_limit": "100",
}


def docker_cmd_prefix() -> list[str]:
    if os.environ.get("SANDBOX_DOCKER_SUDO") == "1":
        return ["sudo", "-n", "docker"]
    return ["docker"]


def docker_available(prefix: list[str] | None = None) -> bool:
    """docker 是否可用（二进制存在且 daemon 可达）。"""
    cmd = prefix or docker_cmd_prefix()
    if shutil.which(cmd[0]) is None:
        return False
    try:
        proc = subprocess.run([*cmd, "info"], capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def image_available(image: str = DEFAULT_IMAGE, prefix: list[str] | None = None) -> bool:
    cmd = prefix or docker_cmd_prefix()
    try:
        proc = subprocess.run([*cmd, "image", "inspect", image], capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def build_image(image: str = DEFAULT_IMAGE, prefix: list[str] | None = None) -> None:
    """构建沙箱镜像（deploy/saas/sandbox.Dockerfile）。失败抛 RuntimeError。"""
    cmd = prefix or docker_cmd_prefix()
    proc = subprocess.run(
        [*cmd, "build", "-t", image, "-f", str(DOCKERFILE_DIR / "sandbox.Dockerfile"),
         str(DOCKERFILE_DIR)],
        capture_output=True, text=True, timeout=1800,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"沙箱镜像构建失败: {proc.stderr[-2000:]}")


def run_sandboxed(
    code: str,
    *,
    image: str = DEFAULT_IMAGE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    prefix: list[str] | None = None,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    """在隔离容器内执行 Python 代码。

    返回 {"ok", "exit_code", "stdout", "stderr", "timed_out", "truncated"}；
    调用方按 exit_code/timed_out 判定，本函数不抛执行语义异常。
    """
    cmd_prefix = prefix or docker_cmd_prefix()
    import uuid

    container_name = f"qre-sandbox-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="qre-sandbox-") as tmp:
        workdir = Path(tmp)
        main_py = workdir / "main.py"
        main_py.write_text(code, encoding="utf-8")
        # 容器以 nobody(65534) 运行：只读挂载须保证他人可读
        workdir.chmod(0o755)
        main_py.chmod(0o644)
        run_cmd = [
            *cmd_prefix, "run", "--rm", "--name", container_name,
            "--network", CONTAINER_LIMITS["network"],
            "--memory", CONTAINER_LIMITS["memory"],
            "--cpus", CONTAINER_LIMITS["cpus"],
            "--pids-limit", CONTAINER_LIMITS["pids_limit"],
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "65534:65534",  # nobody
            "-v", f"{workdir}:/work:ro",
            "-w", "/work",
            image, "python", "main.py",
        ]
        try:
            proc = subprocess.run(run_cmd, capture_output=True, timeout=timeout + 10)
            stdout, stderr, exit_code, timed_out = proc.stdout, proc.stderr, proc.returncode, False
        except subprocess.TimeoutExpired:
            # 超时时 docker CLI 已死但容器仍在：按名字强杀（--rm 负责清理）
            subprocess.run([*cmd_prefix, "kill", container_name], capture_output=True, timeout=15)
            stdout, stderr, exit_code, timed_out = b"", b"", None, True
    truncated = len(stdout) > max_output_bytes or len(stderr) > max_output_bytes
    return {
        "ok": exit_code == 0 and not timed_out,
        "exit_code": exit_code,
        "stdout": stdout[:max_output_bytes].decode("utf-8", errors="replace"),
        "stderr": stderr[:max_output_bytes].decode("utf-8", errors="replace"),
        "timed_out": timed_out,
        "truncated": truncated,
    }
