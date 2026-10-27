#!/usr/bin/env bash
# QRE-SAAS-ADMIN-TUNNEL 附加项：从 ECS 拉取最新 aguhuice PG dump 到本地。
# ECS 侧由 root cron 每日 03:17 生成 /srv/aguhuice/backups/aguhuice-*.dump（保留 7 天）；
# 本脚本由本地 WSL cron 每日运行（建议错开 ECS 生成时间，如 04:23），scp 拉取模式，
# ECS 无需反向访问。本地只保留最近 7 份。
#
# 手动执行：./deploy/saas/pull-ecs-backup.sh
# 本地目标目录：~/quant-workspace/backups/ecs-aguhuice/
#
# QRE-ECS-SSH-HARDENING（2026-10-27）：root 直连已禁（PermitRootLogin no），
# 默认走 deploy 用户拉取（/srv/aguhuice/backups 为 0644，deploy 可读）。
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

KEY="${SSH_KEY:-$HOME/.ssh/aguhuice_ed25519}"
HOST="${ECS_HOST:-deploy@47.119.127.40}"
DEST="${BACKUP_DIR:-$HOME/quant-workspace/backups/ecs-aguhuice}"
mkdir -p "$DEST"

latest=$(ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes "$HOST" \
  'ls -1t /srv/aguhuice/backups/aguhuice-*.dump | head -1')
name=$(basename "$latest")
if [ -s "$DEST/$name" ]; then
  echo "already have $name, skip"
else
  scp -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes "$HOST:$latest" "$DEST/$name"
  echo "pulled $name"
fi
# 本地同样只留最近 7 份
ls -1t "$DEST"/aguhuice-*.dump 2>/dev/null | tail -n +8 | xargs -r rm -f
