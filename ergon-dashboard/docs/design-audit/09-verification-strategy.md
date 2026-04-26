# Verification Strategy — Making Each Phase Agent-Delegatable

## Current state of verification

| Layer | What exists | What's missing |
|-------|------------|----------------|
| **Typecheck** | `npm run typecheck` — full TS coverage | Nothing — this works |
| **E2E harness** | Seed/reset in-memory fixtures, DOM assertions on testids, structure | No assertions on *styling* — only that elements exist |
| **Screenshots** | `VISUAL_DEBUGGER_SCREENSHOTS=1` dumps PNGs to `tmp/visual-debugger/` | **Manual inspection only** — no baselines, no pixel-diff, no automated comparison |
| **Visual regression** | None | No `toHaveScreenshot()`, no Playwright visual comparisons, no baseline images |
| **Unit tests** | Some for layout/mutation logic | No tests for design tokens, component rendering, pill colors |
| **Backend data** | Harness seeds cohorts + runs with realistic data | Missing fields: tokens, cost, resolution %, avg tasks per run |

**Bottom line**: An agent can currently verify that code compiles and that DOM elements exist. It **cannot** verify that the UI *looks right*. That's the gap.

---

## Three pillars of agent-verifiable design work

### Pillar 1: Structural E2E assertions (DOM correctness)

For each new/changed component, the agent needs testid-based assertions that verify the **structure** is correct — right elements present, right text content, right hierarchy.

**What to add per phase**:

#### P0 — Topbar + tokens
```typescript
// New spec: topbar.spec.ts
test("topbar renders on cohort list", async ({ page }) => {
  await seedHarness(page, createDashboardSeed());
  await page.goto("/");
  const topbar = page.getByTestId("topbar");
  await expect(topbar).toBeVisible();
  // Nav tabs
  for (const tab of ["Cohorts", "Runs", "Training", "Models", "Settings"]) {
    await expect(topbar.getByRole("link", { name: tab })).toBeVisible();
  }
  // Active tab
  await expect(topbar.getByRole("link", { name: "Cohorts" })).toHaveAttribute("aria-current", "page");
  // Search bar
  await expect(topbar.getByPlaceholder(/search/i)).toBeVisible();
  // User avatar
  await expect(topbar.getByTestId("user-avatar")).toBeVisible();
});

test("topbar renders on run page with Runs active", async ({ page }) => {
  // ...seed + navigate to run
  await expect(topbar.getByRole("link", { name: "Runs" })).toHaveAttribute("aria-current", "page");
});
```

#### P1 — Graph + drawer
```typescript
// Extend activity-stack.spec.ts or new graph.spec.ts
test("graph has floating controls", async ({ page }) => {
  await expect(page.getByTestId("graph-zoom-controls")).toBeVisible();
  await expect(page.getByTestId("graph-depth-selector")).toBeVisible();
  await expect(page.getByTestId("graph-search")).toBeVisible();
  await expect(page.getByTestId("graph-legend")).toBeVisible();
  await expect(page.getByTestId("graph-minimap")).toBeVisible();
});

test("drawer has tab navigation", async ({ page }) => {
  // click a node to open drawer
  await page.getByTestId("graph-canvas").locator(".react-flow__node").first().click();
  const drawer = page.getByTestId("workspace-region");
  for (const tab of ["Overview", "Transitions", "Generations", "Resources", "Evals", "Logs"]) {
    await expect(drawer.getByRole("tab", { name: new RegExp(tab) })).toBeVisible();
  }
});

test("drawer is 460px wide", async ({ page }) => {
  // ...open drawer
  const box = await page.getByTestId("workspace-region").boundingBox();
  expect(box?.width).toBeCloseTo(460, -1); // within 10px
});

test("run header shows tokens and cost", async ({ page }) => {
  await expect(page.getByTestId("stat-tokens")).toBeVisible();
  await expect(page.getByTestId("stat-cost")).toBeVisible();
});
```

#### P2 — Activity stack
```typescript
test("activity stack has NOW cursor in live mode", async ({ page }) => {
  await expect(page.getByTestId("now-cursor")).toBeVisible();
  await expect(page.getByTestId("now-cursor-pill")).toHaveText(/NOW/);
});

test("activity stack shows snapshot pin after event click", async ({ page }) => {
  // click an activity bar
  await page.getByTestId("activity-stack-region").locator("[data-activity-id]").first().click();
  await expect(page.getByTestId("snapshot-pin")).toBeVisible();
});

test("activity stack has kind legend in header", async ({ page }) => {
  for (const kind of ["graph mutation", "task", "tool call", "message", "resource", "eval"]) {
    await expect(page.getByTestId("activity-kind-legend").getByText(kind)).toBeVisible();
  }
});

test("activity stack has footer hints", async ({ page }) => {
  await expect(page.getByTestId("activity-footer-hints")).toBeVisible();
  await expect(page.getByTestId("activity-footer-hints")).toContainText("Color = kind");
});
```

#### P3 — Cohorts
```typescript
// New spec: cohort-design.spec.ts
test("cohort list has 7-column header", async ({ page }) => {
  const headers = page.getByTestId("cohort-table-header");
  for (const col of ["Cohort", "Runs", "Avg score", "Failure", "Runtime", "Status"]) {
    await expect(headers.getByText(col, { exact: false })).toBeVisible();
  }
});

test("cohort detail has 5 metric tiles", async ({ page }) => {
  // navigate to cohort detail
  for (const metric of ["resolution", "runs-pass-fail", "avg-runtime", "avg-tasks", "cost"]) {
    await expect(page.getByTestId(`metric-tile-${metric}`)).toBeVisible();
  }
});
```

### Pillar 2: Visual regression via Playwright `toHaveScreenshot()`

This is the **most important missing piece**. Playwright has built-in visual comparison:

```typescript
// First run generates baseline images in tests/e2e/*.spec.ts-snapshots/
// Subsequent runs compare against baselines with configurable threshold
await expect(page).toHaveScreenshot("cohort-list.png", {
  maxDiffPixelRatio: 0.01, // 1% tolerance
});

await expect(page.getByTestId("graph-region")).toHaveScreenshot("graph-compact-nodes.png", {
  maxDiffPixelRatio: 0.02,
});
```

**Setup needed**:
1. Add `expect.toHaveScreenshot.maxDiffPixelRatio` to `playwright.config.ts`
2. Generate baseline screenshots from the *completed* design work
3. Commit baselines to `tests/e2e/*.spec.ts-snapshots/` (Playwright's convention)

**Per-phase screenshot gates**:

| Phase | Screenshots to baseline |
|-------|------------------------|
| P0 | `topbar.png`, `cohort-list-with-topbar.png` |
| P1 | `graph-compact-nodes.png`, `graph-floating-controls.png`, `drawer-open.png`, `drawer-tabs.png` |
| P2 | `activity-stack-live.png`, `activity-stack-snapshot.png` |
| P3 | `cohort-list-table.png`, `cohort-detail-tiles.png`, `empty-cohort.png` |
| P4 | Full page screenshots at 1920×1080 matching spec slides |

**Workflow for agents**: The agent runs `npx playwright test --update-snapshots` after making changes, then the baselines get committed. On review, a human checks the baseline diffs. For subsequent agents, the baselines serve as regression gates.

### Pillar 3: Computed style assertions (CSS correctness)

For design-token work where screenshots are overkill but DOM assertions aren't enough:

```typescript
test("body uses Inter font", async ({ page }) => {
  const fontFamily = await page.evaluate(() =>
    getComputedStyle(document.body).fontFamily
  );
  expect(fontFamily).toContain("Inter");
});

test("status pill uses correct oklch colors", async ({ page }) => {
  const pill = page.locator("[data-status='running'] .swatch").first();
  const bg = await pill.evaluate((el) => getComputedStyle(el).backgroundColor);
  // oklch(0.78 0.14 80) ≈ rgb(226, 185, 77) — check approximate
  expect(bg).toMatch(/rgb\(2[12]\d, 1[78]\d, [67]\d\)/);
});

test("drawer width is 460px", async ({ page }) => {
  const width = await page.getByTestId("workspace-region").evaluate(
    (el) => el.getBoundingClientRect().width
  );
  expect(width).toBeCloseTo(460, -1);
});
```

---

## Backend gaps — what's missing from the API

The design spec shows data that **does not exist** in the current API contracts:

| Spec field | Where shown | API status |
|------------|------------|------------|
| **Tokens** (per run) | Run header: `Tokens: 142k` | **Not in schema**. Not on `CohortRunRow`, `WorkflowRunState`, or `CohortSummary`. |
| **Cost** (per run) | Run header: `Cost: $0.18` | **Not in schema**. |
| **Cost** (per cohort) | Cohort detail tile: `$84.20` | **Not in schema**. |
| **Resolution %** | Cohort detail tile: `62.4%` | **Computable**: `completed / total` from `status_counts`, but no explicit `resolution_rate` field. |
| **Avg tasks per run** | Cohort detail tile: `11.4` | **Not in schema**. Individual runs have `totalTasks` but no cohort-level aggregate. |
| **Depth levels** | Cohort detail tile: `2.1 levels deep` | **Not in schema**. |
| **Retries** | Cohort detail tile: `1.7 retries` | **Not in schema**. |
| **Tokens** (per cohort) | Cohort detail tile: `41M tokens` | **Not in schema**. |
| **p95 runtime** | Cohort detail tile: `p95 4:32` | **Not in schema**. Only `average_duration_ms`. |

### Options

**Option A: Backend implements these fields** — Add token/cost tracking to the Ergon core, aggregate at cohort level. This is the "right" answer but requires backend work.

**Option B: Compute client-side where possible** — Resolution = `completed / total`. Avg tasks requires iterating runs (expensive). Tokens/cost need backend support.

**Option C: Show what we have, use `—` for missing** — The dashboard fixtures can seed fake values. The harness already uses arbitrary data. We can add `tokens`, `cost` fields to the **fixture** data and show them in the UI, with the real backend catching up later.

**Recommendation: Option C for now.** Extend the test fixtures to include `tokens` and `cost` fields on run/cohort data. The UI renders them. The harness tests verify the rendering. When the backend adds real fields, the UI just works.

### Fixture extensions needed

In `tests/helpers/dashboardFixtures.ts`, extend:

```typescript
// On CohortSummary extras:
extras: {
  total_tokens: 41_000_000,
  total_cost_usd: 84.20,
  avg_tasks_per_run: 11.4,
  avg_depth: 2.1,
  avg_retries: 1.7,
  p95_duration_ms: 272_000, // 4:32
}

// On CohortRunRow or WorkflowRunState extras:
extras: {
  total_tokens: 142_000,
  cost_usd: 0.18,
}
```

Since the Zod schemas use `.passthrough()`, extra fields survive parsing.

---

## Putting it together: the agent delegation loop

For each phase, the agent receives:

1. **The plan document** (e.g., `04-P0-design-foundations.md`)
2. **A test spec file** with all structural assertions pre-written (failing)
3. **Baseline screenshots** (if phase > P0 — generated from the previous phase's output)

The agent's job:
1. Implement the changes described in the plan
2. Run `npm run typecheck` — must pass
3. Run the phase's test spec — all assertions must pass
4. Run `npx playwright test --update-snapshots` to generate new baselines
5. Run the full e2e suite — no regressions

The verification is **automated except for baseline review**. A human reviews the screenshot baselines once; after that, agents can't regress them.

### Concrete test files to write BEFORE delegating

| Phase | Test file to pre-write | Assertions |
|-------|----------------------|------------|
| P0 | `tests/e2e/topbar.spec.ts` | Topbar visible on all pages, nav tabs, search, avatar, active tab, font-family check |
| P1 | `tests/e2e/graph-design.spec.ts` | Floating controls, compact nodes (bounding box height ≤ 80px), drawer width, drawer tabs, stats row content |
| P2 | `tests/e2e/activity-design.spec.ts` | NOW cursor, snapshot pin, kind legend, footer hints, left rubric width |
| P3 | `tests/e2e/cohort-design.spec.ts` | 7-column table, metric tiles, empty state, chart area |
| P4 | `tests/e2e/visual-regression.spec.ts` | `toHaveScreenshot()` for all 8 key views |

---

## Implementation order for verification infra

Before delegating ANY phase to an agent:

1. **Enable `toHaveScreenshot`** in playwright config (set threshold, snapshot dir)
2. **Write the failing test specs** for P0 (topbar.spec.ts)
3. **Extend fixtures** with tokens/cost/resolution extras
4. **Add testids** to the plan documents so the agent knows where to place them
5. Delegate P0 with the test spec as the acceptance criterion

After P0 lands:
6. Generate P0 screenshot baselines
7. Write failing specs for P1 + P2 (can parallelize)
8. Delegate P1 and P3 in parallel
9. After P1: write P2 specs, delegate P2
10. After all: write P4 visual regression spec, delegate P4
