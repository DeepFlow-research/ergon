#!/usr/bin/env bash
# Bring up the full smoke stack for local iteration.
#
# Usage: scripts/smoke_local_up.sh [--with-observability]
#
# Starts the unified docker-compose stack: postgres + api + dashboard +
# inngest-dev.  Add ``--with-observability`` to also start otel +
# jaeger via the ``observability`` profile.
#
# Waits for all services to be reachable, then prints the env vars to
# export before running ``scripts/smoke_local_run.sh``.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
cd "${ROOT}"

PROFILES_ARG=""
if [ "${1:-}" = "--with-observability" ]; then
  PROFILES_ARG="--profile observability"
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "FATAL: docker CLI not on PATH" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "FATAL: docker daemon not running" >&2
  exit 1
fi

echo "-> Starting unified docker stack (postgres + api + dashboard + inngest-dev)..."
# shellcheck disable=SC2086
docker compose ${PROFILES_ARG} up -d --build --wait

bash ci/wait_for_stack.sh
bash ci/wait_for_dashboard.sh

cat <<'EOF'

Stack is up.  Export these in your shell before running smoke:

    export ERGON_DATABASE_URL=postgresql://ergon:ergon_dev@localhost:5433/ergon
    export INNGEST_API_BASE_URL=http://localhost:8289
    export INNGEST_DEV=1
    export INNGEST_EVENT_KEY=dev
    export ERGON_API_BASE_URL=http://127.0.0.1:9000
    export PLAYWRIGHT_BASE_URL=http://127.0.0.1:3001
    export ENABLE_TEST_HARNESS=1
    export TEST_HARNESS_SECRET=local-dev
    export SCREENSHOT_DIR=/tmp/playwright
    export E2B_API_KEY=<your key>   # required for real sandbox runs

Then: scripts/smoke_local_run.sh minif2f   (or researchrubrics / swebench-verified)

Teardown: docker compose down -v
API logs: docker compose logs -f api
Dashboard logs: docker compose logs -f dashboard
EOF
