import { expect, test } from "@playwright/test";

import {
  CONCURRENT_MAS_FIXTURE_IDS,
  createDashboardSeed,
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

async function expectNoTimelinePlaybackControls(page: import("@playwright/test").Page) {
  await expect(page.getByTestId("mode-live")).toHaveCount(0);
  await expect(page.getByTestId("mode-timeline")).toHaveCount(0);
  await expect(page.getByTestId("activity-play-toggle")).toHaveCount(0);
  await expect(page.getByTestId("activity-speed-control")).toHaveCount(0);
  await expect(page.getByTestId("activity-step-back")).toHaveCount(0);
  await expect(page.getByTestId("activity-step-forward")).toHaveCount(0);
}

test("run page keeps cohort breadcrumb context", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);

  await expect(page.getByTestId("run-breadcrumb-cohort")).toContainText(
    "minif2f-react-worker-gpt5v3",
  );
  await expect(page.getByTestId("run-header")).toContainText("parallel");
});

test("run workspace does not expose manual live or timeline mode controls", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);

  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await expectNoTimelinePlaybackControls(page);
});

test("run workspace shows rerun as unavailable until backend support exists", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);

  const rerunButton = page.getByTestId("rerun-button");
  await expect(rerunButton).toBeVisible();
  await expect(rerunButton).toBeDisabled();
  await expect(rerunButton).toHaveAttribute("title", /not wired/i);
});

test("snapshot selection does not expose playback or speed controls", async ({ page }) => {
  await page.goto(
    `/cohorts/${CONCURRENT_MAS_FIXTURE_IDS.cohortId}/runs/${CONCURRENT_MAS_FIXTURE_IDS.runId}`,
  );

  await expect(page.getByTestId("activity-stack-region")).toBeVisible();
  const activity = page.locator('[data-activity-id^="graph:"]').first();
  await expect(activity).toBeVisible();
  await activity.click();

  await expect(page.getByTestId("activity-current-sequence")).toContainText("replay");
  await expectNoTimelinePlaybackControls(page);
});

test("activity marker locks graph and header to snapshot until Escape returns to live", async ({
  page,
}) => {
  await page.goto(
    `/cohorts/${CONCURRENT_MAS_FIXTURE_IDS.cohortId}/runs/${CONCURRENT_MAS_FIXTURE_IDS.runId}`,
  );

  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  const validateCitationsNode = page.getByTestId(
    "graph-node-10000000-0000-4000-8000-000000000006",
  );
  await expect(validateCitationsNode).toHaveAttribute("data-task-status", "completed");

  const snapshotMarker = page.getByTestId(
    "activity-bar-graph-70000000-0000-4000-8000-000000000014",
  );
  await expect(snapshotMarker).toBeVisible();
  await snapshotMarker.click();

  await expect(page.getByTestId("snapshot-lock-label")).toBeVisible();
  await expect(page.getByTestId("snapshot-pin").first()).toBeVisible();
  await expect(page.getByTestId("run-header")).toContainText("snapshot · seq 14");
  await expect(validateCitationsNode).toHaveAttribute("data-task-status", "pending");

  await page.keyboard.press("Escape");
  await expect(page.getByTestId("run-header")).toContainText(/live/i);
  await expect(page.getByTestId("snapshot-lock-label")).toHaveCount(0);
  await expect(validateCitationsNode).toHaveAttribute("data-task-status", "completed");
});

test("graph selection opens workspace evidence sections", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);

  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await expect(page.getByTestId("workspace-launcher")).toBeVisible();
  await page.getByTestId(`graph-node-${FIXTURE_IDS.solveTaskId}`).click();

  await expect(page.getByTestId("workspace-header")).toContainText("Write proof");
  await expect(page.getByTestId("workspace-close")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-overview")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-actions")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-communication")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-outputs")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-transitions")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-evaluation")).toBeVisible();
  await expect(page.getByTestId("workspace-overview")).toBeVisible();
  await expect(page.getByTestId("workspace-actions")).toHaveCount(0);

  const overviewTab = page.getByTestId("workspace-tab-overview");
  const actionsTab = page.getByTestId("workspace-tab-actions");
  await expect(overviewTab).toHaveAttribute("id", "workspace-tab-button-overview");
  await expect(overviewTab).toHaveAttribute("aria-controls", "workspace-tab-panel-overview");
  await expect(overviewTab).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#workspace-tab-panel-overview")).toHaveAttribute("role", "tabpanel");
  await expect(page.locator("#workspace-tab-panel-overview")).toHaveAttribute(
    "aria-labelledby",
    "workspace-tab-button-overview",
  );
  await expect(page.locator("#workspace-tab-panel-overview")).toHaveAttribute("tabindex", "0");

  await overviewTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(actionsTab).toBeFocused();
  await expect(actionsTab).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("#workspace-tab-panel-actions")).toHaveAttribute("role", "tabpanel");

  await page.getByTestId("workspace-tab-actions").click();
  await expect(page.getByTestId("workspace-actions")).toContainText("lean_check");
  await expect(page.getByTestId("workspace-action-card").first()).toBeVisible();
  await expect(page.getByTestId("workspace-action-summary").first()).toContainText("Tool call");
  await expect(page.getByTestId("workspace-action-payload").first()).toContainText("Arguments");
  await expect(page.getByTestId("workspace-executions")).toContainText("Attempt 1");
  await expect(page.getByTestId("workspace-sandbox")).toContainText("lake env lean proof.lean");

  await page.getByTestId("workspace-tab-communication").click();
  await expect(page.getByTestId("communication-thread-list")).toBeVisible();
  await expect(page.getByTestId("communication-thread-card").first()).toContainText("task_clarification");
  await expect(page.getByTestId("communication-chat-trace")).toBeVisible();
  await expect(page.getByTestId("communication-chat-message").first()).toBeVisible();
  const communicationLayout = await page.evaluate(() => {
    const list = document.querySelector('[data-testid="communication-thread-list"]');
    const chat = document.querySelector('[data-testid="communication-chat-trace"]');
    if (!list || !chat) return null;
    const listBox = list.getBoundingClientRect();
    const chatBox = chat.getBoundingClientRect();
    return { listBottom: listBox.bottom, chatTop: chatBox.top };
  });
  expect(communicationLayout).not.toBeNull();
  expect(communicationLayout!.chatTop).toBeGreaterThanOrEqual(communicationLayout!.listBottom);
  await expect
    .poll(async () =>
      page.getByTestId("workspace-communication").evaluate((element) => ({
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
      })),
    )
    .toEqual(expect.objectContaining({ scrollWidth: expect.any(Number) }));
  const communicationOverflow = await page
    .getByTestId("workspace-communication")
    .evaluate((element) => element.scrollWidth - element.clientWidth);
  expect(communicationOverflow).toBeLessThanOrEqual(1);
  await expect(page.getByTestId("workspace-communication")).toContainText(
    "Can I use the standard divisibility lemma here?",
  );

  await page.getByTestId("workspace-tab-evaluation").click();
  await expect(page.getByTestId("workspace-evaluation")).toBeVisible();
  await expect(page.getByTestId("workspace-evaluation")).toContainText(
    "Proof compiles and closes all goals",
  );

  await page.getByTestId("workspace-tab-outputs").click();
  await expect(page.getByTestId("workspace-outputs")).toContainText("proof.lean");
});

test("persisted run snapshot remains inspectable after refresh", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);
  await page.reload();

  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await page.getByTestId(`graph-node-${FIXTURE_IDS.solveTaskId}`).click();

  await expect(page.getByTestId("workspace-header")).toContainText("Write proof");
  await page.getByTestId("workspace-tab-outputs").click();
  await expect(page.getByTestId("workspace-outputs")).toContainText("proof.lean");
  await page.getByTestId("workspace-tab-actions").click();
  await expect(page.getByTestId("workspace-executions")).toContainText("Attempt 1");
});

test("run debugger panels can be resized and persist across reloads", async ({ page }) => {
  await page.goto(`/cohorts/${FIXTURE_IDS.cohortId}/runs/${FIXTURE_IDS.runId}`);

  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await expect(page.getByTestId("timeline-region")).toBeVisible();

  // ``toBeVisible`` can pass before react-resizable-panels has laid out
  // non-zero geometry; ``boundingBox()`` then returns null and the drag
  // math fails. Wait for real layout (CI Chromium can be slower than local).
  await expect
    .poll(async () => {
      const region = await page.getByTestId("timeline-region").boundingBox();
      const handle = await page.getByTestId("timeline-resize-handle").boundingBox();
      if (region == null || handle == null) return 0;
      return Math.min(region.height, handle.height);
    })
    .toBeGreaterThan(4);

  const timelineBefore = await page.getByTestId("timeline-region").boundingBox();
  const timelineHandle = page.getByTestId("timeline-resize-handle");
  const timelineHandleBox = await timelineHandle.boundingBox();
  expect(timelineBefore).not.toBeNull();
  expect(timelineHandleBox).not.toBeNull();

  await page.mouse.move(timelineHandleBox!.x + timelineHandleBox!.width / 2, timelineHandleBox!.y + 2);
  await page.mouse.down();
  await page.mouse.move(timelineHandleBox!.x + timelineHandleBox!.width / 2, timelineHandleBox!.y - 90);
  await page.mouse.up();

  await expect
    .poll(async () => (await page.getByTestId("timeline-region").boundingBox())?.height ?? 0)
    .toBeGreaterThan(timelineBefore!.height + 40);
  const savedVerticalLayout = await page.evaluate(() =>
    window.localStorage.getItem("ergon-run-debugger-vertical-layout:v1"),
  );
  expect(savedVerticalLayout).not.toBeNull();
  expect(JSON.parse(savedVerticalLayout!).timeline).toBeGreaterThan(38);

  await page.getByTestId(`graph-node-${FIXTURE_IDS.solveTaskId}`).click();
  await expect(page.getByTestId("workspace-region")).toBeVisible();

  await expect
    .poll(async () => {
      const region = await page.getByTestId("workspace-region").boundingBox();
      const handle = await page.getByTestId("workspace-resize-handle").boundingBox();
      if (region == null || handle == null) return 0;
      return Math.min(region.width, handle.width);
    })
    .toBeGreaterThan(4);

  const workspaceBefore = await page.getByTestId("workspace-region").boundingBox();
  const workspaceHandle = page.getByTestId("workspace-resize-handle");
  const workspaceHandleBox = await workspaceHandle.boundingBox();
  expect(workspaceBefore).not.toBeNull();
  expect(workspaceHandleBox).not.toBeNull();

  await page.mouse.move(workspaceHandleBox!.x + 2, workspaceHandleBox!.y + workspaceHandleBox!.height / 2);
  await page.mouse.down();
  await page.mouse.move(workspaceHandleBox!.x - 90, workspaceHandleBox!.y + workspaceHandleBox!.height / 2);
  await page.mouse.up();

  await expect
    .poll(async () => (await page.getByTestId("workspace-region").boundingBox())?.width ?? 0)
    .toBeGreaterThan(workspaceBefore!.width + 40);

  const timelineAfterDrag = await page.getByTestId("timeline-region").boundingBox();
  const workspaceAfterDrag = await page.getByTestId("workspace-region").boundingBox();
  expect(timelineAfterDrag).not.toBeNull();
  expect(workspaceAfterDrag).not.toBeNull();

  await page.reload();
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await page.getByTestId(`graph-node-${FIXTURE_IDS.solveTaskId}`).click();
  await expect(page.getByTestId("workspace-region")).toBeVisible();

  await expect
    .poll(async () => (await page.getByTestId("timeline-region").boundingBox())?.height ?? 0)
    .toBeGreaterThan(timelineBefore!.height + 40);
  await expect
    .poll(async () => (await page.getByTestId("workspace-region").boundingBox())?.width ?? 0)
    .toBeGreaterThan(workspaceBefore!.width + 40);
});
