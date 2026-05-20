import Link from "next/link";
import { notFound } from "next/navigation";

import { StatusBadge } from "@/components/common/StatusBadge";
import { RunMetricExplorer } from "@/components/experiments/RunMetricExplorer";
import { formatRunMetricValue, metricDescriptor } from "@/components/experiments/runMetricExplorerModel";
import { formatDurationMs } from "@/lib/formatDuration";
import { loadExperimentDetail, type ExperimentDetailWithRunMetrics } from "@/lib/server-data/experiments";

interface ExperimentPageProps {
  params: Promise<{ definitionId: string }>;
}

function formatNumber(value: number | null | undefined, fallback = "—") {
  if (value === null || value === undefined) return fallback;
  return Number.isInteger(value) ? value.toString() : value.toFixed(2);
}

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function workerTeamLabel(workerTeam: Record<string, unknown>) {
  const entries = Object.entries(workerTeam);
  if (entries.length === 0) return "—";
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(", ");
}

function runLink(runId: string) {
  return `/run/${runId}`;
}

export default async function ExperimentPage({ params }: ExperimentPageProps) {
  const { definitionId } = await params;
  let detail: ExperimentDetailWithRunMetrics | null = null;
  const result = await loadExperimentDetail(definitionId);
  if (result.ok) {
    detail = result.data;
  } else {
    if (result.status === 404) notFound();
    throw new Error(`Failed to load experiment ${definitionId}: ${result.status}`);
  }

  const experiment = detail.experiment;
  const analytics = detail.analytics;
  const sampleSelection = detail.sample_selection ?? {};
  const scoreDescriptor = metricDescriptor("score");
  const durationDescriptor = metricDescriptor("duration_ms");
  const tasksDescriptor = metricDescriptor("total_tasks");
  const costDescriptor = metricDescriptor("total_cost_usd");
  const observedCostTotal = detail.runMetricPoints.reduce((total, point) => {
    const cost = point.metrics.total_cost_usd;
    return cost.available && cost.value != null ? total + cost.value : total;
  }, 0);
  const hasObservedCosts = detail.runMetricPoints.some((point) => point.metrics.total_cost_usd.available);

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <Link
            href="/experiments"
            className="text-sm text-[var(--muted)] hover:text-[var(--ink)]"
          >
            Experiments
          </Link>
          <h1 className="mt-2 text-3xl font-semibold text-[var(--ink)]">
            {experiment.name}
          </h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {experiment.benchmark_type} · {experiment.sample_count} samples ·{" "}
            {experiment.run_count} runs · latest activity {formatDate(analytics.latest_activity_at)}
          </p>
        </div>
        <StatusBadge status={experiment.status} />
      </div>

      <section className="mb-6 grid gap-3 md:grid-cols-4">
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Model</div>
          <div className="mt-1 text-sm text-[var(--ink)]">{experiment.default_model_target ?? "—"}</div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Evaluator</div>
          <div className="mt-1 text-sm text-[var(--ink)]">{experiment.default_evaluator_slug ?? "—"}</div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Worker team</div>
          <div className="mt-1 text-sm text-[var(--ink)]">
            {workerTeamLabel(experiment.default_worker_team ?? {})}
          </div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Samples</div>
          <div className="mt-1 text-sm text-[var(--ink)]">
            {Array.isArray(sampleSelection.instance_keys)
              ? sampleSelection.instance_keys.join(", ")
              : experiment.sample_count}
          </div>
        </div>
      </section>

      <section
        className="mb-6 grid gap-3 md:grid-cols-4"
        data-testid="experiment-summary-cards"
      >
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Score</div>
          <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">
            {formatNumber(analytics.average_score)}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">average completed-run score</div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Runs</div>
          <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">
            {analytics.status_counts.completed}/{analytics.total_runs}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {analytics.status_counts.failed} failed ·{" "}
            {analytics.status_counts.executing + analytics.status_counts.evaluating} active
          </div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Runtime</div>
          <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">
            {formatDurationMs(analytics.average_duration_ms)}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {formatNumber(analytics.average_tasks)} avg tasks
          </div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Cost</div>
          <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">
            {hasObservedCosts ? formatRunMetricValue(costDescriptor, observedCostTotal) : "Unavailable"}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {hasObservedCosts ? "observed run costs only" : "no observed cost instrumentation"}
          </div>
        </div>
      </section>

      <div className="mb-6" data-testid="experiment-run-distribution">
        <RunMetricExplorer points={detail.runMetricPoints} getRunHref={runLink} />
      </div>

      <div className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-card">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-[var(--line)] bg-[var(--paper)] text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
            <tr>
              <th className="px-3 py-2">Run</th>
              <th className="px-3 py-2">Sample</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Score</th>
              <th className="px-3 py-2">Duration</th>
              <th className="px-3 py-2">Tasks</th>
              <th className="px-3 py-2">Cost</th>
              <th className="px-3 py-2">Model</th>
            </tr>
          </thead>
          <tbody>
            {detail.runMetricPoints.map((point) => (
              <tr key={point.runId} className="border-b border-[var(--line)] last:border-0 hover:bg-[var(--paper)]">
                <td className="px-3 py-2">
                  <Link
                    href={runLink(point.runId)}
                    className="font-mono text-xs text-[var(--ink)] underline-offset-2 hover:underline"
                  >
                    {point.runName}
                  </Link>
                </td>
                <td className="px-3 py-2 text-[var(--muted)]">{point.sampleLabel}</td>
                <td className="px-3 py-2 text-[var(--muted)]">
                  <StatusBadge status={point.status} size="sm" />
                  {point.errorSummary ? <div className="mt-1 max-w-56 truncate text-xs text-red-500">{point.errorSummary}</div> : null}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-[var(--ink)]">
                  {formatRunMetricValue(scoreDescriptor, point.metrics.score)}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-[var(--muted)]">
                  {formatRunMetricValue(durationDescriptor, point.metrics.duration_ms)}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-[var(--muted)]">
                  {formatRunMetricValue(tasksDescriptor, point.metrics.total_tasks)}
                </td>
                <td className="px-3 py-2 text-xs text-[var(--muted)]">
                  {formatRunMetricValue(costDescriptor, point.metrics.total_cost_usd)}
                </td>
                <td className="px-3 py-2 text-[var(--muted)]">{point.modelTarget ?? "—"}</td>
              </tr>
            ))}
            {detail.runMetricPoints.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-[var(--muted)]">
                  This experiment has not launched any runs yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </main>
  );
}
