#!/usr/bin/env bash
# QRE-SAAS-ADMIN-TUNNEL：ECS SaaS 管理台（/saas/console）已从公网撤下（nginx return 404），
# 仅经 SSH 隧道访问。本脚本把 ECS 上的 gunicorn（127.0.0.1:8090）映射到本地 9090。
#
# 用法：
#   ./deploy/saas/admin-tunnel.sh
#   保持本进程运行，然后浏览器打开  http://localhost:9090/saas/console
#   （登录用管理员账号；token 存 localStorage，按 localhost:9090 独立）
# 结束：Ctrl-C。
set -euo pipefail

KEY="${SSH_KEY:-$HOME/.ssh/aguhuice_ed25519}"
HOST="${ECS_HOST:-root@47.119.127.40}"
LOCAL_PORT="${LOCAL_PORT:-9090}"

exec ssh -N \
  -i "$KEY" \
  -o IdentitiesOnly=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L "${LOCAL_PORT}:127.0.0.1:8090" \
  "$HOST"
