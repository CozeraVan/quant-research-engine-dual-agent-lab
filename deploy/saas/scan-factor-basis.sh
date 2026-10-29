#!/usr/bin/env bash
# QRE-FACTOR-BASIS-CONTRACT 契约第 3 条（运维侧）：全量审计 per-symbol 产物的
# 复权口径标记（factor_basis）。
#
# 为什么需要它：因子表 hfq / K 线 qfq，价格型因子不除锚点就会与 K 线差一个复权
# 倍数（600330 实测 ema_5=113.26 vs 收盘 21.97）。这类问题已复发四次，光靠读取侧
# 拒发不够——得能主动发现「哪些产物没有口径标记」，否则永远是用户先发现。
#
# 扫的对象：ECS 上 live（uploads）与归档（archive）两处 job_*/_symbol_details/*.json.gz。
# 通过：全部产物带**已登记**口径 → 退出码 0。
# 失败：存在缺标记 / 未登记口径 / 读不动的产物 → 打印明细，退出码 1（可接 timer/告警）。
#
# 用法：
#   deploy/saas/scan-factor-basis.sh            # 审计并打印，非零退出即告警
#   deploy/saas/scan-factor-basis.sh --record   # 同时追加到仓库内审计日志
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

KEY="${SSH_KEY:-$HOME/.ssh/aguhuice_ed25519}"
HOST="${ECS_HOST:-deploy@47.119.127.40}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
# 与 MACD 旧系周扫同思路：审计日志落仓库内持久路径（不许放 .tmp，清了就没有历史）。
LOG="$REPO/deploy/saas/factor-basis-scan.log"
RECORD=0
[ "${1:-}" = "--record" ] && RECORD=1

SSH="ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15 $HOST"

# 远端一次性统计：live + archive 两处，逐产物取 factor_basis，按白名单判定。
# 白名单与 src/quant_research_engine/factor_basis.py 保持一致（改那边记得改这里）。
REMOTE='
import gzip, json, glob, collections
known = {"qfq_anchor_v1"}
roots = ["/srv/aguhuice/uploads", "/srv/aguhuice/archive"]
total = 0
bad = []
values = collections.Counter()
for root in roots:
    for f in sorted(glob.glob(root + "/job_*/_symbol_details/*.json.gz")):
        total += 1
        try:
            d = json.load(gzip.open(f, "rt", encoding="utf-8"))
            b = d.get("factor_basis")
        except Exception as exc:
            bad.append(("unreadable", f, type(exc).__name__))
            continue
        values[str(b)] += 1
        if not b:
            bad.append(("missing", f, ""))
        elif b not in known:
            bad.append(("unknown", f, str(b)))
print("scanned_files", total)
for k, v in sorted(values.items(), key=lambda kv: -kv[1]):
    print("basis_value", k, v)
print("bad_total", len(bad))
for kind, f, extra in bad[:200]:
    print("bad", kind, f, extra)
'

OUT="$($SSH "sudo -n python3 -c '$REMOTE'" 2>&1)" || { echo "远端审计失败："; echo "$OUT"; exit 1; }
echo "$OUT"

BAD_TOTAL="$(echo "$OUT" | awk '/^bad_total /{print $2}')"
echo
if [ "${BAD_TOTAL:-0}" = "0" ]; then
  echo ">>> QRE-FACTOR-BASIS-CONTRACT 审计通过：所有产物均带已登记口径 <<<"
else
  echo ">>> 审计失败：${BAD_TOTAL} 个产物口径缺失/未登记/不可读（见上方 bad 行）<<<"
fi

if [ "$RECORD" = "1" ]; then
  mkdir -p "$(dirname "$LOG")"
  { echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="; echo "$OUT"; } >> "$LOG"
  echo "已追加到 $LOG"
fi

[ "${BAD_TOTAL:-0}" = "0" ]
