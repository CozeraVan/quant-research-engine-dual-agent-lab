#!/usr/bin/env bash
# QRE-ECS-SSH-HARDENING：deploy + sudo 部署脚本（root 直连已禁后的唯一部署入口）。
#
# 背景（2026-10-27）：ECS 已禁 root 直连（/etc/ssh/sshd_config.d/99-qre-hardening.conf：
# PermitRootLogin no / PasswordAuthentication no / KbdInteractiveAuthentication no /
# PubkeyAuthentication yes / AllowTcpForwarding yes），业务树 /srv/aguhuice/qre 属 root，
# 因此部署链必须是「deploy scp 到 /tmp → sudo install 到业务路径 → sudo systemctl
# restart qre-saas → 校验」。禁止再用 root@ 直连、禁止把文件落成 root 属主。
#
# 用法：
#   ./deploy/saas/deploy-ecs.sh <本地文件> [更多本地文件...]
#     # 本地路径按仓库相对路径映射到 /srv/aguhuice/qre/<同一相对路径>
#     ./deploy/saas/deploy-ecs.sh deploy/saas/metadata.json
#     ./deploy/saas/deploy-ecs.sh configs/factor_registry.json deploy/saas/metadata.json
#
#   ./deploy/saas/deploy-ecs.sh --dry-run <文件>   # 只打印将执行的步骤，不碰生产
#
# 环境变量：
#   SSH_KEY   默认 ~/.ssh/aguhuice_ed25519
#   ECS_HOST  默认 deploy@47.119.127.40
#   REMOTE_ROOT 默认 /srv/aguhuice/qre
#   SAAS_UNIT 默认 qre-saas（只重启它；worker 在家，绝不动）
#
# 纪律（R-DEPLOY-001）：改生产文件前先在本地跑测试；本脚本自带 /tmp 备份，
# 但**任务级回滚点**仍按各任务文档另存（如 /tmp/qre-<task>-pre-<date>/）。
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

KEY="${SSH_KEY:-$HOME/.ssh/aguhuice_ed25519}"
HOST="${ECS_HOST:-deploy@47.119.127.40}"
REMOTE_ROOT="${REMOTE_ROOT:-/srv/aguhuice/qre}"
SAAS_UNIT="${SAAS_UNIT:-qre-saas}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SSH_OPTS=(-i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15)

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then DRY_RUN=1; shift; fi

if [ "$#" -eq 0 ]; then
  echo "用法: $0 [--dry-run] <仓库相对路径文件> [...]" >&2
  exit 2
fi

# 本地文件必须存在，且按仓库相对路径解析（禁止绝对路径/越界路径）
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILES=()
for f in "$@"; do
  case "$f" in
    /*) echo "拒绝绝对路径（请用仓库相对路径）: $f" >&2; exit 2 ;;
    *)  ;;
  esac
  src="$REPO_ROOT/$f"
  [ -f "$src" ] || { echo "本地文件不存在: $src" >&2; exit 2; }
  FILES+=("$f")
done

echo "==> 目标: $HOST:$REMOTE_ROOT  单位: $SAAS_UNIT  时间戳: $STAMP"
for f in "${FILES[@]}"; do echo "    - $f"; done

if [ "$DRY_RUN" = "1" ]; then
  cat <<EOM
[dry-run] 将执行：
  1. scp 各文件到 $HOST:/tmp/qre-deploy-$STAMP/
  2. ssh $HOST 'sudo -n install -o deploy -g deploy -m 0644 <tmp> $REMOTE_ROOT/<同一相对路径>'
     （已在生产存在的文件先 sudo -n cp 到 /tmp/qre-deploy-$STAMP.bak/ 留回滚点）
  3. ssh $HOST 'sudo -n systemctl restart $SAAS_UNIT'
  4. ssh $HOST 'sudo -n systemctl is-active $SAAS_UNIT' 与公网应用层 curl 校验
[dry-run] 未触碰生产。
EOM
  exit 0
fi

REMOTE_TMP="/tmp/qre-deploy-$STAMP"
REMOTE_BAK="/tmp/qre-deploy-$STAMP.bak"
echo "==> 1/4 scp 到 $REMOTE_TMP"
# scp 不会自建远程嵌套目录，先按各文件的相对路径建好
MKDIR_CMDS="set -e; mkdir -p '$REMOTE_TMP' '$REMOTE_BAK';"
for f in "${FILES[@]}"; do MKDIR_CMDS+=" mkdir -p '$REMOTE_TMP/$(dirname "$f")';"; done
ssh "${SSH_OPTS[@]}" "$HOST" "$MKDIR_CMDS"
for f in "${FILES[@]}"; do
  scp "${SSH_OPTS[@]}" -q "$REPO_ROOT/$f" "$HOST:$REMOTE_TMP/$f.tmp"
done

echo "==> 2/4 sudo install 到业务路径（先留回滚副本）"
# 用远程脚本文件而不是内联字符串：嵌套路径/引号不会被二次转义搞坏。
# 路径在本地就展开写死（这些路径不含引号，免得起引号地狱）。
REMOTE_SCRIPT="$REMOTE_TMP/install.sh"
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  for f in "${FILES[@]}"; do
    echo "mkdir -p '$REMOTE_BAK/$(dirname "$f")' '$REMOTE_ROOT/$(dirname "$f")'"
    echo "if [ -f '$REMOTE_ROOT/$f' ]; then cp -a '$REMOTE_ROOT/$f' '$REMOTE_BAK/$f'; fi"
    echo "install -o deploy -g deploy -m 0644 '$REMOTE_TMP/$f.tmp' '$REMOTE_ROOT/$f'"
  done
  echo "rm -rf '$REMOTE_TMP'"
  echo "echo installed"
} > /tmp/qre-deploy-install.$$.sh
scp "${SSH_OPTS[@]}" -q /tmp/qre-deploy-install.$$.sh "$HOST:$REMOTE_SCRIPT"
rm -f /tmp/qre-deploy-install.$$.sh
ssh "${SSH_OPTS[@]}" "$HOST" "sudo -n bash '$REMOTE_SCRIPT'"

echo "==> 3/4 重启 $SAAS_UNIT（仅此单位；worker 在家不动）"
ssh "${SSH_OPTS[@]}" "$HOST" "sudo -n systemctl restart '$SAAS_UNIT' && sleep 3 && sudo -n systemctl is-active '$SAAS_UNIT'"

echo "==> 4/4 校验"
ssh "${SSH_OPTS[@]}" "$HOST" "sudo -n systemctl show -p MainPID '$SAAS_UNIT'; \
  curl -s -o /dev/null -w 'api/saas/factors %{http_code}\n' -H 'Host: www.aguhuice.com' http://127.0.0.1:8090/api/saas/factors; \
  curl -s -o /dev/null -w '/saas/new %{http_code}\n' -H 'Host: www.aguhuice.com' http://127.0.0.1:8090/saas/new"

echo "==> 完成。生产回滚副本在 $HOST:$REMOTE_BAK（恢复：sudo -n install 回原路径并 restart $SAAS_UNIT）"
