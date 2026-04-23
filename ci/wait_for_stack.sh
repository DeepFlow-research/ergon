#!/usr/bin/env bash
# Wait for the CI docker-compose stack (postgres + inngest + api) to be
# reachable.  Exits nonzero after a 60-second deadline.
#
# Used by .github/workflows/e2e-benchmarks.yml before running pytest.
# Keeps the workflow log clean: failures here point at a specific
# service rather than surfacing as a pytest collection error.

set -euo pipefail

DEADLINE=$(( $(date +%s) + 60 ))

check() {
  local name="$1" probe="$2"
  until eval "$probe"; do
    if (( $(date +%s) > DEADLINE )); then
      echo "FATAL: $name did not become ready within 60s" >&2
      return 1
    fi
    echo "  waiting for ${name}..."
    sleep 2
  done
  echo "  $name ready"
}

# Postgres via docker exec (host may not have pg_isready installed).
check "postgres"  "docker compose -f docker-compose.ci.yml exec -T postgres pg_isready -U ergon > /dev/null 2>&1"
check "inngest"   "curl -sf http://localhost:8289/v1/events/test > /dev/null 2>&1"
# The api has no / or /healthz route today; any HTTP response (including
# 404) from uvicorn counts as "reachable".  ``curl -s`` without ``-f``
# returns 0 on any HTTP status; ``--connect-timeout 2`` keeps probes snappy.
check "api"       "curl -s -o /dev/null --connect-timeout 2 http://localhost:9000/ 2>/dev/null"

echo "stack up"
