#!/usr/bin/env bash
# Run one smoke driver against the local stack by execing pytest INSIDE
# the api container.
#
# Usage: scripts/smoke_local_run.sh <env> [<cohort_size>]
#   env:         researchrubrics | minif2f | swebench-verified
#   cohort_size: integer, default 1 (local iteration preset).
#                CI uses 3; pass 3 here to mirror CI exactly.
#
# Assumes ``scripts/smoke_local_up.sh`` has already brought the stack up.
# No host-side env var exports are required — the env vars live inside
# the api container already (see ``docker-compose.yml``).  Playwright is
# skipped by default in this mode; run it separately on the host via
# ``scripts/smoke_playwright_run.sh`` once the cohort is persisted.

set -euo pipefail

env_slug="${1:?usage: smoke_local_run.sh <env> [cohort_size]}"
cohort_size="${2:-1}"

case "${env_slug}" in
  researchrubrics)   pyfile="tests/e2e/test_researchrubrics_smoke.py" ;;
  minif2f)           pyfile="tests/e2e/test_minif2f_smoke.py" ;;
  swebench-verified) pyfile="tests/e2e/test_swebench_smoke.py" ;;
  *) echo "unknown env: ${env_slug}" >&2; exit 2 ;;
esac

if ! docker compose ps --status running api | grep -q api; then
  echo "FATAL: api container is not running — run scripts/smoke_local_up.sh first" >&2
  exit 1
fi

echo "-> Running ${pyfile} inside api container with SMOKE_COHORT_SIZE=${cohort_size}"
echo "   (env: ${env_slug}; Playwright skipped — see smoke_playwright_run.sh)"
echo

docker compose exec \
  -e SMOKE_COHORT_SIZE="${cohort_size}" \
  -e SMOKE_ENV="${env_slug}" \
  -e SKIP_PLAYWRIGHT=1 \
  api \
  pytest "${pyfile}" -v --timeout=300 --tb=short
