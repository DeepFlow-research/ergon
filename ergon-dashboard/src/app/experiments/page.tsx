import Link from "next/link";

import { fetchErgonApi } from "@/lib/serverApi";

interface ExperimentSummary {
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

export default async function ExperimentsPage() {
  let experiments: ExperimentSummary[] = [];
  let error: string | null = null;

  try {
    const response = await fetchErgonApi("/experiments?limit=100");
    if (response.ok) {
      experiments = (await response.json()) as ExperimentSummary[];
    } else {
      error = `API returned ${response.status}`;
    }
  } catch (err) {
    error = err instanceof Error ? err.message : "Failed to load experiments";
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--faint)]">
          Experiment Index
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-[var(--ink)]">
          Experiments
        </h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          One experiment is a launched design; each row can own multiple workflow runs.
        </p>
      </div>

      {error ? (
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 text-sm text-[var(--muted)]">
          {error}
        </div>
      ) : null}

      <div className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-card">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Benchmark</th>
              <th className="px-4 py-3">Samples</th>
              <th className="px-4 py-3">Runs</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Model</th>
            </tr>
          </thead>
          <tbody>
            {experiments.map((experiment) => (
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
                <td className="px-4 py-3 text-[var(--muted)]">{experiment.run_count}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{experiment.status}</td>
                <td className="px-4 py-3 text-[var(--muted)]">
                  {experiment.default_model_target ?? "—"}
                </td>
              </tr>
            ))}
            {experiments.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-[var(--muted)]">
                  No experiments yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </main>
  );
}
