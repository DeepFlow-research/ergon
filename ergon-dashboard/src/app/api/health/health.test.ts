import assert from "node:assert/strict";
import { describe, it } from "node:test";

/**
 * Unit tests for the /api/health endpoint logic.
 *
 * These tests verify that:
 * 1. The health check returns "healthy" when all imports and API are OK
 * 2. SSR import failures are surfaced as "degraded" with actionable messages
 * 3. Ergon API failures are surfaced as "degraded"
 * 4. Both failing at once reports both errors
 */

// Extracted health-check logic (mirrors what route.ts does, testable without Next.js runtime)
interface HealthResult {
  status: "healthy" | "degraded";
  checks: Record<string, "ok" | "fail">;
  errors: string[];
}

async function runHealthChecks(deps: {
  importSSRModules: () => Promise<{ parseRunSnapshot: unknown; TaskStatus: unknown }>;
  fetchErgonApi: (path: string) => Promise<{ ok: boolean; status: number }>;
}): Promise<HealthResult> {
  const checks: Record<string, "ok" | "fail"> = {};
  const errors: string[] = [];

  try {
    const { parseRunSnapshot, TaskStatus } = await deps.importSSRModules();
    checks.ssr_imports =
      typeof parseRunSnapshot === "function" && typeof TaskStatus !== "undefined"
        ? "ok"
        : "fail";
  } catch (e) {
    checks.ssr_imports = "fail";
    errors.push(`SSR import failure: ${e instanceof Error ? e.message : String(e)}`);
  }

  try {
    const res = await deps.fetchErgonApi("/cohorts?limit=1");
    checks.ergon_api = res.ok ? "ok" : "fail";
    if (!res.ok) errors.push(`Ergon API returned ${res.status}`);
  } catch (e) {
    checks.ergon_api = "fail";
    errors.push(`Ergon API unreachable: ${e instanceof Error ? e.message : String(e)}`);
  }

  const healthy = Object.values(checks).every((v) => v === "ok");
  return { status: healthy ? "healthy" : "degraded", checks, errors };
}

describe("Health check logic", () => {
  const okImport = async () => ({
    parseRunSnapshot: () => {},
    TaskStatus: { COMPLETED: "completed" },
  });

  const okApi = async () => ({ ok: true, status: 200 });

  it("returns healthy when imports and API both succeed", async () => {
    const result = await runHealthChecks({
      importSSRModules: okImport,
      fetchErgonApi: okApi,
    });

    assert.equal(result.status, "healthy");
    assert.equal(result.checks.ssr_imports, "ok");
    assert.equal(result.checks.ergon_api, "ok");
    assert.equal(result.errors.length, 0);
  });

  it("returns degraded with SSR error when imports fail (stale build)", async () => {
    const result = await runHealthChecks({
      importSSRModules: async () => {
        throw new Error("Cannot find module './421.js'");
      },
      fetchErgonApi: okApi,
    });

    assert.equal(result.status, "degraded");
    assert.equal(result.checks.ssr_imports, "fail");
    assert.equal(result.checks.ergon_api, "ok");
    assert.equal(result.errors.length, 1);
    assert.match(result.errors[0], /Cannot find module/);
    assert.match(result.errors[0], /SSR import failure/);
  });

  it("returns degraded when Ergon API is unreachable", async () => {
    const result = await runHealthChecks({
      importSSRModules: okImport,
      fetchErgonApi: async () => {
        throw new Error("fetch failed: ECONNREFUSED");
      },
    });

    assert.equal(result.status, "degraded");
    assert.equal(result.checks.ssr_imports, "ok");
    assert.equal(result.checks.ergon_api, "fail");
    assert.equal(result.errors.length, 1);
    assert.match(result.errors[0], /Ergon API unreachable/);
  });

  it("returns degraded when Ergon API returns non-200", async () => {
    const result = await runHealthChecks({
      importSSRModules: okImport,
      fetchErgonApi: async () => ({ ok: false, status: 503 }),
    });

    assert.equal(result.status, "degraded");
    assert.equal(result.checks.ergon_api, "fail");
    assert.match(result.errors[0], /Ergon API returned 503/);
  });

  it("reports both errors when both SSR and API fail", async () => {
    const result = await runHealthChecks({
      importSSRModules: async () => {
        throw new Error("Cannot find module './999.js'");
      },
      fetchErgonApi: async () => {
        throw new Error("ECONNREFUSED");
      },
    });

    assert.equal(result.status, "degraded");
    assert.equal(result.checks.ssr_imports, "fail");
    assert.equal(result.checks.ergon_api, "fail");
    assert.equal(result.errors.length, 2);
  });

  it("returns fail for ssr_imports when parseRunSnapshot is not a function", async () => {
    const result = await runHealthChecks({
      importSSRModules: async () => ({
        parseRunSnapshot: "not-a-function",
        TaskStatus: { COMPLETED: "completed" },
      }),
      fetchErgonApi: okApi,
    });

    assert.equal(result.status, "degraded");
    assert.equal(result.checks.ssr_imports, "fail");
  });
});

describe("SSR error classification", () => {
  function classifySSRError(msg: string): string {
    if (msg.includes("Cannot find module")) {
      return "Stale build — the .next cache is corrupted. Restart the dev server (rm -rf .next && docker compose restart dashboard).";
    }
    return `Server-side data fetch failed: ${msg}`;
  }

  it("classifies 'Cannot find module' as stale build", () => {
    const result = classifySSRError("Cannot find module './421.js'");
    assert.match(result, /Stale build/);
    assert.match(result, /rm -rf .next/);
  });

  it("classifies other errors as generic fetch failure", () => {
    const result = classifySSRError("ECONNREFUSED 127.0.0.1:9000");
    assert.match(result, /Server-side data fetch failed/);
    assert.match(result, /ECONNREFUSED/);
  });

  it("classifies timeout as generic fetch failure", () => {
    const result = classifySSRError("The operation was aborted due to timeout");
    assert.match(result, /Server-side data fetch failed/);
    assert.match(result, /timeout/);
  });
});
