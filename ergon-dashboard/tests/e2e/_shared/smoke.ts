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

import { expect, Page, test } from "@playwright/test";

import { BackendHarnessClient } from "../../helpers/backendHarnessClient";
import { EXPECTED_SUBTASK_SLUGS } from "./expected";

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
          expect(state.graph_nodes.length).toBe(10);

          const leafSlugs = state.graph_nodes
            .filter((n) => n.level > 0)
            .map((n) => n.task_slug)
            .sort();
          expect(leafSlugs).toEqual([...EXPECTED_SUBTASK_SLUGS].sort());

          for (const n of state.graph_nodes) {
            expect(n.status).toBe("completed");
          }

          const successfulEval = state.evaluations.some((e) => e.score === 1.0);
          expect(successfulEval).toBe(true);

          await page.goto(`/run/${run_id}`);
          // Graph canvas is the dashboard contract we rely on today.
          await expect(page.getByTestId("graph-canvas")).toBeVisible();

          await screenshot(
            page,
            path.join(screenshotDir, cfg.env, `${run_id}-happy.png`),
          );

          if (cfg.extraRunAssertions) {
            await cfg.extraRunAssertions(page, run_id);
          }
          return;
        }

        // sad-path run assertions (researchrubrics-only today)
        expect(state.status).toBe("failed");
        const statusBySlug = new Map(
          state.graph_nodes.filter((n) => n.level > 0).map((n) => [n.task_slug, n.status]),
        );
        expect(statusBySlug.get("l_1")).toBe("completed");
        expect(statusBySlug.get("l_2")).toBe("failed");
        expect(["blocked", "cancelled"]).toContain(statusBySlug.get("l_3") ?? "");
        for (const slug of ["d_root", "d_left", "d_right", "d_join", "s_a", "s_b"]) {
          expect(statusBySlug.get(slug)).toBe("completed");
        }

        await page.goto(`/run/${run_id}`);
        await expect(page.getByTestId("graph-canvas")).toBeVisible();
        await screenshot(
          page,
          path.join(screenshotDir, cfg.env, `${run_id}-sad.png`),
        );
      });
    }

    test(`cohort ${cohortKey} index lists all runs`, async ({ page }) => {
      const cohortRuns = await client.getCohortRuns(cohortKey);
      expect(cohortRuns.length).toBe(cohort.length);

      await page.goto(`/cohort/${encodeURIComponent(cohortKey)}`);
      // Dashboard keys cohort-run rows as ``cohort-run-row-<run_id>``
      // (per CohortDetailView.tsx:36) — prefix match via locator rather
      // than exact getByTestId.
      const rows = page.locator('[data-testid^="cohort-run-row-"]');
      await expect(rows).toHaveCount(cohort.length);
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
