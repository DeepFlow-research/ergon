# 05 — Implementation Shape, File Ownership, and Refactor Boundaries

**Status:** draft for review.
**Scope:** the reviewer-facing "how" plan: what domains the frontend should have after this work, which files are added, which files are refactored, which files are deleted or deliberately left alone, and how tests are laid out.

Cross-refs: product/DTO stance in [`00-program.md`](00-program.md), activity contracts in [`01-contracts-and-state.md`](01-contracts-and-state.md), phase gates in [`04-phases.md`](04-phases.md).

---

## 1. Target domain map

After the implementation, the run dashboard should have these frontend domains:

| Domain | Responsibility | Owns | Must not own |
|---|---|---|---|
| `features/activity` | Turn run state into time-based activity, pack overlaps into stack rows, render bottom dock. | Activity types, derivation, overlap layout, activity timeline UI. | Graph replay, workspace evidence rendering, backend fetching. |
| `features/graph` | Reconstruct and render recursive task topology at selected sequence/time. | Graph mutation contracts, replay reducer, React Flow layout, node components. | Activity stacking, agent lanes, workspace filtering. |
| `components/workspace` | Show task-scoped evidence for the selected task. | Resources, executions, sandbox commands, messages, context events, evaluations for one task. | Timeline packing, graph topology. |
| `components/run` | Page orchestration and cross-panel selection state. | Live/timeline mode, selected task, selected activity, selected sequence, panel composition. | Pure derivation algorithms. |
| `lib/runEvents` | Normalize existing state into a chronological event stream. | Event union, event labels/colors, stream rows. | Visual timeline row allocation. |
| `tests/e2e` + `tests/helpers` | Prove the visual debugger contract with fixture and smoke runs. | Stable selectors, seeded concurrent fixture, screenshot capture, harness assertions. | Pixel-perfect visual diffs. |

The most important boundary: **activity stack rows are not a domain concept**. They are a layout result. The domain concept is a `RunActivity` with task/time/kind metadata.

---

## 2. Intended folder layout

Target new files:

```text
ergon-dashboard/src/features/activity/
  types.ts
  buildRunActivities.ts
  stackLayout.ts
  goldenFixture.test.ts
  buildRunActivities.test.ts
  stackLayout.test.ts
  components/
    ActivityStackTimeline.tsx
    ActivityBar.tsx
    ActivityKindLegend.tsx
    SequenceControls.tsx
```

Target modified existing files:

```text
ergon-dashboard/src/components/run/
  RunWorkspacePage.tsx

ergon-dashboard/src/components/dag/
  DAGCanvas.tsx
  TaskNode.tsx

ergon-dashboard/src/features/graph/components/
  ContainerNode.tsx
  LeafNode.tsx
  MutationTimeline.tsx

ergon-dashboard/src/features/graph/layout/
  hierarchicalLayout.ts
  layoutTypes.ts

ergon-dashboard/src/components/workspace/
  TaskWorkspace.tsx

ergon-dashboard/src/lib/
  runEvents.ts
  statusTokens.ts
```

Target test files:

```text
ergon-dashboard/tests/helpers/
  dashboardFixtures.ts
  testHarnessClient.ts
  backendHarnessClient.ts

ergon-dashboard/tests/fixtures/mas-runs/
  concurrent-mas-run.json
  nested-delegation-run.json
  README.md

ergon-dashboard/tests/e2e/
  activity-stack.spec.ts
  _shared/smoke.ts
```

Optional backend files if the e2e harness needs additive DTO truth:

```text
ergon_core/ergon_core/core/api/test_harness.py
tests/unit/test_test_harness.py
tests/integration/smokes/test_smoke_harness.py
```

---

## 3. Add, refactor, delete, leave alone

### Add

| File | Why it exists |
|---|---|
| `features/activity/types.ts` | Shared activity vocabulary: `RunActivity`, `ActivityKind`, `ActivityStackLayout`, `ActivityStackItem`. |
| `features/activity/buildRunActivities.ts` | Pure state-to-activity derivation. Lets tests verify semantics without React. |
| `features/activity/stackLayout.ts` | Pure overlap packing. Keeps "concurrency stack" independent from rendering. |
| `features/activity/components/ActivityStackTimeline.tsx` | Bottom dock shell: time ruler, rows, controls, legend, selection. |
| `features/activity/components/ActivityBar.tsx` | Single activity marker/span renderer. Keeps bar styling out of the dock shell. |
| `features/activity/components/ActivityKindLegend.tsx` | Small count/filter legend if `ActivityStackTimeline.tsx` gets too large. |
| `features/activity/components/SequenceControls.tsx` | Reusable play/step/speed controls extracted from old mutation timeline behavior. |
| `features/activity/buildRunActivities.test.ts` | Unit coverage for event/span semantics. |
| `features/activity/stackLayout.test.ts` | Unit coverage for overlap packing and max concurrency. |
| `features/activity/goldenFixture.test.ts` | Pumps realistic MAS fixture data through replay/activity/stack derivation. |
| `tests/fixtures/mas-runs/concurrent-mas-run.json` | Stable local fixture for semantic layout and browser visual review. |
| `tests/fixtures/mas-runs/nested-delegation-run.json` | Optional second fixture for deeper recursive nesting once the first path is green. |
| `tests/e2e/activity-stack.spec.ts` | Fast fixture-driven UI contract for the new debugger. |

### Refactor

| File | Refactor |
|---|---|
| `RunWorkspacePage.tsx` | Becomes the cross-panel coordinator. It should compute display state, activities, selected time, selected task/activity, and pass props down. It should not implement activity derivation inline. |
| `DAGCanvas.tsx` | Adds highlight props and preserves graph-level controls. No activity logic here. |
| `TaskNode.tsx`, `ContainerNode.tsx`, `LeafNode.tsx` | Add selected/highlight styling and stable test IDs. Avoid redesigning node semantics. |
| `TaskWorkspace.tsx` | Adds time-aware filtering by selected sequence time. Keep the existing evidence sections. |
| `MutationTimeline.tsx` | Either deleted after replacement, or split so reusable sequence controls move to `features/activity/components/SequenceControls.tsx`. |
| `hierarchicalLayout.ts`, `layoutTypes.ts` | Only tune spacing if smoke screenshots still show overlap. Keep dagre and current recursive container model. |
| `runEvents.ts` | Remains event normalization. It may gain helper exports, but it should not pack visual rows. |
| `dashboardFixtures.ts` | Adds a deterministic concurrent MAS fixture, preserving existing fixture exports. |
| `_shared/smoke.ts` | Adds activity stack assertions and screenshots without making visual pixel claims. |
| `activity-stack.spec.ts` | Adds coarse DOM bounding-box overlap checks and optional local screenshot dumping behind `VISUAL_DEBUGGER_SCREENSHOTS=1`. |

### Delete

Delete only after the activity stack is wired and tested:

| File | Delete condition |
|---|---|
| `features/graph/components/MutationTimeline.tsx` | Delete if no code is reused by `SequenceControls.tsx`. |

No other deletions are planned for the first visual debugger PR.

### Leave alone

| Area | Reason |
|---|---|
| Backend execution/control-flow services | The UI problem is representational; backend task orchestration does not need to change. |
| Graph mutation persistence model | Existing sequence/time mutation contract is the right replay primitive. |
| React Flow dependency | The current rendering stack already supports recursive graph rendering. |
| Cohort pages | This work is scoped to run detail pages and smoke screenshots. |
| Production REST schemas | Avoid production DTO expansion unless a real user-facing timestamp gap is proven. |

---

## 4. Data flow after refactor

```text
REST snapshot / socket updates
        |
        v
useRunState(runId) --------------------+
        |                              |
        v                              |
WorkflowRunState                       |
        |                              |
        +--> replayToSequence() ----> displayState at T ----> DAGCanvas
        |                              |
        +--> buildRunEvents() ---------+
        |                              |
/api/runs/{runId}/mutations -----------+
        |
        v
buildRunActivities(displayState, events, mutations, currentSequence)
        |
        v
stackActivities(activities)
        |
        v
ActivityStackTimeline
        |
        +--> select task/activity/sequence
        |
        v
RunWorkspacePage state
        |
        +--> DAGCanvas highlight/selection
        +--> TaskWorkspace selected task + selected time
```

Selection rules:

- Graph node click sets `selectedTaskId`.
- Activity click sets `selectedActivityId`, sets `selectedTaskId` when present, and jumps to `activity.sequence` when present.
- Sequence scrub changes `currentSequence`; it does not clear task selection unless the selected task does not exist at that sequence.
- Workspace reads selected task from `displayState`, not live state, when timeline mode is active.

---

## 5. Test layout

### Pure unit tests

```text
ergon-dashboard/src/features/activity/buildRunActivities.test.ts
ergon-dashboard/src/features/activity/stackLayout.test.ts
```

These tests should use small inline fixture builders. Do not import Playwright, React, or browser APIs.

### Component-level tests if local harness exists

If the dashboard already has React component tests, add:

```text
ergon-dashboard/src/features/activity/components/ActivityStackTimeline.test.tsx
```

This test should assert:

- rows render from layout items.
- clicking a bar calls `onActivityClick`.
- controls call `onSequenceChange`.

If the project does not have component-test infrastructure, skip this and rely on pure unit + Playwright.

### Fixture e2e

```text
ergon-dashboard/tests/e2e/activity-stack.spec.ts
```

This is the fast UI contract:

- seed concurrent MAS fixture.
- open run page.
- assert graph, stack, and workspace regions.
- assert more than one stack row.
- assert no catastrophic graph-node bounding-box overlaps.
- click activity -> workspace opens.
- scrub sequence -> current sequence indicator changes.
- dump local PNGs only when `VISUAL_DEBUGGER_SCREENSHOTS=1`.

### Golden fixture semantic tests

```text
ergon-dashboard/src/features/activity/goldenFixture.test.ts
ergon-dashboard/src/features/graph/layout/goldenLayout.test.ts
ergon-dashboard/src/components/workspace/filterTaskEvidenceForTime.test.ts
```

These are the fast feedback loop for the exact failure mode we want to avoid:

- replay fixture to selected sequence `T`;
- assert whole graph expected at `T`;
- assert no overlapping graph boxes in pure layout output;
- assert activity stack max concurrency;
- assert row assignment does not depend on agent/worker identity;
- assert future task evidence is hidden in timeline mode.

### Local PNG review

```text
ergon-dashboard/tmp/visual-debugger/
  run-full.png
  graph-canvas.png
  activity-stack.png
  workspace-open.png
```

Generated only by local command:

```bash
VISUAL_DEBUGGER_SCREENSHOTS=1 pnpm --dir ergon-dashboard exec playwright test tests/e2e/activity-stack.spec.ts --project=chromium
```

These files are for human review while building. They should not be committed and should not be required in CI.

### Smoke e2e

```text
ergon-dashboard/tests/e2e/_shared/smoke.ts
```

This is the real integration contract:

- backend harness proves graph/resources/evaluations are real.
- dashboard proves visual debugger renders real run state.
- screenshots capture full page and activity stack.

---

## 6. Review questions before implementation

1. Should `features/activity` own `SequenceControls.tsx`, or should sequence controls live under `features/graph` because sequences come from graph mutations?
2. Should `ActivityStackTimeline` support filtering by kind in the first PR, or only render the legend counts?
3. Should `TaskWorkspace` hide future evidence in timeline mode, or show it disabled with "after selected time" labels?
4. Should the old event stream stay visible by default, or be collapsed once the activity stack exists?
5. Should fixture e2e be required before smoke e2e changes, or can smoke drive the first UI contract directly?
6. Should `nested-delegation-run.json` ship in the first PR, or should the first PR use only `concurrent-mas-run.json` and add the deeper fixture after the UI stabilizes?
