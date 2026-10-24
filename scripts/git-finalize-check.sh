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
if git diff --unified=0 HEAD | grep -E '^\+[^+]' | grep -Ei '[a]pi[_-]?key|[s]ecret|[t]oken|[p]assword|[p]asswd|BEGIN (RSA|OPENSSH|PRIVATE) KEY' >/tmp/agent-credential-scan.txt; then
  echo "ERROR: Potential secret-like text found in git diff."
  cat /tmp/agent-credential-scan.txt
  rm -f /tmp/agent-credential-scan.txt
  exit 1
else
  echo "No obvious secret-like text found in git diff."
fi
rm -f /tmp/agent-credential-scan.txt

echo
echo "== Remote =="
git remote -v || true

echo
echo "Git finalize check completed."
