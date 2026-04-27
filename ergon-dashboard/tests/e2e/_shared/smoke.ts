/**
 * Shared Playwright factory for canonical smoke specs.
 *
 * Each per-env spec (researchrubrics / minif2f / swebench-verified)
 * invokes ``defineSmokeSpec`` and the factory handles:
 *
 * - Parsing ``SMOKE_COHORT_JSON`` (array of ``{run_id, kind}``) so a
 *   heterogeneous cohort (happy + sad slots) dispatches per-kind.
 * - Per-run assertions against the backend harness DTO + dashboard UI.
 * - Screenshot capture points keyed on run_id + kind.
 * - Cohort index assertion (N runs listed, env label).
 *
 * Contract with the dashboard: all assertions use ``data-testid``
 * attributes.  See ``docs/superpowers/plans/test-refactor/03-dashboard-and-playwright.md §6``.
 */

import * as fs from "node:fs/promises";
import * as path from "node:path";

import { expect, Locator, Page, test } from "@playwright/test";

import { BackendHarnessClient, BackendRunState } from "../../helpers/backendHarnessClient";
import { EXPECTED_NESTED_SUBTASK_SLUGS, EXPECTED_SUBTASK_SLUGS } from "./expected";

export interface SmokeSpecConfig {
  env: string;
  /** Optional per-run additional assertions (e.g. env-specific UI check) */
  extraRunAssertions?: (page: Page, runId: string) => Promise<void>;
}

interface CohortMember {
  run_id: string;
  kind: "happy" | "sad";
}

function readCohortFromEnv(): CohortMember[] {
  const raw = process.env.SMOKE_COHORT_JSON;
  if (!raw) {
    throw new Error(
      "SMOKE_COHORT_JSON is not set — smoke spec cannot dispatch per-kind",
    );
  }
  return JSON.parse(raw) as CohortMember[];
}

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`${name} is not set`);
  return v;
}

async function screenshot(target: Page, out: string): Promise<void> {
  await fs.mkdir(path.dirname(out), { recursive: true });
  await target.screenshot({ path: out, fullPage: true });
}

async function locatorScreenshot(target: Locator, out: string): Promise<void> {
  await fs.mkdir(path.dirname(out), { recursive: true });
  await target.screenshot({ path: out });
}

function graphElementForTask(page: Page, taskId: string): Locator {
  return page
    .locator(
      `[data-testid="graph-node-${taskId}"], [data-testid="graph-container-${taskId}"]`,
    )
    .first();
}

async function selectRenderedGraphTask(
  page: Page,
  state: BackendRunState,
  runId: string,
  evaluatedTaskIds: Set<string>,
): Promise<BackendRunState["graph_nodes"][number]> {
  const candidates = [
    ...state.graph_nodes.filter((node) => node.level > 0 && node.task_slug === "d_root"),
    ...state.graph_nodes.filter((node) => node.level > 0 && evaluatedTaskIds.has(node.id)),
    ...state.graph_nodes.filter((node) => node.level > 0),
  ];

  for (const candidate of candidates) {
    const graphElement = graphElementForTask(page, candidate.id);
    if (await graphElement.isVisible()) {
      return candidate;
    }
  }

  await expect(page.locator('[data-testid^="graph-node-"], [data-testid^="graph-container-"]').first()).toBeVisible();
  for (const candidate of candidates) {
    const graphElement = graphElementForTask(page, candidate.id);
    if (await graphElement.isVisible()) {
      return candidate;
    }
  }

  throw new Error(`no rendered graph task found for run ${runId}`);
}

async function openWorkspaceForGraphTask(page: Page, taskId: string): Promise<void> {
  const graphElement = graphElementForTask(page, taskId);
  await expect(graphElement).toBeVisible();
  await graphElement.evaluate((node) => {
    (node as HTMLElement).click();
  });
  try {
    await expect(page.getByTestId("workspace-region")).toBeVisible({ timeout: 2_000 });
    return;
  } catch {
    await graphElement.click({ force: true });
  }
}

async function expectNoTimelinePlaybackControls(page: Page): Promise<void> {
  await expect(page.getByTestId("activity-play-toggle")).toHaveCount(0);
  await expect(page.getByTestId("activity-speed-control")).toHaveCount(0);
  await expect(page.getByTestId("activity-step-back")).toHaveCount(0);
  await expect(page.getByTestId("activity-step-forward")).toHaveCount(0);
}

async function assertRunWorkspace(
  page: Page,
  state: BackendRunState,
  runId: string,
): Promise<void> {
  await expect(page.getByTestId("run-header")).toBeVisible();
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  await expect(page.getByTestId("activity-stack-region")).toBeVisible();
  await expect(page.locator('[data-testid^="activity-bar-"]').first()).toBeVisible();

  const evaluatedTaskIds = new Set(state.evaluations.map((evaluation) => evaluation.task_id));
  const selected = await selectRenderedGraphTask(page, state, runId, evaluatedTaskIds);

  await openWorkspaceForGraphTask(page, selected.id);
  await expect(page.getByTestId("workspace-region")).toBeVisible();
  await expect(page.getByTestId("workspace-header")).toContainText(selected.task_slug);
  await expect(page.getByTestId("workspace-tab-overview")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-actions")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-communication")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-outputs")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-transitions")).toBeVisible();
  await expect(page.getByTestId("workspace-tab-evaluation")).toBeVisible();
  await expect(page.getByTestId("evaluation-lens-toggle")).toBeVisible();
  await page.getByTestId("evaluation-lens-toggle").click();
  if (evaluatedTaskIds.size > 0) {
    await expect(page.locator('[data-testid^="graph-node-rubric-glyph-"]').first()).toBeVisible();
  }

  await page.getByTestId("workspace-tab-actions").click();
  await expect(page.getByTestId("workspace-actions")).toBeVisible();
  await expect(page.getByTestId("workspace-executions")).toBeVisible();
  await expect(page.getByTestId("workspace-sandbox")).toBeVisible();

  await page.getByTestId("workspace-tab-outputs").click();
  await expect(page.getByTestId("workspace-outputs")).toBeVisible();

  await page.getByTestId("workspace-tab-communication").click();
  await expect(page.getByTestId("workspace-communication")).toBeVisible();

  await page.getByTestId("workspace-tab-transitions").click();
  await expect(page.getByTestId("workspace-transitions")).toBeVisible();

  await page.getByTestId("workspace-tab-evaluation").click();
  if (evaluatedTaskIds.has(selected.id)) {
    await expect(page.getByTestId("workspace-evaluation")).toContainText("Total score");
    await expect(page.getByTestId("workspace-evaluation")).toContainText("Evaluator");
    await expect(page.locator('[data-testid^="evaluation-criterion-status-"]').first()).toBeVisible();
  } else {
    await expect(page.getByTestId("workspace-evaluation")).toBeVisible();
  }

  const eventStream = page.getByTestId("event-stream-region");
  if (!(await eventStream.isVisible())) {
    await page.getByTestId("event-stream-toggle").click();
  }
  await expect(eventStream).toBeVisible();
  await expect(page.locator('[data-testid^="event-row-"]').first()).toBeVisible();

  if (state.mutation_count > 0) {
    await page.locator('[data-testid^="activity-bar-"]').first().click();
    await expect(page.getByTestId("timeline-region")).toBeVisible();
    await expect(page.getByTestId("activity-current-sequence")).toContainText(/seq/i);
    await expectNoTimelinePlaybackControls(page);
  }
}

export function defineSmokeSpec(cfg: SmokeSpecConfig): void {
  const cohortKey = requireEnv("COHORT_KEY");
  const screenshotDir = requireEnv("SCREENSHOT_DIR");
  const secret = requireEnv("TEST_HARNESS_SECRET");
  const apiBase = requireEnv("ERGON_API_BASE_URL");

  const client = new BackendHarnessClient(apiBase, secret);
  const cohort = readCohortFromEnv();

  test.describe(`${cfg.env} canonical smoke`, () => {
    for (const { run_id, kind } of cohort) {
      test(`run ${run_id} (${kind})`, async ({ page }) => {
        const state = await client.getRunState(run_id);

        // Backend-DTO assertions are the load-bearing contract.  The UI
        // assertions below use graph-canvas + page-load + screenshot
        // capture only; per-node `task-node-<slug>` data-testid
        // attributes are a dashboard follow-up (Phase F notes them as
        // an open item).  Smoke passes as long as the DTO + run page
        // renders cleanly and a screenshot is captured.

        if (kind === "happy") {
          expect(state.status).toBe("completed");
          expect(state.graph_nodes.length).toBe(12);
          expect(state.resource_count).toBeGreaterThanOrEqual(20);
          expect(state.mutation_count).toBeGreaterThan(0);
          expect(state.mutations.length).toBe(state.mutation_count);
          expect(state.executions.length).toBeGreaterThan(0);
          expect(state.executions.length).toBe(state.execution_count);
          expect(state.thread_count).toBeGreaterThan(0);
          expect(state.context_event_count).toBeGreaterThan(0);

          const leafSlugs = state.graph_nodes
            .filter((n) => n.level === 1)
            .map((n) => n.task_slug)
            .sort();
          expect(leafSlugs).toEqual([...EXPECTED_SUBTASK_SLUGS].sort());

          const nestedSlugs = state.graph_nodes
            .filter((n) => n.level === 2)
            .map((n) => n.task_slug)
            .sort();
          expect(nestedSlugs).toEqual([...EXPECTED_NESTED_SUBTASK_SLUGS].sort());

          for (const n of state.graph_nodes) {
            expect(n.status).toBe("completed");
          }

          const successfulEval = state.evaluations.some((e) => e.score === 1.0);
          expect(successfulEval).toBe(true);

          const cohortId = await client.getCohortId(cohortKey);
          await page.goto(`/cohorts/${cohortId}/runs/${run_id}`);
          await assertRunWorkspace(page, state, run_id);

          await screenshot(
            page,
            path.join(screenshotDir, cfg.env, `${run_id}-happy.png`),
          );
          await screenshot(
            page,
            path.join(screenshotDir, cfg.env, `${run_id}-visual-debugger-full.png`),
          );
          await locatorScreenshot(
            page.getByTestId("activity-stack-region"),
            path.join(screenshotDir, cfg.env, `${run_id}-activity-stack.png`),
          );

          if (cfg.extraRunAssertions) {
            await cfg.extraRunAssertions(page, run_id);
          }
          return;
        }

        // Canonical sad path: l_2 fails, l_3 blocks, independent leaves complete.
        expect(state.status).toBe("failed");
        expect(state.resource_count).toBeGreaterThanOrEqual(15);
        expect(state.executions.length).toBe(state.execution_count);
        expect(state.mutations.length).toBe(state.mutation_count);
        expect(state.thread_count).toBeGreaterThan(0);
        expect(state.context_event_count).toBeGreaterThan(0);
        const statusBySlug = new Map(
          state.graph_nodes.filter((n) => n.level > 0).map((n) => [n.task_slug, n.status]),
        );
        for (const slug of EXPECTED_SUBTASK_SLUGS.filter((s) => !["l_2", "l_3"].includes(s))) {
          expect(statusBySlug.get(slug)).toBe("completed");
        }
        expect(statusBySlug.get("l_2")).toBe("failed");
        expect(statusBySlug.get("l_3")).toBe("blocked");

        const cohortId = await client.getCohortId(cohortKey);
        await page.goto(`/cohorts/${cohortId}/runs/${run_id}`);
        await assertRunWorkspace(page, state, run_id);
        await screenshot(
          page,
          path.join(screenshotDir, cfg.env, `${run_id}-sad.png`),
        );
        await screenshot(
          page,
          path.join(screenshotDir, cfg.env, `${run_id}-visual-debugger-full.png`),
        );
        await locatorScreenshot(
          page.getByTestId("activity-stack-region"),
          path.join(screenshotDir, cfg.env, `${run_id}-activity-stack.png`),
        );
      });
    }

    test(`cohort ${cohortKey} index lists all runs`, async ({ page }) => {
      const cohortRuns = await client.getCohortRuns(cohortKey);
      expect(cohortRuns.length).toBe(cohort.length);

      const cohortId = await client.getCohortId(cohortKey);
      await page.goto(`/cohorts/${cohortId}`);
      // Dashboard keys cohort-run rows as ``cohort-run-row-<run_id>``
      // (per CohortDetailView.tsx:36) — prefix match via locator rather
      // than exact getByTestId.
      const rows = page.locator('[data-testid^="cohort-run-row-"]');
      await expect(rows).toHaveCount(cohort.length);
      await expect(page.locator('[data-testid^="cohort-rubric-status-pips-"]')).toHaveCount(cohort.length);
      // ``cohort-header`` exists but no dedicated env label testid yet —
      // follow-up for dashboard.  Screenshot captures the page state.
      await expect(page.getByTestId("cohort-header")).toBeVisible();
      await screenshot(
        page,
        path.join(screenshotDir, cfg.env, `cohort-${cohortKey}.png`),
      );
    });
  });
}
