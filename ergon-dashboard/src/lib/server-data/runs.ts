import { config } from "@/lib/config";
import { parseRunSnapshot, type RunSnapshot } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessRun } from "@/lib/testing/dashboardHarness";

import { backendUnavailable, type ServerDataResult } from "./responses";

export async function loadRunSnapshot(runId: string): Promise<ServerDataResult<RunSnapshot>> {
  if (config.enableTestHarness) {
    const run = getHarnessRun(runId);
    if (run !== null) {
      return { ok: true, data: parseRunSnapshot(run), status: 200, source: "harness" };
    }
  }

  try {
    const response = await fetchErgonApi(`/runs/${runId}`);
    const body = await response.json();
    if (response.ok) {
      return {
        ok: true,
        data: parseRunSnapshot(body),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable(`Ergon API is unavailable while loading run ${runId}.`, error);
  }
}
