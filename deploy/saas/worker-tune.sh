#!/usr/bin/env bash
# R3 切片2（2026-10-04）：本机 worker 资源配置一键应用。
# 更新 /etc/qre-saas-worker.env 的槽位/内存闸门键并重启 qre-saas-worker。
# 用法（console「Worker 资源」卡在不一致时给出可直接复制的同款命令）：
#   bash deploy/saas/worker-tune.sh --light-slots 2 --heavy-slots 3 \
#       --light-min-avail-mb 2000 --heavy-min-avail-mb 6500
set -euo pipefail

ENV_FILE=${QRE_WORKER_ENV_FILE:-/etc/qre-saas-worker.env}
SERVICE=${QRE_WORKER_SERVICE-qre-saas-worker}  # 显式置空 = 跳过重启（测试）

usage() {
    echo "用法: $0 --light-slots N --heavy-slots N --light-min-avail-mb M --heavy-min-avail-mb M" >&2
    exit 2
}

declare -A KV=()
while [ $# -gt 0 ]; do
    case "$1" in
        --light-slots)          KV[QRE_WORKER_LIGHT_SLOTS]=$2 ;;
        --heavy-slots)          KV[QRE_WORKER_HEAVY_SLOTS]=$2 ;;
        --light-min-avail-mb)   KV[QRE_WORKER_LIGHT_MIN_AVAIL_MB]=$2 ;;
        --heavy-min-avail-mb)   KV[QRE_WORKER_HEAVY_MIN_AVAIL_MB]=$2 ;;
        *) echo "未知参数: $1" >&2; usage ;;
    esac
    [[ "$2" =~ ^[0-9]+$ ]] || { echo "错误：$1 的值须为非负整数，收到 '$2'" >&2; exit 2; }
    shift 2
done
[ ${#KV[@]} -eq 4 ] || usage

# 自提权：/etc 下的 env 文件与 systemctl 都需要 root；目标文件可写时（测试）跳过
if [ "$EUID" -ne 0 ] && [ ! -w "$ENV_FILE" ]; then
    exec sudo QRE_WORKER_ENV_FILE="$ENV_FILE" QRE_WORKER_SERVICE="$SERVICE" bash "$0" \
        --light-slots "${KV[QRE_WORKER_LIGHT_SLOTS]}" \
        --heavy-slots "${KV[QRE_WORKER_HEAVY_SLOTS]}" \
        --light-min-avail-mb "${KV[QRE_WORKER_LIGHT_MIN_AVAIL_MB]}" \
        --heavy-min-avail-mb "${KV[QRE_WORKER_HEAVY_MIN_AVAIL_MB]}"
fi

[ -f "$ENV_FILE" ] || { echo "错误：$ENV_FILE 不存在" >&2; exit 1; }

backup="${ENV_FILE}.bak-$(date +%Y%m%d%H%M%S)"
cp -a "$ENV_FILE" "$backup"
echo "已备份：$backup"

for key in "${!KV[@]}"; do
    if grep -qE "^${key}=" "$ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${KV[$key]}|" "$ENV_FILE"
    else
        echo "${key}=${KV[$key]}" >> "$ENV_FILE"
    fi
done

echo "新配置："
for key in QRE_WORKER_LIGHT_SLOTS QRE_WORKER_HEAVY_SLOTS QRE_WORKER_LIGHT_MIN_AVAIL_MB QRE_WORKER_HEAVY_MIN_AVAIL_MB; do
    grep -E "^${key}=" "$ENV_FILE"
done

if [ -n "$SERVICE" ]; then
    systemctl restart "$SERVICE"
    sleep 2
    systemctl is-active "$SERVICE"
    echo "已重启 $SERVICE；下次 status 上报（默认 15s 内）管理台将回到一致态"
else
    echo "QRE_WORKER_SERVICE 为空，跳过重启（测试模式）"
fi