#!/usr/bin/env bash
# Run one smoke driver locally against an already-up stack.
#
# Usage: scripts/smoke_local_run.sh <env> [<cohort_size>]
#   env:         researchrubrics | minif2f | swebench-verified
#   cohort_size: integer, default 1 (local iteration preset).
#                CI uses 3; pass 3 here to mirror CI exactly.
#
# Assumes ``scripts/smoke_local_up.sh`` has been run and the env vars
# it printed are exported.  Errors loudly if they aren't.

set -euo pipefail

env_slug="${1:?usage: smoke_local_run.sh <env> [cohort_size]}"
cohort_size="${2:-1}"

case "${env_slug}" in
  researchrubrics)   pyfile="tests/e2e/test_researchrubrics_smoke.py" ;;
  minif2f)           pyfile="tests/e2e/test_minif2f_smoke.py" ;;
  swebench-verified) pyfile="tests/e2e/test_swebench_smoke.py" ;;
  *) echo "unknown env: ${env_slug}" >&2; exit 2 ;;
esac

for var in ERGON_DATABASE_URL ERGON_API_BASE_URL TEST_HARNESS_SECRET ENABLE_TEST_HARNESS; do
  if [ -z "${!var:-}" ]; then
    echo "FATAL: \$${var} not set — run 'source <(scripts/smoke_local_up.sh | tail -n +2)' or export manually" >&2
    exit 1
  fi
done

export SMOKE_COHORT_SIZE="${cohort_size}"
export SMOKE_ENV="${env_slug}"

echo "→ Running ${pyfile} with SMOKE_COHORT_SIZE=${cohort_size}"
echo "  (env: ${env_slug}, harness: ${ERGON_API_BASE_URL})"
echo

uv run pytest "${pyfile}" -v --timeout=300 --tb=short
