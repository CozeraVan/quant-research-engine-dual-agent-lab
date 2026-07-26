#!/usr/bin/env bash
# 全期全量回测（过夜手动执行）
# 用法:  bash scripts/run_full_history_overnight.sh
# 断点续跑: 直接再次执行同一命令即可（--resume 会跳过已完成策略）
set -euo pipefail

cd "$(dirname "$0")/.."
export QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data'

STAMP=$(date +%Y%m%d_%H%M%S)
OUT_DIR="outputs/backtests/full_history_overnight"
LOG="${OUT_DIR}_${STAMP}.log"
mkdir -p outputs/backtests

END_DATE=$(date +%Y-%m-%d)

echo "=================================================================="
echo " 全期全量回测  2010-01-04 → ${END_DATE}"
echo " 策略: 全部 111 个 catalog 策略 (含断点续跑)"
echo " 配置: vectorized / jobs 4 / 分块 400 / compact+workbook"
echo "      apply-stops + universe-filter + benchmark(000300.SH)"
echo " 日志: $LOG"
echo " 预估: 6-10 小时 (111 策略 × 全市场 × 16 年)"
echo "=================================================================="

time uv run python scripts/batch_backtest_runner.py \
  --start 2010-01-04 --end "${END_DATE}" \
  --engine-impl vectorized \
  --jobs 4 \
  --symbol-chunk-size 400 \
  --compact --workbook \
  --apply-stops \
  --universe-filter \
  --metadata-columns board industry_group market_cap_bucket liquidity_bucket \
  --benchmark-table reference.index_daily \
  --benchmark-code 000300.SH \
  --skip-preflight --skip-eval \
  --resume \
  --output-dir "${OUT_DIR}" 2>&1 | tee "${LOG}"

echo "完成. 产物目录: ${OUT_DIR}/"
echo "快速查看: ls ${OUT_DIR}/*/batch_summary.json"
