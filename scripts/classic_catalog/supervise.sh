#!/usr/bin/env bash
# CF 队列自愈监管：队列进程或事件监视器消失后自动拉起。
#
# 背景（2026-11-05/06）：fullscale.py 在 WebBridge 瞬断重试耗尽后以非零码退出，
# 事件监视器也可能随会话丢失。历史上两次 502 都靠主 Agent 手工恢复，中断期间
# ~8 小时无任务在跑。本脚本把「发现 → 重建标签 → 校验会话 → resume」变成自动循环。
#
# 只做三件事，绝不重复建单：
#   1) fullscale.py 不在跑 且 仍有未完成 CF → 校验/重建 WebBridge 标签 → resume
#   2) event_watch.py 不在跑 → 后台拉起
#   3) 每轮追加一行日志；连续快速失败 3 次则写 HALTED 标记并退出（交人判断）
#
# 用法：bash scripts/classic_catalog/supervise.sh [--once]
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 1

STATE_DIR=.tmp/classic-catalog-fullscale
LOG=$STATE_DIR/supervisor.log
HALT=$STATE_DIR/SUPERVISOR_HALTED
EVENT_LOG=docs/agent/40_CF_QUEUE_EVENT_LOG_2026-11-04.md
# F-03：worker cgroup 峰值达到 17 GiB 即降回 1 路（上限 18 GiB）。
# 只降提交深度、不打断在飞 job（它们在服务端继续跑）。
PEAK_PATH=/sys/fs/cgroup/system.slice/qre-saas-worker.service/memory.peak
PEAK_LIMIT_B=18253611008
ENV_FILE=/etc/qre-saas-worker.env
WEBBRIDGE=${WEBBRIDGE_URL:-http://127.0.0.1:10086/command}
SESSION=classic-catalog-smoke
SITE=https://aguhuice.com/saas/new
GROUP=经典策略全量回测
TOTAL_CF=118
INTERVAL=120
# 队列参数：默认 2 路流水线（用户 2026-11-07 批准）。要求 worker 重槽 ≥2
# （deploy/saas/qre-saas-worker.serial.conf 的 --heavy-slots），否则两个 job
# 只是排队不并行。改回串行用 FULLSCALE_ARGS="--resume" 启动本脚本。
FULLSCALE_ARGS=${FULLSCALE_ARGS:---resume --concurrency 2}
ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

mkdir -p "$STATE_DIR"

# 单实例锁：2026-11-07 发现 supervise.sh 曾被重复拉起两份（pid 1177017 + 其
# 命令替换子壳），两份同时监控会在队列退出瞬间各自 resume 一次。加锁后
# 后来的实例只写一行日志即退出，保证「一个队列 + 一个监管」。
LOCK=$STATE_DIR/supervisor.lock
exec 9>"$LOCK"
if ! flock -n 9; then
  printf '%s | 已有 supervisor 实例持有锁，本次退出 pid=%s\n' "$(date '+%F %T')" "$$" >>"$STATE_DIR/supervisor.log"
  exit 0
fi

log() { printf '%s | %s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }

# F-01：HALT 不能只落本地文件（11-08 因此无人知晓停了 17.8h）。
# 追加到 40 号长期事件日志；若配置 QRE_ALERT_WEBHOOK 再推一条外部消息。
write_halt() {
  local reason="$1"
  printf '%s %s\n' "$(date '+%F %T')" "$reason" >"$HALT"
  printf '| %s | HALT | - | - | %s |\n' "$(date -Iseconds)" "$reason" >>"$EVENT_LOG"
  if [ -n "${QRE_ALERT_WEBHOOK:-}" ]; then
    curl -sS -m 10 -X POST "$QRE_ALERT_WEBHOOK" -H 'Content-Type: application/json' \
      -d "{\"text\":\"QRE CF 队列已暂停：$reason\"}" >/dev/null 2>&1
  fi
}

# F-03：cgroup memory.peak 逼近上限时把提交深度降回 1 路。
check_memory_pressure() {
  [ -f "$PEAK_PATH" ] || return 0
  local peak
  peak=$(cat "$PEAK_PATH" 2>/dev/null)
  if [ "${peak:-0}" -ge "$PEAK_LIMIT_B" ] && [[ "$FULLSCALE_ARGS" != *"--concurrency 1"* ]]; then
    log "内存峰值 ${peak}B ≥ 17GiB，降档为 1 路（F-03）"
    printf '| %s | 降档 | - | - | cgroup peak %sB ≥ 17GiB，并发降为 1 |\n' "$(date -Iseconds)" "$peak" >>"$EVENT_LOG"
    FULLSCALE_ARGS="--resume --concurrency 1"
    # 主动停驱动让降档生效；在飞 job 在服务端继续跑，不丢数据
    pkill -f 'classic_catalog/fullscale.py' >/dev/null 2>&1
  fi
}

remaining() {
  # 用结果文件算已完成数（与 fullscale.py --resume 同一口径）
  local done=0
  if [ -f "$STATE_DIR/results.jsonl" ]; then
    done=$(grep -c '"status": *"completed"' "$STATE_DIR/results.jsonl" 2>/dev/null || echo 0)
  fi
  echo $((TOTAL_CF - done))
}

running_fullscale() { pgrep -f 'classic_catalog/fullscale\.py --resume' >/dev/null 2>&1; }
running_watch() { pgrep -f 'classic_catalog/event_watch\.py' >/dev/null 2>&1; }

wb() {  # wb <action> <json-args>
  curl -sS -m 20 -X POST "$WEBBRIDGE" -H 'Content-Type: application/json' \
    -d "{\"action\":\"$1\",\"args\":$2,\"session\":\"$SESSION\"}"
}

tab_count() { wb list_tabs '{}' | grep -o '"tabId"' | wc -l | tr -d ' '; }

ensure_tab() {
  local n
  n=$(tab_count)
  if [ "${n:-0}" -gt 0 ]; then
    log "tab ok (${n} 个)"
    return 0
  fi
  log "标签丢失，重建 -> $SITE"
  wb navigate "{\"url\":\"$SITE\",\"newTab\":true,\"group_title\":\"$GROUP\"}" >/dev/null
  sleep 5
  n=$(tab_count)
  if [ "${n:-0}" -gt 0 ]; then
    log "标签重建成功 (${n} 个)"
    return 0
  fi
  log "标签重建失败"
  return 1
}

session_ok() {
  # 会话失效（logged out）时 submit 会 401，届时需人工登录，脚本不硬闯
  local out
  out=$(wb evaluate '{"code":"(async()=>{const r=await apiFetch(\"/api/saas/me\");return {status:r.status};})()"}')
  case "$out" in
    *'"status":200'*) return 0 ;;
    *) log "会话校验失败：$out"; return 1 ;;
  esac
}

relaunch_watch() {
  # 9>&- 必须带：flock 用的是 fd 9，bash 会把该 fd 继承给子进程；event_watch
  # 是长驻进程，若它继承 fd 9，锁就被它永久持有，后续任何 supervisor 都会
  # 被判「已有实例」而退出（2026-11-07 实测踩坑：切换并行后监管自锁死 1h48m）。
  nohup .venv/bin/python scripts/classic_catalog/event_watch.py >>"$STATE_DIR/event_watch.out" 2>&1 9>&- &
  sleep 2
  if running_watch; then log "事件监视器已重启 pid=$!"; else log "事件监视器重启失败"; fi
}

run_fullscale() {
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  log "resume: 剩余 $(remaining) 个 CF，启动 fullscale $FULLSCALE_ARGS"
  local started_at rc
  started_at=$(date +%s)
  # shellcheck disable=SC2086
  .venv/bin/python scripts/classic_catalog/fullscale.py $FULLSCALE_ARGS >>"$STATE_DIR/fullscale.supervisor.out" 2>&1 9>&-
  rc=$?
  local dur=$(( $(date +%s) - started_at ))
  log "fullscale 退出 rc=$rc 用时 ${dur}s 剩余 $(remaining) 个"
  echo "$dur $rc"
}

log "supervisor 启动 (interval=${INTERVAL}s, once=${ONCE})"
fast_fails=0

while :; do
  if [ -f "$HALT" ]; then
    log "检测到 HALTED 标记，退出"; exit 0
  fi

  if ! running_watch; then
    log "事件监视器不在，尝试拉起"
    relaunch_watch
  fi

  rem=$(remaining)
  check_memory_pressure
  if [ "$rem" -le 0 ]; then
    log "全部 $TOTAL_CF 个 CF 已完成，supervisor 退出"
    exit 0
  fi

  if running_fullscale; then
    log "队列在跑 pid=$(pgrep -f 'classic_catalog/fullscale\.py --resume' | head -1) 剩余 $rem"
  else
    log "队列不在跑，剩余 $rem 个 CF"
    if ensure_tab && session_ok; then
      out=$(run_fullscale)
      dur=${out%% *}; rc=${out##* }
      if [ "$rc" -ne 0 ] && [ "$dur" -lt 60 ]; then
        fast_fails=$((fast_fails + 1))
        log "快速失败计数 $fast_fails/3"
        if [ "$fast_fails" -ge 3 ]; then
          write_halt "连续 3 次快速失败，需人工介入"
          log "写 HALTED 标记并退出"
          exit 1
        fi
        sleep 60
      else
        fast_fails=0
      fi
    else
      log "标签或会话不可用，等待重试（需要人工登录时脚本不会硬闯）"
      sleep 300
    fi
  fi

  [ "$ONCE" = "1" ] && exit 0
  sleep "$INTERVAL"
done