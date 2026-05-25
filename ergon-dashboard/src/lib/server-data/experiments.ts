import { config } from "@/lib/config";
import { parseExperimentDetail, type ExperimentDetail } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessExperiment } from "@/lib/testing/dashboardHarness";
import {
  normalizeRunMetricPoints,
  type RunMetricPoint,
} from "@/components/experiments/sampleRunMetricExplorerModel";

import { backendUnavailable, type ServerDataResult } from "./responses";

export interface ExperimentSummary {
  definition_id: string;
  name: string;
  description: string | null;
  benchmark_type: string;
  sample_count: number;
  status: string;
  default_model_target: string | null;
  default_evaluator_slug: string | null;
  created_at: string;
  run_count: number;
  status_counts: {
    pending: number;
    executing: number;
    evaluating: number;
    completed: number;
    failed: number;
    cancelled: number;
  };
  failure_count: number;
  latest_activity_at: string | null;
  average_score: number | null;
  average_duration_ms: number | null;
  average_tasks: number | null;
  total_cost_usd: number | null;
}

export interface ExperimentDetailWithRunMetrics extends ExperimentDetail {
  runMetricPoints: RunMetricPoint[];
}

export function normalizeExperimentDetail(detail: ExperimentDetail): ExperimentDetailWithRunMetrics {
  return {
    ...detail,
    runMetricPoints: normalizeRunMetricPoints(detail.runs),
  };
}

function parseExperimentList(input: unknown): ExperimentSummary[] {
  if (!Array.isArray(input)) return [];
  return input.map((item) => {
    const record = typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {};
    return {
      definition_id: String(record.definition_id ?? ""),
      name: String(record.name ?? ""),
      description: optionalString(record.description),
      benchmark_type: String(record.benchmark_type ?? ""),
      sample_count: Number(record.sample_count ?? 0),
      status: String(record.status ?? ""),
      default_model_target: optionalString(record.default_model_target),
      default_evaluator_slug: optionalString(record.default_evaluator_slug),
      created_at: String(record.created_at ?? ""),
      run_count: Number(record.run_count ?? 0),
      status_counts: parseStatusCounts(record.status_counts),
      failure_count: Number(record.failure_count ?? 0),
      latest_activity_at: optionalString(record.latest_activity_at),
      average_score: optionalNumber(record.average_score),
      average_duration_ms: optionalNumber(record.average_duration_ms),
      average_tasks: optionalNumber(record.average_tasks),
      total_cost_usd: optionalNumber(record.total_cost_usd),
    };
  });
}

function parseStatusCounts(input: unknown): ExperimentSummary["status_counts"] {
  const record = typeof input === "object" && input !== null ? (input as Record<string, unknown>) : {};
  return {
    pending: Number(record.pending ?? 0),
    executing: Number(record.executing ?? 0),
    evaluating: Number(record.evaluating ?? 0),
    completed: Number(record.completed ?? 0),
    failed: Number(record.failed ?? 0),
    cancelled: Number(record.cancelled ?? 0),
  };
}

function optionalString(input: unknown): string | null {
  return typeof input === "string" && input.length > 0 ? input : null;
}

function optionalNumber(input: unknown): number | null {
  return typeof input === "number" && Number.isFinite(input) ? input : null;
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
  definitionId: string,
): Promise<ServerDataResult<ExperimentDetailWithRunMetrics>> {
  if (config.enableTestHarness) {
    const detail = getHarnessExperiment(definitionId);
    if (detail !== null) {
      return {
        ok: true,
        data: normalizeExperimentDetail(parseExperimentDetail(detail)),
        status: 200,
        source: "harness",
      };
    }
  }

  try {
    const response = await fetchErgonApi(`/experiments/${definitionId}`);
    const body = await response.json();
    if (response.ok) {
      return {
        ok: true,
        data: normalizeExperimentDetail(parseExperimentDetail(body)),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable(`Ergon API is unavailable while loading experiment ${definitionId}.`, error);
  }
}
