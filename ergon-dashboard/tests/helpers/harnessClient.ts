import type { APIRequestContext } from "@playwright/test";
import { mkdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import type { DashboardHarnessSeedPayload } from "../../src/lib/testing/dashboardHarness";

const HARNESS_LOCK_DIR = join(tmpdir(), "ergon-dashboard-shared-harness.lock");
const HARNESS_LOCK_TIMEOUT_MS = 30_000;
const HARNESS_LOCK_RETRY_MS = 50;

function delay(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function getErrorCode(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("code" in error)) {
    return null;
  }
  return String(error.code);
}

export async function acquireHarnessLock(): Promise<() => Promise<void>> {
  const startedAt = Date.now();

  while (true) {
    try {
      await mkdir(HARNESS_LOCK_DIR);
      return async () => {
        await rm(HARNESS_LOCK_DIR, { force: true, recursive: true });
      };
    } catch (error) {
      const code = getErrorCode(error);
      if (code !== "EEXIST") {
        throw error;
      }
      if (Date.now() - startedAt > HARNESS_LOCK_TIMEOUT_MS) {
        throw new Error("Timed out waiting for dashboard harness lock");
      }
      await delay(HARNESS_LOCK_RETRY_MS);
    }
  }
}

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
