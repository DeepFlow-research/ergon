"use client";

import Link from "next/link";

interface CohortExperimentRow {
  experiment_id: string;
  name: string;
  benchmark_type: string;
  sample_count: number;
  total_runs: number;
  status: string;
  default_model_target: string | null;
  default_evaluator_slug: string | null;
}

interface CohortExperimentDetail {
  summary: {
    cohort_id: string;
    name: string;
    description: string | null;
    status: string;
    total_runs: number;
  };
  experiments: CohortExperimentRow[];
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

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6">
        <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--ink)]">
          Cohorts
        </Link>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-[var(--ink)]">
          {detail.summary.name}
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          {detail.summary.description ?? "Project folder"} · {detail.experiments.length} experiments ·{" "}
          {detail.summary.total_runs} runs
        </p>
      </div>

      <div className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-card">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
            <tr>
              <th className="px-4 py-3">Experiment</th>
              <th className="px-4 py-3">Benchmark</th>
              <th className="px-4 py-3">Samples</th>
              <th className="px-4 py-3">Runs</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Model</th>
            </tr>
          </thead>
          <tbody>
            {detail.experiments.map((experiment) => (
              <tr key={experiment.experiment_id} className="border-b border-[var(--line)] last:border-0">
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
                <td className="px-4 py-3 text-[var(--muted)]">{experiment.status}</td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {experiment.default_model_target ?? "—"}
                </td>
              </tr>
            ))}
            {detail.experiments.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-[var(--muted)]">
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
