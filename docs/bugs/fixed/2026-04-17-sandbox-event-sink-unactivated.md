---
status: fixed
opened: 2026-04-17
fixed_pr: 11
priority: P2
invariant_violated: docs/architecture/03_providers.md#sandboxeventsink
related_rfc: docs/rfcs/accepted/2026-04-17-sandbox-event-sink-activation.md
---

# Bug: SandboxEventSink Protocol is unactivated across every benchmark

## Symptom

The `SandboxEventSink` Protocol at `ergon_core/core/providers/sandbox/event_sink.py:7-36` is
defined as the canonical path by which sandbox managers emit lifecycle events
(`sandbox_created`, `sandbox_command`, `sandbox_closed`). Two implementations exist —
`NoopSandboxEventSink` (the default) and `DashboardEmitterSandboxEventSink` (forwards to the
dashboard emitter). In practice, NO manager is ever constructed with a non-noop sink. Every
sandbox manager call site across every benchmark omits the `event_sink=` kwarg, so every
manager defaults to `NoopSandboxEventSink()`.

Consequence: sandbox events do not reach the dashboard at all on the live-update path. There
is no second, inline path — a grep of `dashboard_emitter.sandbox_` across `ergon_core`,
`ergon_builtins`, `ergon_cli`, and `ergon_infra` returns zero production call sites (only
`event_sink.py`'s own forwarder, which is never constructed). The dashboard's sandbox view
updates only on page refresh, when the cold-start REST snapshot
(`build_run_snapshot()` at `ergon_core/core/api/runs.py:343`) rereads the mutable tables
that persist sandbox rows. While a run is live, sandbox lifecycle is invisible in the UI.

## Repro

```
grep -rn "SandboxManager(" ergon_builtins/ | grep -v "def "
```

Output shows five instantiation sites, none pass `event_sink=`:

- `ergon_builtins/workers/baselines/minif2f_react_worker.py:111` — `MiniF2FSandboxManager()`
- `ergon_builtins/workers/baselines/swebench_worker.py:123` — `SWEBenchSandboxManager()`
- `ergon_builtins/benchmarks/swebench_verified/criterion.py:72` — `SWEBenchSandboxManager()`
- `ergon_builtins/workers/research_rubrics/researcher_worker.py:74` — `ResearchRubricsSandboxManager()`
- `ergon_builtins/workers/research_rubrics/stub_worker.py:78` — `ResearchRubricsSandboxManager()`

Confirm no alternate inline path exists:

```
grep -rn "dashboard_emitter.sandbox_" ergon_core/ ergon_builtins/ ergon_cli/ ergon_infra/
```

Returns zero production call sites (only the `DashboardEmitterSandboxEventSink` forwarder
inside `event_sink.py`, which nothing constructs). No sandbox events reach the dashboard
during a live run; the view populates only via the REST snapshot on cold start.

## Root cause

`BaseSandboxManager.__init__` accepts `event_sink: SandboxEventSink | None = None`,
defaulting to the noop when None is passed. No call site passes a real sink. The Protocol
and its `DashboardEmitterSandboxEventSink` forwarder landed, but no follow-up PR ever wired
production managers to the forwarder. The `dashboard_emitter.sandbox_created/command/closed`
methods defined at `ergon_core/core/dashboard/emitter.py:246-321` exist only so the
forwarder has something to call; they have zero direct callers elsewhere.

The result is silent architectural drift: the Protocol exists, has two implementations, is
referenced by documentation, and is exercised by zero production code on the live path.
Sandbox lifecycle still lands in the database (rows populate normally), so the REST
snapshot serves the dashboard correctly on page load — but the live Socket.io stream never
carries a sandbox event. A reader of `event_sink.py` would reasonably assume the sink
carries the data end-to-end; it does not.

## Scope

- Every benchmark that uses a sandbox is affected: smoke-test (default template), minif2f,
  swebench-verified, researchrubrics.
- User-visible impact: sandbox lifecycle is not visible in the dashboard during a live run.
  The view appears correct on initial page load (REST snapshot reads the tables) but stays
  stale until refresh — sandbox created/command/closed transitions do not stream in.
- Data persistence itself is unaffected: `RunResource` rows, execution rows, and any
  sandbox-id linkage continue to be written through their normal paths. The bug is purely
  in the live-update lane.
- Tests that assert sandbox-event emission on the live path, if any, are effectively
  asserting nothing today. The fix will require adding coverage against a recording sink.

## Proposed fix

Follow the revised `docs/rfcs/active/2026-04-17-sandbox-event-sink-activation.md`. The
approach shifted away from "make `event_sink=` required at every construction site"
after the singleton-per-subclass pattern at
`ergon_core/ergon_core/core/providers/sandbox/manager.py:69-72` — combined with the
`__init__` stomp at `manager.py:76-78` — was re-examined. Passing the sink at five call
sites is a behavioral no-op (there is only one `dashboard_emitter` in the process) and
creates a test-isolation hazard tracked separately at
`docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md`.

1. Add a `@classmethod set_event_sink(cls, sink)` on `BaseSandboxManager` that assigns
   `cls._event_sink`.
2. In FastAPI app init (`ergon_core/ergon_core/core/api/app.py`, inside `lifespan`),
   call `Manager.set_event_sink(DashboardEmitterSandboxEventSink(dashboard_emitter))`
   once per manager subclass.
3. Remove the `event_sink=` kwarg from the production `__init__` signature (keep a
   narrow test-only override path if needed); leave all 5 construction sites unchanged.
4. Add an integration test using a recording sink installed via `set_event_sink` in
   fixture setup, asserting every lifecycle transition produces exactly one sink call
   and the dashboard receives the corresponding `DashboardSandbox*Event`.

## On fix

- Set `status: fixed`, `fixed_pr: <PR#>`.
- Confirm `docs/architecture/03_providers.md` invariant "every sandbox event flows through
  the sink" is stated without the "partially wired" softener, since wiring now exists.
- Move this file to `docs/bugs/fixed/`.
