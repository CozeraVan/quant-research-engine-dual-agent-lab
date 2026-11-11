#!/usr/bin/env bash
# QRE 大库本地一致备份（上云迁移准备；默认 dry-run，不执行备份）。
#
# 用法：
#   bash deploy/cloud/backup-market-db.sh --dry-run
#   SOURCE_DB_URL="postgresql://..." bash deploy/cloud/backup-market-db.sh --out /path/to/dir
#
# 说明：
# - 默认从 QRE_MARKET_DB_URL 或 SOURCE_DB_URL 读取源库；
# - 输出 custom format dump + sha256 + manifest.json；
# - manifest 不含任何密钥。
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

DRY_RUN=0
OUT_DIR=""
SOURCE_DB_URL="${SOURCE_DB_URL:-${QRE_MARKET_DB_URL:-}}"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --out) OUT_DIR="${2:-}"; shift 2 ;;
    --source) SOURCE_DB_URL="${2:-}"; shift 2 ;;
    -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$SOURCE_DB_URL" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] 未设置 SOURCE_DB_URL/QRE_MARKET_DB_URL；真运行时会要求"
    exit 0
  fi
  echo "缺少源库连接：请设置 SOURCE_DB_URL 或 QRE_MARKET_DB_URL" >&2
  exit 2
fi

# 连接串归一化：QRE_MARKET_DB_URL 是 SQLAlchemy 形态（postgresql+psycopg://…），
# pg_dump/psql 只认 libpq 形态，必须去掉 +psycopg，否则被当成库名报错。
SOURCE_DB_URL="${SOURCE_DB_URL/postgresql+psycopg:\/\//postgresql:\/\/}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${OUT_DIR:-./qre-cloud-backup-$STAMP}"
DUMP="$OUT_DIR/tushare_data-$STAMP.dump"

echo "== QRE market DB backup =="
# 不在日志里写用户名/密码：只保留 host（之前 ${%%@*} 会把密码打进日志）
echo "source: $(printf %s "$SOURCE_DB_URL" | sed -E 's#//[^@]*@#//***@#')"
echo "out:    $DUMP"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] 将执行：mkdir -p '$OUT_DIR'; pg_dump -Fc -Z 6; sha256sum; 生成 manifest.json"
  exit 0
fi

mkdir -p "$OUT_DIR"
# 允许以 postgres 超级用户执行（TimescaleDB 的 _compressed_hypertable_* 只读账号无权）：
# PG_DUMP_PREFIX="sudo -n -u postgres"。输出走 stdout 重定向（由当前用户写文件），
# 避免 postgres 用户对 van 目录无写权限的问题。
${PG_DUMP_PREFIX:-} pg_dump -Fc -Z 6 -d "$SOURCE_DB_URL" > "$DUMP"
sha256sum "$DUMP" > "$DUMP.sha256"

DB_SIZE_BYTES="$(${PG_DUMP_PREFIX:-} psql "$SOURCE_DB_URL" -Atc 'SELECT pg_database_size(current_database())')"
PG_VERSION="$(${PG_DUMP_PREFIX:-} psql "$SOURCE_DB_URL" -Atc 'SHOW server_version')"
TS_VERSION="$(${PG_DUMP_PREFIX:-} psql "$SOURCE_DB_URL" -Atc "SELECT extversion FROM pg_extension WHERE extname='timescaledb'" || true)"

cat > "$OUT_DIR/manifest.json" <<EOF
{
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "source_db_url": "${SOURCE_DB_URL%%@*}@***",
  "dump_file": "$(basename "$DUMP")",
  "dump_sha256": "$(awk '{print $1}' "$DUMP.sha256")",
  "dump_size_bytes": $(stat -c%s "$DUMP"),
  "db_size_bytes": $DB_SIZE_BYTES,
  "pg_version": "$PG_VERSION",
  "timescaledb_version": "$TS_VERSION"
}
EOF

echo "backup done: $DUMP"
echo "manifest: $OUT_DIR/manifest.json"
