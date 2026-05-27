import { SampleIndexTable } from "@/components/indexes/SampleIndexTable";
import { loadSampleList, type SampleSummary } from "@/lib/server-data/samples";

export default async function RunsPage() {
  let runs: SampleSummary[] = [];
  let error: string | null = null;

  const result = await loadSampleList({ limit: 100 });
  if (result.ok) {
    runs = result.data;
  } else {
    const detail = (result.body as { detail?: string })?.detail;
    error = detail ?? `API returned ${result.status}`;
  }

  const runningCount = runs.filter((run) => ["executing", "evaluating"].includes(run.status)).length;
  const failedCount = runs.filter((run) => run.status === "failed" || run.failed_tasks > 0).length;
  const completedCount = runs.filter((run) => run.status === "completed").length;

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-5">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--faint)]">
          Run Index
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-[var(--ink)]">Runs</h1>
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
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Failed</div>
          <div className="mt-1 font-mono text-2xl text-[var(--ink)]">{failedCount}</div>
        </div>
        <div className="border border-[var(--line)] bg-[var(--card)] px-4 py-3">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Completed</div>
          <div className="mt-1 font-mono text-2xl text-[var(--ink)]">{completedCount}</div>
        </div>
      </div>

      <SampleIndexTable runs={runs} />
    </main>
  );
}
