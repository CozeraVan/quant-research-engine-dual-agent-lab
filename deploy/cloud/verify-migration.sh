#!/usr/bin/env bash
# QRE 迁移对账：源库 vs 目标库。默认 dry-run。
#
# 用法：
#   bash deploy/cloud/verify-migration.sh --dry-run
#   bash deploy/cloud/verify-migration.sh --source "$HOME_DB_URL" --target "$CLOUD_DB_URL"
#   bash deploy/cloud/verify-migration.sh --source ... --target ... --tables public.stock_daily,factors.stock_daily_alpha191
#
# 说明：
# - 对账行数 + min/max 时间列 + DB 大小 + TimescaleDB 扩展；
# - 大表 count 可能很慢，这是预期；真迁移验收必须跑；
# - 不通过时退出码非 0。
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

DRY_RUN=0
SOURCE="${SOURCE_DB_URL:-${QRE_MARKET_DB_URL:-}}"
TARGET="${CLOUD_DB_URL:-}"
TABLES="public.stock_daily:trade_date,public.stock_minute_1m:trade_time,factors.stock_daily_overlap_close:trade_date,factors.stock_daily_momentum_close:trade_date,factors.stock_daily_alpha191:trade_date,reference.stock_basic:"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --source) SOURCE="${2:-}"; shift 2 ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    --tables) TABLES="${2:-}"; shift 2 ;;
    -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] tables: $TABLES"
  echo "[dry-run] 需要 --source 和 --target；将逐表 count/min/max，并比较 pg_database_size 与 timescaledb extversion"
  exit 0
fi

if [ -z "$SOURCE" ] || [ -z "$TARGET" ]; then
  echo "缺少 --source 或 --target" >&2
  exit 2
fi

echo "== QRE migration verification =="
echo "source: ${SOURCE%%@*}@***"
echo "target: ${TARGET%%@*}@***"

q() { psql "$1" -Atc "$2"; }

fail=0

src_size="$(q "$SOURCE" 'SELECT pg_database_size(current_database())')"
tgt_size="$(q "$TARGET" 'SELECT pg_database_size(current_database())')"
src_ts="$(q "$SOURCE" "SELECT extversion FROM pg_extension WHERE extname='timescaledb'" || true)"
tgt_ts="$(q "$TARGET" "SELECT extversion FROM pg_extension WHERE extname='timescaledb'" || true)"

printf '%s\n' '--- database-level ---'
printf 'source db bytes: %s\n' "$src_size"
printf 'target db bytes: %s\n' "$tgt_size"
printf 'source timescaledb: %s\n' "${src_ts:-missing}"
printf 'target timescaledb: %s\n' "${tgt_ts:-missing}"
if [ "$src_ts" != "$tgt_ts" ]; then
  echo "FAIL: timescaledb version mismatch"
  fail=1
fi

printf '%s\n' '--- table-level ---'
IFS=',' read -r -a items <<< "$TABLES"
for item in "${items[@]}"; do
  tbl="${item%%:*}"
  col="${item#*:}"
  if ! [[ "$tbl" =~ ^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$ ]]; then
    echo "FAIL: illegal table name: $tbl"
    fail=1
    continue
  fi
  if [ -n "$col" ] && [ "$col" != "$tbl" ] && ! [[ "$col" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "FAIL: illegal date column: $col"
    fail=1
    continue
  fi
  if [ -n "$col" ] && [ "$col" != "$tbl" ]; then
    sql="SELECT count(*) || '|' || min($col) || '|' || max($col) FROM $tbl"
  else
    sql="SELECT count(*) FROM $tbl"
  fi
  src_val="$(q "$SOURCE" "$sql")"
  tgt_val="$(q "$TARGET" "$sql")"
  if [ "$src_val" = "$tgt_val" ]; then
    printf 'OK   %-55s %s\n' "$tbl" "$src_val"
  else
    printf 'FAIL %-55s source=%s target=%s\n' "$tbl" "$src_val" "$tgt_val"
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "verification FAILED"
  exit 1
fi
echo "verification PASSED"
