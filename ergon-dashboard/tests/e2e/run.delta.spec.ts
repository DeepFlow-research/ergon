import { expect, test } from "@playwright/test";

import {
  createDashboardSeed,
  createDeltaThread,
  createUpdatedEvaluation,
  FIXTURE_IDS,
} from "../helpers/dashboardFixtures";
import { resetHarness, seedHarness } from "../helpers/harnessClient";

test.beforeEach(async ({ request }) => {
  await resetHarness(request);
  await seedHarness(request, createDashboardSeed());
});

test("run header reacts to controlled completion delta", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);

  await expect(page.getByTestId("run-header")).toContainText("Executing");

  const response = await page.request.post("/api/test/dashboard/events/run-complete", {
    data: {
      runId: FIXTURE_IDS.runId,
      status: "completed",
      durationSeconds: 42,
      finalScore: 0.75,
      error: null,
      cohortId: FIXTURE_IDS.cohortId,
    },
  });
  expect(response.ok()).toBeTruthy();

  await expect(page.getByTestId("run-header")).toContainText("Completed");
  await expect(page.getByTestId("run-header")).toContainText("75.0%");
});

test("communication and evaluation react to controlled deltas", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);
  await page.getByTestId(`graph-node-${FIXTURE_IDS.solveTaskId}`).click();

  const messageResponse = await page.request.post("/api/test/dashboard/events/thread-message", {
    data: {
      runId: FIXTURE_IDS.runId,
      thread: createDeltaThread(),
    },
  });
  expect(messageResponse.ok()).toBeTruthy();

  const evaluationResponse = await page.request.post("/api/test/dashboard/events/task-evaluation", {
    data: {
      runId: FIXTURE_IDS.runId,
      taskId: FIXTURE_IDS.solveTaskId,
      evaluation: createUpdatedEvaluation(),
    },
  });
  expect(evaluationResponse.ok()).toBeTruthy();

  await expect(page.getByTestId("workspace-communication")).toContainText(
    "I am rewriting the final proof around that parity split now.",
  );
  await expect(page.getByTestId("workspace-evaluation")).toContainText(
    "The updated proof compiles cleanly and closes every goal",
  );
  await expect(page.getByTestId("workspace-actions")).not.toContainText(
    "I am rewriting the final proof around that parity split now.",
  );
});
