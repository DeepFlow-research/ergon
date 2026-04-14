import { expect, test } from "@playwright/test";

import { createDashboardSeed, FIXTURE_IDS } from "../helpers/dashboardFixtures";
import { resetHarness, seedHarness } from "../helpers/harnessClient";

test.beforeEach(async ({ request }) => {
  await resetHarness(request);
  await seedHarness(request, createDashboardSeed());
});

test("cohort index renders cohort-first snapshot truth", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByTestId("cohort-index-header")).toContainText("Experiment Cohorts");
  await expect(page.getByTestId(`cohort-row-${FIXTURE_IDS.cohortId}`)).toContainText(
    "minif2f-react-worker-gpt5v3",
  );
  await expect(page.getByTestId(`cohort-row-${FIXTURE_IDS.cohortId}`)).toContainText("Runs");
});

test("cohort detail renders summary and run list", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}`);

  await expect(page.getByTestId("cohort-header")).toContainText("minif2f-react-worker-gpt5v3");
  await expect(page.getByTestId("cohort-summary-cards")).toContainText("Total runs");
  const runRow = page.getByTestId(`cohort-run-row-${FIXTURE_IDS.runId}`);
  await expect(runRow).toContainText("minif2f-react-worker-gpt5v3");
  await expect(runRow).toContainText("Started");
  await expect(runRow.locator("time[datetime]")).toHaveAttribute(
    "datetime",
    "2026-03-18T12:00:00.000Z",
  );
});
