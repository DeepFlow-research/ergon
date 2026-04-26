import { test, expect } from "@playwright/test";

/**
 * E2E tests for the /api/health endpoint.
 *
 * Validates that:
 * - The health endpoint is reachable and returns structured JSON
 * - SSR imports are exercised (catches stale .next cache)
 * - The response shape matches the expected schema
 */

const BASE = process.env.BASE_URL ?? "http://localhost:3001";

test.describe("Health endpoint", () => {
  test("returns 200 with healthy status when build is fresh", async ({ request }) => {
    const res = await request.get(`${BASE}/api/health`);
    expect(res.status()).toBe(200);

    const body = await res.json();
    expect(body.status).toBe("healthy");
    expect(body.checks).toHaveProperty("ssr_imports", "ok");
    expect(body.checks).toHaveProperty("ergon_api");
    expect(body.build).toHaveProperty("nodeEnv");
    expect(body.build).toHaveProperty("pid");
    expect(typeof body.build.pid).toBe("number");
  });

  test("response schema includes all expected fields", async ({ request }) => {
    const res = await request.get(`${BASE}/api/health`);
    const body = await res.json();

    expect(body).toHaveProperty("status");
    expect(body).toHaveProperty("checks");
    expect(body).toHaveProperty("build");
    expect(["healthy", "degraded"]).toContain(body.status);

    for (const value of Object.values(body.checks)) {
      expect(["ok", "fail"]).toContain(value);
    }
  });

  test("SSR import check exercises the actual module graph", async ({ request }) => {
    const res = await request.get(`${BASE}/api/health`);
    const body = await res.json();

    expect(body.checks.ssr_imports).toBe("ok");
    if (body.checks.ssr_imports === "fail") {
      expect(body.errors).toBeDefined();
      expect(body.errors.length).toBeGreaterThan(0);
      expect(body.errors[0]).toContain("SSR import");
    }
  });
});

test.describe("Build health toast (UI)", () => {
  test("toast is hidden when build is healthy", async ({ page }) => {
    await page.goto(`${BASE}/`);
    await page.waitForLoadState("networkidle");

    const toast = page.locator('[data-testid="build-health-toast"]');
    await expect(toast).not.toBeVisible();
  });
});
