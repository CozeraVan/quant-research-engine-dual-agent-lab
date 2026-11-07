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
ENV_FILE=/etc/qre-saas-worker.env
WEBBRIDGE=${WEBBRIDGE_URL:-http://127.0.0.1:10086/command}
SESSION=classic-catalog-smoke
SITE=https://aguhuice.com/saas/new
GROUP=经典策略全量回测
TOTAL_CF=118
INTERVAL=120
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
  nohup .venv/bin/python scripts/classic_catalog/event_watch.py >>"$STATE_DIR/event_watch.out" 2>&1 &
  sleep 2
  if running_watch; then log "事件监视器已重启 pid=$!"; else log "事件监视器重启失败"; fi
}

run_fullscale() {
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  log "resume: 剩余 $(remaining) 个 CF，启动 fullscale --resume"
  local started_at rc
  started_at=$(date +%s)
  .venv/bin/python scripts/classic_catalog/fullscale.py --resume >>"$STATE_DIR/fullscale.supervisor.out" 2>&1
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
          printf '%s 连续 3 次快速失败，需人工介入\n' "$(date '+%F %T')" >"$HALT"
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