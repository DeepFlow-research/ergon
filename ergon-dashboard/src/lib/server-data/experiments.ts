import { config } from "@/lib/config";
import { parseExperimentDetail, type ExperimentDetail } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessExperiment } from "@/lib/testing/dashboardHarness";

import { backendUnavailable, type ServerDataResult } from "./responses";

export interface ExperimentSummary {
  experiment_id: string;
  cohort_id: string | null;
  name: string;
  benchmark_type: string;
  sample_count: number;
  status: string;
  default_model_target: string | null;
  default_evaluator_slug: string | null;
  created_at: string;
  run_count: number;
}

function parseExperimentList(input: unknown): ExperimentSummary[] {
  if (!Array.isArray(input)) return [];
  return input.map((item) => {
    const record = typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {};
    return {
      experiment_id: String(record.experiment_id ?? ""),
      cohort_id: (record.cohort_id as string | null | undefined) ?? null,
      name: String(record.name ?? ""),
      benchmark_type: String(record.benchmark_type ?? ""),
      sample_count: Number(record.sample_count ?? 0),
      status: String(record.status ?? ""),
      default_model_target: (record.default_model_target as string | null | undefined) ?? null,
      default_evaluator_slug: (record.default_evaluator_slug as string | null | undefined) ?? null,
      created_at: String(record.created_at ?? ""),
      run_count: Number(record.run_count ?? 0),
    };
  });
}

export async function loadExperimentList(): Promise<ServerDataResult<ExperimentSummary[]>> {
  try {
    const response = await fetchErgonApi("/experiments?limit=100");
    const body = await response.json();
    if (response.ok) {
      return {
        ok: true,
        data: parseExperimentList(body),
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
): Promise<ServerDataResult<ExperimentDetail>> {
  if (config.enableTestHarness) {
    const detail = getHarnessExperiment(experimentId);
    if (detail !== null) {
      return {
        ok: true,
        data: parseExperimentDetail(detail),
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
        data: parseExperimentDetail(body),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable(`Ergon API is unavailable while loading experiment ${experimentId}.`, error);
  }
}
