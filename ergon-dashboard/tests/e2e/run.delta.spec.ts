import { expect, test } from "@playwright/test";

import {
  createDashboardSeed,
  createDeltaContextEvent,
  createDeltaThread,
  createEmptyCriteriaEvaluation,
  createUpdatedEvaluation,
  FIXTURE_IDS,
} from "../helpers/dashboardFixtures";
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

  await page.getByTestId("workspace-tab-communication").click();
  await expect(page.getByTestId("workspace-communication")).toContainText(
    "I am rewriting the final proof around that parity split now.",
  );
  await page.getByTestId("workspace-tab-evaluation").click();
  await expect(page.getByTestId("workspace-evaluation")).toContainText(
    "The updated proof compiles cleanly and closes every goal",
  );
  await page.getByTestId("workspace-tab-actions").click();
  await expect(page.getByTestId("workspace-actions")).not.toContainText(
    "I am rewriting the final proof around that parity split now.",
  );
});

test("workspace actions react to controlled context event deltas", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);
  await page.getByTestId(`graph-node-${FIXTURE_IDS.solveTaskId}`).click();

  await page.getByTestId("workspace-tab-actions").click();
  await expect(page.getByTestId("workspace-actions")).toContainText("lean_check");
  const response = await page.request.post("/api/test/dashboard/events/context-event", {
    data: {
      runId: FIXTURE_IDS.runId,
      taskNodeId: FIXTURE_IDS.solveTaskId,
      event: createDeltaContextEvent(),
    },
  });
  expect(response.ok()).toBeTruthy();

  await expect(page.getByTestId("workspace-actions")).toContainText("lake_build");
});

test("evaluation tab shows a clear empty criteria state", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);
  await page.getByTestId(`graph-node-${FIXTURE_IDS.solveTaskId}`).click();

  const response = await page.request.post("/api/test/dashboard/events/task-evaluation", {
    data: {
      runId: FIXTURE_IDS.runId,
      taskId: FIXTURE_IDS.solveTaskId,
      evaluation: createEmptyCriteriaEvaluation(),
    },
  });
  expect(response.ok()).toBeTruthy();

  await page.getByTestId("workspace-tab-evaluation").click();
  await expect(page.getByTestId("evaluation-criteria-empty")).toContainText(
    "No evaluation criteria recorded yet",
  );
  await expect(page.getByTestId("evaluation-criteria-empty")).toContainText(
    "This task has no criterionResults in the persisted evaluation payload.",
  );
});
