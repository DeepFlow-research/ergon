import type { APIRequestContext } from "@playwright/test";

import type { DashboardHarnessSeedPayload } from "../../src/lib/testing/dashboardHarness";

export async function resetHarness(request: APIRequestContext) {
  const response = await request.post("/api/test/dashboard/reset");
  if (!response.ok()) {
    throw new Error(`Failed to reset dashboard harness: ${response.status()}`);
  }
}

export async function seedHarness(
  request: APIRequestContext,
  payload: DashboardHarnessSeedPayload,
) {
  const response = await request.post("/api/test/dashboard/seed", {
    data: payload,
  });
  if (!response.ok()) {
    throw new Error(`Failed to seed dashboard harness: ${response.status()}`);
  }
}
