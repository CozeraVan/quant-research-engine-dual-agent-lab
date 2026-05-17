#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" 2>/dev/null || exit 0

if [ -x scripts/check-progress-docs.sh ]; then
  scripts/check-progress-docs.sh || {
    cat >&2 <<'ERR'
Progress or handoff documentation is missing.

Before stopping, update the appropriate docs:
- docs/agent/04_TASK_HANDOFF.md
- docs/agent/05_PROGRESS.md
- docs/agent/08_IMPLEMENTATION_BRIEF.md
- docs/agent/09_CODING_HANDOFF.md
- docs/agent/10_REVIEW_REPORT.md
- docs/agent/11_AGENT_STATE.md
- docs/agent/06_DECISION_LOG.md if needed

Use update-progress skill if available.
ERR
    exit 2
  }
fi

exit 0
