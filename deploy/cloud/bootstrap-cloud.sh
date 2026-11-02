#!/usr/bin/env bash
# QRE 一键上云部署入口（买云后只跑这一条）。
#
# 前置：云资源已按 docs/agent/32_CLOUD_FULLSTACK_PREP_2026-11-03.md 创建好，
#       deploy/cloud/cloud.env 已填真实连接（由 cloud.env.example 复制）。
#
# 用法：
#   bash deploy/cloud/bootstrap-cloud.sh --dry-run                 # 只打印将执行的步骤，不碰任何机器
#   bash deploy/cloud/bootstrap-cloud.sh                           # 全流程：备份→迁移→对账→worker→产物→验收
#   bash deploy/cloud/bootstrap-cloud.sh --step migrate            # 只跑某一步（backup/migrate/verify/worker/artifacts/check）
#   ENV_FILE=deploy/cloud/cloud.env bash deploy/cloud/bootstrap-cloud.sh --dry-run
#
# 纪律：真迁移前必须用户批准；本脚本不购买资源、不修改源库 stock_daily、不切流。
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/cloud.env}"
DRY_RUN=0
STEP="all"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --step) STEP="${2:-}"; shift 2 ;;
    -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [ ! -f "$ENV_FILE" ]; then
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] 未找到 $ENV_FILE；真运行前请由 cloud.env.example 复制并填值"
    echo "[dry-run] 将依次执行：backup → migrate → verify → worker → artifacts → check"
    exit 0
  fi
  echo "缺少配置文件 $ENV_FILE（请先 cp deploy/cloud/cloud.env.example deploy/cloud/cloud.env 并填值）" >&2
  exit 2
fi

# shellcheck disable=SC1090
. "$ENV_FILE"

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] $*"
  else
    echo "+ $*"
    eval "$@"
  fi
}

need() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "cloud.env 缺少必需项：$name" >&2
    exit 2
  fi
}

preflight() {
  need SOURCE_DB_URL
  need LOCAL_BACKUP_DIR
  need CLOUD_DB_URL
  need CLOUD_DB_SSH
  need CLOUD_WORKER_SSH_LIST
  need QRE_SAAS_BASE_URL
  need QRE_WORKER_TOKEN
  need ARTIFACT_DST
  command -v pg_dump >/dev/null || { echo "缺少 pg_dump" >&2; exit 2; }
  command -v pg_restore >/dev/null || { echo "缺少 pg_restore" >&2; exit 2; }
  command -v rsync >/dev/null || { echo "缺少 rsync" >&2; exit 2; }
  echo "== 预检通过 =="
}

step_backup() {
  echo "== 1/6 本地一致备份 =="
  run "mkdir -p '$LOCAL_BACKUP_DIR'"
  run "SOURCE_DB_URL='$SOURCE_DB_URL' bash '$SCRIPT_DIR/backup-market-db.sh' --out '$LOCAL_BACKUP_DIR'"
}

step_migrate() {
  echo "== 2/6 逻辑迁移到云 DB =="
  local dump
  if [ "$DRY_RUN" -eq 1 ]; then
    dump="$LOCAL_BACKUP_DIR/<latest>.dump"  # dry-run 不真正产生备份，只打印计划
  else
    dump="$(find "$LOCAL_BACKUP_DIR" -name '*.dump' -o -name '*.backup' 2>/dev/null | sort | tail -1 || true)"
    if [ -z "$dump" ]; then
      echo "未在 $LOCAL_BACKUP_DIR 找到 dump 文件，请先跑 --step backup" >&2
      exit 2
    fi
  fi
  run "rsync -az -e 'ssh -i ${CLOUD_DB_SSH_KEY:-$HOME/.ssh/id_rsa}' '$dump' '${CLOUD_DB_SSH}:/tmp/qre-market.dump'"
  local extra=""
  if [ "${ALLOW_NONEMPTY:-0}" = "1" ]; then extra="--allow-nonempty"; fi
  run "ssh -i '${CLOUD_DB_SSH_KEY:-$HOME/.ssh/id_rsa}' '${CLOUD_DB_SSH}' "CLOUD_DB_URL='$CLOUD_DB_URL' bash -s -- --full --source /tmp/qre-market.dump --target '$CLOUD_DB_URL' $extra" < '$SCRIPT_DIR/migrate-market-db.sh'"
}

step_verify() {
  echo "== 3/6 迁移对账 =="
  run "SOURCE_DB_URL='$SOURCE_DB_URL' CLOUD_DB_URL='$CLOUD_DB_URL' bash '$SCRIPT_DIR/verify-migration.sh' --source '$SOURCE_DB_URL' --target '$CLOUD_DB_URL' --tables '${VERIFY_TABLES:-}'"
}

step_worker() {
  echo "== 4/6 部署云 worker =="
  local host key
  key="${CLOUD_WORKER_SSH_KEY:-$HOME/.ssh/id_rsa}"
  for host in $CLOUD_WORKER_SSH_LIST; do
    echo "-- 部署到 $host"
    run "rsync -az -e 'ssh -i $key' '$SCRIPT_DIR/qre-cloud-worker.service' '$SCRIPT_DIR/qre-cloud-worker.env.example' '$host:/tmp/'"
    run "ssh -i '$key' '$host' 'sudo -n mkdir -p /etc/qre && sudo -n cp /tmp/qre-cloud-worker.env.example /etc/qre/qre-cloud-worker.env && sudo -n cp /tmp/qre-cloud-worker.service /etc/systemd/system/qre-cloud-worker.service && sudo -n systemctl daemon-reload && sudo -n systemctl enable --now qre-cloud-worker'"
  done
}

step_artifacts() {
  echo "== 5/6 产物同步到对象存储 =="
  run "bash '$SCRIPT_DIR/sync-artifacts.sh' --src '${ARTIFACT_SRC:-/home/van/qre-outputs}' --dst '$ARTIFACT_DST'"
}

step_check() {
  echo "== 6/6 部署后验证 =="
  if [ "${SKIP_SMOKE:-0}" = "1" ]; then
    echo "已按 SKIP_SMOKE=1 跳过"
    return 0
  fi
  run "curl -fsS -o /dev/null -w 'saas /saas/ -> %{http_code}\n' '$QRE_SAAS_BASE_URL/saas/'"
  run "curl -fsS -o /dev/null -w 'saas factors -> %{http_code}\n' '$QRE_SAAS_BASE_URL/api/saas/factors'"
  for host in $CLOUD_WORKER_SSH_LIST; do
    run "ssh -i '${CLOUD_WORKER_SSH_KEY:-$HOME/.ssh/id_rsa}' '$host' 'systemctl is-active qre-cloud-worker && systemctl show qre-cloud-worker -p MainPID --value'"
  done
  echo "== 一键部署完成 =="
}

preflight
case "$STEP" in
  all) step_backup; step_migrate; step_verify; step_worker; step_artifacts; step_check ;;
  backup) step_backup ;;
  migrate) step_migrate ;;
  verify) step_verify ;;
  worker) step_worker ;;
  artifacts) step_artifacts ;;
  check) step_check ;;
  *) echo "未知 step: $STEP" >&2; exit 2 ;;
esac
