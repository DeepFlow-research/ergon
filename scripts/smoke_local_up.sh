#!/usr/bin/env bash
# Bring up the full smoke stack for local iteration.
#
# Usage: scripts/smoke_local_up.sh
#
# Starts:
#   1. docker-compose.ci.yml (postgres + inngest + api) via ``up -d``
#   2. Next.js dashboard dev server on :3000 (not prod build — dev
#      server gives <3s reload vs prod's 30s rebuild per iteration)
#
# Waits for all four services to be reachable, then prints the env
# vars you should export before running ``scripts/smoke_local_run.sh``.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
cd "${ROOT}"

if ! command -v docker >/dev/null 2>&1; then
  echo "FATAL: docker CLI not on PATH" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "FATAL: docker daemon not running" >&2
  exit 1
fi
if ! command -v pnpm >/dev/null 2>&1; then
  echo "FATAL: pnpm not on PATH — dashboard dev server won't start" >&2
  exit 1
fi

echo "→ Starting docker stack (postgres + inngest-dev + api)…"
docker compose -f docker-compose.ci.yml up -d --build --wait
bash ci/wait_for_stack.sh

# Dashboard dev server in background.  Use nohup + disown so this
# script returns cleanly.
DASHBOARD_LOG="${ROOT}/.local-smoke.dashboard.log"
if pgrep -f "next .*dev.*3000" >/dev/null 2>&1; then
  echo "→ Dashboard dev server already running; skipping start"
else
  echo "→ Starting dashboard dev server (logs → ${DASHBOARD_LOG})…"
  nohup pnpm --dir ergon-dashboard dev > "${DASHBOARD_LOG}" 2>&1 &
  disown
fi
bash ci/wait_for_dashboard.sh

cat <<'EOF'

Stack is up.  Export these in your shell before running smoke:

    export ERGON_DATABASE_URL=postgresql://ergon:ci_test@localhost:5433/ergon
    export INNGEST_API_BASE_URL=http://localhost:8289
    export INNGEST_DEV=1
    export INNGEST_EVENT_KEY=dev
    export ERGON_API_BASE_URL=http://127.0.0.1:9000
    export PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000
    export ENABLE_TEST_HARNESS=1
    export TEST_HARNESS_SECRET=local-dev
    export SCREENSHOT_DIR=/tmp/playwright
    export E2B_API_KEY=<your key>   # required for real sandbox runs

Then: scripts/smoke_local_run.sh minif2f   (or researchrubrics / swebench-verified)

Teardown when done: docker compose -f docker-compose.ci.yml down -v
Dashboard log: .local-smoke.dashboard.log (tail with: tail -f .local-smoke.dashboard.log)
EOF
