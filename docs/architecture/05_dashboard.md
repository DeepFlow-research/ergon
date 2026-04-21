# 05 — Dashboard

## 1. Purpose

The dashboard is a Next.js app that renders run state. It consumes a narrow
set of Inngest events from the Python runtime, maintains an in-memory
`DashboardStore`, and pushes updates to connected browsers via Socket.io.
The durable source of truth is Postgres; the in-memory store is a cache
that can always be rebuilt from the database via `build_run_snapshot`.

Current live-update surface is narrow: only graph mutations and context
events flow through the delta stream. All other dashboard data (task
statuses rendered outside graph nodes, sandbox activity, resources,
evaluations, thread messages) is populated by a cold-start REST snapshot
and does not update live today. See Follow-ups for tracked gaps.

## 2. Core abstractions

- `DashboardEmitter` — Python-side fire-and-forget sender. Exposes one
  typed async method per `dashboard/*` event; errors are caught and
  logged and the emitter never blocks callers. Most methods are defined
  but unwired today (see Follow-ups). Lives in
  `ergon_core/ergon_core/core/dashboard/emitter.py`.

- `DashboardXxxEvent` contracts — typed Pydantic models that define the
  wire format, in
  `ergon_core/ergon_core/core/dashboard/event_contracts.py`. A matching
  Zod schema lives at `ergon-dashboard/src/lib/contracts/events.ts`;
  whether the mirror is codegen or hand-maintained has drifted (see
  Follow-ups).

- `DashboardEmitterSandboxEventSink` — sink adapter intended to route
  E2B sandbox lifecycle into the emitter. Defined but has no constructor
  site today (see Follow-ups).

- Next.js Inngest handlers — one registration per event type that
  updates `DashboardStore` and broadcasts via Socket.io. Live under
  `ergon-dashboard/src/inngest/functions/`.

- `DashboardStore` — process-local in-memory cache
  (`ergon-dashboard/src/lib/state/store.ts`) with a bounded retention
  policy: oldest runs beyond a cap are pruned on new-run arrival. The
  cap is configurable via env; the default lives in
  `ergon-dashboard/src/lib/config.ts:29`. Pruned runs become
  inaccessible because there is no historical REST endpoint today (see
  Follow-ups).

- Socket.io server (`ergon-dashboard/src/lib/socket/server.ts`) —
  broadcasts to per-run rooms (`run:<runId>`) and answers cold-start
  snapshot requests. Clients explicitly subscribe/unsubscribe per run.

- `SocketProvider` — browser-side socket.io client
  (`ergon-dashboard/src/providers/SocketProvider.tsx`). Owns subscription
  state for the current view.

- `useRunState` — per-run hydration + live-update hook
  (`ergon-dashboard/src/hooks/useRunState.ts`). Requests a fresh snapshot
  when `runId` changes.

- `RunEvent` union — chronological shape consumed by
  `UnifiedEventStream` and `RunTimeline`, defined in
  `ergon-dashboard/src/lib/runEvents.ts`.

## 3. Control flow

Cold-start (authoritative, works today):

```
browser opens /runs/<id>
      |
      v
useRunState -> socket.emit("request:run", runId)
      |
      v
Socket.io server -> build_run_snapshot(run_id) via REST to Python
      |
      v
DashboardStore populated + sync:run emitted to this socket
```

Live delta stream (what actually flows today):

```
Python runtime                               Next.js
--------------                               -------
WorkflowGraphRepository mutation listener --> dashboard/graph_mutation
ContextEventRepository listener           --> dashboard/context_event
                                                      |
                                                      v
                                              DashboardStore reducer
                                                      |
                                                      v
                                              Socket.io room run:<id>
```

The broader set of `DashboardEmitter` methods exists for the target
pipeline shape but has no live call sites yet; see Follow-ups.

## 4. Invariants

- The dashboard is event-driven end-to-end for the surfaces that are
  wired. No polling from the backend. No SSE.
- Every persistent backend state change on a wired surface must have a
  corresponding `dashboard/*` event; a state change without an emit is
  a bug in the emitter layer. Enforcement is not automated today (see
  Follow-ups).
- `DashboardStore` is a cache. The durable source of truth is Postgres.
  On cold start, the browser sends `request:run` and the store is
  rebuilt via `build_run_snapshot`.
- Browser clients subscribe to specific run rooms; they do NOT receive
  events for runs they have not subscribed to.
- Emitter calls are best-effort. The backend never blocks on dashboard
  delivery, and no business logic depends on emission success.

## 5. Extension points

- New event type: add a Pydantic contract in `event_contracts.py`, a
  method on `DashboardEmitter`, the matching handler under
  `ergon-dashboard/src/inngest/functions/`, a reducer in
  `DashboardStore`, and a call site in the runtime. All five are
  required to complete the pipeline.
- New graph mutation kind: extend `RunGraphMutation.kind`; the Python
  listener forwards automatically. Add the corresponding TS reducer
  under `ergon-dashboard/src/inngest/functions/` or
  `features/graph/contracts/graphMutations.ts`.
- New store slice: extend `DashboardStore` and expose a selector. Do
  not read the raw store from JSX.

## 6. Anti-patterns

- Adding a backend state change without a corresponding
  `DashboardEmitter.*` call. Already the dominant failure mode — most
  emitter methods are currently dead (see Follow-ups).
- Reading `DashboardStore` as if it were durable. It is a cache; use
  `build_run_snapshot` for authoritative state.
- Polling the dashboard REST API for live state. REST is for
  rehydration; live state is Socket.io.
- Emitting from inside a DB transaction. Emission is best-effort and
  must not gate commit.
- Assuming reconnect rehydrates. `SocketProvider` does not re-subscribe
  on reconnect; `useRunState` does not re-fetch the snapshot; the
  server does not replay. Tracked in Follow-ups.
- Hand-editing the Zod contracts without updating the Pydantic source
  (or vice-versa).

## 7. Follow-ups

Known limitations tracked as bugs or RFCs:

- `docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md` —
  most emitter methods are defined but never invoked.
- `docs/bugs/open/2026-04-18-dashboard-reconnect-stale-ui.md` — no
  re-subscribe, no snapshot re-fetch, no replay on Socket.io reconnect.
- `docs/bugs/open/2026-04-17-dashboard-process-local-state.md` —
  `global.__socketIO` / `global.__dashboardStore` are process-local, so
  multi-replica deployments diverge. Treated as intentional research-
  tool simplification for now; long-term direction undecided.
- `docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md` — the
  `DashboardEmitterSandboxEventSink` has no constructor site.
- `docs/rfcs/active/2026-04-18-dashboard-paginated-runs-api.md` —
  proposes replacing the in-memory cap + `request:runs` with a
  paginated REST endpoint.
- `docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md` —
  proposes a contract test that fails CI when an emitter method has
  zero call sites, and when a `RunGraphMutation.kind` has no TS
  reducer.

Open questions:

- Contract versioning: whether the Zod schema is meant to be generated
  from the Pydantic contracts, and if so how to wire the generator into
  `pnpm run check:fe`.
- HA posture: whether to keep process-local state indefinitely or adopt
  Redis / session affinity is unresolved.
