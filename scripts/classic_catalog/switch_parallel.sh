#!/usr/bin/env bash
# 串行 ↔ 并行切换（重载 worker 槽位的一次性编排）。
#
# 为什么要等空档：改槽位必须 restart worker，而 restart 会打断在飞的回测
# 子进程（2026-11-07 CF-065 已跑 3h，直接重启等于白烧）。所以本脚本：
#   1) 写 SUPERVISOR_HALTED，停监管（防止它在切换过程中拉起新驱动）
#   2) 停本地驱动（服务端 job 照常跑完，job 不丢）
#   3) 轮询生产库直到「任何用户都没有 running/queued 任务」
#   4) install serial.conf -> daemon-reload -> restart worker
#   5) 解除 HALT，拉起监管（它按 FULLSCALE_ARGS，默认 --resume --concurrency 2）
#
# 槽位数由 deploy/saas/qre-saas-worker.serial.conf 决定；切回串行就先把该文件
# 改成 --heavy-slots 1 再跑本脚本（或直接用 FULLSCALE_ARGS 覆盖驱动侧）。
#
# 用法：bash scripts/classic_catalog/switch_parallel.sh [--max-wait-min 360]
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1

STATE_DIR=.tmp/classic-catalog-fullscale
LOG=$STATE_DIR/parallel-switch.log
HALT=$STATE_DIR/SUPERVISOR_HALTED
SERIAL_CONF=deploy/saas/qre-saas-worker.serial.conf
SSH=(ssh -i "$HOME/.ssh/aguhuice_ed25519" -o BatchMode=yes deploy@47.119.127.40)
MAX_WAIT_MIN=360
[ "${1:-}" = "--max-wait-min" ] && MAX_WAIT_MIN=${2:-360}

mkdir -p "$STATE_DIR"
log() { printf '%s | %s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }

active_jobs() {
  "${SSH[@]}" "sudo -n -u postgres psql -d aguhuice -At -c \"select count(*) from jobs where status in ('running','queued')\"" 2>/dev/null | tr -d '[:space:]'
}

log "=== 开始切换：目标槽位 $(grep -o 'heavy-slots [0-9]*' "$SERIAL_CONF" | tail -1) ==="
printf '%s 切换槽位，暂停监管（switch_parallel.sh）\n' "$(date '+%F %T')" >"$HALT"
pkill -f 'classic_catalog/fullscale.py' >/dev/null 2>&1
log "本地驱动已停；服务端在飞任务不受影响"

deadline=$(( $(date +%s) + MAX_WAIT_MIN * 60 ))
while :; do
  n=$(active_jobs)
  if [ "${n:-x}" = "0" ]; then
    log "队列已空（running+queued=0），可以重启 worker"
    break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "等待 ${MAX_WAIT_MIN} 分钟仍有 ${n} 个活动任务，放弃切换并恢复监管"
    rm -f "$HALT"
    nohup bash scripts/classic_catalog/supervise.sh >/dev/null 2>&1 &
    exit 1
  fi
  sleep 20
done

sudo -n install -m 0644 "$SERIAL_CONF" /etc/systemd/system/qre-saas-worker.service.d/serial.conf \
  && log "已安装 serial.conf" || { log "安装 serial.conf 失败"; exit 1; }
sudo -n systemctl daemon-reload && log "daemon-reload 完成"
sudo -n systemctl restart qre-saas-worker.service && log "worker 已重启"
sleep 6
pid=$(systemctl show -p MainPID --value qre-saas-worker.service)
state=$(systemctl is-active qre-saas-worker.service)
slots=$(systemctl cat qre-saas-worker.service --no-pager | grep -o 'heavy-slots [0-9]*' | tail -1)
log "worker active=$state MainPID=$pid $slots"

rm -f "$HALT"
# 旧版监管的长驻子进程（event_watch）可能继承 flock 的 fd 9，使新监管被判「已有
# supervisor 实例持有锁」而退出——2026-11-07 因此空转 1h49m。启动前先清掉任何
# 锁持有者并等锁释放（锁只应由监管自己持有，杀掉长驻子进程是安全的：它的状态
# 全在磁盘上，重启后按去重状态续记）。
for pid in $(ls /proc 2>/dev/null | grep -E '^[0-9]+$'); do
  if [ -e "/proc/$pid/fd/9" ] && readlink "/proc/$pid/fd/9" 2>/dev/null | grep -q supervisor.lock; then
    log "清理锁持有者 pid=$pid（cmd=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null)）"
    kill "$pid" >/dev/null 2>&1
  fi
done
sleep 3
nohup bash scripts/classic_catalog/supervise.sh >/dev/null 2>&1 &
log "HALT 已解除，监管与驱动已重新拉起"
echo "switch done: active=$state pid=$pid $slots"