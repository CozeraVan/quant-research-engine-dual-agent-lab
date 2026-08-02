#!/usr/bin/env bash
# install_timers_hardened.sh — 安装 QRE qre-refresh hardened systemd unit。
#
# ⚠️ 需用户手动执行，会改动 systemd（/etc/systemd/system/）并启用定时任务。
# 用法：bash scripts/install_timers_hardened.sh
#
# 本脚本只安装 QRE 自己的 qre-refresh.{service,timer}（hardened 版）。
# 上游两个项目的 unit 请按脚本末尾打印的指引到各自项目目录手动安装。
set -euo pipefail

UNIT_SRC="deploy/hardened"
UNIT_DST="/etc/systemd/system"

echo "==> [1/4] 复制 hardened unit 到 ${UNIT_DST}（需 sudo）"
sudo cp -v "${UNIT_SRC}/qre-refresh.service" "${UNIT_SRC}/qre-refresh.timer" "${UNIT_DST}/"

echo "==> [2/4] daemon-reload"
sudo systemctl daemon-reload

echo "==> [3/4] 启用并立即启动 timer"
sudo systemctl enable --now qre-refresh.timer

echo "==> [4/4] 状态确认"
systemctl list-timers qre-refresh.timer --no-pager || true

cat <<'EOF'

完成。qre-refresh.timer 已安装（每日 18:30 ±5min，watermark 无新数据时自动跳过）。

上游项目的 hardened unit 本脚本不代装，请分别到项目目录查看其 deploy/ 说明手动安装：
  - quant_ts:          /home/van/quant-workspace/quant_ts/deploy/         (quant-ts-daily.timer, 16:30)
  - indicators_tushare:/home/van/quant-workspace/indicators_tushare/deploy/ (indicators-tushare-daily.timer, 16:40)
两个项目当前均已有 timer 在运行，如需 hardened 变体请先停用旧 unit 再安装，避免重复触发。
EOF
