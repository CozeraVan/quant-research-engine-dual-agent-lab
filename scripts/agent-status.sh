#!/usr/bin/env bash
set -euo pipefail

echo "== Agent State =="
if [ -f docs/agent/11_AGENT_STATE.md ]; then
  sed -n '1,120p' docs/agent/11_AGENT_STATE.md
else
  echo "docs/agent/11_AGENT_STATE.md not found."
fi

echo
echo "== Git Status =="
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git status --short
  echo
  echo "== Last commits =="
  git log --oneline -5 || true
else
  echo "Not a git repository."
fi
