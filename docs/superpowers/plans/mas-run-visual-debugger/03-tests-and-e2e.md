# 03 — Tests and E2E

**Status:** draft.
**Scope:** frontend unit tests, dashboard fixture tests, Playwright smoke assertions, screenshot capture points, and optional backend harness DTO additions.

Cross-refs: test-refactor north star in `docs/superpowers/plans/test-refactor/03-dashboard-and-playwright.md`, implementation tasks in [`02-frontend-implementation.md`](02-frontend-implementation.md).

---

## 1. Test strategy

Use five layers:

- **Pure unit tests:** prove activity derivation and stack packing without React or browser layout.
- **Golden fixture semantic tests:** pump realistic serialized MAS run data through replay, activity derivation, stack layout, and graph layout.
- **Coarse browser geometry checks:** assert catastrophic overlaps do not happen without pinning exact pixels.
- **Dashboard fixture e2e:** seed a deterministic concurrent run through dashboard harness routes and assert the visual debugger contract quickly.
- **Canonical smoke e2e:** run against real backend state and capture screenshots for graph + activity stack review.

Do not assert pixel-perfect bar positions. Assert stable structure, counts, selected state, and task/sequence coordination.
Use local PNG dumps for human visual review while building; do not make PNG diffs a CI gate in the first PR.

---

## 2. Unit tests

### Activity derivation tests

File: `ergon-dashboard/src/features/activity/buildRunActivities.test.ts`

Required cases:

- `ExecutionAttemptState.startedAt/completedAt` -> execution span.
- open running execution -> execution span ending at selected timeline time.
- resource event -> artifact marker.
- thread message -> message marker.
- task evaluation -> evaluation marker.
- context event with start/end -> context span.
- graph mutation -> graph marker with sequence.
- no agent lane key is emitted.

### Stack layout tests

File: `ergon-dashboard/src/features/activity/stackLayout.test.ts`

Required cases:

- non-overlap reuses row.
- overlap allocates rows.
- three-way overlap reports max concurrency.
- instant marker has minimum render width.
- deterministic order independent of input order.

### Golden fixture semantic tests

Files:

- `ergon-dashboard/tests/fixtures/mas-runs/concurrent-mas-run.json`
- `ergon-dashboard/src/features/activity/goldenFixture.test.ts`
- `ergon-dashboard/src/features/graph/layout/goldenLayout.test.ts`
- `ergon-dashboard/src/components/workspace/filterTaskEvidenceForTime.test.ts`

Required cases:

- replaying fixture mutations to checkpoint sequence `T` yields the whole expected graph at `T`.
- graph layout for the fixture has no overlapping node/container boxes using coarse rectangle checks.
- activity stack reports expected max concurrency for overlapping executions.
- activity rows are not grouped by agent or worker identity.
- task evidence filtering hides resources/messages/evaluations created after selected time.

Full details live in [`06-fast-feedback-and-visual-review.md`](06-fast-feedback-and-visual-review.md).

---

## 3. Dashboard fixture update

Modify `ergon-dashboard/tests/helpers/dashboardFixtures.ts`.

Add a fixture run with:

- root task plus at least 5 child tasks.
- two executions overlapping between `12:00:10` and `12:00:20`.
- one sandbox command inside an execution span.
- one thread message marker.
- one resource marker.
- one evaluation marker attached to a non-root task.
- graph mutations with sequences spanning node add/status events.

Suggested helper shape:

```typescript
export function concurrentMasRunState(): SerializedWorkflowRunState {
  return serializedRunState({
    scenario: "concurrent-mas-debugger",
  });
}
```

If `serializedRunState` is not currently parameterized, extract current fixture setup into small helpers first. Keep old fixture behavior unchanged for existing specs.

---

## 4. Playwright dashboard fixture spec

Create `ergon-dashboard/tests/e2e/activity-stack.spec.ts`.

Core assertions:

```typescript
test("run visual debugger shows recursive graph, activity stack, and time-aware workspace", async ({ page }) => {
  const client = new DashboardHarnessClient(page);
  const { cohortId, runId } = await client.seedConcurrentMasRun();

  await page.goto(`/cohorts/${cohortId}/runs/${runId}`);

  await expect(page.getByTestId("run-header")).toBeVisible();
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await expect(page.getByTestId("activity-stack-region")).toBeVisible();
  await expect(page.getByTestId("activity-stack-row")).toHaveCountGreaterThan(1);
  expect(
    await overlappingPairsFor(page, '[data-testid^="graph-node-"]'),
  ).toEqual([]);

  const firstExecution = page.locator('[data-testid^="activity-bar-"][data-kind="execution"]').first();
  await expect(firstExecution).toBeVisible();
  await firstExecution.click();

  await expect(page.getByTestId("workspace-region")).toBeVisible();
  await expect(page.getByTestId("workspace-header")).toBeVisible();

  await page.getByTestId("activity-step-forward").click();
  await expect(page.getByTestId("activity-current-sequence")).toContainText(/seq/i);
});
```

If Playwright's matcher set lacks `toHaveCountGreaterThan`, replace with:

```typescript
expect(await page.getByTestId("activity-stack-row").count()).toBeGreaterThan(1);
```

Add coarse geometry helpers in the spec or shared helper:

```typescript
async function overlappingPairsFor(page: Page, selector: string): Promise<[number, number][]> {
  const boxes = await page.locator(selector).evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    }),
  );
  return overlappingPairs(boxes, { tolerancePx: 2 });
}
```

The overlap assertion is intentionally coarse. It catches the broken layout class we care about without becoming a pixel-perfect visual test.

### Local-only PNG dumps

The fixture spec should dump review screenshots only when explicitly requested:

```bash
VISUAL_DEBUGGER_SCREENSHOTS=1 pnpm --dir ergon-dashboard exec playwright test tests/e2e/activity-stack.spec.ts --project=chromium
```

Output:

```text
ergon-dashboard/tmp/visual-debugger/run-full.png
ergon-dashboard/tmp/visual-debugger/graph-canvas.png
ergon-dashboard/tmp/visual-debugger/activity-stack.png
ergon-dashboard/tmp/visual-debugger/workspace-open.png
```

These PNGs are for local human review while building. They should not run in CI and should not be committed.

---

## 5. Canonical smoke e2e changes

Modify `ergon-dashboard/tests/e2e/_shared/smoke.ts`.

Add to `assertRunWorkspace` after `graph-canvas` assertion:

```typescript
await expect(page.getByTestId("activity-stack-region")).toBeVisible();

const activityBars = page.locator('[data-testid^="activity-bar-"]');
await expect(activityBars.first()).toBeVisible();

if (state.mutation_count > 0) {
  await page.getByTestId("mode-timeline").click();
  await expect(page.getByTestId("timeline-region")).toBeVisible();
  await expect(page.getByTestId("activity-current-sequence")).toContainText(/seq/i);
}
```

Screenshot additions:

- `<env>/<run_id>-visual-debugger-full.png` — full run page.
- `<env>/<run_id>-activity-stack.png` — bottom dock if Playwright can screenshot locator reliably.
- Keep existing happy/sad screenshots until the new ones prove stable.

---

## 6. Optional backend harness DTO additions

Only add these after frontend derivation is implemented and the e2e test needs backend truth for concurrency:

Modify backend `/api/test/read/run/{run_id}/state` DTO to include:

```json
{
  "activity_event_count": 37,
  "activity_span_count": 12,
  "max_concurrency": 4
}
```

Modify `ergon-dashboard/tests/helpers/backendHarnessClient.ts`:

```typescript
export interface BackendRunState {
  activity_event_count?: number;
  activity_span_count?: number;
  max_concurrency?: number;
}
```

Rules:

- These fields are optional in TypeScript while the backend branch catches up.
- Do not block the visual debugger UI on these fields.
- If added, Playwright may assert `max_concurrency >= 2` for the smoke run.

---

## 7. Accessibility and stable selectors

Required test IDs:

- `activity-stack-region`
- `activity-stack-row`
- `activity-bar-{activityId}`
- `activity-current-sequence`
- `activity-step-back`
- `activity-step-forward`
- `activity-play-toggle`
- `activity-speed-control`
- `graph-canvas`
- `graph-node-{taskId}`
- `graph-container-{taskId}`
- `workspace-region`
- `workspace-header`

Required ARIA labels:

- Activity bar button: `Open activity {label}`.
- Sequence scrubber: `Run timeline sequence`.
- Play/pause: `Play timeline` / `Pause timeline`.

---

## 8. Acceptance gate

- [ ] Pure activity tests pass.
- [ ] Golden fixture semantic/layout tests pass.
- [ ] Dashboard fixture e2e passes locally.
- [ ] Fixture e2e coarse graph overlap check passes.
- [ ] Local PNG dump works when `VISUAL_DEBUGGER_SCREENSHOTS=1` is set.
- [ ] Canonical smoke e2e still passes locally.
- [ ] Screenshots show more than one activity row for concurrent samples.
- [ ] Clicking an activity with a task opens the workspace for that task.
- [ ] Scrubbing sequence updates graph status/topology via existing replay.
- [ ] No assertion relies on agent lane count.
