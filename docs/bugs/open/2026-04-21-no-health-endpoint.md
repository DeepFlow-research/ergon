---
status: open
opened: 2026-04-21
fixed_pr: null
priority: P1
invariant_violated: null
related_rfc: null
---

# Bug: API has no /health endpoint, real-LLM stack fixture treats 404 as ready

## Symptom

The real-LLM stack fixture at `tests/real_llm/fixtures/stack.py` polls
`http://127.0.0.1:9000/health` to decide when the backend is ready before
yielding to tests. Two defects interact:

1. `ergon_core/ergon_core/core/api/app.py` registers `runs_router`,
   `cohorts_router`, `rollouts_router`, and the Inngest webhook at
   `/api/inngest`, but no `/health` route. A GET to `/health` returns 404.
2. `_wait_for` (`tests/real_llm/fixtures/stack.py:16-25`) calls
   `client.get(url)` without checking `r.status_code` and without
   `raise_for_status()`. httpx does not raise on 404; the function returns.

Net effect: `real_llm_stack` "succeeds" as soon as the FastAPI process
accepts TCP and responds to anything — including 404 on a still-booting
or partially-broken app. Tests then race against a not-actually-ready
backend.

## Repro

1. `docker compose -f docker-compose.real-llm.yml up -d --wait` (or
   `pnpm dev:test` locally + `pytest --assume-stack-up`).
2. `pytest tests/real_llm/... --assume-stack-up`.
3. `_wait_for("http://127.0.0.1:9000/health", ...)` returns on the first
   request because the 404 is a complete HTTP response. A test that then
   hits `/api/runs/...` may see 500s or stale data if lifespan hasn't
   finished.

## Root cause

Two independent defects compound:

  - **Missing endpoint.** `ergon_core/ergon_core/core/api/app.py` never
    defined `/health`. The harness assumed it existed.
  - **Permissive poll.** `_wait_for` (`tests/real_llm/fixtures/stack.py:20-22`)
    treats any complete HTTP response as "ready", including 4xx and 5xx.

## Scope

Affects the `real-LLM` test tier (`tests/real_llm/`) and any operator who
relies on `/health` for a liveness probe (e.g. docker-compose healthchecks,
Kubernetes readiness probes). Low user-facing blast radius today because
real-LLM is opt-in (`ERGON_REAL_LLM=1`) and not in CI, but the silent
"ready-on-404" behavior is the kind of thing that produces flaky real-LLM
runs whose failure mode looks like a model bug.

## Proposed fix

  1. Add a trivial `@app.get("/health")` handler on the FastAPI app in
     `ergon_core/ergon_core/core/api/app.py` returning `{"status": "ok"}`
     with 200. No DB check, no dependency injection — the contract is
     "process is up and serving HTTP".
  2. Tighten `_wait_for` in `tests/real_llm/fixtures/stack.py` to only
     return on 2xx; 4xx/5xx keep polling until `timeout` elapses.
  3. Add unit coverage for both: `tests/unit/test_health_endpoint.py`
     asserts the route, `tests/unit/test_wait_for.py` covers the 200 /
     404 / ConnectError branches.

## On fix

When moving from `open/` to `fixed/`:
  - Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
  - Note `/health` in `docs/architecture/07_testing.md` as the canonical
    liveness endpoint for the real-LLM stack fixture.
