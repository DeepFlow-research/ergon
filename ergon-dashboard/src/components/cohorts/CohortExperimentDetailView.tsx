"use client";

import Link from "next/link";

interface StatusCounts {
  pending: number;
  executing: number;
  evaluating: number;
  completed: number;
  failed: number;
}

interface CohortExperimentRow {
  experiment_id: string;
  name: string;
  benchmark_type: string;
  sample_count: number;
  total_runs: number;
  status_counts: StatusCounts;
  status: string;
  created_at: string;
  default_model_target: string | null;
  default_evaluator_slug: string | null;
  final_score: number | null;
  total_cost_usd: number | null;
  error_message: string | null;
}

interface CohortExperimentDetail {
  summary: {
    cohort_id: string;
    name: string;
    description: string | null;
    created_by: string | null;
    created_at: string;
    status: string;
    total_runs: number;
    average_score: number | null;
    average_duration_ms: number | null;
  };
  experiments: CohortExperimentRow[];
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

function statusSummary(counts: StatusCounts) {
  return `${counts.completed} done · ${counts.failed} failed · ${
    counts.executing + counts.evaluating + counts.pending
  } active`;
}

function latestExperimentActivity(experiments: CohortExperimentRow[]) {
  const latest = experiments
    .map((experiment) => Date.parse(experiment.created_at))
    .filter(Number.isFinite)
    .sort((a, b) => b - a)[0];
  return latest ? new Date(latest).toLocaleString() : "—";
}

function totalExperimentCost(experiments: CohortExperimentRow[]) {
  const costs = experiments
    .map((experiment) => experiment.total_cost_usd)
    .filter((cost): cost is number => cost !== null);
  if (costs.length === 0) return null;
  return costs.reduce((total, cost) => total + cost, 0);
}

export function CohortExperimentDetailView({
  detail,
}: {
  detail: CohortExperimentDetail | null;
}) {
  if (detail === null) {
    return (
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-6 text-sm text-[var(--muted)]">
          Cohort not found.
        </div>
      </main>
    );
  }

  const totalCost = totalExperimentCost(detail.experiments);

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6" data-testid="cohort-header">
        <Link href="/cohorts" className="text-sm text-[var(--muted)] hover:text-[var(--ink)]">
          Cohorts
        </Link>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-[var(--ink)]">
          {detail.summary.name}
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          {detail.summary.description ?? "Project folder"} · created by{" "}
          {detail.summary.created_by ?? "unknown"} · latest activity{" "}
          {latestExperimentActivity(detail.experiments)}
        </p>
      </div>

      <section className="mb-6 grid gap-3 md:grid-cols-3" data-testid="cohort-summary-cards">
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
            Experiments
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">
            {detail.experiments.length}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {detail.summary.total_runs} total runs
          </div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
            Score / runtime
          </div>
          <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">
            {formatNumber(detail.summary.average_score)}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            avg score · {formatDuration(detail.summary.average_duration_ms)} avg runtime
          </div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 shadow-card">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Cost</div>
          <div className="mt-2 text-2xl font-semibold text-[var(--ink)]">
            {formatCurrency(totalCost)}
          </div>
          <div className="mt-1 text-xs text-[var(--muted)]">
            from experiments with persisted cost
          </div>
        </div>
      </section>

      <div className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-card">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
            <tr>
              <th className="px-4 py-3">Experiment</th>
              <th className="px-4 py-3">Benchmark</th>
              <th className="px-4 py-3">Samples</th>
              <th className="px-4 py-3">Runs</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Cost</th>
              <th className="px-4 py-3">Evaluator</th>
              <th className="px-4 py-3">Model</th>
            </tr>
          </thead>
          <tbody>
            {detail.experiments.map((experiment) => (
              <tr
                key={experiment.experiment_id}
                className="border-b border-[var(--line)] last:border-0"
                data-testid={`cohort-experiment-row-${experiment.experiment_id}`}
              >
                <td className="px-4 py-3">
                  <Link
                    href={`/experiments/${experiment.experiment_id}`}
                    className="font-medium text-[var(--ink)] underline-offset-2 hover:underline"
                  >
                    {experiment.name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">{experiment.benchmark_type}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{experiment.sample_count}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{experiment.total_runs}</td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  <div className="text-[var(--ink)]">{experiment.status}</div>
                  <div className="text-xs">{statusSummary(experiment.status_counts)}</div>
                  {experiment.error_message ? (
                    <div className="mt-1 text-xs text-red-500">{experiment.error_message}</div>
                  ) : null}
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {formatNumber(experiment.final_score)}
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {formatCurrency(experiment.total_cost_usd)}
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {experiment.default_evaluator_slug ?? "—"}
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {experiment.default_model_target ?? "—"}
                </td>
              </tr>
            ))}
            {detail.experiments.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-[var(--muted)]">
                  This cohort does not contain any experiments yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </main>
  );
}
