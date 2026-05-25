import type { ExperimentRunRow, RunLifecycleStatus } from "@/lib/contracts/rest";
import { formatDurationMs } from "@/lib/formatDuration";

export type RunMetricKey =
  | "score"
  | "duration_ms"
  | "total_tasks"
  | "tool_call_count"
  | "total_tokens"
  | "total_cost_usd";

export type RunMetricUnit = "score" | "duration" | "count" | "tokens" | "usd";

export interface RunMetricDescriptor {
  key: RunMetricKey;
  label: string;
  unit: RunMetricUnit;
  unavailableLabel?: string;
}

export interface RunMetricValue {
  value: number | null;
  available: boolean;
  unavailableReason?: string;
}

export interface RunMetricPoint {
  sampleId: string;
  runName: string;
  status: RunLifecycleStatus | string;
  sampleLabel: string;
  instanceKey: string;
  modelTarget: string | null;
  evaluatorSlug: string | null;
  errorSummary: string | null;
  startedAt: string | null;
  completedAt: string | null;
  metrics: Record<RunMetricKey, RunMetricValue>;
  tokenBreakdown: Record<string, number> | null;
}

export type SampleRunMetricExplorerMode = "1d" | "2d";
export type SampleRunMetricExplorerView =
  | "empty"
  | "ranked-list"
  | "strip"
  | "histogram"
  | "scatter"
  | "too-few-points";

export const RUN_METRIC_DESCRIPTORS: RunMetricDescriptor[] = [
  { key: "score", label: "Score", unit: "score" },
  { key: "duration_ms", label: "Duration", unit: "duration" },
  { key: "total_tasks", label: "Tasks", unit: "count" },
  { key: "tool_call_count", label: "Tool calls", unit: "count" },
  { key: "total_tokens", label: "Tokens", unit: "tokens", unavailableLabel: "Token usage not instrumented" },
  { key: "total_cost_usd", label: "Cost", unit: "usd", unavailableLabel: "Observed cost unavailable" },
];

const metricDescriptorByKey = new Map(RUN_METRIC_DESCRIPTORS.map((descriptor) => [descriptor.key, descriptor]));

export function formatRunMetricValue(
  descriptor: RunMetricDescriptor,
  value: RunMetricValue | number | null | undefined,
): string {
  const metricValue: RunMetricValue =
    typeof value === "number" || value == null
      ? { value: value ?? null, available: value != null }
      : value;
  if (!metricValue.available || metricValue.value == null || Number.isNaN(metricValue.value)) {
    return descriptor.unavailableLabel ?? metricValue.unavailableReason ?? "Unavailable";
  }

  switch (descriptor.unit) {
    case "duration":
      return formatDurationMs(metricValue.value);
    case "usd":
      return `$${metricValue.value.toFixed(metricValue.value < 1 ? 4 : 2)}`;
    case "score":
      return Number.isInteger(metricValue.value) ? metricValue.value.toString() : metricValue.value.toFixed(2);
    case "tokens":
    case "count":
      return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(metricValue.value);
  }
}

export function metricDescriptor(key: RunMetricKey): RunMetricDescriptor {
  const descriptor = metricDescriptorByKey.get(key);
  if (!descriptor) throw new Error(`Unknown metric descriptor: ${key}`);
  return descriptor;
}

export function availableMetricPoints(
  points: RunMetricPoint[],
  primaryMetricKey: RunMetricKey,
  secondaryMetricKey?: RunMetricKey,
): RunMetricPoint[] {
  return points.filter((point) => {
    const primary = point.metrics[primaryMetricKey];
    const secondary = secondaryMetricKey ? point.metrics[secondaryMetricKey] : undefined;
    return (
      primary?.available === true &&
      primary.value != null &&
      Number.isFinite(primary.value) &&
      (!secondaryMetricKey || (secondary?.available === true && secondary.value != null && Number.isFinite(secondary.value)))
    );
  });
}

export function selectSampleRunMetricExplorerView(
  mode: SampleRunMetricExplorerMode,
  points: RunMetricPoint[],
  primaryMetricKey: RunMetricKey,
  secondaryMetricKey?: RunMetricKey,
): SampleRunMetricExplorerView {
  const comparableCount = availableMetricPoints(points, primaryMetricKey, mode === "2d" ? secondaryMetricKey : undefined).length;
  if (comparableCount === 0) return "empty";
  if (mode === "2d") return comparableCount >= 3 ? "scatter" : "too-few-points";
  if (comparableCount < 5) return "ranked-list";
  if (comparableCount < 20) return "strip";
  return "histogram";
}

export function percentile(values: number[], percentileValue: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * percentileValue;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sorted[lower] ?? null;
  const weight = index - lower;
  return (sorted[lower] ?? 0) * (1 - weight) + (sorted[upper] ?? 0) * weight;
}

function knownNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function metricValue(value: number | null, unavailableReason = "Metric unavailable"): RunMetricValue {
  return value == null ? { value: null, available: false, unavailableReason } : { value, available: true };
}

function observedMetricValue(value: number | null, observed: boolean, unavailableReason: string): RunMetricValue {
  return observed && value != null ? { value, available: true } : { value: null, available: false, unavailableReason };
}

export function normalizeRunMetricPoint(run: ExperimentRunRow): RunMetricPoint {
  const metrics = run.metrics;
  const costValue = knownNumber(metrics.total_cost_usd ?? run.total_cost_usd);
  const tokensValue = knownNumber(metrics.total_tokens);
  const tokenBreakdown = metrics.token_breakdown ?? null;

  return {
    sampleId: run.sample_id,
    runName: metrics.run_name ?? run.sample_id.slice(0, 8),
    status: run.status,
    sampleLabel: metrics.sample_label ?? run.instance_key,
    instanceKey: run.instance_key,
    modelTarget: metrics.model_target ?? run.model_target,
    evaluatorSlug: metrics.evaluator_slug ?? run.evaluator_slug,
    errorSummary: metrics.error_summary ?? run.error_message,
    startedAt: run.started_at,
    completedAt: run.completed_at,
    tokenBreakdown,
    metrics: {
      score: metricValue(knownNumber(metrics.score ?? metrics.return_value ?? run.final_score)),
      duration_ms: metricValue(knownNumber(metrics.duration_ms ?? run.running_time_ms)),
      total_tasks: metricValue(knownNumber(metrics.total_tasks ?? run.total_tasks)),
      tool_call_count: metricValue(knownNumber(metrics.tool_call_count), "Tool call events not available"),
      total_tokens: observedMetricValue(tokensValue, tokensValue != null && metrics.tokens_observed !== false, "Token usage not instrumented"),
      total_cost_usd: observedMetricValue(costValue, metrics.cost_observed === true, "Observed cost unavailable"),
    },
  };
}

export function normalizeRunMetricPoints(runs: ExperimentRunRow[]): RunMetricPoint[] {
  return runs.map(normalizeRunMetricPoint);
}
