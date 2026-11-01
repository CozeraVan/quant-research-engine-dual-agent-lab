#!/usr/bin/env bash
set -euo pipefail

echo "== Git Finalize Check =="

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: Not inside a git repository."
  exit 1
fi

echo
echo "== Current branch =="
git branch --show-current || true

echo
echo "== Git status =="
git status --short

echo
echo "== Changed files =="
git diff --name-only HEAD || true

echo
echo "== Progress docs check =="
if [ -x scripts/check-progress-docs.sh ]; then
  scripts/check-progress-docs.sh
else
  echo "WARNING: scripts/check-progress-docs.sh not found or not executable."
fi

echo
echo "== Secret scan =="
# 硬失败：只匹配「键 = 长随机值」形态（真泄漏），不再因文档里出现 api_tokens 这类
# 标识符/表名而误报（2026-11-02 第四入口设计文档引入 api_tokens 表名导致误报）。
SECRET_SCAN_FILE=/tmp/agent-credential-scan.txt
if git diff --unified=0 HEAD | grep -E '^\+[^+]' \
  | grep -Ei "(api[_-]?key|secret|token|password|passwd|credential)[\"']?[[:space:]]*[:=：][[:space:]]*[\"']?[A-Za-z0-9/_.+-]{16,}" \
  >"$SECRET_SCAN_FILE"; then
  echo "ERROR: Potential secret-like text found in git diff."
  cat "$SECRET_SCAN_FILE"
  rm -f "$SECRET_SCAN_FILE"
  exit 1
else
  echo "No secret-like assignment found in git diff."
fi
rm -f "$SECRET_SCAN_FILE"

# 软提醒：仅出现关键字（无赋值）时列出行供人工扫一眼，不阻断提交。
if git diff --unified=0 HEAD | grep -E '^\+[^+]' \
  | grep -Ei '[a]pi[_-]?key|[s]ecret|[t]oken|[p]assword|[p]asswd|BEGIN (RSA|OPENSSH|PRIVATE) KEY' \
  >/tmp/agent-credential-mentions.txt; then
  echo "NOTE: lines mention key/token-like words (no assignment matched) — please eyeball:"
  cat /tmp/agent-credential-mentions.txt
else
  echo "No key/token-like word mentions in git diff."
fi
rm -f /tmp/agent-credential-mentions.txt

echo
echo "== Remote =="
git remote -v || true

echo
echo "Git finalize check completed."
