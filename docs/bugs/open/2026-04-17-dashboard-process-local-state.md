---
status: open
opened: 2026-04-17
fixed_pr: null
priority: P3
invariant_violated: docs/architecture/05_dashboard.md#known-limitation
related_rfc: null
---

# Bug: Dashboard state is Next.js-process-local; no HA deployment is possible

## Symptom

The Next.js dashboard holds all live run state in in-process singletons:

- `global.__socketIO` — the Socket.io server instance — at
  `ergon-dashboard/src/lib/socket/server.ts:36-47`.
- `store` — the `DashboardStore` singleton — at `ergon-dashboard/src/lib/state/store.ts`.

Two consequences follow:

1. A multi-replica dashboard deployment has DIVERGENT state across replicas. An Inngest
   handler runs on one replica, mutates that replica's `DashboardStore`, and broadcasts
   via that replica's Socket.io. Browser clients connected to a DIFFERENT replica will
   not see the update until a `request:run` refetches from Postgres.
2. On a dashboard process restart, in-memory state is lost. Browsers recover via the
   cold-start `request:run` handler, which rebuilds from `build_run_snapshot` over
   Postgres. That works, but makes every restart a cold cache and a burst of DB load.

## Repro

Scale the dashboard to N > 1 replicas in any of:

- Kubernetes with `replicas: N`.
- Docker Compose with `deploy.replicas: N`.
- Multiple `next dev` instances behind a load balancer (nginx, HAProxy, Caddy).

Point browsers at the LB. Trigger an Inngest event (e.g., start a benchmark run). Observe:
each Inngest event is delivered to ONE replica; only that replica's currently-connected
Socket.io clients see the update in realtime. Clients on other replicas see nothing until
they reconnect or explicitly `request:run`, which then hits Postgres.

## Root cause

The Next.js Inngest handlers at `ergon-dashboard/src/inngest/functions/index.ts` write
directly into a process-local singleton. The Socket.io server is also process-local.
There is no shared-state layer — no Redis, no pub/sub, no session-affine routing —
coordinating state across replicas.

This is not a bug in the sense of "feature broken." It is a design constraint. The
dashboard was built for single-node development and has never needed HA. The problem is
that the constraint is currently UNDOCUMENTED at the architecture level, so a future
operator could attempt a multi-replica deployment, see no error, and only discover the
divergence under load.

## Scope

- Blocks HA deployment of the dashboard tier.
- Works correctly for single-node dev, staging, and single-replica production — which
  describes every deployment today.
- Not visible to single-node users. No data loss; Postgres remains the source of truth
  for finalized runs. The issue is strictly realtime UX under horizontal scale.
- Also mildly degrades restart behavior (cold cache on every reboot) but this is
  tolerable.

## Proposed fix

Future RFC (none filed yet). Three candidate approaches:

1. **Redis-backed store**. Move `DashboardStore` state to Redis; every replica reads and
   writes the shared store. Socket.io broadcasts use Redis pub/sub
   (`socket.io-redis-adapter`) for cross-replica event fan-out. This is the canonical
   pattern for horizontally-scaled Socket.io deployments.
2. **Session affinity**. Load-balancer routing based on `runId` (sticky by header or
   cookie), so all traffic for a given run lands on the same replica. Sharded by runId.
   Simpler but brittle under replica churn.
3. **Postgres-backed store with short-poll fallback**. Drop the in-memory store entirely;
   every read hits Postgres; Socket.io delivers invalidation pings only. Simpler but
   loses realtime granularity for cross-replica events and adds DB load.

Option 1 is the recommended direction. File as "proposed future RFC" in
`docs/architecture/05_dashboard.md#follow-ups`.

Until then, this limitation is DOCUMENTED in
`docs/architecture/05_dashboard.md#known-limitation`. Any HA deploy attempt without
addressing this is explicitly out of scope.

## On fix

- Set `status: fixed`, `fixed_pr: <PR#>`.
- Remove the "known limitation" section from `docs/architecture/05_dashboard.md` or
  rewrite it to reflect the new design (Redis adapter, session affinity, whichever
  lands).
- Move this file to `docs/bugs/fixed/`.
