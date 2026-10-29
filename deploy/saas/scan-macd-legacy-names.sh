#!/usr/bin/env bash
# R4-4 / R5-2（TV_ROUND4 §5 / TV_ROUND5 §3）：MACD 旧系列名周扫。
#
# 目的：为「familyOf 旧名分支退场」提供**事件触发**证据，替代日历式退场。
# 触发条件（两条同时满足才动手删旧名分支，**两条均可由本脚本机械判定**）：
#   ① 连续 4 次周扫「新产物因子名含旧系（macd_dif/macd_dea/macd_hist）」计数为 0；
#   ② 所有 legacy_count>0 的 job **均已过期（创建时间早于保留期）或已归档**。
#
# 扫的对象：ECS 上 saas_uploads 下所有 job 的 per-symbol 产物因子名 + job 年龄。
# 输出：计数 + 命中的 job/symbol 明细 + 每个含旧系 job 的年龄与过期判定；
#       计数写入 .tmp/macd-legacy-scan.log 供连续 4 次的比对。
#
# 用法：
#   deploy/saas/scan-macd-legacy-names.sh                      # 扫并打印
#   deploy/saas/scan-macd-legacy-names.sh --record              # 扫并追加到周扫日志
#   LEGACY_RETENTION_DAYS=60 deploy/saas/scan-macd-legacy-names.sh   # 自定义保留期
#
# 环境变量：
#   LEGACY_RETENTION_DAYS   旧 job 保留期（天），默认 90。**参数值待用户确认**。
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

KEY="${SSH_KEY:-$HOME/.ssh/aguhuice_ed25519}"
HOST="${ECS_HOST:-deploy@47.119.127.40}"
ROOT="/srv/aguhuice/uploads"
LOG="$(cd "$(dirname "$0")/../.." && pwd)/.tmp/macd-legacy-scan.log"
# R5-2：条件②机械化——旧 job 保留期（天）。默认 90，待用户确认。
LEGACY_RETENTION_DAYS="${LEGACY_RETENTION_DAYS:-90}"
RECORD=0
[ "${1:-}" = "--record" ] && RECORD=1

SSH="ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 $HOST"

# 远端一次性统计：遍历所有 job 的 _symbol_details，解 gz 取因子 name，
# 只统计**含旧系名**的（新系 macd_12_26_9 等不算）。
REMOTE='
import gzip, json, glob, os, collections, time
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
# R5-2 条件②机械化：每个含旧系 job 的年龄 + 是否已过保留期
now = time.time()
retention = float(os.environ.get("LEGACY_RETENTION_DAYS", "90")) * 86400
for job in sorted(hits):
    # 年龄取**稳定的创建证据**：risk_report.json 优先（worker 生成即不再变），
    # 退回 job 目录 mtime。不能用 _symbol_details 目录 mtime——部署/拷贝会刷新它。
    jdir = os.path.join("'"$ROOT"'", "job_" + job)
    stamp = None
    for cand in ("risk_report.json",):
        fp = os.path.join(jdir, cand)
        if os.path.isfile(fp):
            stamp = os.path.getmtime(fp)
            break
    if stamp is None:
        try:
            stamp = os.path.getmtime(jdir)
        except OSError:
            stamp = None
    if stamp is None:
        print("legacy_age", job, "unknown", "unknown")
        continue
    age_days = (now - stamp) / 86400.0
    print("legacy_age", job, round(age_days, 1), "expired" if (now - stamp) > retention else "active")
print("retention_days", os.environ.get("LEGACY_RETENTION_DAYS", "90"))
'

OUT="$($SSH "sudo -n python3 -c '$REMOTE'" 2>&1)" || { echo "远端扫描失败："; echo "$OUT"; exit 1; }
echo "$OUT"

if [ "$RECORD" = "1" ]; then
  mkdir -p "$(dirname "$LOG")"
  { echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="; echo "$OUT"; } >> "$LOG"
  echo "已追加到 $LOG"
fi

# 触发判定（两条都可机械判定；不自动删代码，只报结论）
LEGACY_TOTAL="$(echo "$OUT" | awk '/^legacy_total /{print $2}')"
ACTIVE_JOBS="$(echo "$OUT" | awk '/^legacy_age / && $4 == "active" {print $2}' | tr '\n' ' ')"
echo
echo "保留期 LEGACY_RETENTION_DAYS = ${LEGACY_RETENTION_DAYS} 天"
if [ "${LEGACY_TOTAL:-0}" = "0" ]; then
  echo "条件①：本次旧系计数 0（需连续 4 次，见 $LOG）"
else
  echo "条件①：本次仍有 $LEGACY_TOTAL 个产物含旧系名 → 不满足"
fi
if [ -z "${ACTIVE_JOBS// /}" ]; then
  echo "条件②：所有含旧系的 job 均已过期或已归档 → 满足"
else
  echo "条件②：以下 job 仍在保留期内，未过期 → 不满足：${ACTIVE_JOBS}"
fi
if [ "${LEGACY_TOTAL:-0}" = "0" ] && [ -z "${ACTIVE_JOBS// /}" ]; then
  echo
  echo ">>> 两条触发条件均满足（若条件①已连续 4 次为 0），可删 familyOf 旧名分支 <<<"
else
  echo
  echo ">>> 退场条件未满足，familyOf 旧名分支继续保留 <<<"
fi
