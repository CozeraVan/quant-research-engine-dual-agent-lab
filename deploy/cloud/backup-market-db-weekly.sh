#!/usr/bin/env bash
# QRE 大库每周备份（F-20）：pg_dump -Fc -Z6 + sha256 + manifest，只保留最新一份。
#
# 背景：`deploy/cloud/backup-market-db.sh` 只做单次 dump，没有周期与保留策略；
# 本脚本补上「磁盘闸门 + 定期 + 保留 1 份」。
#
# 磁盘口径：本机 1007G，目前剩 ~230G；519GB 库压缩后约 100–180GB。
# 保留策略只留**最新一份成功 dump**（两份同时存在可能撑爆磁盘）；
# 长期异地/多副本归上云方案（32 号 §0 的 OSS）。
#
# 安装：
#   sudo install -m 0644 deploy/cloud/qre-market-backup.service /etc/systemd/system/
#   sudo install -m 0644 deploy/cloud/qre-market-backup.timer /etc/systemd/system/
#   sudo systemctl daemon-reload && sudo systemctl enable --now qre-market-backup.timer
set -euo pipefail

BACKUP_ROOT=${QRE_BACKUP_ROOT:-/home/van/backups/market-db}
MIN_FREE_GB=${QRE_BACKUP_MIN_FREE_GB:-200}
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="$BACKUP_ROOT/$STAMP"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

free_gb=$(df -BG / | awk 'NR==2 {gsub("G","",$4); print $4}')
if [ "$free_gb" -lt "$MIN_FREE_GB" ]; then
  echo "磁盘可用 ${free_gb}G < ${MIN_FREE_GB}G，放弃本次备份（先清理或扩容）" >&2
  exit 1
fi

mkdir -p "$BACKUP_ROOT"
# 中断保护：被 kill/出错时清掉半成品目录，避免留下几 GB 的不可用 dump
# （用户 2026-11-11 提示可能 1 小时内重启 PC，pg_dump 519GB 未必跑得完）
trap 'rm -rf "$OUT_DIR"; echo "[$(date -Iseconds)] 备份中断，已清理半成品 $OUT_DIR" >&2' ERR INT TERM
echo "[$(date -Iseconds)] 开始备份 → $OUT_DIR（可用 ${free_gb}G）"

# shellcheck disable=SC1091
set -a; source /etc/qre-saas-worker.env; set +a

# 本机备份走 postgres 超级用户（peer 认证，不需要密码；TimescaleDB 内部压缩表
# 只读账号无权读取，2026-11-11 实测 permission denied for _compressed_hypertable_61）。
# SOURCE_DB_URL 用本机 libpq 形态（postgresql:///库名），与 QRE_MARKET_DB_URL 的
# SQLAlchemy 形态区分开。
export PG_DUMP_PREFIX="${QRE_BACKUP_PG_PREFIX:-sudo -n -u postgres}"
export SOURCE_DB_URL="${QRE_BACKUP_SOURCE_URL:-postgresql:///tushare_data}"

bash "$SCRIPT_DIR/backup-market-db.sh" --out "$OUT_DIR"

# 校验：dump 必须存在且 sha256 与 manifest 齐全
test -s "$OUT_DIR"/*.dump
ls "$OUT_DIR"/manifest.json >/dev/null

# 保留策略：仅保留最新一份（本次成功后删除更旧的目录）
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d ! -name "$STAMP" -exec rm -rf {} +

echo "[$(date -Iseconds)] 备份完成：$OUT_DIR"
du -sh "$OUT_DIR"