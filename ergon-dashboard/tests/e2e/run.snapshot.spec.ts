import { expect, test } from "@playwright/test";

import { createDashboardSeed, FIXTURE_IDS } from "../helpers/dashboardFixtures";
import { resetHarness, seedHarness } from "../helpers/harnessClient";

test.beforeEach(async ({ request }) => {
  await resetHarness(request);
  await seedHarness(request, createDashboardSeed());
});

test("run page keeps cohort breadcrumb context", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);

  await expect(page.getByTestId("run-breadcrumb-cohort")).toContainText(
    "minif2f-react-worker-gpt5v3",
  );
  await expect(page.getByTestId("run-header")).toContainText("amc12a_2008_p25");
});

test("graph selection opens workspace evidence sections", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);

  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await expect(page.getByTestId("workspace-launcher")).toBeVisible();
  await page.getByTestId(`graph-node-${FIXTURE_IDS.solveTaskId}`).click();

  await expect(page.getByTestId("workspace-header")).toContainText("Write proof");
  await expect(page.getByTestId("workspace-close")).toBeVisible();
  await expect(page.getByTestId("workspace-actions")).toContainText("lean_check");
  await expect(page.getByTestId("workspace-communication")).toContainText(
    "Can I use the standard divisibility lemma here?",
  );
  await expect(page.getByTestId("workspace-evaluation")).toContainText(
    "Proof compiles and closes all goals",
  );
  await expect(page.getByTestId("workspace-outputs")).toContainText("proof.lean");
  await expect(page.getByTestId("workspace-executions")).toContainText("Attempt 1");
  await expect(page.getByTestId("workspace-sandbox")).toContainText("lake env lean proof.lean");
});

test("persisted run snapshot remains inspectable after refresh", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);
  await page.reload();

  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await page.getByTestId(`graph-node-${FIXTURE_IDS.solveTaskId}`).click();

  await expect(page.getByTestId("workspace-header")).toContainText("Write proof");
  await expect(page.getByTestId("workspace-outputs")).toContainText("proof.lean");
  await expect(page.getByTestId("workspace-executions")).toContainText("Attempt 1");
});
