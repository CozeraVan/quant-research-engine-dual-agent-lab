#!/usr/bin/env bash
# QRE 大库逻辑迁移（pg_dump custom -> pg_restore）。默认 dry-run。
#
# 用法：
#   bash deploy/cloud/migrate-market-db.sh --dry-run
#   bash deploy/cloud/migrate-market-db.sh --full --source /path/to/dump --target "$CLOUD_DB_URL"
#
# 说明：
# - 仅做逻辑迁移准备；真迁移前必须用户批准；
# - 目标库默认必须为空；确认要写入非空库时加 --allow-nonempty；
# - 不包含 GRANT/OWNER，权限在云端单独最小化配置。
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

DRY_RUN=0
MODE=""
SOURCE=""
TARGET="${CLOUD_DB_URL:-}"
ALLOW_NONEMPTY=0
JOBS="${MIGRATE_JOBS:-4}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --full) MODE="full"; shift ;;
    --source) SOURCE="${2:-}"; shift 2 ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    --allow-nonempty) ALLOW_NONEMPTY=1; shift ;;
    -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] 需要 --full --source <dump> --target <url>"
  echo "[dry-run] 将执行：目标非空检查 -> pg_restore --no-owner --no-privileges -j $JOBS"
  exit 0
fi

if [ "$MODE" != "full" ]; then
  echo "目前只实现 --full 逻辑迁移；增量追数请按 Runbook §4.3 用 watermark 作业" >&2
  exit 2
fi
if [ -z "$SOURCE" ] || [ -z "$TARGET" ]; then
  echo "缺少 --source 或 --target（CLOUD_DB_URL）" >&2
  exit 2
fi
if [ ! -f "$SOURCE" ]; then
  echo "源 dump 不存在: $SOURCE" >&2
  exit 2
fi

echo "== QRE market DB logical migration =="
echo "source dump: $SOURCE"
echo "target:      ${TARGET%%@*}@***"
echo "jobs:        $JOBS"

USER_TABLES="$(psql "$TARGET" -Atc "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')")"
if [ "$USER_TABLES" != "0" ] && [ "$ALLOW_NONEMPTY" -ne 1 ]; then
  echo "目标库非空（user tables=$USER_TABLES）；如确认覆盖请加 --allow-nonempty" >&2
  exit 3
fi

pg_restore --no-owner --no-privileges -j "$JOBS" -d "$TARGET" "$SOURCE"
echo "restore done"
