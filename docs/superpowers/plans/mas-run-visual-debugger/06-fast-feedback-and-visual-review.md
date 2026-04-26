# 06 — Fast Feedback, TDD, and Local Visual Review

**Status:** draft.
**Scope:** the feedback loop that prevents another unreadable MAS layout from landing: test-first semantic layout checks, coarse browser geometry assertions, and local-only PNG dumps for human visual review.

Cross-refs: test contract in [`03-tests-and-e2e.md`](03-tests-and-e2e.md), implementation shape in [`05-implementation-shape.md`](05-implementation-shape.md).

---

## 1. Why this exists

The prior UI failure was not mainly a data-fetching failure. It was a semantics/layout failure:

- recursive task containers were hard to read;
- graph state at selected time `T` was not clearly represented;
- timeline lanes implied stable agents even though agents/workers can join and leave;
- overlapping work was not represented as concurrency;
- visual density problems were not caught by tests.

This plan adds a fast feedback loop before full e2e smoke:

1. Pure TDD tests for semantics and layout algorithms.
2. Coarse browser geometry checks for catastrophic overlap.
3. Local-only PNG dumps that humans inspect while building the UI.

PNG review is required for development/review discipline, but it is **not** a CI gate in the first PR.

---

## 2. Test-first policy for this feature

Use TDD for the core behavior:

- write the failing semantic/layout test;
- run it and confirm it fails for the expected reason;
- implement the smallest code to pass;
- keep the test as a regression guard.

Do this for:

- activity derivation;
- activity overlap packing;
- graph snapshot at sequence `T`;
- no graph node overlap for the golden fixture;
- activity click -> task/sequence selection;
- workspace time filtering.

Do not use TDD for throwaway visual CSS tweaking. For CSS, use local PNG review and coarse browser checks.

---

## 3. Golden fixture data

Add deterministic fixture data that represents the MAS case we care about.

Target files:

```text
ergon-dashboard/tests/fixtures/mas-runs/
  concurrent-mas-run.json
  nested-delegation-run.json
  README.md
```

`concurrent-mas-run.json` should include:

- full serialized run snapshot;
- graph mutations sorted by sequence;
- expected sequence checkpoints;
- expected graph node IDs/slugs at each checkpoint;
- expected activity concurrency facts.

Example shape:

```json
{
  "name": "concurrent-mas-run",
  "runState": {},
  "mutations": [],
  "checkpoints": [
    {
      "sequence": 12,
      "expectedTaskSlugs": ["root", "d_root", "d_left", "d_right", "d_join", "l_1"],
      "expectedVisibleResourceNames": [],
      "expectedMaxConcurrency": 3
    }
  ]
}
```

Rules:

- Keep fixture JSON small enough to review.
- Prefer real captured run shape when available, then minimize it.
- Do not include secrets, model outputs, or large artifacts.
- If the fixture comes from a real run/VCR capture, sanitize IDs only if tests do not depend on specific UUID shape.

---

## 4. Pure semantic layout tests

Create:

```text
ergon-dashboard/src/features/activity/goldenFixture.test.ts
ergon-dashboard/src/features/graph/layout/goldenLayout.test.ts
ergon-dashboard/src/components/workspace/timeFiltering.test.ts
```

### Activity fixture test

This test pumps fixture data through pure functions:

```typescript
import fixture from "../../../tests/fixtures/mas-runs/concurrent-mas-run.json";
import { parseGraphMutationDtoArray } from "@/features/graph/contracts/graphMutations";
import { replayToSequence } from "@/features/graph/state/graphMutationReducer";
import { buildRunActivities } from "./buildRunActivities";
import { stackActivities } from "./stackLayout";
import { buildRunEvents } from "@/lib/runEvents";
import { deserializeRunState } from "@/lib/runState";

it("derives concurrency from overlapping activity rather than agent lanes", () => {
  const liveState = deserializeRunState(fixture.runState);
  const mutations = parseGraphMutationDtoArray(fixture.mutations);
  const checkpoint = fixture.checkpoints.find((c) => c.sequence === 12)!;
  const displayState = replayToSequence(mutations, checkpoint.sequence, emptyRunStateFrom(liveState), new Map());
  const events = buildRunEvents(displayState);
  const activities = buildRunActivities({ runState: displayState, events, mutations, currentSequence: checkpoint.sequence });
  const stack = stackActivities(activities);

  expect(stack.maxConcurrency).toBe(checkpoint.expectedMaxConcurrency);
  expect(new Set(activities.map((activity) => activity.kind))).toEqual(
    expect.arrayContaining(["execution", "graph", "artifact", "evaluation"]),
  );
  expect(stack.items.some((item) => item.activity.actor && item.row === Number(item.activity.actor))).toBe(false);
});
```

The exact helper names can change during implementation, but the assertion intent must stay:

- concurrency comes from overlap;
- activities are not grouped by agent/worker lane;
- graph mutations remain sequence-addressable.

### Graph layout fixture test

This test runs the same fixture through replay + layout and asserts no overlapping rendered boxes.

```typescript
it("lays out the whole recursive graph at sequence T without overlapping node boxes", () => {
  const displayState = replayFixtureToSequence("concurrent-mas-run", 12);
  const result = computeHierarchicalLayout(
    displayState.tasks,
    calculateExpandedContainers(displayState.tasks, Infinity),
    "",
    undefined,
    null,
    "LR",
    new Set(),
  );

  expect(new Set(result.nodes.map((node) => node.id))).toEqual(expectedWholeGraphNodeIdsAtSequence(12));
  expect(findOverlappingNodeBoxes(result.nodes)).toEqual([]);
});
```

`findOverlappingNodeBoxes` should compare coarse rectangles from React Flow node `position`, `width`, and `height`. This is not a pixel-perfect visual diff; it catches catastrophic overlap.

### Workspace time filtering test

Extract filtering into a pure helper if `TaskWorkspace.tsx` is otherwise hard to test:

```text
ergon-dashboard/src/components/workspace/filterTaskEvidenceForTime.ts
ergon-dashboard/src/components/workspace/filterTaskEvidenceForTime.test.ts
```

Assert:

- resource created after selected time is hidden;
- execution started before selected time is visible;
- message created after selected time is hidden;
- live mode returns unfiltered evidence.

---

## 5. Browser geometry checks

Add coarse checks to `ergon-dashboard/tests/e2e/activity-stack.spec.ts`.

Use DOM bounding boxes for rendered elements:

```typescript
async function boxesFor(page: Page, selector: string) {
  return page.locator(selector).evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    }),
  );
}

function overlappingPairs(boxes: { x: number; y: number; width: number; height: number }[]) {
  const pairs: [number, number][] = [];
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      if (boxesOverlap(boxes[i], boxes[j])) pairs.push([i, j]);
    }
  }
  return pairs;
}

expect(overlappingPairs(await boxesFor(page, '[data-testid^="graph-node-"]'))).toEqual([]);
```

Rules:

- Use coarse overlap checks only.
- Do not assert exact coordinates.
- Ignore tiny overlaps below 2px if React Flow transform/subpixel rendering creates false positives.
- Keep these checks on fixture e2e first; only add to real smoke if stable.

---

## 6. Local-only PNG dump

Add a developer-only screenshot command/spec path. This is for us while building and reviewing. It does **not** need to run in CI.

Target output:

```text
ergon-dashboard/tmp/visual-debugger/
  run-full.png
  graph-canvas.png
  activity-stack.png
  workspace-open.png
```

Suggested command:

```bash
pnpm --dir ergon-dashboard exec playwright test tests/e2e/activity-stack.spec.ts --project=chromium
```

The spec should write screenshots when `VISUAL_DEBUGGER_SCREENSHOTS=1`:

```typescript
const shouldDumpScreenshots = process.env.VISUAL_DEBUGGER_SCREENSHOTS === "1";

if (shouldDumpScreenshots) {
  await page.screenshot({
    path: "tmp/visual-debugger/run-full.png",
    fullPage: true,
  });
  await page.getByTestId("graph-canvas").screenshot({
    path: "tmp/visual-debugger/graph-canvas.png",
  });
  await page.getByTestId("activity-stack-region").screenshot({
    path: "tmp/visual-debugger/activity-stack.png",
  });
  await page.getByTestId("workspace-region").screenshot({
    path: "tmp/visual-debugger/workspace-open.png",
  });
}
```

Recommended local command:

```bash
VISUAL_DEBUGGER_SCREENSHOTS=1 pnpm --dir ergon-dashboard exec playwright test tests/e2e/activity-stack.spec.ts --project=chromium
```

Review rules:

- Inspect PNGs locally during development.
- Look for cramped graph, overlapping containers, unreadable labels, poor activity row density, confusing color hierarchy, and workspace clipping.
- Treat final implementation review as incomplete until the implementer presents the four panel PNGs to the user/reviewer: `run-full.png`, `graph-canvas.png`, `activity-stack.png`, and `workspace-open.png`.
- Do not commit PNGs from `tmp/visual-debugger/`.
- Do not block CI on PNG generation or screenshot diffs in the first PR.

---

## 7. What becomes a hard gate

Hard gates:

- pure semantic tests pass;
- fixture e2e renders graph/stack/workspace;
- coarse graph node overlap check passes for golden fixture;
- no test asserts fixed agent lane counts;
- local screenshot command works when run manually.

Not hard gates in first PR:

- pixel-perfect screenshot diff;
- exact `x/y` coordinate assertions;
- local PNG files existing in CI;
- visual comparison against the HTML mockup.

---

## 8. Phase impact

This adds work to the phase plan:

- Phase B adds golden fixture semantic tests before implementing activity/layout code.
- Phase E adds browser geometry overlap checks and local screenshot dumping behind `VISUAL_DEBUGGER_SCREENSHOTS=1` to fixture e2e.
- Phase F keeps screenshot artifacts for real smoke/PR review, but no CI visual-diff gate.
