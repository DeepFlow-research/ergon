---
status: open
opened: 2026-04-18
fixed_pr: null
priority: P2
invariant_violated: null
related_rfc: null
---

# Bug: Dashboard UI freezes after Socket.io reconnect

## Symptom

When the browser's Socket.io connection drops mid-run (network blip,
laptop sleep/wake, WiFi handoff), the UI stops receiving updates and
stays frozen at the pre-disconnect state indefinitely. A full page
reload restores the view. The Socket.io client itself reconnects
automatically, but no state re-sync happens.

## Repro

1. Open a run workspace page at `/runs/<id>` while a workflow is
   producing graph mutations or context events.
2. In browser devtools, Application → WebSockets (or Network → WS),
   close the active Socket.io connection.
3. Observe the client auto-reconnect (new WS entry appears).
4. Continue the workflow. New graph mutations and context events fire
   on the backend but never reach the UI.
5. Reload the page — all the missed state appears, confirming the
   backend did its job and only the client-side resync is broken.

## Root cause

Three cooperating gaps:

- `ergon-dashboard/src/providers/SocketProvider.tsx` exposes
  `subscribe` at line 117 but the reconnect handler does not re-emit
  `subscribe(runId)` for any active subscriptions. On reconnect the
  socket is in a fresh session with no room memberships, so
  `run:<id>` broadcasts go nowhere for that client.
- `ergon-dashboard/src/hooks/useRunState.ts` fires
  `socket.emit("request:run", runId)` at line 497 only when `runId`
  changes, not on a new `isConnected` transition. A reconnect does
  not re-hydrate the snapshot.
- `ergon-dashboard/src/lib/socket/server.ts` has no replay logic on
  room rejoin; `subscribe` at line 114 is a plain `socket.join(room)`.
- The reducer has no idempotency keys, so even if we did replay, the
  current reducer would risk double-apply on events bracketing the
  disconnect.

## Scope

Any user whose connection drops mid-run. In local dev this is rare; in
any real deployment (WiFi networks, mobile, laptops that sleep) this is
routine and makes the live dashboard effectively unreliable for long
runs.

## Proposed fix

Three-part, all in one PR:

1. `SocketProvider.tsx`: track active subscriptions in a ref; on
   `socket.io-client`'s `reconnect` event, re-emit `subscribe(runId)`
   for each one.
2. `useRunState.ts`: add an effect keyed on `isConnected` that, when
   transitioning false → true with a live `runId`, re-emits
   `request:run`.
3. Add idempotency keys so snapshot + delta converge cleanly:
   `(run_id, task_id, turn_id, event_index)` for context events and
   `(run_id, sequence)` for graph mutations. The reducer drops events
   whose key is already applied.

Server-side replay buffering is out of scope — the
`request:run` re-fetch covers the same ground more simply.

## On fix

When moving from `open/` to `fixed/`:
- Set `status: fixed` and `fixed_pr: <PR#>` in frontmatter.
- Remove the reconnect anti-pattern bullet from
  `docs/architecture/05_dashboard.md` section 6 or mark it resolved.
