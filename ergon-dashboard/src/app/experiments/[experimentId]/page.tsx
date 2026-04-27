import Link from "next/link";
import { notFound } from "next/navigation";

import { config } from "@/lib/config";
import { fetchErgonApi } from "@/lib/serverApi";
import { getHarnessExperiment } from "@/lib/testing/dashboardHarness";

interface ExperimentRunRow {
  run_id: string;
  workflow_definition_id: string;
  benchmark_type: string;
  instance_key: string;
  status: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  model_target: string | null;
  evaluator_slug: string | null;
  worker_team: Record<string, unknown>;
  seed: number | null;
  running_time_ms: number | null;
  final_score: number | null;
  total_tasks: number | null;
  total_cost_usd: number | null;
  error_message: string | null;
}

interface ExperimentStatusCounts {
  pending: number;
  executing: number;
  evaluating: number;
  completed: number;
  failed: number;
  cancelled: number;
}

interface ExperimentAnalytics {
  total_runs: number;
  status_counts: ExperimentStatusCounts;
  average_score: number | null;
  average_duration_ms: number | null;
  average_tasks: number | null;
  total_cost_usd: number | null;
  latest_activity_at: string | null;
  error_count: number;
}

interface ExperimentDetail {
  experiment: {
    experiment_id: string;
    cohort_id: string | null;
    name: string;
    benchmark_type: string;
    sample_count: number;
    status: string;
    default_model_target: string | null;
    default_evaluator_slug: string | null;
    default_worker_team: Record<string, unknown>;
    created_at: string;
    started_at: string | null;
    completed_at: string | null;
    run_count: number;
  };
  runs: ExperimentRunRow[];
  analytics: ExperimentAnalytics;
  sample_selection: Record<string, unknown>;
  design: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

interface ExperimentPageProps {
  params: Promise<{ experimentId: string }>;
}

function formatNumber(value: number | null | undefined, fallback = "—") {
  if (value === null || value === undefined) return fallback;
  return Number.isInteger(value) ? value.toString() : value.toFixed(2);
}

function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return `$${value.toFixed(2)}`;
}

function formatDuration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${(seconds / 60).toFixed(1)}m`;
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

function runLink(runId: string, cohortId: string | null) {
  if (cohortId) return `/cohorts/${cohortId}/runs/${runId}`;
  return `/run/${runId}`;
}

export default async function ExperimentPage({ params }: ExperimentPageProps) {
  const { experimentId } = await params;
  let detail: ExperimentDetail | null = null;
  if (config.enableTestHarness) {
    detail = getHarnessExperiment(experimentId) as ExperimentDetail | null;
    if (detail === null) notFound();
  } else {
    const response = await fetchErgonApi(`/experiments/${experimentId}`);
    if (response.status === 404) notFound();
    if (!response.ok) {
      throw new Error(`Failed to load experiment ${experimentId}: ${response.status}`);
    }
    detail = (await response.json()) as ExperimentDetail;
  }

  const experiment = detail.experiment;
  const analytics = detail.analytics;

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <Link
            href={experiment.cohort_id ? `/cohorts/${experiment.cohort_id}` : "/experiments"}
            className="text-sm text-[var(--muted)] hover:text-[var(--ink)]"
          >
            {experiment.cohort_id ? "Cohort" : "Experiments"}
          </Link>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-[var(--ink)]">
            {experiment.name}
          </h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {experiment.benchmark_type} · {experiment.sample_count} samples ·{" "}
            {experiment.run_count} runs · latest activity {formatDate(analytics.latest_activity_at)}
          </p>
        </div>
        <div className="rounded-full border border-[var(--line)] px-3 py-1 text-sm text-[var(--muted)]">
          {experiment.status}
        </div>
      </div>

      <section className="mb-6 grid gap-3 md:grid-cols-3">
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
            {workerTeamLabel(experiment.default_worker_team)}
          </div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Samples</div>
          <div className="mt-1 text-sm text-[var(--ink)]">
            {Array.isArray(detail.sample_selection.instance_keys)
              ? detail.sample_selection.instance_keys.join(", ")
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
            {formatDuration(analytics.average_duration_ms)}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {formatNumber(analytics.average_tasks)} avg tasks
          </div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Cost</div>
          <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">
            {formatCurrency(analytics.total_cost_usd)}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {analytics.error_count} runs with errors
          </div>
        </div>
      </section>

      <section
        className="mb-6 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card"
        data-testid="experiment-run-distribution"
      >
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-[var(--ink)]">Run distribution</h2>
            <p className="text-xs text-[var(--muted)]">
              Score and runtime by benchmark instance.
            </p>
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {detail.runs.map((run) => (
            <div
              key={run.run_id}
              className="rounded-[var(--radius-sm)] border border-[var(--line)] px-3 py-2 text-xs"
              data-testid="experiment-distribution-row"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium text-[var(--ink)]">{run.instance_key}</span>
                <span className="text-[var(--muted)]">{run.status}</span>
              </div>
              <div className="mt-1 text-[var(--muted)]">
                score {formatNumber(run.final_score)} · runtime {formatDuration(run.running_time_ms)}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-card">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
            <tr>
              <th className="px-4 py-3">Run</th>
              <th className="px-4 py-3">Sample</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Duration</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Tasks</th>
              <th className="px-4 py-3">Model</th>
              <th className="px-4 py-3">Evaluator</th>
            </tr>
          </thead>
          <tbody>
            {detail.runs.map((run) => (
              <tr key={run.run_id} className="border-b border-[var(--line)] last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={runLink(run.run_id, experiment.cohort_id)}
                    className="font-mono text-xs text-[var(--ink)] underline-offset-2 hover:underline"
                  >
                    {run.run_id}
                  </Link>
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">{run.instance_key}</td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  <div className="text-[var(--ink)]">{run.status}</div>
                  {run.error_message ? <div className="text-xs text-red-500">{run.error_message}</div> : null}
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {formatDuration(run.running_time_ms)}
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {run.final_score === null ? "—" : `Eval ${formatNumber(run.final_score)}`}
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">{run.total_tasks ?? "—"}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{run.model_target ?? "—"}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{run.evaluator_slug ?? "—"}</td>
              </tr>
            ))}
            {detail.runs.length === 0 ? (
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
