# 07 — Testing

## 1. Purpose

Describe the testing posture of Ergon: what each tier is for, what a green
run implies about production correctness, and where the current layout
diverges from where the system owner has decided to take it.

The central design question at this layer is **fidelity vs. speed**: a
fast tier that bypasses Inngest and Postgres tests code paths that do not
match production. The target posture trades broad-surface-at-wrong-layer
for narrower-surface-at-right-layer.

## 2. Core abstractions

Three tiers, separated by filesystem path (not pytest markers):

- **Fast tier** — in-memory SQLite, direct service-class calls, no Inngest,
  no Docker. Covers graph propagation, context assembly, repository
  behavior, RL extraction, state-machine scenarios, and pure-logic
  helpers. Split today between `tests/state/` (unit-ish + service) and
  `tests/integration/` (same stack plus a stub worker through the
  pipeline).
- **E2E tier** (`tests/e2e/`) — full Docker stack: Postgres, Inngest dev
  server, FastAPI app. `StubWorker` + `StubRubric` by default; real E2B
  enabled on `feature/*` branches.
- **Frontend e2e** (`ergon-dashboard/tests/e2e/`) — Playwright. Not wired
  into CI yet.

Tier boundaries are paths, not markers. This is load-bearing: the local
gate and the CI workflow both dispatch by directory.

### Code map

| Tier | Location | Infra |
|------|----------|-------|
| Fast — graph/service | `tests/state/` | SQLite, no Inngest |
| Fast — stub-worker pipeline | `tests/integration/` | SQLite, no Inngest |
| E2E | `tests/e2e/` | Docker + Inngest + optional E2B |
| Frontend | `ergon-dashboard/tests/e2e/` | Playwright (not in CI) |
| real-LLM | `tests/real_llm/` | Docker + Inngest + Postgres + Playwright; opt-in via `ERGON_REAL_LLM=1` + `OPENROUTER_API_KEY`; manual dispatch only (not in CI) |

### real-LLM tier

Optional pytest tier at `tests/real_llm/`, gated by `ERGON_REAL_LLM=1` and
`OPENROUTER_API_KEY`, runs real Sonnet-class experiments against a full local
stack (backend + dashboard + Inngest + Postgres) via `docker-compose.real-llm.yml`.
Assertions combine Postgres state, `/api/test/*` harness endpoints, and
Playwright dashboard checks. An `OpenRouterBudget` session fixture gates total
spend. This tier is a bug-hunting instrument; it is not required for CI.

`GET /health` on the FastAPI app (`ergon_core/core/api/app.py`) is the canonical
liveness endpoint: trivial 200 + `{"status": "ok"}` used by the stack fixture's
`_wait_for` to decide the backend is ready. It does not check the DB — booting
past lifespan is out of scope for liveness.

## 3. Control flow — choosing a tier

```
Pure function / validator / Pydantic model?
    yes -> fast tier
    no  -> next

Drives graph state or service-class behavior, no Inngest runtime?
    yes -> fast tier
    no  -> next

Needs Docker, Inngest dev server, or a sandbox?
    yes -> tests/e2e/ (feature-branch CI only)
```

The canonical local gate is `pnpm run check:fast && pnpm run test:be:fast`.
CI mirrors it for the fast tier; the e2e workflow runs on
`workflow_dispatch` or `feature/*` branches only.

## 4. Invariants

- The fast tier must stay fast enough to be the "ready for review" gate.
  If it needs Docker, Postgres, or an Inngest runtime, it does not belong
  in the fast tier.
- Tier boundaries are filesystem paths. No pytest markers.
- State tests do not read `RunTaskStateEvent` (deprecated). Assertions go
  through `RunGraphMutation` or `RunGraphNode.status`.
- State tests assert against service-class return values or graph
  mutation shapes, never direct DB writes.
- E2E tests must not mock the LLM (the point of e2e is to catch
  provider-layer regressions). A pre-scripted smoke is the only
  exception.
- A contract test asserts criterion source files do not instantiate any
  `SandboxManager` directly. The placeholder currently fails against
  `ergon_builtins/benchmarks/swebench_verified/criterion.py:72` —
  documented gap; the fix is scoped to the criterion-runtime-DI RFC.

## 5. Extension points

- **New unit-level test** — place alongside the code under test, or in
  the fast tier. No I/O fixtures.
- **New integration test** — fast tier today. Drive through service
  classes. Post-reset, drive through the Inngest event API against real
  Postgres.
- **New e2e test** — `tests/e2e/`. Must run against the Docker + E2B
  stack. Feature-branch CI gate.
- **New Playwright test** — `ergon-dashboard/tests/e2e/`. Wiring into CI
  is an open follow-up.
- **New benchmark** — once the smoke pattern lands (see §7), every
  benchmark will be required to ship a paired smoke test; enforced by a
  discovery test that walks the registry.

## 6. Anti-patterns

- **State-machine assertions via direct DB writes.** Tests must drive
  the same path production takes.
- **Pushing a Postgres-requiring test into the fast tier.** Breaks the
  speed guarantee the tier is built around.
- **Reading `RunTaskStateEvent` from any test.** Deprecated table.
- **Fast-tier state tests that skip Inngest when production does not.**
  This is the root cause motivating the posture-reset follow-up: a green
  test that bypasses the production event path claims correctness it
  cannot support.
- **Mocking the LLM in e2e.** Defeats the purpose of the tier.

## 7. Follow-ups

The system owner has decided to retire the fast tier in favor of a single
real-infrastructure integration tier (Postgres + Inngest dev server +
stub workers), keeping a pure-logic `tests/unit/` tier beside it. The
driving invariant under this plan: **tests that exercise graph semantics
MUST run against real Postgres and real Inngest.** Path-based tier
boundaries are preserved. CI budgets shift from seconds to minutes.

Paired shifts under the same planning arc:

- A per-benchmark smoke pattern at
  `tests/integration/smokes/test_<slug>_smoke.py`, using a shared
  fixed-delegation stub worker to exercise a complex-enough subgraph.
- Test-harness endpoints (`/api/test/read/*`, `/api/test/write/*`) that
  mount only when `ENABLE_TEST_HARNESS=1`, so Playwright can assert
  backend state inside a single test invocation. Writes gated by
  `X-Test-Secret`.
- Two contract tests migrated from the dashboard layer: every
  `DashboardEmitter` method must have a non-trivial call site, and every
  `RunGraphMutation.kind` must have a matching TypeScript reducer.

Tracking:

- `docs/rfcs/active/2026-04-18-testing-posture-reset.md`
- `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md`
- `docs/rfcs/active/2026-04-18-test-harness-endpoints.md`
- `docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md`
- `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md`
- `docs/bugs/open/2026-04-18-ci-docker-caching.md` — Docker rebuild cost
  becomes load-bearing once the integration tier hits real infra on
  every PR.

**Sandbox test strategy.** No in-memory fake sandbox. Tests that need
sandbox behavior use real E2B against a pre-warmed template. Rationale:
E2B is cheap and fast; a fake is an unnecessary maintenance surface.

**Coverage.** Untracked. No thresholds set, none enforced. Documented
here so silence is not read as a target; any change is RFC-scoped.

**Frontend e2e wiring.** Playwright lives in the repo but is not wired
into CI. Wiring it in is part of the integration-tier rebuild.
