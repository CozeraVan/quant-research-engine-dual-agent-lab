#!/usr/bin/env bash
# QRE 产物同步到对象存储（上云准备）。默认 dry-run，不同步。
#
# 用法：
#   bash deploy/cloud/sync-artifacts.sh --dry-run --src /home/van/qre-outputs --dst s3://<bucket>/qre-artifacts
#   bash deploy/cloud/sync-artifacts.sh --src /home/van/qre-outputs --dst s3://<bucket>/qre-artifacts
#   bash deploy/cloud/sync-artifacts.sh --src ... --dst <remote>:<path> --engine rclone
#
# 说明：
# - 自动选择 aws s3 / rclone；DEST 以 s3:// 开头且安装了 aws 时用 aws；
# - 生成 artifact-manifest.txt（相对路径 + sha256）并一并同步；
# - 默认不加 --delete；确需镜像删除时显式加 --delete。
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

DRY_RUN=0
DELETE=0
ENGINE="${SYNC_ENGINE:-auto}"
SRC=""
DST=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --delete) DELETE=1; shift ;;
    --engine) ENGINE="${2:-}"; shift 2 ;;
    --src) SRC="${2:-}"; shift 2 ;;
    --dst) DST="${2:-}"; shift 2 ;;
    -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$SRC" ] || [ -z "$DST" ]; then
  echo "缺少 --src 或 --dst" >&2
  exit 2
fi
if [ ! -d "$SRC" ]; then
  echo "源目录不存在: $SRC" >&2
  exit 2
fi

if [ "$ENGINE" = "auto" ]; then
  if [[ "$DST" == s3://* ]] && command -v aws >/dev/null 2>&1; then
    ENGINE="aws"
  elif command -v rclone >/dev/null 2>&1; then
    ENGINE="rclone"
  elif [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] 未安装 aws/rclone；真运行时需要一个同步引擎"
    echo "[dry-run] 将生成 sha256 manifest 并同步到目标存储"
    exit 0
  else
    echo "未找到 aws/rclone，且无法自动选择同步引擎" >&2
    exit 2
  fi
fi

MANIFEST="$SRC/artifact-manifest.txt"

echo "== QRE artifact sync =="
echo "src:  $SRC"
echo "dst:  $DST"
echo "engine: $ENGINE"
echo "delete: $DELETE"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] 将生成 sha256 manifest 并同步到目标存储"
  exit 0
fi

(
  cd "$SRC"
  find . -type f ! -name 'artifact-manifest.txt' -print0 | sort -z | xargs -0 sha256sum > artifact-manifest.txt
)

case "$ENGINE" in
  aws)
    if [[ "$DST" != s3://* ]]; then
      echo "aws 引擎要求 --dst 以 s3:// 开头" >&2
      exit 2
    fi
    args=(s3 sync "$SRC" "$DST")
    if [ "$DELETE" -eq 1 ]; then args+=(--delete); fi
    aws "${args[@]}"
    ;;
  rclone)
    args=(sync "$SRC" "$DST")
    if [ "$DELETE" -eq 1 ]; then args+=(--delete); fi
    rclone "${args[@]}"
    ;;
  *)
    echo "不支持的引擎: $ENGINE" >&2
    exit 2
    ;;
esac

echo "artifact sync done; manifest: $MANIFEST"
