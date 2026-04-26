# Run Workspace Interaction Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the run workspace back into alignment with the design brief: tabbed right-hand task workspace, always-live graph with bottom timeline-driven snapshots, cleaner concurrent activity visualization, and no dead controls.

**Architecture:** Keep `RunWorkspacePage` as the orchestration point, but replace the `live | timeline` mode split with a single `snapshotSequence: number | null`. A null snapshot means live; a selected sequence replays graph mutations with `replayToSequence()`. `TaskWorkspace` becomes a tabbed inspector, and `buildRunActivities()` stops mixing every event type into the concurrent activity stack.

**Tech Stack:** Next.js App Router, React client components, React Flow, node:test via `tsx --test`, Playwright for browser verification.

---

## File Structure

- Modify: `ergon-dashboard/src/components/run/RunWorkspacePage.tsx`
  - Owns run-level live state, snapshot selection, mutation loading, graph replay, header controls, and rerun button state.
- Modify: `ergon-dashboard/src/components/workspace/TaskWorkspace.tsx`
  - Converts the right drawer from stacked sections to tabs: `Overview`, `Actions`, `Communication`, `Outputs`, `State transitions`, `Evaluation`.
- Modify: `ergon-dashboard/src/features/activity/buildRunActivities.ts`
  - Narrows the concurrent activity data model to execution/concurrency bars plus graph/key-event markers.
- Modify: `ergon-dashboard/src/features/activity/components/ActivityStackTimeline.tsx`
  - Removes play/pause/speed controls and uses click-only marker navigation.
- Modify: `ergon-dashboard/src/features/activity/components/ActivityBar.tsx`
  - Keeps bar rendering, but supports clearer marker-vs-span styling.
- Create: `ergon-dashboard/src/features/activity/snapshotSequence.ts`
  - Pure helper for resolving a clicked activity to the nearest replay mutation sequence.
- Create: `ergon-dashboard/src/features/activity/snapshotSequence.test.ts`
  - Unit tests for direct sequence and timestamp-to-nearest-mutation behavior.
- Modify: `ergon-dashboard/src/features/activity/buildRunActivities.test.ts`
  - Regression tests for “do not flood the stack with context/sandbox command detail”.
- Create/modify: `ergon-dashboard/tests/e2e/run-workspace-interactions.spec.ts`
  - Browser-level checks for drawer tabs, timeline click rollback, no live/timeline toggle, no playback controls, no active dead rerun.

---

## Current State Summary

The backend and existing frontend data structures already support graph replay through:

- `GET /api/runs/[runId]/mutations`
- `parseGraphMutationDtoArray()`
- `replayToSequence(mutations, currentSequence, emptyState, snapshotCache)`

The current UI does not consistently use that support because:

- `RunWorkspacePage` only fetches mutations after entering `timelineMode === "timeline"`.
- Activity clicks only rewind when `activity.sequence !== null`.
- Most visible activity bars have `sequence: null` because they represent execution/sandbox/context spans, not graph mutations.
- `buildRunActivities()` mixes execution spans, sandbox spans, sandbox commands, context events, event markers, and graph mutations into one stacked view.
- The right drawer is still a stacked section list, not tabs.
- The rerun button is visually active but has no `onClick`.

---

## Task 1: Snapshot State Model In `RunWorkspacePage`

**Files:**
- Modify: `ergon-dashboard/src/components/run/RunWorkspacePage.tsx`
- Test: `ergon-dashboard/tests/e2e/run-workspace-interactions.spec.ts`

- [ ] **Step 1: Write failing E2E test for removed mode controls**

Create or extend `tests/e2e/run-workspace-interactions.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

const BASE = process.env.BASE_URL ?? "http://localhost:3001";
const COHORT_ID = "a39ee959-376d-490c-8705-22f0c3e32d1e";
const RUN_ID = "4028c6d2-d9db-4c5a-be21-d9223d46b4ca";

test("run workspace is always live and has no manual live/timeline or playback controls", async ({ page }) => {
  await page.goto(`${BASE}/cohorts/${COHORT_ID}/runs/${RUN_ID}`);
  await expect(page.locator('[data-testid="graph-canvas"]')).toBeVisible();

  await expect(page.locator('[data-testid="mode-live"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="mode-timeline"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="activity-play-toggle"]')).toHaveCount(0);
  await expect(page.locator('[data-testid^="speed-"]')).toHaveCount(0);
});
```

- [ ] **Step 2: Run E2E test and verify it fails**

Run:

```bash
cd ergon-dashboard
BASE_URL=http://localhost:3001 pnpm exec playwright test tests/e2e/run-workspace-interactions.spec.ts -g "always live"
```

Expected: FAIL because `mode-live`, `mode-timeline`, play/pause, and speed controls are currently rendered.

- [ ] **Step 3: Replace mode state with snapshot state**

In `RunWorkspacePage.tsx`, replace:

```ts
const [timelineMode, setTimelineMode] = useState<"live" | "timeline">("live");
const [currentSequence, setCurrentSequence] = useState(0);
const [isPlaying, setIsPlaying] = useState(false);
const [playbackSpeed, setPlaybackSpeed] = useState(1);
```

with:

```ts
const [snapshotSequence, setSnapshotSequence] = useState<number | null>(null);
const currentSequence = snapshotSequence ?? 0;
```

- [ ] **Step 4: Always fetch mutations once per run**

Replace the current mutation `useEffect()` guard:

```ts
if (timelineMode !== "timeline") return;
```

with unconditional loading:

```ts
useEffect(() => {
  let cancelled = false;
  fetch(`/api/runs/${runId}/mutations`)
    .then((res) => res.json())
    .then((data) => {
      if (cancelled) return;
      const parsed = parseGraphMutationDtoArray(data);
      setMutations(parsed);
      snapshotCache.current.clear();
      const requestedSequence = requestedSequenceRef.current;
      requestedSequenceRef.current = null;
      if (requestedSequence !== null) {
        setSnapshotSequence(nearestMutationAtOrBefore(parsed, requestedSequence)?.sequence ?? null);
      }
    })
    .catch(() => {
      if (!cancelled) setMutations([]);
    });
  return () => {
    cancelled = true;
  };
}, [runId]);
```

- [ ] **Step 5: Replay only when `snapshotSequence !== null`**

Change `displayState` to:

```ts
const displayState = useMemo(() => {
  if (snapshotSequence === null || mutations.length === 0) return runState;
  if (!runState) return runState;
  const emptyState: WorkflowRunState = {
    ...runState,
    tasks: new Map(),
    totalTasks: 0,
    totalLeafTasks: 0,
    completedTasks: 0,
    runningTasks: 0,
    failedTasks: 0,
  };
  return replayToSequence(mutations, snapshotSequence, emptyState, snapshotCache.current);
}, [runState, mutations, snapshotSequence]);
```

- [ ] **Step 6: Remove header mode toggle**

Delete the whole `role="tablist"` block that renders `mode-live` and `mode-timeline`.

Change header chip text from:

```tsx
{timelineMode === "live" ? "live" : `seq ${currentSequence}`} · {formatSeconds(...)}
```

to:

```tsx
{snapshotSequence === null ? "live" : `snapshot · seq ${snapshotSequence}`} · {formatSeconds(...)}
```

- [ ] **Step 7: Update keyboard behavior**

Remove the `t` shortcut entirely. Change `Esc` behavior to:

```ts
if (e.key === "Escape") {
  if (selectedTaskId) { setSelectedTaskId(null); return; }
  if (snapshotSequence !== null) { setSnapshotSequence(null); return; }
  if (statusFilter) { setStatusFilter(null); return; }
  return;
}
```

Change arrow stepping to use `snapshotSequence !== null`.

- [ ] **Step 8: Run E2E test and verify it passes**

Run:

```bash
cd ergon-dashboard
BASE_URL=http://localhost:3001 pnpm exec playwright test tests/e2e/run-workspace-interactions.spec.ts -g "always live"
```

Expected: PASS.

---

## Task 2: Activity Click Resolves To Snapshot Sequence

**Files:**
- Create: `ergon-dashboard/src/features/activity/snapshotSequence.ts`
- Create: `ergon-dashboard/src/features/activity/snapshotSequence.test.ts`
- Modify: `ergon-dashboard/src/components/run/RunWorkspacePage.tsx`

- [ ] **Step 1: Write failing unit tests**

Create `src/features/activity/snapshotSequence.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import type { RunActivity } from "./types";
import { resolveActivitySnapshotSequence } from "./snapshotSequence";

function mutation(sequence: number, createdAt: string): GraphMutationDto {
  return {
    id: `m-${sequence}`,
    run_id: "run-1",
    sequence,
    mutation_type: "node.status_changed",
    target_type: "node",
    target_id: "task-1",
    old_value: null,
    new_value: { status: "running" },
    actor: "worker",
    reason: null,
    created_at: createdAt,
  } as GraphMutationDto;
}

function activity(overrides: Partial<RunActivity>): RunActivity {
  return {
    id: "a-1",
    kind: "execution",
    label: "activity",
    taskId: "task-1",
    sequence: null,
    startAt: "2026-04-26T10:00:05.000Z",
    endAt: "2026-04-26T10:00:08.000Z",
    isInstant: false,
    actor: "worker",
    sourceKind: "execution.span",
    metadata: {},
    ...overrides,
  };
}

test("uses explicit activity sequence when present", () => {
  assert.equal(
    resolveActivitySnapshotSequence(activity({ sequence: 67 }), [
      mutation(1, "2026-04-26T10:00:00.000Z"),
    ]),
    67,
  );
});

test("uses nearest mutation at or before activity start time when sequence is absent", () => {
  assert.equal(
    resolveActivitySnapshotSequence(activity({ startAt: "2026-04-26T10:00:05.000Z" }), [
      mutation(10, "2026-04-26T10:00:00.000Z"),
      mutation(20, "2026-04-26T10:00:04.000Z"),
      mutation(30, "2026-04-26T10:00:06.000Z"),
    ]),
    20,
  );
});

test("returns null when no mutation can represent the activity time", () => {
  assert.equal(
    resolveActivitySnapshotSequence(activity({ startAt: "2026-04-26T09:59:00.000Z" }), [
      mutation(10, "2026-04-26T10:00:00.000Z"),
    ]),
    null,
  );
});
```

- [ ] **Step 2: Run unit test and verify it fails**

Run:

```bash
cd ergon-dashboard
npx tsx --test src/features/activity/snapshotSequence.test.ts
```

Expected: FAIL because `snapshotSequence.ts` does not exist.

- [ ] **Step 3: Implement helper**

Create `src/features/activity/snapshotSequence.ts`:

```ts
import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import type { RunActivity } from "./types";

export function resolveActivitySnapshotSequence(
  activity: RunActivity,
  mutations: GraphMutationDto[],
): number | null {
  if (activity.sequence !== null) return activity.sequence;

  const activityMs = Date.parse(activity.startAt);
  if (!Number.isFinite(activityMs)) return null;

  let selected: GraphMutationDto | null = null;
  for (const mutation of mutations) {
    const mutationMs = Date.parse(mutation.created_at);
    if (!Number.isFinite(mutationMs)) continue;
    if (mutationMs > activityMs) break;
    selected = mutation;
  }
  return selected?.sequence ?? null;
}
```

- [ ] **Step 4: Use helper in `handleActivityClick`**

In `RunWorkspacePage.tsx`, import:

```ts
import { resolveActivitySnapshotSequence } from "@/features/activity/snapshotSequence";
```

Replace:

```ts
if (activity.sequence !== null) {
  requestedSequenceRef.current = activity.sequence;
  if (timelineMode !== "timeline") setTimelineMode("timeline");
  handleSequenceChange(activity.sequence);
}
```

with:

```ts
const snapshot = resolveActivitySnapshotSequence(activity, mutations);
if (snapshot !== null) {
  setSnapshotSequence(snapshot);
}
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd ergon-dashboard
npx tsx --test src/features/activity/snapshotSequence.test.ts
npm run build
```

Expected: unit test PASS and build PASS.

---

## Task 3: Simplify Concurrent Activity Stack Data

**Files:**
- Modify: `ergon-dashboard/src/features/activity/buildRunActivities.ts`
- Modify: `ergon-dashboard/src/features/activity/buildRunActivities.test.ts`
- Modify: `ergon-dashboard/src/features/activity/components/ActivityStackTimeline.tsx`
- Modify: `ergon-dashboard/src/features/activity/components/ActivityBar.tsx`

- [ ] **Step 1: Write failing test for reduced activity stack noise**

Add to `src/features/activity/buildRunActivities.test.ts`:

```ts
test("buildRunActivities keeps concurrent stack focused on execution spans and graph markers", () => {
  const runState = makeRunStateWithOneExecutionAndSandboxCommand();
  const activities = buildRunActivities({
    runState,
    events: [
      {
        id: "message-1",
        kind: "thread.message",
        at: "2026-04-26T10:00:01.000Z",
        taskId: "task-1",
        actor: "worker",
        preview: "verbose message",
        sequence: null,
      },
    ] as any,
    mutations: [
      {
        id: "mutation-1",
        run_id: runState.id,
        sequence: 1,
        mutation_type: "node.status_changed",
        target_type: "node",
        target_id: "task-1",
        old_value: null,
        new_value: { status: "running" },
        actor: "worker",
        reason: null,
        created_at: "2026-04-26T10:00:00.000Z",
      } as any,
    ],
    currentSequence: null,
  });

  assert.equal(activities.some((a) => a.sourceKind === "execution.span"), true);
  assert.equal(activities.some((a) => a.sourceKind === "graph.mutation"), true);
  assert.equal(activities.some((a) => a.sourceKind === "sandbox.command"), false);
  assert.equal(activities.some((a) => a.sourceKind === "thread.message"), false);
});
```

Define `makeRunStateWithOneExecutionAndSandboxCommand()` in the test file using the existing `WorkflowRunState` shape from nearby tests. It must include:

```ts
tasks: new Map([["task-1", { id: "task-1", name: "task", status: TaskStatus.COMPLETED, parentId: null, childIds: [], dependsOnIds: [], isLeaf: true, level: 0, assignedWorkerId: "w1", assignedWorkerName: "worker", startedAt: "2026-04-26T10:00:00.000Z", completedAt: "2026-04-26T10:00:10.000Z" }]])
executionsByTask: new Map([["task-1", [{ id: "exec-1", taskId: "task-1", attemptNumber: 1, status: TaskStatus.COMPLETED, agentId: "w1", agentName: "worker", startedAt: "2026-04-26T10:00:00.000Z", completedAt: "2026-04-26T10:00:10.000Z", finalAssistantMessage: null, outputResourceIds: [], errorMessage: null, score: null, evaluationDetails: {} }]]])
sandboxesByTask: new Map([["task-1", { taskId: "task-1", sandboxId: "sandbox-1", status: "closed", template: "default", createdAt: "2026-04-26T10:00:00.000Z", closedAt: "2026-04-26T10:00:10.000Z", closeReason: null, commands: [{ command: "pytest", stdout: "", stderr: "", exitCode: 0, durationMs: 1000, timestamp: "2026-04-26T10:00:01.000Z" }] }]])
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
cd ergon-dashboard
npx tsx --test src/features/activity/buildRunActivities.test.ts
```

Expected: FAIL because sandbox command and message activities are currently included.

- [ ] **Step 3: Narrow `buildRunActivities()` output**

Change:

```ts
return [
  ...executionActivities(input.runState, selectedTime),
  ...sandboxActivities(input.runState, selectedTime),
  ...contextActivities(input.runState),
  ...eventMarkerActivities(input.events),
  ...graphMutationActivities(input.mutations),
].sort(compareActivity);
```

to:

```ts
return [
  ...executionActivities(input.runState, selectedTime),
  ...graphMutationActivities(input.mutations),
].sort(compareActivity);
```

Do not delete helper functions yet unless `npm run build` reports unused exports/imports. This keeps the diff small and allows future detail views to reuse them if needed.

- [ ] **Step 4: Update activity copy**

In `ActivityStackTimeline.tsx`, change:

```tsx
<div className="font-semibold text-[var(--ink)]">Concurrent activity</div>
Bars stack only when they overlap.
```

to:

```tsx
<div className="font-semibold text-[var(--ink)]">Concurrent execution</div>
Bars are task attempts; dots are graph snapshots.
```

Change footer hints:

```tsx
<span>Bar = task execution</span>
<span>Dot = graph mutation snapshot</span>
<span>Click any item = inspect at that time</span>
```

- [ ] **Step 5: Verify visual density**

Run:

```bash
cd ergon-dashboard
npx tsx --test src/features/activity/buildRunActivities.test.ts
npm run build
```

Expected: tests PASS, build PASS. Browser should show fewer rows and fewer visual elements in the bottom stack.

---

## Task 4: Remove Playback Controls From Activity Stack

**Files:**
- Modify: `ergon-dashboard/src/features/activity/components/ActivityStackTimeline.tsx`
- Modify: `ergon-dashboard/src/components/run/RunWorkspacePage.tsx`
- Test: `ergon-dashboard/tests/e2e/run-workspace-interactions.spec.ts`

- [ ] **Step 1: Extend failing E2E test**

Extend the Task 1 E2E test to assert:

```ts
await expect(page.locator('[data-testid="activity-step-back"]')).toHaveCount(0);
await expect(page.locator('[data-testid="activity-step-forward"]')).toHaveCount(0);
await expect(page.locator('[data-testid="activity-play-toggle"]')).toHaveCount(0);
```

- [ ] **Step 2: Remove props from `ActivityStackTimelineProps`**

Delete:

```ts
isPlaying: boolean;
speed: number;
onTogglePlay: () => void;
onSpeedChange: (speed: number) => void;
```

Also delete:

```ts
const SPEED_OPTIONS = [0.5, 1, 2, 4] as const;
const MIN_DELAY_MS = 50;
const MAX_DELAY_MS = 2000;
const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
const currentSequenceRef = useRef(currentSequence);
stepForward
stepBack
useEffect that schedules playback
```

- [ ] **Step 3: Delete playback UI**

Remove the entire `isTimeline && (...)` button group containing `activity-step-back`, `activity-play-toggle`, `activity-step-forward`, and `speed-*`.

- [ ] **Step 4: Update caller**

In `RunWorkspacePage.tsx`, change:

```tsx
<ActivityStackTimeline
  activities={activities}
  mutations={mutations}
  currentSequence={currentSequence}
  onSequenceChange={handleSequenceChange}
  selectedTaskId={selectedTaskId}
  selectedActivityId={selectedActivityId}
  isPlaying={isPlaying}
  onTogglePlay={() => setIsPlaying((p) => !p)}
  speed={playbackSpeed}
  onSpeedChange={setPlaybackSpeed}
  onActivityClick={handleActivityClick}
/>
```

to:

```tsx
<ActivityStackTimeline
  activities={activities}
  mutations={mutations}
  currentSequence={currentSequence}
  onSequenceChange={handleSequenceChange}
  selectedTaskId={selectedTaskId}
  selectedActivityId={selectedActivityId}
  onActivityClick={handleActivityClick}
/>
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd ergon-dashboard
BASE_URL=http://localhost:3001 pnpm exec playwright test tests/e2e/run-workspace-interactions.spec.ts -g "always live"
npm run build
```

Expected: PASS.

---

## Task 5: Tabbed Right-Hand Workspace Drawer

**Files:**
- Modify: `ergon-dashboard/src/components/workspace/TaskWorkspace.tsx`
- Test: `ergon-dashboard/tests/e2e/run-workspace-interactions.spec.ts`

- [ ] **Step 1: Write failing E2E test for drawer tabs and criteria visibility**

Add:

```ts
test("task workspace uses tabs and exposes evaluation criteria tab", async ({ page }) => {
  await page.goto(`${BASE}/cohorts/${COHORT_ID}/runs/${RUN_ID}`);
  await expect(page.locator('[data-testid="graph-canvas"]')).toBeVisible();
  await page.locator('[data-testid^="graph-node-"]').first().click();

  await expect(page.locator('[data-testid="workspace-tab-overview"]')).toBeVisible();
  await expect(page.locator('[data-testid="workspace-tab-actions"]')).toBeVisible();
  await expect(page.locator('[data-testid="workspace-tab-communication"]')).toBeVisible();
  await expect(page.locator('[data-testid="workspace-tab-outputs"]')).toBeVisible();
  await expect(page.locator('[data-testid="workspace-tab-transitions"]')).toBeVisible();
  await expect(page.locator('[data-testid="workspace-tab-evaluation"]')).toBeVisible();

  await expect(page.locator('[data-testid="workspace-overview"]')).toBeVisible();
  await expect(page.locator('[data-testid="workspace-actions"]')).toHaveCount(0);

  await page.locator('[data-testid="workspace-tab-evaluation"]').click();
  await expect(page.locator('[data-testid="workspace-evaluation"]')).toBeVisible();
});
```

- [ ] **Step 2: Run E2E test and verify it fails**

Run:

```bash
cd ergon-dashboard
BASE_URL=http://localhost:3001 pnpm exec playwright test tests/e2e/run-workspace-interactions.spec.ts -g "workspace uses tabs"
```

Expected: FAIL because drawer uses stacked sections.

- [ ] **Step 3: Add tab state and tab metadata**

In `TaskWorkspace.tsx`, import:

```ts
import { useMemo, useState } from "react";
```

Add:

```ts
type WorkspaceTab = "overview" | "actions" | "communication" | "outputs" | "transitions" | "evaluation";

const WORKSPACE_TABS: { id: WorkspaceTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "actions", label: "Actions" },
  { id: "communication", label: "Communication" },
  { id: "outputs", label: "Outputs" },
  { id: "transitions", label: "State transitions" },
  { id: "evaluation", label: "Evaluation" },
];
```

Inside component:

```ts
const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
```

- [ ] **Step 4: Render tab strip below header**

Insert after header metadata:

```tsx
<nav className="flex shrink-0 border-b border-[var(--line)] bg-[var(--card)] px-3" aria-label="Task workspace sections">
  {WORKSPACE_TABS.map((tab) => {
    const active = activeTab === tab.id;
    return (
      <button
        key={tab.id}
        type="button"
        onClick={() => setActiveTab(tab.id)}
        className={`border-b-2 px-3 py-2 text-xs font-medium transition-colors ${
          active
            ? "border-[var(--ink)] text-[var(--ink)]"
            : "border-transparent text-[var(--muted)] hover:text-[var(--ink)]"
        }`}
        data-testid={`workspace-tab-${tab.id}`}
      >
        {tab.label}
        {tab.id === "evaluation" && evaluation ? (
          <span className="ml-1 rounded-full bg-[var(--paper-2)] px-1.5 py-0.5 font-mono text-[10px]">
            {evaluation.criterionResults.length}
          </span>
        ) : null}
      </button>
    );
  })}
</nav>
```

- [ ] **Step 5: Replace stacked sections with single active panel**

Replace the current scroll region contents with:

```tsx
<div className="min-h-0 overflow-y-auto p-3" data-testid="workspace-scroll-region">
  {activeTab === "overview" && (
    <WorkspaceSection testId="workspace-overview" title="Overview">
      {/* existing dependency overview block */}
    </WorkspaceSection>
  )}
  {activeTab === "actions" && (
    <WorkspaceSection testId="workspace-actions" title="Actions">
      <ContextEventLog events={filteredEvidence.contextEvents} />
    </WorkspaceSection>
  )}
  {activeTab === "communication" && (
    <WorkspaceSection testId="workspace-communication" title="Communication">
      <CommunicationPanel threads={filteredEvidence.threads} />
    </WorkspaceSection>
  )}
  {activeTab === "outputs" && (
    <WorkspaceSection testId="workspace-outputs" title="Outputs">
      <ResourcePanel resources={filteredEvidence.resources} runId={runState?.id ?? null} />
    </WorkspaceSection>
  )}
  {activeTab === "transitions" && (
    <WorkspaceSection testId="workspace-transitions" title="State transitions">
      <TaskTransitionLog task={task} onJumpToSequence={onJumpToSequence} />
    </WorkspaceSection>
  )}
  {activeTab === "evaluation" && (
    <WorkspaceSection testId="workspace-evaluation" title="Evaluation criteria">
      <EvaluationPanel evaluation={filteredEvidence.evaluation} />
    </WorkspaceSection>
  )}
</div>
```

Move the existing overview dependency JSX into a local `overviewPanel` constant to avoid duplicating it.

- [ ] **Step 6: Ensure evaluation panel shows criteria absence clearly**

In `EvaluationPanel.tsx`, change the empty state text to:

```tsx
<p>No evaluation criteria recorded yet</p>
<p className="text-sm">This task has no criterionResults in the persisted evaluation payload.</p>
```

If `evaluation` exists but `criterionResults.length === 0`, render:

```tsx
<div data-testid="evaluation-criteria-empty" className="rounded-xl border border-dashed border-[var(--line)] p-4 text-sm text-[var(--muted)]">
  No criteria were recorded for this evaluation payload.
</div>
```

- [ ] **Step 7: Run tests**

Run:

```bash
cd ergon-dashboard
BASE_URL=http://localhost:3001 pnpm exec playwright test tests/e2e/run-workspace-interactions.spec.ts -g "workspace uses tabs"
npm run build
```

Expected: PASS.

---

## Task 6: Rerun Button Behavior

**Files:**
- Modify: `ergon-dashboard/src/components/run/RunWorkspacePage.tsx`
- Test: `ergon-dashboard/tests/e2e/run-workspace-interactions.spec.ts`

- [ ] **Step 1: Write failing E2E test that rerun is not a dead active button**

Add:

```ts
test("rerun control is explicit about unavailable backend action", async ({ page }) => {
  await page.goto(`${BASE}/cohorts/${COHORT_ID}/runs/${RUN_ID}`);
  const rerun = page.locator('[data-testid="rerun-button"]');
  await expect(rerun).toBeVisible();
  await expect(rerun).toBeDisabled();
  await expect(rerun).toHaveAttribute("title", /not wired/i);
});
```

- [ ] **Step 2: Run E2E and verify it fails**

Run:

```bash
cd ergon-dashboard
BASE_URL=http://localhost:3001 pnpm exec playwright test tests/e2e/run-workspace-interactions.spec.ts -g "rerun control"
```

Expected: FAIL because current button has no `data-testid`, is enabled, and has no title explaining state.

- [ ] **Step 3: Make rerun visibly disabled**

Replace current rerun button:

```tsx
<button
  type="button"
  className="rounded-[7px] border border-[var(--line)] bg-[var(--card)] px-3 py-1 text-xs font-medium text-[var(--ink)]"
>
  Re-run
</button>
```

with:

```tsx
<button
  type="button"
  disabled
  title="Re-run is not wired yet: no dashboard API endpoint exists for cloning or dispatching a run."
  className="cursor-not-allowed rounded-[7px] border border-[var(--line)] bg-[var(--paper)] px-3 py-1 text-xs font-medium text-[var(--muted)] opacity-70"
  data-testid="rerun-button"
>
  Re-run unavailable
</button>
```

- [ ] **Step 4: Run test**

Run:

```bash
cd ergon-dashboard
BASE_URL=http://localhost:3001 pnpm exec playwright test tests/e2e/run-workspace-interactions.spec.ts -g "rerun control"
npm run build
```

Expected: PASS.

---

## Task 7: End-To-End Snapshot Rollback Verification

**Files:**
- Modify: `ergon-dashboard/tests/e2e/run-workspace-interactions.spec.ts`

- [ ] **Step 1: Write E2E test that clicking bottom activity changes graph snapshot label**

Add:

```ts
test("clicking bottom activity marker locks graph to snapshot sequence", async ({ page }) => {
  await page.goto(`${BASE}/cohorts/${COHORT_ID}/runs/${RUN_ID}`);
  await expect(page.locator('[data-testid="graph-canvas"]')).toBeVisible();

  const firstActivity = page.locator('[data-testid^="activity-bar-"]').first();
  await expect(firstActivity).toBeVisible();
  await firstActivity.click();

  await expect(page.locator('[data-testid="snapshot-lock-label"]')).toBeVisible();
  await expect(page.locator('[data-testid="snapshot-pin"]')).toBeVisible();
  await expect(page.locator('[data-testid="run-header"]')).toContainText(/snapshot · seq|seq \d+/);
});
```

If `ActivityBar` does not currently expose `data-testid^="activity-bar-"`, add it in `ActivityBar.tsx`:

```tsx
data-testid={`activity-bar-${item.activity.id}`}
```

- [ ] **Step 2: Run E2E and verify failure before fixes**

Run:

```bash
cd ergon-dashboard
BASE_URL=http://localhost:3001 pnpm exec playwright test tests/e2e/run-workspace-interactions.spec.ts -g "clicking bottom activity"
```

Expected: FAIL before Tasks 1-4; PASS after Tasks 1-4.

- [ ] **Step 3: Manual visual check**

Open:

```text
http://localhost:3001/cohorts/a39ee959-376d-490c-8705-22f0c3e32d1e/runs/4028c6d2-d9db-4c5a-be21-d9223d46b4ca
```

Expected:

- No Live/Timeline segmented control.
- No play/pause/speed controls.
- Bottom area is less dense.
- Clicking a bar/marker changes header chip to `snapshot · seq N`.
- `Esc` returns header chip to `live`.
- Graph node statuses/visibility match the selected sequence.

---

## Verification Checklist

- [ ] `npx tsx --test src/features/activity/snapshotSequence.test.ts` passes.
- [ ] `npx tsx --test src/features/activity/buildRunActivities.test.ts` passes.
- [ ] `npx tsx --test src/lib/timeFormat.test.ts` still passes.
- [ ] `npx tsx --test src/hooks/useRunState.socketHydration.test.ts` still passes.
- [ ] `npm run build` passes.
- [ ] `BASE_URL=http://localhost:3001 pnpm exec playwright test tests/e2e/run-workspace-interactions.spec.ts` passes.
- [ ] Browser smoke check shows no Next.js overlay, graph nodes render, drawer tabs render, activity stack is navigable.

---

## Spec Coverage Review

- Right drawer tabs: Task 5.
- Evaluation criteria visibility: Task 5, Step 6.
- Remove explicit live/timeline mode: Task 1.
- Bottom timeline drives graph replay: Tasks 1, 2, 7.
- Data structure support: Task 2 confirms mutation replay supports timestamp-to-sequence lookup.
- Concurrent activity clutter: Task 3.
- Remove pause/play/speed controls: Task 4.
- Dead rerun button: Task 6.

Known follow-up outside this plan: implement a real rerun backend action if product wants rerun to work. This plan only makes the current dead button honest and non-interactive because no confirmed dashboard rerun API exists in the current frontend.
