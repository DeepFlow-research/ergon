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

Stack is up.

Smoke runs (pytest execs inside the api container — zero host setup):

    scripts/smoke_local_run.sh minif2f            # cohort_size=1 by default
    scripts/smoke_local_run.sh researchrubrics 3  # match CI cohort size

E2B_API_KEY + OPENROUTER_API_KEY must be set in the shell before
``smoke_local_up.sh`` runs — docker compose passes them through to the
api container.

Playwright screenshots run host-side (they need node + pnpm + chromium):

    export COHORT_KEY=<copy from the pytest output>
    pnpm --dir ergon-dashboard exec playwright test \
         tests/e2e/${ENV}.smoke.spec.ts --project=chromium

Teardown: docker compose down -v
API logs: docker compose logs -f api
Dashboard logs: docker compose logs -f dashboard
EOF
