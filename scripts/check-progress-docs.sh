#!/usr/bin/env bash
set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  exit 0
fi

CHANGED_FILES="$(git diff --name-only HEAD 2>/dev/null || true)"

if [ -z "$CHANGED_FILES" ]; then
  echo "No uncommitted changes."
  exit 0
fi

CODE_CHANGED="$(printf '%s\n' "$CHANGED_FILES" | grep -E '^(src/|app/|components/|screens/|services/|lib/|api/|server/|backend/|packages/|tests/|__tests__/|ios/|android/|package\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|tsconfig\.json|babel\.config\.js|metro\.config\.js|app\.json|pyproject\.toml|requirements\.txt|poetry\.lock|Cargo\.toml|go\.mod|Dockerfile|docker-compose\.ya?ml)' || true)"

PROGRESS_DOC_CHANGED="$(printf '%s\n' "$CHANGED_FILES" | grep -E '^docs/agent/(03_ROADMAP|04_TASK_HANDOFF|05_PROGRESS|06_DECISION_LOG|08_IMPLEMENTATION_BRIEF|09_CODING_HANDOFF|10_REVIEW_REPORT|11_AGENT_STATE)\.md$' || true)"

if [ -n "$CODE_CHANGED" ] && [ -z "$PROGRESS_DOC_CHANGED" ]; then
  echo "ERROR: Code/config changed, but progress or handoff docs were not updated."
  echo
  echo "Please update at least one of:"
  echo "- docs/agent/04_TASK_HANDOFF.md"
  echo "- docs/agent/05_PROGRESS.md"
  echo "- docs/agent/08_IMPLEMENTATION_BRIEF.md"
  echo "- docs/agent/09_CODING_HANDOFF.md"
  echo "- docs/agent/10_REVIEW_REPORT.md"
  echo "- docs/agent/11_AGENT_STATE.md"
  echo "- docs/agent/06_DECISION_LOG.md if architecture/data/safety/compliance changed"
  exit 1
fi

echo "Progress docs check passed."
