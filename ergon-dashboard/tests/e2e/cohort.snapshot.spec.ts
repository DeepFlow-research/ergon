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
  await page.goto("/cohorts");

  await expect(page.getByTestId("cohort-index-header")).toContainText("Cohorts");
  await expect(page.getByTestId(`cohort-row-${FIXTURE_IDS.cohortId}`)).toContainText(
    "minif2f-react-worker-gpt5v3",
  );
  await expect(page.getByTestId("cohort-index-list")).toContainText("Runs");
});

test("cohort detail renders summary and experiment list", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}`);

  await expect(page.getByTestId("cohort-header")).toContainText("minif2f-react-worker-gpt5v3");
  await expect(page.getByTestId("cohort-summary-cards")).toContainText("Experiments");
  await expect(page.getByTestId("cohort-summary-cards")).toContainText("3 total runs");
  await expect(page.getByTestId("cohort-summary-cards")).toContainText("$0.42");
  await expect(page.getByRole("button", { name: "Compare" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Re-run failed" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Open in training" })).toHaveCount(0);
  const experimentRow = page.getByTestId(`cohort-experiment-row-${FIXTURE_IDS.experimentId}`);
  await expect(experimentRow).toContainText("minif2f smoke n=3");
  await expect(experimentRow).toContainText("3 done · 0 failed · 0 active");
  await expect(experimentRow).toContainText("lean-evaluator");
});

test("experiment detail renders restored run analytics surface", async ({ page }) => {
  await page.goto(`/experiments/${FIXTURE_IDS.experimentId}`);

  await expect(page.getByRole("heading", { name: "minif2f smoke n=3" })).toBeVisible();
  await expect(page.getByTestId("experiment-summary-cards")).toContainText("Score");
  await expect(page.getByTestId("experiment-summary-cards")).toContainText("10");
  await expect(page.getByTestId("experiment-run-distribution")).toContainText("algebra_sample");
  await expect(page.getByTestId("experiment-run-distribution")).toContainText("score 1");
  await expect(page.getByRole("link", { name: FIXTURE_IDS.runId })).toHaveAttribute(
    "href",
    `/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`,
  );
});
