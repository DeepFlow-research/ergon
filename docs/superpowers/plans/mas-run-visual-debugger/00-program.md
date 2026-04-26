# MAS Run Visual Debugger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current unreadable MAS run view with a visual debugger that shows the whole recursive graph at selected time `T`, an overlap-based bottom activity stack, and a task-scoped workspace drawer.

**Architecture:** Keep graph mutation replay as the source of topology truth and derive the activity stack from existing run state plus graph mutations. Avoid fixed agent lanes: agents can join/leave dynamically, while tasks, events, and wall-clock timestamps are stable. Introduce small frontend domain modules for activity derivation/layout and keep backend DTO changes additive and narrow.

**Tech Stack:** Next.js/React, TypeScript, React Flow, Tailwind CSS, Zod contracts, Playwright e2e, FastAPI test harness DTOs.

---

## 1. Goals and non-goals

**Goals**

- Render the full recursive task graph as it existed at selected sequence/time `T`.
- Move the timeline into a bottom dock that visualizes concurrency by stacking overlapping activity bars.
- Keep the right-hand workspace task-scoped and time-aware: selecting a node at `T` shows resources, executions, messages, context events, and evaluations available at `T`.
- Make activity layout independent of agent cardinality. Agent/worker names are labels and filter metadata only.
- Preserve the live mode. Timeline mode must be opt-in and must not make the live dashboard feel stale.
- Add focused Playwright coverage that proves the graph canvas, activity stack, sequence scrubber, and workspace drawer are all usable on canonical MAS smoke runs.
- Use the mockup `ergon-dashboard/mockups/mas-activity-stack-debugger.html` as the UX target, not as code to copy directly.

**Non-goals**

- No rewrite of backend execution/control flow.
- No persistent "agent timeline" DTO.
- No new graph database model.
- No attempt to solve arbitrary huge-graph navigation in the first PR. The first PR should make the existing 9-leaf smoke and representative MAS samples readable.
- No replacing React Flow.
- No pixel-perfect visual snapshot testing in phase 1. Screenshot artifacts are review aids; assertions target stable structure and visibility.

---

## 2. UX invariants

- **Whole graph at T:** timeline scrub changes graph state, not graph scope. Collapsed containers are allowed for readability, but nodes are not silently omitted due to focus.
- **Concurrency by overlap:** overlapping work appears stacked vertically in the bottom dock. Vertical position means "needed another row because time overlaps", not "agent N".
- **Stable categories, unstable actors:** kind chips (`Execution`, `Graph`, `Talk`, `Artifact`, `Evaluation`, `Context`) are stable; worker/agent labels are secondary.
- **Task identity everywhere:** clicking an activity with `taskId` selects the graph node and opens the workspace. Clicking a graph node highlights related activity.
- **Replay is deterministic:** the same snapshot + mutation list + selected sequence produces the same graph and activity view.
- **Missing duration is explicit:** instant events render as markers; spans render as bars. Do not fake long durations for resources/messages/evaluations.

---

## 3. DTO stance

Production DTO changes should be avoided in the first phase unless implementation proves a real gap.

Existing production data already gives the frontend enough to build the first activity stack:

- `RunSnapshotDto` -> tasks, executions, resources, sandboxes, threads, evaluations.
- `dashboard/graph.mutation` + `/api/runs/{runId}/mutations` -> sequence, mutation kind, actor, reason, `created_at`.
- `context.event` state -> task execution, task node, event type, created/started/completed times where available.
- `task_evaluation_updated` -> task-scoped evaluation marker.

Additive DTO work is still planned for testability and future precision:

- Extend the **test harness** run-state DTO with activity-stack facts that Playwright can assert without reverse-engineering layout from pixels: mutation count, execution spans, context-event count, evaluation task IDs, and graph node IDs already exist; add `activity_event_count`, `activity_span_count`, and `max_concurrency` in Phase C if needed.
- Add production REST fields only if the current generated `RunSnapshotDto` lacks a timestamp needed for an honest bar. The likely candidate is evaluation duration (`startedAt`/`completedAt`) if evaluations become spans rather than instant markers.

---

## 4. File map

**New frontend domain files**

- `ergon-dashboard/src/features/activity/types.ts` — `RunActivity`, `ActivityKind`, `ActivityStackRow`, layout result types.
- `ergon-dashboard/src/features/activity/buildRunActivities.ts` — pure derivation from `WorkflowRunState`, `RunEvent[]`, and `GraphMutationDto[]`.
- `ergon-dashboard/src/features/activity/stackLayout.ts` — overlap packing algorithm.
- `ergon-dashboard/src/features/activity/components/ActivityStackTimeline.tsx` — bottom dock UI.
- `ergon-dashboard/src/features/activity/components/ActivityBar.tsx` — single bar/marker renderer.

**Modified frontend files**

- `ergon-dashboard/src/components/run/RunWorkspacePage.tsx` — three-pane debugger shell, timeline mode wiring, selection/highlight coordination.
- `ergon-dashboard/src/components/dag/DAGCanvas.tsx` — accept highlight props and expose stable graph container/node test IDs.
- `ergon-dashboard/src/features/graph/components/MutationTimeline.tsx` — either retire after Phase B or reduce to sequence controls reused by `ActivityStackTimeline`.
- `ergon-dashboard/src/components/workspace/TaskWorkspace.tsx` — filter task-scoped collections to selected sequence/time when timeline mode is active.
- `ergon-dashboard/src/lib/runEvents.ts` — keep flat event stream derivation, but do not make it own activity packing.

**Modified tests**

- `ergon-dashboard/tests/helpers/dashboardFixtures.ts` — add a concurrent MAS fixture with overlapping executions/context events.
- `ergon-dashboard/tests/e2e/_shared/smoke.ts` — assert activity stack presence and screenshots.
- `ergon-dashboard/tests/helpers/backendHarnessClient.ts` — add narrow test harness fields only if backend exposes them.

---

## 5. Merge checklist

- [ ] `pnpm --dir ergon-dashboard test` or the repository's frontend unit command is green for activity derivation/layout tests.
- [ ] `pnpm --dir ergon-dashboard run check` or current frontend type/lint command is green.
- [ ] Playwright smoke opens a canonical MAS run, enters timeline mode, sees `activity-stack-region`, scrubs sequence, opens workspace from a graph node, and captures run screenshots.
- [ ] Activity stack never creates rows from agent names.
- [ ] E2E screenshot shows full recursive graph at selected `T`, not focus-filtered branch-only graph.
- [ ] Implementation handoff includes PNGs of every new UI panel: full debugger page, graph canvas, activity stack bottom dock, and workspace drawer open on a selected task.
- [ ] Existing live run updates still render without requiring mutation fetch success.
- [ ] No production backend DTO changes unless justified in `01-contracts-and-state.md`.

---

## 6. Open decisions

1. **Activity source for graph mutations:** default to using `/api/runs/{runId}/mutations` in timeline mode. If live mode needs graph mutation bars before entering timeline, also retain recent socket mutation events in `useRunState`.
2. **Evaluation duration:** default to instant marker at `evaluation.createdAt`. Upgrade to span only if backend has real start/end timestamps.
3. **Viewport fit:** default to React Flow `fitView` on initial load and sequence changes only when user has not manually panned/zoomed.
4. **Saved layout state:** defer persistence of pane sizes/zoom to a follow-up.
5. **Virtualization:** defer until the activity count in a smoke run or real run demonstrably causes UI lag.
