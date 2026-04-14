"use client";

import Link from "next/link";

import { useCohortDetail } from "@/hooks/useCohortDetail";
import { CohortRunRow, RunLifecycleStatus } from "@/lib/types";
import { StatusBadge } from "@/components/common/StatusBadge";
import { getCohortDisplayStatus } from "@/lib/cohortStatus";
import { CohortDetail } from "@/lib/types";
import { formatDurationMs } from "@/lib/formatDuration";

function formatScore(score: number | null | undefined): string {
  if (score == null) return "—";
  return `${(score * 100).toFixed(1)}%`;
}

const startedAtDisplayFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatStartedAt(iso: string | null): { text: string; dateTime: string | null } {
  if (iso == null || iso === "") return { text: "—", dateTime: null };
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { text: "—", dateTime: null };
  return { text: startedAtDisplayFormatter.format(d), dateTime: iso };
}

function CohortRunRowCard({ cohortId, run }: { cohortId: string; run: CohortRunRow }) {
  const started = formatStartedAt(run.started_at);

  return (
    <Link
      href={`/cohorts/${cohortId}/runs/${run.run_id}`}
      className="grid grid-cols-1 gap-3 rounded-2xl border border-gray-200 bg-white px-4 py-4 transition-colors hover:border-blue-300 hover:bg-blue-50/40 dark:border-gray-800 dark:bg-gray-900 dark:hover:border-blue-700 dark:hover:bg-blue-950/20 lg:grid-cols-[minmax(0,1.2fr)_repeat(6,minmax(0,0.7fr))]"
      data-testid={`cohort-run-row-${run.run_id}`}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-base font-medium text-gray-900 dark:text-white">
            {run.run_id}
          </span>
          <StatusBadge status={run.status as RunLifecycleStatus} size="sm" />
        </div>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span>{run.cohort_name}</span>
          <span>•</span>
          <span className="font-mono">{run.run_id.slice(0, 8)}...</span>
        </div>
        {run.error_message && (
          <div className="mt-2 text-sm text-red-600 dark:text-red-400">{run.error_message}</div>
        )}
      </div>

      <div>
        <div className="text-xs text-gray-500 dark:text-gray-400">Benchmark</div>
        <div className="text-sm font-medium text-gray-900 dark:text-white">{run.cohort_name}</div>
      </div>
      <div>
        <div className="text-xs text-gray-500 dark:text-gray-400">Status</div>
        <div className="text-sm font-medium capitalize text-gray-900 dark:text-white">{run.status}</div>
      </div>
      <div>
        <div className="text-xs text-gray-500 dark:text-gray-400">Started</div>
        <div className="text-sm font-medium text-gray-900 dark:text-white">
          {started.dateTime ? (
            <time dateTime={started.dateTime} title={started.dateTime}>
              {started.text}
            </time>
          ) : (
            started.text
          )}
        </div>
      </div>
      <div>
        <div className="text-xs text-gray-500 dark:text-gray-400">Runtime</div>
        <div className="text-sm font-medium text-gray-900 dark:text-white">
          {formatDurationMs(run.running_time_ms)}
        </div>
      </div>
      <div>
        <div className="text-xs text-gray-500 dark:text-gray-400">Score</div>
        <div className="text-sm font-medium text-gray-900 dark:text-white">
          {formatScore(run.final_score)}
        </div>
      </div>
    </Link>
  );
}

export function CohortDetailView({
  cohortId,
  initialDetail = null,
}: {
  cohortId: string;
  initialDetail?: CohortDetail | null;
}) {
  const { detail, isLoading, error } = useCohortDetail(cohortId, initialDetail);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 text-sm text-gray-500 dark:bg-gray-950 dark:text-gray-400">
        Loading cohort...
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-6 text-sm text-gray-500 dark:bg-gray-950 dark:text-gray-400">
        {error ?? "Cohort not found"}
      </div>
    );
  }

  const { summary, runs } = detail;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <header className="border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
        <div className="mx-auto max-w-7xl px-6 py-6">
          <Link
            href="/"
            className="mb-4 inline-flex items-center gap-2 text-sm text-gray-500 transition-colors hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
            data-testid="cohort-breadcrumb-home"
          >
            <span>Experiment Cohorts</span>
          </Link>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div data-testid="cohort-header">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-semibold text-gray-900 dark:text-white">
                  {summary.name}
                </h1>
                <StatusBadge status={getCohortDisplayStatus(summary)} />
              </div>
              <p className="mt-2 max-w-3xl text-sm text-gray-500 dark:text-gray-400">
                {summary.description ??
                  "Monitor cohort progress, inspect runs, and drill into task-level evidence."}
              </p>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm dark:border-gray-700 dark:bg-gray-800/50">
              <div className="text-gray-500 dark:text-gray-400">Model</div>
              <div className="font-semibold text-gray-900 dark:text-white">
                {summary.metadata_summary.model_name ?? "—"}
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-8 px-6 py-8">
        {error && (
          <div className="rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300">
            {error}
          </div>
        )}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6" data-testid="cohort-summary-cards">
          <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
            <div className="text-sm text-gray-500 dark:text-gray-400">Total runs</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">
              {summary.total_runs}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
            <div className="text-sm text-gray-500 dark:text-gray-400">Executing</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">
              {summary.status_counts.executing}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
            <div className="text-sm text-gray-500 dark:text-gray-400">Completed</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">
              {summary.status_counts.completed}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
            <div className="text-sm text-gray-500 dark:text-gray-400">Failed</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">
              {summary.status_counts.failed}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
            <div className="text-sm text-gray-500 dark:text-gray-400">Average score</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">
              {formatScore(summary.average_score)}
            </div>
          </div>
          <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
            <div className="text-sm text-gray-500 dark:text-gray-400">Failure rate</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">
              {formatScore(summary.failure_rate)}
            </div>
          </div>
        </section>

        <section data-testid="cohort-run-list">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Runs</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Select a run to inspect graph topology and task workspace evidence.
              </p>
            </div>
          </div>
          <div className="space-y-3">
            {runs.map((run) => (
              <CohortRunRowCard key={run.run_id} cohortId={cohortId} run={run} />
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
