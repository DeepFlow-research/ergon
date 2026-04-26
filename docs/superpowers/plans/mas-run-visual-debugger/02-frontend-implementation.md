# 02 — Frontend Implementation

**Status:** draft.
**Scope:** component boundaries, UI behavior, and task-by-task implementation plan for the visual debugger shell.

Cross-refs: contracts in [`01-contracts-and-state.md`](01-contracts-and-state.md), tests in [`03-tests-and-e2e.md`](03-tests-and-e2e.md), phase order in [`04-phases.md`](04-phases.md).

---

## 1. Target layout

The run page becomes a three-region visual debugger:

- Header/status strip remains at the top with run status, cohort breadcrumb, live/timeline toggle, and connection state.
- Main region is the React Flow recursive graph, showing the whole graph at selected `T`.
- Bottom dock is `ActivityStackTimeline`, always horizontal time, vertical rows allocated by overlap.
- Right drawer is `TaskWorkspace`, opened by graph node or activity click.

The accepted mockup is `ergon-dashboard/mockups/mas-activity-stack-debugger.html`.

---

## 2. Component map

### New components

- `ergon-dashboard/src/features/activity/components/ActivityStackTimeline.tsx`
  - Props: activities, current sequence, selected task, selected activity, callbacks.
  - Owns time ruler, row rendering, legend, scrubber controls, and empty state.

- `ergon-dashboard/src/features/activity/components/ActivityBar.tsx`
  - Props: stack item, selected/highlight booleans, click handler.
  - Renders span or marker using kind-specific styling.

### Modified components

- `RunWorkspacePage.tsx`
  - Replaces old bottom `MutationTimeline` region with activity stack.
  - Creates `activities = buildRunActivities({ runState: displayState, events, mutations, currentSequence })`.
  - Tracks `selectedActivityId`.
  - Activity click sets current sequence if present and selects `taskId` if present.
  - Graph node click selects task and highlights related activities.

- `DAGCanvas.tsx`
  - Accepts `highlightedTaskIds?: Set<string>`.
  - Passes selected/highlight information through node data.
  - Keeps depth expansion controls, search, minimap, and React Flow controls.
  - Ensures canvas has `data-testid="graph-canvas"` and individual graph elements keep `graph-node-{taskId}` / `graph-container-{taskId}`.

- `TaskWorkspace.tsx`
  - Accepts `selectedTime?: string | null` or `currentSequence?: number | null`.
  - Filters task collections for timeline mode only:
    - resources with `createdAt <= selectedTime`
    - executions with `startedAt <= selectedTime`
    - sandbox commands with `timestamp <= selectedTime`
    - thread messages with `createdAt <= selectedTime`
    - context events with `createdAt <= selectedTime`
    - evaluation with `createdAt <= selectedTime`
  - Live mode keeps current behavior.

---

## 3. Task 1: Activity domain module

**Files:**

- Create: `ergon-dashboard/src/features/activity/types.ts`
- Create: `ergon-dashboard/src/features/activity/buildRunActivities.ts`
- Create: `ergon-dashboard/src/features/activity/stackLayout.ts`
- Test: `ergon-dashboard/src/features/activity/buildRunActivities.test.ts`
- Test: `ergon-dashboard/src/features/activity/stackLayout.test.ts`

- [ ] **Step 1: Write tests for activity derivation**

```typescript
import { describe, expect, it } from "vitest";
import { buildRunActivities } from "./buildRunActivities";

describe("buildRunActivities", () => {
  it("renders execution attempts as spans and graph mutations as sequence markers", () => {
    const activities = buildRunActivities({
      runState: makeRunStateWithExecution({
        taskId: "task-a",
        startedAt: "2026-04-26T10:00:00.000Z",
        completedAt: "2026-04-26T10:00:05.000Z",
      }),
      events: [],
      mutations: [
        makeGraphMutation({
          sequence: 12,
          target_id: "task-a",
          mutation_type: "node.status_changed",
          created_at: "2026-04-26T10:00:01.000Z",
        }),
      ],
      currentSequence: 12,
    });

    expect(activities).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "execution", taskId: "task-a", isInstant: false }),
        expect.objectContaining({ kind: "graph", taskId: "task-a", sequence: 12, isInstant: true }),
      ]),
    );
  });
});
```

- [ ] **Step 2: Write tests for stack packing**

```typescript
import { describe, expect, it } from "vitest";
import { stackActivities } from "./stackLayout";

describe("stackActivities", () => {
  it("puts overlapping spans on separate rows and reuses rows after overlap ends", () => {
    const layout = stackActivities([
      activity("a", "2026-04-26T10:00:00.000Z", "2026-04-26T10:00:10.000Z"),
      activity("b", "2026-04-26T10:00:05.000Z", "2026-04-26T10:00:12.000Z"),
      activity("c", "2026-04-26T10:00:12.000Z", "2026-04-26T10:00:15.000Z"),
    ]);

    expect(layout.rowCount).toBe(2);
    expect(layout.maxConcurrency).toBe(2);
    expect(layout.items.find((item) => item.activity.id === "c")?.row).toBe(0);
  });
});
```

- [ ] **Step 3: Implement derivation and packing**

Implement the interfaces and functions from [`01-contracts-and-state.md`](01-contracts-and-state.md). Keep the implementation pure and free of React.

- [ ] **Step 4: Run unit tests**

Run: `pnpm --dir ergon-dashboard test src/features/activity`

Expected: activity tests pass; no browser required.

---

## 4. Task 2: Activity stack UI

**Files:**

- Create: `ergon-dashboard/src/features/activity/components/ActivityStackTimeline.tsx`
- Create: `ergon-dashboard/src/features/activity/components/ActivityBar.tsx`
- Modify: `ergon-dashboard/src/lib/statusTokens.ts` only if existing colors cannot cover activity kinds.

- [ ] **Step 1: Add render contract**

`ActivityStackTimeline` must expose:

- `data-testid="activity-stack-region"` on the dock root.
- `data-testid="activity-stack-row"` per rendered row.
- `data-testid="activity-bar-{activity.id}"` per activity.
- `data-kind` and `data-task-id` on activity bars.
- `data-testid="activity-current-sequence"` for the visible selected sequence.

- [ ] **Step 2: Implement timeline controls**

Controls required in first pass:

- Step back/forward by available graph mutation sequence.
- Play/pause using mutation timestamps, preserving current `MutationTimeline` min/max delay behavior.
- Drag/scrub range input using sequence numbers.
- Kind legend showing counts.

- [ ] **Step 3: Implement click behavior**

Activity click behavior:

```typescript
function handleActivityClick(activity: RunActivity) {
  setSelectedActivityId(activity.id);
  if (activity.sequence !== null) setCurrentSequence(activity.sequence);
  if (activity.taskId) setSelectedTaskId(activity.taskId);
}
```

- [ ] **Step 4: Add empty and partial-data states**

Empty states:

- No run state: "Run state is still loading."
- Run has no activities: "No activity has been recorded for this run yet."
- Timeline mode has no mutations: show activities from snapshot timestamps but disable sequence scrub.

---

## 5. Task 3: Wire into `RunWorkspacePage`

**Files:**

- Modify: `ergon-dashboard/src/components/run/RunWorkspacePage.tsx`
- Modify: `ergon-dashboard/src/features/graph/components/MutationTimeline.tsx` only if extracting reusable controls.

- [ ] **Step 1: Build activities from display state**

Add:

```typescript
const activities = useMemo(
  () =>
    buildRunActivities({
      runState: displayState,
      events,
      mutations,
      currentSequence: timelineMode === "timeline" ? currentSequence : null,
    }),
  [displayState, events, mutations, timelineMode, currentSequence],
);
```

- [ ] **Step 2: Replace timeline region**

Replace the old `MutationTimeline` bottom panel with:

```tsx
<section data-testid="timeline-region" className="border-t border-slate-200 bg-white">
  <ActivityStackTimeline
    activities={activities}
    mutations={mutations}
    currentSequence={currentSequence}
    selectedTaskId={selectedTaskId}
    selectedActivityId={selectedActivityId}
    isPlaying={isPlaying}
    speed={playbackSpeed}
    onSequenceChange={setCurrentSequence}
    onTogglePlay={() => setIsPlaying((prev) => !prev)}
    onSpeedChange={setPlaybackSpeed}
    onActivityClick={handleActivityClick}
  />
</section>
```

- [ ] **Step 3: Preserve event stream**

Keep `UnifiedEventStream` as a collapsible secondary inspector, not the primary bottom timeline.

- [ ] **Step 4: Run frontend check**

Run: `pnpm --dir ergon-dashboard run check`

Expected: TypeScript and lint pass.

---

## 6. Task 4: Time-aware workspace

**Files:**

- Modify: `ergon-dashboard/src/components/workspace/TaskWorkspace.tsx`
- Test: add or extend component/unit tests near existing workspace tests if present.

- [ ] **Step 1: Add selected time prop**

`RunWorkspacePage` computes:

```typescript
const selectedTimelineTime = useMemo(() => {
  if (timelineMode !== "timeline") return null;
  return mutations.find((mutation) => mutation.sequence === currentSequence)?.created_at ?? null;
}, [timelineMode, mutations, currentSequence]);
```

- [ ] **Step 2: Filter visible task evidence**

Inside `TaskWorkspace`, apply filtering only when `selectedTimelineTime` is non-null. Use ISO string comparison after converting both sides to milliseconds with `Date.parse`.

- [ ] **Step 3: Show time badge**

Add a small badge in the workspace header:

`Viewing evidence available at seq {currentSequence}`

Only render in timeline mode.

---

## 7. Task 5: Graph highlighting and readability

**Files:**

- Modify: `ergon-dashboard/src/components/dag/DAGCanvas.tsx`
- Modify: `ergon-dashboard/src/components/dag/TaskNode.tsx`
- Modify: `ergon-dashboard/src/features/graph/components/ContainerNode.tsx`
- Modify: `ergon-dashboard/src/features/graph/components/LeafNode.tsx`
- Modify: `ergon-dashboard/src/features/graph/layout/hierarchicalLayout.ts` only for collision/readability fixes.

- [ ] **Step 1: Add highlight data**

Pass node data flags:

```typescript
isSelected: task.id === selectedTaskId,
isHighlighted: highlightedTaskIds.has(task.id),
```

- [ ] **Step 2: Keep whole graph at T**

Do not filter nodes by selected activity/task. Highlight related nodes while preserving full topology.

- [ ] **Step 3: Improve fit and spacing only where measured**

If overlap persists in the 9-leaf smoke graph, tune `MIN_CONTAINER_WIDTH`, `CONTAINER_PADDING`, and dagre separation constants in `layoutTypes.ts` / `hierarchicalLayout.ts`. Do not introduce a second graph layout engine in this PR.

---

## 8. Task 6: Remove or demote old mutation strip

**Files:**

- Modify or delete: `ergon-dashboard/src/features/graph/components/MutationTimeline.tsx`

Decision after Task 2:

- If controls are reused, rename to `SequenceControls.tsx`.
- If no code is reused, delete the component and update imports.

Acceptance: the only bottom timeline users see is activity-stack based.
