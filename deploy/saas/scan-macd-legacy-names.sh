#!/usr/bin/env bash
# R4-4（TV_ROUND4 §5）：MACD 旧系列名周扫。
#
# 目的：为「familyOf 旧名分支退场」提供**事件触发**证据，替代日历式退场。
# 触发条件（两条同时满足才动手删旧名分支）：
#   ① 连续 4 次周扫「新产物因子名含旧系（macd_dif/macd_dea/macd_hist）」计数为 0；
#   ② 旧 job（58/66/74/78）已归档或按保留期过期。
#
# 扫的对象：ECS 上 saas_uploads 下所有 job 的 per-symbol 产物因子名。
# 输出：计数 + 命中的 job/symbol 明细；计数写入 .tmp/macd-legacy-scan.log 供比对。
#
# 用法：
#   deploy/saas/scan-macd-legacy-names.sh            # 扫并打印
#   deploy/saas/scan-macd-legacy-names.sh --record    # 扫并追加到周扫日志
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

KEY="${SSH_KEY:-$HOME/.ssh/aguhuice_ed25519}"
HOST="${ECS_HOST:-deploy@47.119.127.40}"
ROOT="/srv/aguhuice/uploads"
LOG="$(cd "$(dirname "$0")/../.." && pwd)/.tmp/macd-legacy-scan.log"
RECORD=0
[ "${1:-}" = "--record" ] && RECORD=1

SSH="ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 $HOST"

# 远端一次性统计：遍历所有 job 的 _symbol_details，解 gz 取因子 name，
# 只统计**含旧系名**的（新系 macd_12_26_9 等不算）。
REMOTE='
import gzip, json, glob, os, collections
legacy = ("macd_dif", "macd_dea", "macd_hist")
hits = collections.Counter()
total = 0
for f in glob.glob("'"$ROOT"'/job_*/_symbol_details/*.json.gz"):
    total += 1
    try:
        d = json.load(gzip.open(f, "rt", encoding="utf-8"))
    except Exception:
        continue
    names = [str(x.get("name") or "") for x in (d.get("factors") or [])]
    if any(n in legacy for n in names):
        job = f.split("/job_")[1].split("/")[0]
        hits[job] += 1
print("scanned_files", total)
for job in sorted(hits):
    print("legacy_job", job, hits[job])
print("legacy_total", sum(hits.values()))
'

OUT="$($SSH "sudo -n python3 -c '$REMOTE'" 2>&1)" || { echo "远端扫描失败："; echo "$OUT"; exit 1; }
echo "$OUT"

if [ "$RECORD" = "1" ]; then
  mkdir -p "$(dirname "$LOG")"
  { echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="; echo "$OUT"; } >> "$LOG"
  echo "已追加到 $LOG"
fi

# 触发判定提示（不自动删代码，只报状态）
LEGACY_TOTAL="$(echo "$OUT" | awk '/^legacy_total /{print $2}')"
echo
if [ "${LEGACY_TOTAL:-0}" = "0" ]; then
  echo "本次周扫：旧系计数 0（条件①的其中一次满足；需连续 4 次）"
else
  echo "本次周扫：仍有 $LEGACY_TOTAL 个产物含旧系名 → 不满足退场条件①"
fi
