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

Four tiers, separated by filesystem path (not pytest markers):

- **Unit tier** (`tests/unit/`) — pure-logic tests: validators, Pydantic
  model construction, contract tests, mocked-SDK CLI flows. No I/O, no
  DB, no fixtures. Fastest possible signal.
- **Integration tier** (`tests/integration/`) — real Postgres + real
  Inngest dev server via the `docker-compose.ci.yml` stack. Tests drive
  the production event seam (`inngest_client.send(...)`), then block on
  durable Inngest processing, then assert terminal state via ORM reads.
  Direct service-class calls that bypass the Inngest layer are banned in
  this tier. Benchmark-specific sandbox integration (MiniF2F, SWE-Bench
  Verified) lives in `tests/integration/<benchmark>/` subdirectories.
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
| Unit — pure logic | `tests/unit/` | None — no I/O, no fixtures |
| Integration — stub-worker pipeline | `tests/integration/` | Postgres + Inngest dev server (docker-compose.ci.yml) |
| Integration — benchmark sandboxes | `tests/integration/minif2f/`, `tests/integration/swebench_verified/` | Real E2B template (opt-in; skipped when template/API key absent) |
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

## 3. Control flow — choosing a tier

```
Pure function / validator / Pydantic model / mocked SDK?
    yes -> tests/unit/
    no  -> next

Drives graph state, persists via ORM, or dispatches an Inngest event?
    yes -> tests/integration/
    no  -> next

Needs Docker stack, real E2B sandbox, or a full FastAPI server?
    yes -> tests/e2e/ (feature-branch CI only)
```

The canonical local gate is `pnpm run check:fast && pnpm run test:be:fast`.
CI mirrors it for the unit tier; the integration job brings up
`docker-compose.ci.yml` and the e2e workflow runs on `workflow_dispatch`
or `feature/*` branches only.

## 4. Invariants

- The unit tier must stay fast enough to be the "ready for review" gate.
  If a test needs Docker, Postgres, or an Inngest runtime, it does not
  belong in `tests/unit/`.
- Tier boundaries are filesystem paths. No pytest markers.
- **Integration tests MUST drive through Inngest events.** Direct
  service-class calls that bypass the event seam are banned in
  `tests/integration/`. Tests use `inngest_client.send(...)` (typically
  indirectly via `Experiment.run()` → `create_experiment_run`), wait for
  Inngest to durably process, then assert on ORM state. A helper class
  that wraps "call the same service the Inngest fn would call" is the
  anti-pattern this invariant closes — it yielded green-theatre signal
  because the event wiring itself was never exercised.
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

- **New unit-level test** — place under `tests/unit/`. No I/O fixtures,
  no DB, no live services; mock SDK boundaries.
- **New integration test** — place under `tests/integration/`. Drive
  through the Inngest event API against real Postgres; assert via ORM
  reads. Benchmark-specific sandbox tests go under
  `tests/integration/<benchmark>/`.
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
- **Pushing a Postgres-requiring test into the unit tier.** Breaks the
  speed guarantee the tier is built around.
- **Reviving in-memory SQLite for graph/persistence coverage.** The
  SQLite-backed `tests/state/` tier has been deleted; it diverged from
  Postgres semantics and masked persistence bugs. Graph and persistence
  coverage lives in `tests/integration/` against real Postgres.
- **Reading `RunTaskStateEvent` from any test.** Deprecated table.
- **Integration-tier tests that skip Inngest when production does not.**
  All integration tests must drive through `inngest_client.send(...)`
  (typically via `Experiment.run()`), wait for Inngest to durably
  process, then assert via ORM reads. Direct service-class calls that
  bypass the event seam are banned.
- **Mocking the LLM in e2e.** Defeats the purpose of the tier.

## 7. Follow-ups

The tier retirement and orphan-tier consolidation have landed. Current
posture: `tests/unit/` (pure logic), `tests/integration/` (real
Postgres + Inngest), `tests/e2e/` (full Docker + optional E2B), and
`tests/real_llm/` (opt-in, bug-hunting). The SQLite-backed
`tests/state/` tier is gone; the orphan `tests/contract/`,
`tests/cli/`, `tests/minif2f/`, and `tests/swebench_verified/` roots
have been folded into unit/integration.

Paired shifts under the same planning arc:

- A per-benchmark smoke pattern at
  `tests/integration/smokes/test_<slug>_smoke.py`, using the canonical
  smoke worker to exercise a complex-enough subgraph.
- Test-harness endpoints (`/api/test/read/*`, `/api/test/write/*`) that
  mount only when `ENABLE_TEST_HARNESS=1`, so Playwright can assert
  backend state inside a single test invocation. Writes gated by
  `X-Test-Secret`.
- Dashboard contract tests (emitter call-site check and RunGraphMutation
  reducer check) migrated under `tests/unit/`.

Tracking:

- `docs/rfcs/accepted/2026-04-18-testing-posture-reset.md` — resolved.
  Integration lifecycle smokes drive through real Inngest + Postgres,
  the SQLite `tests/state/` tier has been demolished, and orphan tiers
  have been folded in.
- `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md`
- `docs/rfcs/active/2026-04-18-test-harness-endpoints.md`
- `docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md`
- `docs/rfcs/accepted/2026-04-17-criterion-runtime-di-container.md`
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
