import { ExperimentIndexTable } from "@/components/indexes/ExperimentIndexTable";
import { loadExperimentList, type ExperimentSummary } from "@/lib/server-data/experiments";

export default async function ExperimentsPage() {
  let experiments: ExperimentSummary[] = [];
  let error: string | null = null;

  const result = await loadExperimentList();
  if (result.ok) {
    experiments = result.data;
  } else {
    const detail = (result.body as { detail?: string })?.detail;
    error = detail ?? `API returned ${result.status}`;
  }

  const runningCount = experiments.reduce(
    (sum, experiment) =>
      sum + experiment.status_counts.executing + experiment.status_counts.evaluating,
    0,
  );
  const failedCount = experiments.reduce(
    (sum, experiment) => sum + experiment.failure_count,
    0,
  );
  const totalRuns = experiments.reduce((sum, experiment) => sum + experiment.run_count, 0);

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-5">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--faint)]">
          Experiment Index
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-[var(--ink)]">
          Experiments
        </h1>
      </div>

      {error ? (
        <div className="mb-4 border border-[var(--line)] bg-[var(--card)] p-4 text-sm text-[var(--muted)]">
          {error}
        </div>
      ) : null}

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <div className="border border-[var(--line)] bg-[var(--card)] px-4 py-3">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Running</div>
          <div className="mt-1 font-mono text-2xl text-[var(--ink)]">{runningCount}</div>
        </div>
        <div className="border border-[var(--line)] bg-[var(--card)] px-4 py-3">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Failures</div>
          <div className="mt-1 font-mono text-2xl text-[var(--ink)]">{failedCount}</div>
        </div>
        <div className="border border-[var(--line)] bg-[var(--card)] px-4 py-3">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Runs</div>
          <div className="mt-1 font-mono text-2xl text-[var(--ink)]">{totalRuns}</div>
        </div>
      </div>

      <ExperimentIndexTable experiments={experiments} />
    </main>
  );
}
