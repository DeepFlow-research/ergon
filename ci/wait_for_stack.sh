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
    echo "  waiting for $name…"
    sleep 2
  done
  echo "  $name ready"
}

check "postgres"  "pg_isready -h localhost -p 5433 -U ergon > /dev/null 2>&1"
check "inngest"   "curl -sf http://localhost:8289/v1/events/test > /dev/null 2>&1"
check "api"       "curl -sf http://localhost:9000/healthz > /dev/null 2>&1 || curl -sf http://localhost:9000/ > /dev/null 2>&1"

echo "stack up"
