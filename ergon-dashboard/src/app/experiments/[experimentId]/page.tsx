import Link from "next/link";
import { notFound } from "next/navigation";

import { fetchErgonApi } from "@/lib/serverApi";

interface ExperimentRunRow {
  run_id: string;
  workflow_definition_id: string;
  benchmark_type: string;
  instance_key: string;
  status: string;
  created_at: string;
  model_target: string | null;
  evaluator_slug: string | null;
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
    run_count: number;
  };
  runs: ExperimentRunRow[];
  sample_selection: Record<string, unknown>;
  design: Record<string, unknown>;
}

interface ExperimentPageProps {
  params: Promise<{ experimentId: string }>;
}

export default async function ExperimentPage({ params }: ExperimentPageProps) {
  const { experimentId } = await params;
  const response = await fetchErgonApi(`/experiments/${experimentId}`);
  if (response.status === 404) notFound();
  if (!response.ok) {
    throw new Error(`Failed to load experiment ${experimentId}: ${response.status}`);
  }

  const detail = (await response.json()) as ExperimentDetail;
  const experiment = detail.experiment;

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <Link href="/experiments" className="text-sm text-[var(--muted)] hover:text-[var(--ink)]">
            Experiments
          </Link>
          <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-[var(--ink)]">
            {experiment.name}
          </h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {experiment.benchmark_type} · {experiment.sample_count} samples · {experiment.run_count} runs
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
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Samples</div>
          <div className="mt-1 text-sm text-[var(--ink)]">
            {Array.isArray(detail.sample_selection.instance_keys)
              ? detail.sample_selection.instance_keys.join(", ")
              : experiment.sample_count}
          </div>
        </div>
      </section>

      <div className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-card">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
            <tr>
              <th className="px-4 py-3">Run</th>
              <th className="px-4 py-3">Sample</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Model</th>
              <th className="px-4 py-3">Evaluator</th>
            </tr>
          </thead>
          <tbody>
            {detail.runs.map((run) => (
              <tr key={run.run_id} className="border-b border-[var(--line)] last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={`/run/${run.run_id}`}
                    className="font-mono text-xs text-[var(--ink)] underline-offset-2 hover:underline"
                  >
                    {run.run_id}
                  </Link>
                </td>
                <td className="px-4 py-3 text-[var(--muted)]">{run.instance_key}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{run.status}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{run.model_target ?? "—"}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{run.evaluator_slug ?? "—"}</td>
              </tr>
            ))}
            {detail.runs.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-[var(--muted)]">
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
