import { expect, Page, test } from "@playwright/test";
import * as fs from "node:fs/promises";
import * as path from "node:path";

import {
  CONCURRENT_MAS_FIXTURE_IDS,
  createConcurrentMasDashboardSeed,
} from "../helpers/dashboardFixtures";
import { acquireHarnessLock, resetHarness, seedHarness } from "../helpers/harnessClient";

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

test.describe.configure({ mode: "serial" });

let releaseHarnessLock: (() => Promise<void>) | null = null;

test.beforeEach(async ({ request }) => {
  releaseHarnessLock = await acquireHarnessLock();
  try {
    await resetHarness(request);
    await seedHarness(request, createConcurrentMasDashboardSeed());
  } catch (error) {
    await releaseHarnessLock();
    releaseHarnessLock = null;
    throw error;
  }
});

test.afterEach(async () => {
  await releaseHarnessLock?.();
  releaseHarnessLock = null;
});

function boxesOverlap(a: Box, b: Box, tolerancePx = 2): boolean {
  return (
    a.x + tolerancePx < b.x + b.width &&
    a.x + a.width > b.x + tolerancePx &&
    a.y + tolerancePx < b.y + b.height &&
    a.y + a.height > b.y + tolerancePx
  );
}

async function overlappingPairsFor(page: Page, selector: string): Promise<[number, number][]> {
  const boxes = await page.locator(selector).evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
    }),
  );
  const pairs: [number, number][] = [];
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      if (boxesOverlap(boxes[i], boxes[j])) pairs.push([i, j]);
    }
  }
  return pairs;
}

async function activityGeometry(page: Page): Promise<Record<string, Box>> {
  return page.locator('[data-activity-id]').evaluateAll((elements) => {
    return Object.fromEntries(
      elements.map((element) => {
        return [
          element.getAttribute("data-activity-id") ?? "",
          {
            x: Number(element.getAttribute("data-left-pct")),
            y: Number(element.getAttribute("data-row")),
            width: Number(element.getAttribute("data-width-pct")),
            height: 1,
          },
        ];
      }),
    );
  });
}

function expectGeometryStable(before: Record<string, Box>, after: Record<string, Box>) {
  for (const [id, box] of Object.entries(before)) {
    const next = after[id];
    expect(next, `${id} still exists after replay selection`).toBeTruthy();
    expect(Math.round(next.x * 1000), `${id} left pct`).toBe(Math.round(box.x * 1000));
    expect(Math.round(next.y), `${id} y`).toBe(Math.round(box.y));
    expect(Math.round(next.width * 1000), `${id} width pct`).toBe(Math.round(box.width * 1000));
    expect(Math.round(next.height), `${id} height`).toBe(Math.round(box.height));
  }
}

async function dumpScreenshots(page: Page) {
  if (process.env.VISUAL_DEBUGGER_SCREENSHOTS !== "1") return;
  const outDir = path.join(process.cwd(), "tmp", "visual-debugger");
  await fs.mkdir(outDir, { recursive: true });
  await page.screenshot({ path: path.join(outDir, "run-full.png"), fullPage: true });
  await page.getByTestId("activity-stack-region").screenshot({
    path: path.join(outDir, "activity-stack.png"),
  });
  await page.getByTestId("workspace-region").screenshot({
    path: path.join(outDir, "workspace-open.png"),
  });
}

async function dumpGraphScreenshot(page: Page) {
  if (process.env.VISUAL_DEBUGGER_SCREENSHOTS !== "1") return;
  const outDir = path.join(process.cwd(), "tmp", "visual-debugger");
  await fs.mkdir(outDir, { recursive: true });
  await page.getByTestId("graph-canvas").screenshot({
    path: path.join(outDir, "graph-canvas.png"),
  });
}

async function expectNoTimelinePlaybackControls(page: Page) {
  await expect(page.getByTestId("activity-play-toggle")).toHaveCount(0);
  await expect(page.getByTestId("activity-speed-control")).toHaveCount(0);
  await expect(page.getByTestId("activity-step-back")).toHaveCount(0);
  await expect(page.getByTestId("activity-step-forward")).toHaveCount(0);
}

test("visual debugger renders graph, activity stack, and time-aware workspace", async ({ page }) => {
  await page.goto(
    `/cohorts/${CONCURRENT_MAS_FIXTURE_IDS.cohortId}/runs/${CONCURRENT_MAS_FIXTURE_IDS.runId}`,
  );

  await expect(page.getByTestId("run-header")).toBeVisible();
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await expect(page.getByTestId("activity-stack-region")).toBeVisible();
  await expect(page.getByTestId("activity-kind-legend")).toContainText("Span");
  await expect(page.getByTestId("activity-kind-legend")).toContainText("Point event");
  await expect(page.getByTestId("activity-band-work")).toBeVisible();
  await expect(page.getByTestId("activity-band-graph")).toBeVisible();
  await expect(page.getByTestId("activity-band-tools")).toBeVisible();
  await expect(page.getByTestId("activity-band-communication")).toBeVisible();
  await expect(page.getByTestId("activity-band-outputs")).toBeVisible();
  await expectNoTimelinePlaybackControls(page);
  expect(await page.getByTestId("activity-stack-row").count()).toBeGreaterThan(1);
  await expect
    .poll(
      async () =>
        (await overlappingPairsFor(page, "[data-activity-id]")).length,
      { timeout: 5000 },
    )
    .toBe(0);
  await expect
    .poll(
      async () =>
        (
          await overlappingPairsFor(
            page,
            '.react-flow__node:has([data-testid^="graph-node-"])',
          )
        ).length,
      { timeout: 5000 },
    )
    .toBe(0);
  await dumpGraphScreenshot(page);

  const graphActivity = page
    .locator('[data-activity-id^="graph:"]:not([data-task-id=""])')
    .first();
  await expect(graphActivity).toBeVisible();
  const beforeGeometry = await activityGeometry(page);
  await graphActivity.hover();
  await expect(page.getByTestId("activity-debug-preview")).toBeVisible();
  await expect(page.getByTestId("activity-debug-preview")).toContainText("Lineage");
  await expect(page.getByTestId("activity-debug-preview")).toContainText("graph.mutation");
  expect(await page.locator('[data-relation="dimmed"]').count()).toBeGreaterThan(0);
  await graphActivity.click();
  expectGeometryStable(beforeGeometry, await activityGeometry(page));
  await expect(page.locator('[data-current="true"]')).toHaveCount(1);
  await expect(graphActivity).toHaveAttribute("data-current", "true");

  await expect(page.getByTestId("workspace-region")).toBeVisible();
  await expect(page.getByTestId("workspace-header")).toBeVisible();
  await expect(page.getByTestId("workspace-activity-detail")).toBeVisible();
  await expect(page.getByTestId("workspace-activity-detail")).toContainText("Graph mutation");
  await expect(page.getByTestId("workspace-activity-detail")).toContainText("payload");
  await expect(page.getByTestId("workspace-activity-detail")).toContainText("graph.mutation");
  await expect(page.getByTestId("workspace-timeline-badge")).toContainText("seq");
  await expectNoTimelinePlaybackControls(page);

  await page.keyboard.press("Escape");
  const toolActivity = page.locator('[data-activity-id^="context:"]').first();
  await expect(toolActivity).toBeVisible();
  await toolActivity.click();
  await expect(page.getByTestId("workspace-timeline-badge")).toContainText(/seq [1-9]/);
  await expect(page.getByTestId("snapshot-pin").first()).toBeVisible();

  await dumpScreenshots(page);
});
