# 01 — Contracts and State

**Status:** draft.
**Scope:** DTO inventory, frontend activity model, deterministic replay contract, and exact places where additive DTO changes may be needed.

Cross-refs: program goals in [`00-program.md`](00-program.md), UI work in [`02-frontend-implementation.md`](02-frontend-implementation.md), e2e contract in [`03-tests-and-e2e.md`](03-tests-and-e2e.md).

---

## 1. Existing contract inventory

### Production snapshot/state

- `ergon-dashboard/src/lib/contracts/rest.ts`
  - `RunSnapshot` already includes tasks, executions, resources, sandboxes, threads, and evaluations via generated schemas.
  - `RunExecutionAttempt` has `startedAt` and `completedAt`, which are true span endpoints.
  - `RunSandbox` has `createdAt` and `closedAt`, which are true span endpoints.
  - `RunSandboxCommand` has `timestamp` and `durationMs`, which can render as short command spans.
  - `RunTaskEvaluation` currently behaves like an instant marker unless start/end timestamps are present in generated schema.

- `ergon-dashboard/src/lib/types.ts`
  - `WorkflowRunState` is the in-memory source for current display state.
  - `TaskState.history` records task transitions with sequence/time/actor/reason.

### Graph mutations

- `ergon-dashboard/src/features/graph/contracts/graphMutations.ts`
  - `GraphMutationDto` has `sequence`, `mutation_type`, `target_id`, `actor`, `reason`, `created_at`.
  - This is sufficient for graph mutation markers and sequence scrubbing.

- `ergon-dashboard/src/features/graph/state/graphMutationReducer.ts`
  - `replayToSequence` is the topology/status replay engine.
  - Activity derivation should consume its result; it should not duplicate graph replay.

### Unified event stream

- `ergon-dashboard/src/lib/runEvents.ts`
  - `buildRunEvents()` already flattens workflow lifecycle, task transitions, sandbox events, messages, evaluations, resources, context events, and unhandled mutations.
  - Keep this useful for event rows and activity markers, but implement span packing in a separate `features/activity` module.

---

## 2. Frontend domain model

Create `ergon-dashboard/src/features/activity/types.ts`.

```typescript
import type { RunEventKind } from "@/lib/runEvents";

export type ActivityKind =
  | "execution"
  | "graph"
  | "message"
  | "artifact"
  | "evaluation"
  | "context"
  | "sandbox";

export interface RunActivity {
  id: string;
  kind: ActivityKind;
  label: string;
  taskId: string | null;
  sequence: number | null;
  startAt: string;
  endAt: string | null;
  isInstant: boolean;
  actor: string | null;
  sourceKind: RunEventKind | "execution.span" | "sandbox.span" | "graph.mutation";
  metadata: Record<string, string | number | boolean | null>;
}

export interface ActivityStackItem {
  activity: RunActivity;
  row: number;
  leftPct: number;
  widthPct: number;
}

export interface ActivityStackLayout {
  items: ActivityStackItem[];
  rowCount: number;
  startMs: number;
  endMs: number;
  maxConcurrency: number;
}
```

Rules:

- `startAt` is always required.
- `endAt` is `null` for markers.
- `isInstant` is true when `endAt === null` or when duration is below the render minimum.
- `taskId` can be null for workflow-level events.
- `actor` is metadata only; it must not become a lane key.

---

## 3. Activity derivation

Create `ergon-dashboard/src/features/activity/buildRunActivities.ts`.

Inputs:

```typescript
import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import type { RunEvent } from "@/lib/runEvents";
import type { WorkflowRunState } from "@/lib/types";
import type { RunActivity } from "./types";

export interface BuildRunActivitiesInput {
  runState: WorkflowRunState | null;
  events: RunEvent[];
  mutations: GraphMutationDto[];
  currentSequence: number | null;
}

export function buildRunActivities(input: BuildRunActivitiesInput): RunActivity[] {
  if (!input.runState) return [];
  return [
    ...executionActivities(input.runState),
    ...sandboxActivities(input.runState),
    ...contextActivities(input.runState),
    ...eventMarkerActivities(input.events),
    ...graphMutationActivities(input.mutations),
  ].sort(compareActivity);
}
```

Derivation rules:

- Executions: one span per `ExecutionAttemptState` with non-null `startedAt`; use `completedAt` when available, otherwise render open span through selected/current time.
- Sandboxes: one span per `SandboxState`; use `closedAt` when available.
- Sandbox commands: marker or short span using `timestamp + durationMs`.
- Context events: span if both `startedAt` and `completedAt` exist; otherwise marker at `createdAt`.
- Thread messages, resources, evaluations, workflow lifecycle: marker activities from `RunEvent`.
- Graph mutations: marker activities from `GraphMutationDto`.
- Duplicate suppression: do not render both a `task.transition` event and a `graph.mutation` marker as identical labels if they share the same sequence/task/status. Prefer the graph mutation marker for sequence navigation and keep task transition in the event stream.

---

## 4. Stack layout

Create `ergon-dashboard/src/features/activity/stackLayout.ts`.

```typescript
import type { ActivityStackLayout, RunActivity } from "./types";

export interface StackActivityOptions {
  minMarkerWidthPct: number;
  minSpanWidthPct: number;
}

export function stackActivities(
  activities: RunActivity[],
  options: StackActivityOptions = { minMarkerWidthPct: 0.35, minSpanWidthPct: 0.75 },
): ActivityStackLayout {
  const timed = activities
    .map((activity) => toTimedActivity(activity))
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs || a.activity.id.localeCompare(b.activity.id));

  if (timed.length === 0) {
    return { items: [], rowCount: 0, startMs: 0, endMs: 0, maxConcurrency: 0 };
  }

  const startMs = Math.min(...timed.map((a) => a.startMs));
  const endMs = Math.max(...timed.map((a) => a.endMs));
  const spanMs = Math.max(1, endMs - startMs);
  const rowEnds: number[] = [];
  let maxConcurrency = 0;

  const items = timed.map(({ activity, startMs: itemStartMs, endMs: itemEndMs }) => {
    const row = firstFreeRow(rowEnds, itemStartMs);
    rowEnds[row] = itemEndMs;
    maxConcurrency = Math.max(maxConcurrency, rowEnds.filter((rowEnd) => rowEnd > itemStartMs).length);

    const leftPct = ((itemStartMs - startMs) / spanMs) * 100;
    const rawWidthPct = ((itemEndMs - itemStartMs) / spanMs) * 100;
    const widthPct = activity.isInstant
      ? options.minMarkerWidthPct
      : Math.max(options.minSpanWidthPct, rawWidthPct);

    return { activity, row, leftPct, widthPct };
  });

  return { items, rowCount: rowEnds.length, startMs, endMs, maxConcurrency };
}
```

Acceptance rules:

- Two overlapping spans must be placed on different rows.
- Adjacent non-overlapping spans can reuse the same row.
- Instant markers should not force every later item onto a new row; give them a small render interval only for collision.
- Layout must be deterministic for identical inputs.

---

## 5. DTO change decision tree

Use this decision tree before editing backend schema files:

1. Can the UI derive the fact from `WorkflowRunState`, `RunEvent[]`, or `GraphMutationDto[]` without lying about time? If yes, do not change production DTOs.
2. Is the missing fact only needed by Playwright? If yes, add it to `ergon_core/core/api/test_harness.py` and `ergon-dashboard/tests/helpers/backendHarnessClient.ts`, not production REST.
3. Is the missing fact needed by users and already persisted? If yes, add it to the production API schema and generated frontend contracts.
4. Is the missing fact not persisted? Stop and design the backend persistence change separately; do not smuggle fake frontend fields into the UI.

Likely first-PR DTO edits:

- **Test harness only:** add `activity_event_count`, `activity_span_count`, `max_concurrency` after the frontend derivation is stable enough to calculate the same values in backend or harness queries.
- **No production DTO edit:** keep evaluations as markers unless persisted evaluation span timestamps already exist.

---

## 6. Unit test checklist

Create `ergon-dashboard/src/features/activity/buildRunActivities.test.ts`.

- [ ] Execution with start/end becomes a span with `kind: "execution"`.
- [ ] Running execution with no end becomes open span using current selected time.
- [ ] Resource event becomes instant `kind: "artifact"` marker.
- [ ] Evaluation event becomes instant `kind: "evaluation"` marker.
- [ ] Graph mutation becomes instant `kind: "graph"` marker with sequence.
- [ ] Actor names appear in metadata but not in row assignment input.

Create `ergon-dashboard/src/features/activity/stackLayout.test.ts`.

- [ ] Non-overlapping spans reuse one row.
- [ ] Overlapping spans use two rows.
- [ ] Three-way overlap reports `maxConcurrency === 3`.
- [ ] Instant markers do not permanently block a row.
- [ ] Same input order-independent set produces identical `row` assignments after sorting.
