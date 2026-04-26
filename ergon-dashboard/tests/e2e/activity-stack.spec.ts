import { expect, Page, test } from "@playwright/test";
import * as fs from "node:fs/promises";
import * as path from "node:path";

import {
  CONCURRENT_MAS_FIXTURE_IDS,
  createConcurrentMasDashboardSeed,
} from "../helpers/dashboardFixtures";
import { resetHarness, seedHarness } from "../helpers/harnessClient";

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

test.beforeEach(async ({ request }) => {
  await resetHarness(request);
  await seedHarness(request, createConcurrentMasDashboardSeed());
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

test("visual debugger renders graph, activity stack, and time-aware workspace", async ({ page }) => {
  await page.goto(
    `/cohorts/${CONCURRENT_MAS_FIXTURE_IDS.cohortId}/runs/${CONCURRENT_MAS_FIXTURE_IDS.runId}`,
  );

  await expect(page.getByTestId("run-header")).toBeVisible();
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await expect(page.getByTestId("activity-stack-region")).toBeVisible();
  expect(await page.getByTestId("activity-stack-row").count()).toBeGreaterThan(1);
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

  await page.getByTestId("mode-timeline").click();
  await expect(page.getByTestId("activity-current-sequence")).toContainText("seq 14");
  await expect(page.getByText("Graph 18")).toBeVisible();

  const firstExecution = page
    .locator('[data-testid^="activity-bar-"][data-kind="execution"]')
    .first();
  await expect(firstExecution).toBeVisible();
  await firstExecution.click();

  await expect(page.getByTestId("workspace-region")).toBeVisible();
  await expect(page.getByTestId("workspace-header")).toBeVisible();
  await expect(page.getByTestId("workspace-timeline-badge")).toContainText("seq");

  await dumpScreenshots(page);
});
