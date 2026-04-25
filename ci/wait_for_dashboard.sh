#!/usr/bin/env bash
# Wait for the Next.js dashboard to start serving on port 3001.
# Exits nonzero after a 120-second deadline.
#
# Dev server (``pnpm dev``) compiles routes on first hit; the initial
# compile can take 30-60s on a cold ``.next`` cache.  ``curl -s``
# (without ``-f``) returns 0 on any HTTP response so 404/500 during
# warmup still counts as "process is up and responding".

set -euo pipefail

PORT="${DASHBOARD_PORT:-3001}"
DEADLINE=$(( $(date +%s) + 120 ))

until curl -s -o /dev/null --connect-timeout 2 "http://localhost:${PORT}/" 2>/dev/null; do
  if (( $(date +%s) > DEADLINE )); then
    echo "FATAL: dashboard did not become ready on :${PORT} within 120s" >&2
    exit 1
  fi
  echo "  waiting for dashboard on :${PORT}..."
  sleep 2
done

echo "dashboard up on :${PORT}"
