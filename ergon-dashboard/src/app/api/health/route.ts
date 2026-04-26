import { NextResponse } from "next/server";
import { config } from "@/lib/config";
import { fetchErgonApi } from "@/lib/serverApi";

/**
 * GET /api/health
 *
 * Lightweight probe that exercises the SSR import graph — the exact code path
 * that breaks when .next chunks go stale. Returns build metadata + upstream
 * Ergon API reachability so the client can surface actionable error toasts
 * instead of silent data loss.
 */
export async function GET() {
  const checks: Record<string, "ok" | "fail"> = {};
  const errors: string[] = [];

  // 1. Verify critical SSR modules are importable (catches "Cannot find module './421.js'" class of bugs)
  try {
    const rest = await import("@/lib/contracts/rest");
    const types = await import("@/lib/types");
    checks.ssr_imports =
      typeof rest.parseRunSnapshot === "function" && typeof types.TaskStatus !== "undefined"
        ? "ok"
        : "fail";
  } catch (e) {
    checks.ssr_imports = "fail";
    errors.push(`SSR import failure: ${e instanceof Error ? e.message : String(e)}`);
  }

  // 2. Verify upstream Ergon API is reachable
  try {
    const res = await fetchErgonApi("/cohorts?limit=1");
    checks.ergon_api = res.ok ? "ok" : "fail";
    if (!res.ok) errors.push(`Ergon API returned ${res.status}`);
  } catch (e) {
    checks.ergon_api = "fail";
    errors.push(`Ergon API unreachable: ${e instanceof Error ? e.message : String(e)}`);
  }

  const healthy = Object.values(checks).every((v) => v === "ok");

  return NextResponse.json(
    {
      status: healthy ? "healthy" : "degraded",
      checks,
      errors: errors.length > 0 ? errors : undefined,
      build: {
        nodeEnv: config.nodeEnv,
        timestamp: process.env.BUILD_TIMESTAMP ?? null,
        pid: process.pid,
      },
    },
    { status: healthy ? 200 : 503 },
  );
}
