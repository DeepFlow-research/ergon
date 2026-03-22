import { expect, test } from "@playwright/test";

test.skip(process.env.PLAYWRIGHT_LIVE !== "1", "Live probe only runs against a real stack.");

test("live cohort probe shows the requested cohort on the cohort index", async ({ page }) => {
  const cohortName = process.env.LIVE_COHORT_NAME;
  test.skip(!cohortName, "Set LIVE_COHORT_NAME to target a real seeded/running cohort.");

  await page.goto("/");
  await expect(page.getByTestId("cohort-index-list")).toContainText(cohortName!);
});
