#!/usr/bin/env bash
# Wait for the Next.js dashboard production build to start serving on
# port 3000.  Exits nonzero after a 60-second deadline.

set -euo pipefail

DEADLINE=$(( $(date +%s) + 60 ))

until curl -sf http://localhost:3000 > /dev/null 2>&1; do
  if (( $(date +%s) > DEADLINE )); then
    echo "FATAL: dashboard did not become ready within 60s" >&2
    exit 1
  fi
  echo "  waiting for dashboard..."
  sleep 2
done

echo "dashboard up"
