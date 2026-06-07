import { config } from "@/lib/config";
import {
  parseExperimentListState,
  parseExperimentState,
  type ExperimentDetailView,
} from "@/lib/contracts/rest";
import { buildExperimentState, type ExperimentDashboardState } from "@/lib/sample-state/dashboard";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessExperiment } from "@/lib/testing/dashboardHarness";

import { backendUnavailable, type ServerDataResult } from "./responses";

export type ExperimentSummary = ExperimentDashboardState;

function normalizeExperimentDetail(detail: ExperimentDetailView): ExperimentDashboardState {
  return buildExperimentState(detail);
}

export async function loadExperimentList(): Promise<ServerDataResult<ExperimentSummary[]>> {
  try {
    const response = await fetchErgonApi("/experiments?limit=100");
    const body = await response.json();
    if (response.ok) {
      const parsed = parseExperimentListState(body);
      return {
        ok: true,
        data: parsed.items.map(normalizeExperimentDetail),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable("Ergon API is unavailable while loading experiments.", error);
  }
}

export async function loadExperimentDetail(
  experimentId: string,
): Promise<ServerDataResult<ExperimentDashboardState>> {
  if (config.enableTestHarness) {
    const detail = getHarnessExperiment(experimentId);
    if (detail !== null) {
      return {
        ok: true,
        data: normalizeExperimentDetail(parseExperimentState(detail)),
        status: 200,
        source: "harness",
      };
    }
  }

  try {
    const response = await fetchErgonApi(`/experiments/${experimentId}`);
    const body = await response.json();
    if (response.ok) {
      return {
        ok: true,
        data: normalizeExperimentDetail(parseExperimentState(body)),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable(`Ergon API is unavailable while loading experiment ${experimentId}.`, error);
  }
}
