"use client";

import Link from "next/link";
import { useState } from "react";

import { useCohortDetail } from "@/hooks/useCohortDetail";
import { CohortRunRow, CohortSummary, RunLifecycleStatus } from "@/lib/types";
import { StatusBadge } from "@/components/common/StatusBadge";
import { getCohortDisplayStatus } from "@/lib/cohortStatus";
import { CohortDetail } from "@/lib/types";
import { formatDurationMs } from "@/lib/formatDuration";

function formatScore(score: number | null | undefined): string {
  if (score == null) return "—";
  return `${(score * 100).toFixed(1)}%`;
}

function formatCost(value: number | null): string {
  if (value == null) return "—";
  return `$${value.toFixed(2)}`;
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

/* ────────────────────────────────────────────────────────── */
/* Metric Tiles                                               */
/* ────────────────────────────────────────────────────────── */

function MetricTile({
  title,
  value,
  sub,
  children,
}: {
  title: string;
  value: string;
  sub?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-card" style={{ padding: "18px 20px" }}>
      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
        {title}
      </div>
      <div className="mt-1.5 text-[34px] font-semibold leading-none text-[var(--ink)]">
        {value}
      </div>
      {sub && (
        <div className="mt-1 text-[12px] text-[var(--muted)]">{sub}</div>
      )}
      {children}
    </div>
  );
}

interface CohortDetailStats {
  averageCostUsd: number | null;
  averageTasks: number | null;
  completed: number;
  failed: number;
  scores: number[];
  totalCostUsd: number | null;
  totalRuns: number;
}

function buildDetailStats(summary: CohortSummary, runs: CohortRunRow[]): CohortDetailStats {
  const totalRuns = runs.length || summary.total_runs;
  const completed =
    runs.length > 0
      ? runs.filter((run) => run.status === "completed").length
      : summary.status_counts.completed;
  const failed =
    runs.length > 0
      ? runs.filter((run) => run.status === "failed").length
      : summary.status_counts.failed;
  const scores = runs
    .map((run) => run.final_score)
    .filter((score): score is number => score !== null);
  const taskCounts = runs
    .map((run) => run.total_tasks)
    .filter((count): count is number => count !== null);
  const costs = runs
    .map((run) => run.total_cost_usd)
    .filter((cost): cost is number => cost !== null);
  const totalCostUsd = costs.length > 0 ? costs.reduce((sum, cost) => sum + cost, 0) : null;

  return {
    averageCostUsd: costs.length > 0 && totalCostUsd !== null ? totalCostUsd / costs.length : null,
    averageTasks:
      taskCounts.length > 0
        ? taskCounts.reduce((sum, count) => sum + count, 0) / taskCounts.length
        : null,
    completed,
    failed,
    scores,
    totalCostUsd,
    totalRuns,
  };
}

function ResolutionTile({ stats }: { stats: CohortDetailStats }) {
  const total = stats.totalRuns;
  const completed = stats.completed;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <MetricTile
      title="Resolution"
      value={`${pct}%`}
      sub={`${completed} of ${total} runs completed`}
    />
  );
}

function RunsPassFailTile({ stats }: { stats: CohortDetailStats }) {
  const completed = stats.completed;
  const failed = stats.failed;
  const total = stats.totalRuns;
  const greenPct = total > 0 ? (completed / total) * 100 : 0;
  const redPct = total > 0 ? (failed / total) * 100 : 0;

  return (
    <MetricTile
      title="Runs · pass / fail"
      value={`${completed} / ${failed}`}
      sub={`${completed + failed} of ${total} runs terminal`}
    >
      <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-[var(--paper-2)]">
        {greenPct > 0 && (
          <div
            className="rounded-l-full"
            style={{
              width: `${greenPct}%`,
              backgroundColor: "oklch(0.70 0.13 155)",
            }}
          />
        )}
        {redPct > 0 && (
          <div
            className="rounded-r-full"
            style={{
              width: `${redPct}%`,
              backgroundColor: "oklch(0.68 0.18 22)",
            }}
          />
        )}
      </div>
    </MetricTile>
  );
}

type DistributionMetric = "score" | "runtime" | "tasks" | "cost";

const distributionMetrics: Array<{ key: DistributionMetric; label: string }> = [
  { key: "score", label: "Score" },
  { key: "runtime", label: "Runtime" },
  { key: "tasks", label: "Tasks" },
  { key: "cost", label: "Cost" },
];

function metricValue(run: CohortRunRow, metric: DistributionMetric): number | null {
  switch (metric) {
    case "score":
      return run.final_score;
    case "runtime":
      return run.running_time_ms;
    case "tasks":
      return run.total_tasks;
    case "cost":
      return run.total_cost_usd;
  }
}

function formatMetricValue(metric: DistributionMetric, value: number): string {
  switch (metric) {
    case "score":
      return formatScore(value);
    case "runtime":
      return formatDurationMs(value);
    case "tasks":
      return value.toFixed(0);
    case "cost":
      return formatCost(value);
  }
}

function RunDistribution({ cohortId, runs }: { cohortId: string; runs: CohortRunRow[] }) {
  const [selectedMetric, setSelectedMetric] = useState<DistributionMetric>("score");
  const selectedLabel =
    distributionMetrics.find((metric) => metric.key === selectedMetric)?.label ?? "Score";
  const points = runs
    .map((run, index) => ({
      index,
      run,
      value: metricValue(run, selectedMetric),
    }))
    .filter((point): point is { index: number; run: CohortRunRow; value: number } => point.value !== null);
  const values = points.map((point) => point.value);
  const min = selectedMetric === "score" ? 0 : Math.min(...values);
  const max = selectedMetric === "score" ? 1 : Math.max(...values);

  function leftPct(value: number): number {
    if (values.length === 0 || min === max) return 50;
    return ((value - min) / (max - min)) * 100;
  }

  return (
    <section
      className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-5 shadow-card"
      data-testid="cohort-run-distribution"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-[var(--ink)]">
            {selectedLabel} distribution
          </h2>
          <p className="text-sm text-[var(--muted)]">
            One dot per run. Use the metric controls to spot slow, costly, or unusually large runs.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {distributionMetrics.map((metric) => (
            <button
              key={metric.key}
              type="button"
              aria-pressed={selectedMetric === metric.key}
              className={`rounded-full px-2.5 py-1 text-xs font-medium ring-1 transition ${
                selectedMetric === metric.key
                  ? "bg-[var(--ink)] text-[var(--card)] ring-[var(--ink)]"
                  : "bg-[var(--paper)] text-[var(--muted)] ring-[var(--line)] hover:text-[var(--ink)]"
              }`}
              data-testid={`cohort-distribution-metric-${metric.key}`}
              onClick={() => setSelectedMetric(metric.key)}
            >
              {metric.label}
            </button>
          ))}
        </div>
      </div>

      {points.length === 0 ? (
        <div className="mt-4 rounded-[var(--radius-sm)] border border-dashed border-[var(--line)] bg-[var(--paper)] px-4 py-8 text-center text-sm text-[var(--muted)]">
          No {selectedLabel.toLowerCase()} values are available yet.
        </div>
      ) : (
        <div className="mt-5">
          <div className="relative h-36 rounded-[var(--radius-sm)] bg-[var(--paper)] px-4 py-4">
            <div className="absolute left-4 right-4 top-1/2 h-px bg-[var(--line)]" />
            {points.map((point) => {
              const valueLabel = formatMetricValue(selectedMetric, point.value);
              return (
                <Link
                  key={point.run.run_id}
                  href={`/cohorts/${cohortId}/runs/${point.run.run_id}`}
                  className="absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--accent)] shadow-[0_0_0_3px_var(--card)] ring-1 ring-white/80 transition-transform hover:scale-125 focus:outline-none focus:ring-2 focus:ring-[var(--ink)]"
                  data-testid="cohort-distribution-point"
                  style={{
                    left: `${Math.min(96, Math.max(4, leftPct(point.value)))}%`,
                    top: `${38 + (point.index % 4) * 8}%`,
                  }}
                  title={`${point.run.run_id.slice(0, 8)}: ${valueLabel}`}
                >
                  <span className="sr-only">
                    {point.run.run_id} {selectedLabel} {valueLabel}
                  </span>
                </Link>
              );
            })}
          </div>
          <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-[var(--faint)]">
            <span>{formatMetricValue(selectedMetric, min)}</span>
            <span>{points.length} run{points.length === 1 ? "" : "s"}</span>
            <span>{formatMetricValue(selectedMetric, max)}</span>
          </div>
        </div>
      )}
    </section>
  );
}

/* ────────────────────────────────────────────────────────── */
/* Run Row                                                    */
/* ────────────────────────────────────────────────────────── */

function CohortRunRowCard({ cohortId, run }: { cohortId: string; run: CohortRunRow }) {
  const started = formatStartedAt(run.started_at);

  return (
    <Link
      href={`/cohorts/${cohortId}/runs/${run.run_id}`}
      className="grid grid-cols-1 gap-3 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] px-4 py-4 transition-colors hover:bg-[var(--paper)] lg:grid-cols-[minmax(0,1.2fr)_repeat(6,minmax(0,0.7fr))]"
      data-testid={`cohort-run-row-${run.run_id}`}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-base font-medium text-[var(--ink)]">
            {run.run_id}
          </span>
          <StatusBadge status={run.status as RunLifecycleStatus} size="sm" />
        </div>
        <div className="mt-1 flex flex-wrap gap-2 text-xs text-[var(--muted)]">
          <span>{run.cohort_name}</span>
          <span>•</span>
          <span className="font-mono">{run.run_id.slice(0, 8)}...</span>
        </div>
        {run.error_message && (
          <div className="mt-2 text-sm" style={{ color: "oklch(0.50 0.16 22)" }}>
            {run.error_message}
          </div>
        )}
      </div>

      <div>
        <div className="text-xs text-[var(--faint)]">Benchmark</div>
        <div className="text-sm font-medium text-[var(--ink)]">{run.cohort_name}</div>
      </div>
      <div>
        <div className="text-xs text-[var(--faint)]">Status</div>
        <div className="text-sm font-medium capitalize text-[var(--ink)]">{run.status}</div>
      </div>
      <div>
        <div className="text-xs text-[var(--faint)]">Started</div>
        <div className="text-sm font-medium text-[var(--ink)]">
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
        <div className="text-xs text-[var(--faint)]">Runtime</div>
        <div className="text-sm font-medium text-[var(--ink)]">
          {formatDurationMs(run.running_time_ms)}
        </div>
      </div>
      <div>
        <div className="text-xs text-[var(--faint)]">Score</div>
        <div className="text-sm font-medium text-[var(--ink)]">
          {formatScore(run.final_score)}
        </div>
      </div>
    </Link>
  );
}

/* ────────────────────────────────────────────────────────── */
/* Empty State                                                */
/* ────────────────────────────────────────────────────────── */

function EmptyRunsState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-[var(--radius)] border border-dashed border-[var(--line-strong)] bg-[var(--paper)] px-6 py-16 text-center">
      <span className="text-4xl text-[var(--faint)]" aria-hidden>⊘</span>
      <h3 className="mt-4 text-lg font-semibold text-[var(--ink)]">No runs yet</h3>
      <p className="mt-1.5 max-w-sm text-sm text-[var(--muted)]">
        This cohort has no runs. Launch a benchmark run targeting this cohort to get started.
      </p>
      <button
        type="button"
        className="mt-5 inline-flex items-center rounded-[var(--radius-sm)] px-4 py-2 text-sm font-medium shadow-card"
        style={{
          backgroundColor: "var(--ink)",
          color: "var(--card)",
        }}
      >
        Launch cohort
      </button>
    </div>
  );
}

/* ────────────────────────────────────────────────────────── */
/* Main View                                                  */
/* ────────────────────────────────────────────────────────── */

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
      <div className="flex min-h-screen items-center justify-center bg-[var(--paper)] text-sm text-[var(--muted)]">
        Loading cohort...
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--paper)] px-6 text-sm text-[var(--muted)]">
        {error ?? "Cohort not found"}
      </div>
    );
  }

  const { summary, runs } = detail;
  const stats = buildDetailStats(summary, runs);

  return (
    <div className="min-h-screen bg-[var(--paper)]">
      <header className="border-b border-[var(--line)] bg-[var(--card)]">
        <div className="mx-auto max-w-7xl px-6 py-6">
          <Link
            href="/"
            className="mb-4 inline-flex items-center gap-2 text-sm text-[var(--muted)] transition-colors hover:text-[var(--ink)]"
            data-testid="cohort-breadcrumb-home"
          >
            <span>Cohorts</span>
          </Link>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div data-testid="cohort-header">
              <div className="flex items-center gap-3">
                <h1 className="text-[26px] font-semibold leading-tight text-[var(--ink)]">
                  {summary.name}
                </h1>
                <StatusBadge status={getCohortDisplayStatus(summary)} />
              </div>
              <p className="mt-1.5 max-w-3xl text-[13px] text-[var(--muted)]">
                {summary.description ??
                  "Monitor cohort progress, inspect runs, and drill into task-level evidence."}
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-8 px-6 py-8">
        {error && (
          <div className="rounded-[var(--radius)] border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
            {error}
          </div>
        )}

        {/* 5-tile summary row */}
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5" data-testid="cohort-summary-cards">
          <ResolutionTile stats={stats} />
          <RunsPassFailTile stats={stats} />
          <MetricTile
            title="Avg runtime"
            value={formatDurationMs(summary.average_duration_ms)}
            sub="min"
          />
          <MetricTile
            title="Avg tasks"
            value={stats.averageTasks == null ? "—" : stats.averageTasks.toFixed(1)}
            sub={stats.averageTasks == null ? "Not yet available" : "tasks per run"}
          />
          <MetricTile
            title="Cost"
            value={formatCost(stats.totalCostUsd)}
            sub={stats.averageCostUsd == null ? "Not yet available" : `${formatCost(stats.averageCostUsd)} / run`}
          />
        </section>

        <RunDistribution cohortId={cohortId} runs={runs} />

        {/* Runs section */}
        <section data-testid="cohort-run-list">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-[var(--ink)]">Runs</h2>
              <p className="text-sm text-[var(--muted)]">
                Select a run to inspect graph topology and task workspace evidence.
              </p>
            </div>
          </div>
          {runs.length === 0 ? (
            <EmptyRunsState />
          ) : (
            <div className="space-y-3">
              {runs.map((run) => (
                <CohortRunRowCard key={run.run_id} cohortId={cohortId} run={run} />
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
