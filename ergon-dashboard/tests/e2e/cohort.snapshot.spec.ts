import { expect, test } from "@playwright/test";

import { createDashboardSeed, FIXTURE_IDS } from "../helpers/dashboardFixtures";
import { acquireHarnessLock, resetHarness, seedHarness } from "../helpers/harnessClient";

test.describe.configure({ mode: "serial" });

let releaseHarnessLock: (() => Promise<void>) | null = null;

test.beforeEach(async ({ request }) => {
  releaseHarnessLock = await acquireHarnessLock();
  try {
    await resetHarness(request);
    await seedHarness(request, createDashboardSeed());
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

test("cohort index renders cohort-first snapshot truth", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByTestId("cohort-index-header")).toContainText("Cohorts");
  await expect(page.getByTestId(`cohort-row-${FIXTURE_IDS.cohortId}`)).toContainText(
    "minif2f-react-worker-gpt5v3",
  );
  await expect(page.getByTestId("cohort-index-list")).toContainText("Runs");
});

test("cohort detail renders summary and run list", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}`);

  await expect(page.getByTestId("cohort-header")).toContainText("minif2f-react-worker-gpt5v3");
  await expect(page.getByTestId("cohort-summary-cards")).toContainText("Runs · pass / fail");
  await expect(page.getByTestId("cohort-summary-cards")).toContainText("3 of 3 runs");
  await expect(page.getByTestId("cohort-summary-cards")).toContainText("Avg tasks");
  await expect(page.getByTestId("cohort-summary-cards")).toContainText("10.0");
  await expect(page.getByRole("button", { name: "Compare" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Re-run failed" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open in training" })).toHaveCount(0);
  await expect(page.getByTestId("cohort-run-distribution")).toBeVisible();
  await expect(page.getByTestId("cohort-run-distribution")).toContainText("Score distribution");
  await expect(page.getByTestId("cohort-distribution-point")).toHaveCount(3);
  await page.getByTestId("cohort-distribution-metric-runtime").click();
  await expect(page.getByTestId("cohort-run-distribution")).toContainText("Runtime distribution");
  await expect(page.getByTestId("cohort-distribution-point")).toHaveCount(3);
  const runRow = page.getByTestId(`cohort-run-row-${FIXTURE_IDS.runId}`);
  await expect(runRow).toContainText("minif2f-react-worker-gpt5v3");
  await expect(runRow).toContainText("Started");
  await expect(runRow.locator("time[datetime]")).toHaveAttribute(
    "datetime",
    "2026-03-18T12:00:00.000Z",
  );
});
