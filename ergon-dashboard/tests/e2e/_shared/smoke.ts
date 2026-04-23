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
          await expect(page.getByTestId("run-status")).toHaveText(/completed/i);
          for (const slug of EXPECTED_SUBTASK_SLUGS) {
            await expect(page.getByTestId(`task-node-${slug}`)).toBeVisible();
            await expect(
              page.getByTestId(`task-node-${slug}`),
            ).toHaveAttribute("data-status", "completed");
          }
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
        await expect(page.getByTestId("run-status")).toHaveText(/failed/i);
        await expect(page.getByTestId("task-node-l_2"))
          .toHaveAttribute("data-status", "failed");
        await expect(page.getByTestId("task-node-l_3"))
          .toHaveAttribute("data-status", /blocked|cancelled/);
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
      await expect(page.getByTestId("cohort-run-row")).toHaveCount(cohort.length);
      await expect(page.getByTestId("cohort-env-label")).toHaveText(
        new RegExp(cfg.env, "i"),
      );
      await screenshot(
        page,
        path.join(screenshotDir, cfg.env, `cohort-${cohortKey}.png`),
      );
    });
  });
}
