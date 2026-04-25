# 04 — CI workflows, Docker caching, screenshots

**Status:** draft
**Scope:** `.github/workflows/ci-fast.yml`, `.github/workflows/e2e-benchmarks.yml`, `docker-compose.ci.yml`, screenshot push/cleanup scripts, PR comment format.

Cross-refs: assertions + driver in [`02-drivers-and-asserts.md`](02-drivers-and-asserts.md); Playwright in [`03-dashboard-and-playwright.md`](03-dashboard-and-playwright.md).

---

## 1. `ci-fast.yml` — unit + integration, every PR

Jobs (parallel):

```yaml
name: ci-fast
on:
  pull_request:
  push:
    branches: [main]

jobs:
  lint-and-type-check:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - uses: astral-sh/setup-uv@v4
      - run: pnpm install --frozen-lockfile
      - run: pnpm run check:be
      - run: pnpm run check:fe

  unit-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --frozen
      - run: pnpm install --frozen-lockfile
      - run: pnpm run test:be:unit

  integration-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: ergon
          POSTGRES_PASSWORD: ci_test
          POSTGRES_DB: ergon
        ports: ["5433:5432"]
        options: >-
          --health-cmd "pg_isready -U ergon"
          --health-interval 2s --health-retries 20
    env:
      ERGON_DATABASE_URL: postgresql://ergon:ci_test@localhost:5433/ergon
      INNGEST_DEV: "1"
      INNGEST_EVENT_KEY: dev
      INNGEST_API_BASE_URL: http://localhost:8289
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --frozen
      - run: pnpm install --frozen-lockfile
      - name: Start Inngest dev
        run: docker compose -f docker-compose.ci.yml up -d inngest-dev
      - run: pnpm run test:be:integration
```

**No SQLite anywhere** — the fixture in `tests/integration/conftest.py` skips the suite if `ERGON_DATABASE_URL` is missing or points to SQLite (existing behaviour, keep it).

---

## 2. `e2e-benchmarks.yml` — every PR, 3-leg matrix

```yaml
name: e2e-benchmarks
on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: write        # for pushing screenshots to screenshots/pr-{N}
  pull-requests: write   # for gh pr comment

jobs:
  smoke:
    strategy:
      fail-fast: false
      matrix:
        env: [researchrubrics, minif2f, swebench-verified]
    runs-on: ubuntu-latest
    timeout-minutes: 10
    env:
      SMOKE_ENV: ${{ matrix.env }}
      ENABLE_TEST_HARNESS: "1"
      TEST_HARNESS_SECRET: ${{ secrets.TEST_HARNESS_SECRET }}
      E2B_API_KEY: ${{ secrets.E2B_API_KEY }}
      GITHUB_PR_NUMBER: ${{ github.event.pull_request.number }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - uses: astral-sh/setup-uv@v4

      - run: pnpm install --frozen-lockfile
      - run: uv sync --frozen

      # ── Docker layer cache (see §3) ──────────────────────────────
      - uses: docker/setup-buildx-action@v3
      - name: Bring up stack with cache
        run: docker compose -f docker-compose.ci.yml up -d --build
        env:
          DOCKER_BUILDKIT: "1"
          COMPOSE_DOCKER_CLI_BUILD: "1"

      - name: Wait for Postgres + API + Inngest
        run: bash ci/wait_for_stack.sh

      - name: Build + start dashboard
        run: |
          pnpm --dir ergon-dashboard build
          pnpm --dir ergon-dashboard start &
          bash ci/wait_for_dashboard.sh

      # ── Playwright browser (cached) ──────────────────────────────
      - uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: pw-${{ hashFiles('ergon-dashboard/pnpm-lock.yaml') }}
      - run: pnpm --dir ergon-dashboard exec playwright install --with-deps chromium

      # ── Smoke for this matrix env ────────────────────────────────
      - name: Run smoke
        run: |
          uv run pytest tests/e2e/test_${SMOKE_ENV//-/_}_smoke.py -v \
            --timeout=270 --tb=short

      # ── Screenshot push (runs on success and failure) ────────────
      - name: Push screenshots
        if: always()
        run: bash ci/push_screenshots.sh "$GITHUB_PR_NUMBER" "$SMOKE_ENV" /tmp/playwright

      # ── PR comment (on job completion) ───────────────────────────
      - name: Comment on PR
        if: always() && github.event.pull_request.number
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: bash ci/pr_comment_screenshots.sh "$GITHUB_PR_NUMBER" "$SMOKE_ENV"
```

Note the matrix value translates `swebench-verified` → `swebench_verified` for the pytest file path. The slug in Python is `swebench` (see [`01-fixtures.md`](01-fixtures.md)) and the benchmark slug in Ergon is `swebench-verified`; the pytest filename uses the Ergon slug.

---

## 3. Docker layer caching

Blocks on [`docs/bugs/open/2026-04-18-ci-docker-caching.md`](../../../bugs/open/2026-04-18-ci-docker-caching.md). Without the cache, cold legs blow the 10-min job budget and pay for a full rebuild on every PR.

### 3.1 `docker-compose.ci.yml` changes

```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
      cache_from:
        - type=gha,scope=api
      cache_to:
        - type=gha,scope=api,mode=max
    image: ergon-api:ci

  postgres:
    image: postgres:15@sha256:<pinned-digest>
    # ... unchanged

  inngest-dev:
    image: inngest/inngest:<pinned-tag>@sha256:<pinned-digest>
```

Pin the `postgres` and `inngest` image digests so a vendor tag rotation doesn't invalidate the cache mid-PR.

### 3.2 Cold vs warm expectations

| Scenario | Per-leg wall clock |
|---|---|
| Cold PR (cache miss) | 4–5 min — near the hard ceiling |
| Warm PR (cache hit) | 1–3 min |
| Cache rebuild on `main` nightly | acceptable one-shot |

If warm consistently exceeds 3 min, the dashboard prod build is the next budget suspect — revisit the open decision in [`00-program.md §6.3`](00-program.md) to fall back to dev-server for smoke only.

---

## 4. Screenshot delivery

Two shell scripts, both committed under `ci/`.

### 4.1 `ci/push_screenshots.sh`

```bash
#!/usr/bin/env bash
# Usage: push_screenshots.sh <pr_number> <env> <screenshot_dir>
set -euo pipefail
pr="$1"; env="$2"; dir="$3"
branch="screenshots/pr-${pr}"

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

# Fetch or init branch
if git ls-remote --heads origin "$branch" | grep -q "$branch"; then
  git fetch origin "$branch:$branch"
  git checkout "$branch"
else
  git checkout --orphan "$branch"
  git rm -rf . || true
  echo "Screenshots for PR #$pr" > README.md
  git add README.md
  git commit -m "ci: init screenshots/pr-${pr}"
fi

mkdir -p "${env}"
cp -r "${dir}/${env}"/*.png "${env}/" 2>/dev/null || echo "no screenshots for ${env}"

git add "${env}/"
git diff --cached --quiet || git commit -m "ci: screenshots ${env} $(date -u +%Y%m%dT%H%M%SZ)"
git push origin "$branch"
```

### 4.2 `ci/pr_comment_screenshots.sh`

```bash
#!/usr/bin/env bash
# Usage: pr_comment_screenshots.sh <pr_number> <env>
set -euo pipefail
pr="$1"; env="$2"
repo="${GITHUB_REPOSITORY:-DeepFlow-research/ergon}"
base="https://raw.githubusercontent.com/${repo}/screenshots/pr-${pr}/${env}"

# Find the images pushed for this env on this leg
imgs=$(git ls-tree -r --name-only "screenshots/pr-${pr}" -- "${env}" || true)

comment=$(cat <<EOF
## E2E smoke — \`${env}\`

![run-full](${base}/$(echo "$imgs" | grep -m1 run-full.png))
![graph](${base}/$(echo "$imgs" | grep -m1 graph.png))
![cohort](${base}/$(echo "$imgs" | grep -m1 cohort))
EOF
)

gh pr comment "$pr" --body "$comment"
```

Minimal. Graceful degradation when images are missing; no hard failure on comment errors (screenshots in the branch are the primary artifact).

### 4.3 Cleanup on PR close

Separate workflow:

```yaml
# .github/workflows/cleanup-screenshots.yml
name: cleanup-screenshots
on:
  pull_request:
    types: [closed]

permissions:
  contents: write

jobs:
  delete-branch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          branch="screenshots/pr-${{ github.event.pull_request.number }}"
          git push origin --delete "$branch" || true
```

---

## 5. `wait_for_stack.sh` and `wait_for_dashboard.sh`

Small bash scripts with 60-second deadlines. Poll:

- Postgres: `pg_isready -h localhost -p 5433 -U ergon`.
- Inngest: `curl -sf http://localhost:8289/health`.
- API: `curl -sf http://localhost:9000/healthz`.
- Dashboard: `curl -sf http://localhost:3000`.

Exit nonzero on timeout. Keeps the workflow log clean — failures point at a specific service.

---

## 6. Secrets required

| Secret | Where set | Used by |
|---|---|---|
| `E2B_API_KEY` | repo secrets | e2e-benchmarks leg |
| `TEST_HARNESS_SECRET` | repo secrets | e2e-benchmarks leg (exported to backend + Playwright) |
| `GITHUB_TOKEN` | default | gh pr comment |

No separate database or Inngest credentials needed in CI (they stand up inside the job).

---

## 7. Non-goals for the CI file

- No nightly full `tests/real_llm/` run wired here; that has its own workflow file ([`docs/superpowers/plans/2026-04-21-real-llm-debug-harness.md`](../2026-04-21-real-llm-debug-harness.md)).
- No cross-matrix aggregation (the matrix legs are independent; a green PR requires all 3).
- No retry-on-flake logic. If a leg flakes, fix the flake or raise the issue — silent retries mask regressions.
