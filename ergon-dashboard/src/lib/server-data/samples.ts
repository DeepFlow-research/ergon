import { config } from "@/lib/config";
import { parseSampleSnapshot, type SampleSnapshot } from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessSample } from "@/lib/testing/dashboardHarness";

import { backendUnavailable, type ServerDataResult } from "./responses";

export interface SampleListFilters {
  limit?: number;
  offset?: number;
  status?: string;
  definitionId?: string;
  experiment?: string;
}

export interface SampleSummary {
  id: string;
  name: string;
  status: string;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  latest_activity_at: string | null;
  duration_seconds: number | null;
  definition_id: string;
  definition_name: string | null;
  experiment: string | null;
  benchmark_type: string;
  instance_key: string;
  sample_id: string | null;
  sample_label: string;
  evaluator_slug: string | null;
  model_target: string | null;
  final_score: number | null;
  return_value: number | null;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  running_tasks: number;
  cancelled_tasks: number;
  total_cost_usd: number | null;
  error_message: string | null;
  metrics: Record<string, unknown>;
}

export async function loadSampleList(
  filters: SampleListFilters = {},
): Promise<ServerDataResult<SampleSummary[]>> {
  const searchParams = new URLSearchParams();
  searchParams.set("limit", String(filters.limit ?? 100));
  if (filters.offset) searchParams.set("offset", String(filters.offset));
  if (filters.status) searchParams.set("status", filters.status);
  if (filters.definitionId) searchParams.set("definition_id", filters.definitionId);
  if (filters.experiment) searchParams.set("experiment", filters.experiment);

  try {
    const response = await fetchErgonApi(`/samples?${searchParams.toString()}`);
    const body = await response.json();
    if (response.ok) {
      return {
        ok: true,
        data: parseSampleList(body),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable("Ergon API is unavailable while loading runs.", error);
  }
}

export async function loadSampleSnapshot(sampleId: string): Promise<ServerDataResult<SampleSnapshot>> {
  if (config.enableTestHarness) {
    const run = getHarnessSample(sampleId);
    if (run !== null) {
      return { ok: true, data: parseSampleSnapshot(run), status: 200, source: "harness" };
    }
  }

  try {
    const response = await fetchErgonApi(`/samples/${sampleId}`);
    const body = await response.json();
    if (response.ok) {
      return {
        ok: true,
        data: parseSampleSnapshot(body),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable(`Ergon API is unavailable while loading run ${sampleId}.`, error);
  }
}

function parseSampleList(input: unknown): SampleSummary[] {
  if (!Array.isArray(input)) return [];
  return input.map((item) => {
    const record = typeof item === "object" && item !== null ? (item as Record<string, unknown>) : {};
    const returnValue = record.return_value ?? record.return;
    return {
      id: String(record.id ?? ""),
      name: String(record.name ?? ""),
      status: String(record.status ?? ""),
      created_at: optionalString(record.created_at),
      started_at: optionalString(record.started_at),
      completed_at: optionalString(record.completed_at),
      latest_activity_at: optionalString(record.latest_activity_at),
      duration_seconds: optionalNumber(record.duration_seconds),
      definition_id: String(record.definition_id ?? ""),
      definition_name: optionalString(record.definition_name),
      experiment: optionalString(record.experiment),
      benchmark_type: String(record.benchmark_type ?? ""),
      instance_key: String(record.instance_key ?? ""),
      sample_id: optionalString(record.sample_id),
      sample_label: String(record.sample_label ?? record.sample_id ?? record.instance_key ?? ""),
      evaluator_slug: optionalString(record.evaluator_slug),
      model_target: optionalString(record.model_target),
      final_score: optionalNumber(record.final_score),
      return_value: optionalNumber(returnValue),
      total_tasks: Number(record.total_tasks ?? 0),
      completed_tasks: Number(record.completed_tasks ?? 0),
      failed_tasks: Number(record.failed_tasks ?? 0),
      running_tasks: Number(record.running_tasks ?? 0),
      cancelled_tasks: Number(record.cancelled_tasks ?? 0),
      total_cost_usd: optionalNumber(record.total_cost_usd),
      error_message: optionalString(record.error_message),
      metrics: parseObject(record.metrics),
    };
  });
}

function optionalString(input: unknown): string | null {
  return typeof input === "string" && input.length > 0 ? input : null;
}

function optionalNumber(input: unknown): number | null {
  return typeof input === "number" && Number.isFinite(input) ? input : null;
}

function parseObject(input: unknown): Record<string, unknown> {
  return typeof input === "object" && input !== null && !Array.isArray(input)
    ? (input as Record<string, unknown>)
    : {};
}
