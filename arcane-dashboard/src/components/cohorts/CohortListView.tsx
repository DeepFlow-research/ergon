"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useCohorts } from "@/hooks/useCohorts";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SearchInput } from "@/components/common/SearchInput";
import { getCohortDisplayStatus } from "@/lib/cohortStatus";
import { CohortSummary } from "@/lib/types";

type StatusFilter = "all" | "active" | "running" | "needs-attention" | "archived";
type SortKey = "recent" | "failure" | "runs" | "score" | "duration" | "name";

function formatPercent(value: number | null): string {
  if (value === null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatDurationMs(value: number | null): string {
  if (value == null) return "—";
  if (value < 1000) return `${value}ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(1)}s`;
  return `${(value / 60_000).toFixed(1)}m`;
}

function formatRelativeTime(timestamp: string | null | undefined): string {
  if (!timestamp) return "—";

  const value = new Date(timestamp).getTime();
  if (Number.isNaN(value)) return "—";

  const diffMs = value - Date.now();
  const diffMinutes = Math.round(diffMs / 60_000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  if (Math.abs(diffMinutes) < 60) return formatter.format(diffMinutes, "minute");

  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) return formatter.format(diffHours, "hour");

  const diffDays = Math.round(diffHours / 24);
  return formatter.format(diffDays, "day");
}

function getLatestActivityAt(cohort: CohortSummary): string {
  return cohort.extras.latest_run_at ?? cohort.stats_updated_at ?? cohort.created_at;
}

function getSearchText(cohort: CohortSummary): string {
  return [
    cohort.name,
    cohort.description,
    cohort.created_by,
    cohort.metadata_summary.model_name,
    cohort.metadata_summary.model_provider,
    cohort.metadata_summary.prompt_version,
    cohort.metadata_summary.worker_version,
    ...Object.keys(cohort.extras.benchmark_counts ?? {}),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function matchesStatusFilter(cohort: CohortSummary, statusFilter: StatusFilter): boolean {
  if (cohort.status === "archived") {
    return statusFilter === "archived";
  }
  if (statusFilter === "all" || statusFilter === "active") return true;
  if (statusFilter === "needs-attention") return cohort.status_counts.failed > 0;
  if (statusFilter === "running") {
    return cohort.status_counts.executing + cohort.status_counts.evaluating > 0;
  }
  return true;
}

function sortCohorts(cohorts: CohortSummary[], sortKey: SortKey): CohortSummary[] {
  const sorted = [...cohorts];

  sorted.sort((a, b) => {
    switch (sortKey) {
      case "name":
        return a.name.localeCompare(b.name);
      case "runs":
        return b.total_runs - a.total_runs;
      case "failure":
        return b.failure_rate - a.failure_rate;
      case "score":
        return (b.average_score ?? -1) - (a.average_score ?? -1);
      case "duration":
        return (b.average_duration_ms ?? -1) - (a.average_duration_ms ?? -1);
      case "recent":
      default:
        return (
          new Date(getLatestActivityAt(b)).getTime() - new Date(getLatestActivityAt(a)).getTime()
        );
    }
  });

  return sorted;
}

function QuickFilterButton({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors ${
        active
          ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-300"
          : "border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:border-gray-600 dark:hover:text-white"
      }`}
    >
      <span>{label}</span>
      <span className="rounded-full bg-black/5 px-2 py-0.5 text-xs dark:bg-white/10">{count}</span>
    </button>
  );
}

function ArchiveActionButton({
  cohort,
  isUpdating,
  onToggle,
}: {
  cohort: CohortSummary;
  isUpdating: boolean;
  onToggle: (cohort: CohortSummary) => Promise<void>;
}) {
  const isArchived = cohort.status === "archived";

  return (
    <button
      type="button"
      disabled={isUpdating}
      onClick={() => void onToggle(cohort)}
      className={`inline-flex items-center justify-center rounded-lg border px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
        isArchived
          ? "border-emerald-200 bg-emerald-50 text-emerald-700 hover:border-emerald-300 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300"
          : "border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:border-gray-600 dark:hover:text-white"
      }`}
    >
      {isUpdating ? "Saving..." : isArchived ? "Restore" : "Archive"}
    </button>
  );
}

function SummaryCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: string | number;
  helper: string;
}) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
      <div className="text-sm text-gray-500 dark:text-gray-400">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-gray-900 dark:text-white">{value}</div>
      <div className="mt-1 text-xs text-gray-400 dark:text-gray-500">{helper}</div>
    </div>
  );
}

function ProgressBar({ cohort }: { cohort: CohortSummary }) {
  const total = Math.max(cohort.total_runs, 1);
  const segments = [
    {
      key: "completed",
      value: cohort.status_counts.completed,
      className: "bg-emerald-500",
    },
    {
      key: "failed",
      value: cohort.status_counts.failed,
      className: "bg-red-500",
    },
    {
      key: "executing",
      value: cohort.status_counts.executing + cohort.status_counts.evaluating,
      className: "bg-blue-500",
    },
    {
      key: "pending",
      value: cohort.status_counts.pending,
      className: "bg-gray-300 dark:bg-gray-700",
    },
  ].filter((segment) => segment.value > 0);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>Run progress</span>
        <span>
          {cohort.status_counts.completed + cohort.status_counts.failed}/{cohort.total_runs} finished
        </span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
        {segments.map((segment) => (
          <div
            key={segment.key}
            className={segment.className}
            style={{ width: `${(segment.value / total) * 100}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export function CohortListView() {
  const { cohorts, isLoading, error, updatingCohortIds, updateCohortStatus } = useCohorts();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("recent");

  const filteredCohorts = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    const filtered = cohorts.filter((cohort) => {
      if (!matchesStatusFilter(cohort, statusFilter)) return false;

      if (!normalizedQuery) return true;
      return getSearchText(cohort).includes(normalizedQuery);
    });

    return sortCohorts(filtered, sortKey);
  }, [cohorts, query, sortKey, statusFilter]);

  const visibleCohortList = useMemo(
    () => cohorts.filter((cohort) => cohort.status !== "archived"),
    [cohorts],
  );

  const totalRuns = useMemo(
    () => cohorts.reduce((sum, cohort) => sum + cohort.total_runs, 0),
    [cohorts],
  );
  const activeCohorts = useMemo(
    () => visibleCohortList.filter((cohort) => cohort.status === "active").length,
    [visibleCohortList],
  );
  const cohortsNeedingAttention = useMemo(
    () => visibleCohortList.filter((cohort) => cohort.status_counts.failed > 0).length,
    [visibleCohortList],
  );
  const runningCohorts = useMemo(
    () =>
      visibleCohortList.filter(
        (cohort) => cohort.status_counts.executing + cohort.status_counts.evaluating > 0,
      ).length,
    [visibleCohortList],
  );
  const archivedCohorts = useMemo(
    () => cohorts.filter((cohort) => cohort.status === "archived").length,
    [cohorts],
  );
  const visibleCohorts = useMemo(
    () => visibleCohortList.length,
    [visibleCohortList],
  );

  const handleArchiveToggle = async (cohort: CohortSummary) => {
    const nextStatus = cohort.status === "archived" ? "active" : "archived";
    await updateCohortStatus(cohort.cohort_id, nextStatus);
    if (nextStatus === "archived" && statusFilter !== "archived") {
      setStatusFilter("all");
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm text-gray-500 dark:text-gray-400">
        Loading cohorts...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <header
        className="border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
        data-testid="cohort-index-header"
      >
        <div className="mx-auto flex max-w-7xl items-end justify-between gap-4 px-6 py-6">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-gray-500 dark:text-gray-400">
              Arcane Dashboard
            </p>
            <h1 className="text-3xl font-semibold text-gray-900 dark:text-white">
              Experiment Cohorts
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-gray-500 dark:text-gray-400">
              Monitor cohorts first, then drill into runs and task workspaces from the same
              operator surface.
            </p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm dark:border-gray-700 dark:bg-gray-800/50">
            <div className="text-gray-500 dark:text-gray-400">Visible cohorts</div>
            <div className="text-2xl font-semibold text-gray-900 dark:text-white">
              {visibleCohorts}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {error && (
          <div
            className="mb-6 rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-300"
            data-testid="cohort-index-error"
          >
            {error}
          </div>
        )}

        {cohorts.length > 0 && (
          <section className="mb-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <SummaryCard
              label="Visible cohorts"
              value={filteredCohorts.length}
              helper={
                filteredCohorts.length === visibleCohorts
                  ? `${visibleCohorts} visible cohorts in scope`
                  : `Filtered from ${visibleCohorts} visible cohorts`
              }
            />
            <SummaryCard
              label="Open cohorts"
              value={activeCohorts}
              helper={`${runningCohorts} currently executing or evaluating`}
            />
            <SummaryCard
              label="Needs attention"
              value={cohortsNeedingAttention}
              helper="Cohorts with at least one failed run"
            />
            <SummaryCard
              label="Total runs"
              value={totalRuns}
              helper="Across every cohort on this dashboard"
            />
          </section>
        )}

        {cohorts.length === 0 ? (
          <div
            className="rounded-2xl border border-dashed border-gray-300 bg-white p-12 text-center dark:border-gray-700 dark:bg-gray-900"
            data-testid="cohort-index-empty"
          >
            <h2 className="text-lg font-medium text-gray-900 dark:text-white">
              No cohorts yet
            </h2>
            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
              Start a benchmark run with a compulsory cohort name to create the first cohort.
            </p>
          </div>
        ) : (
          <div className="space-y-4" data-testid="cohort-index-list">
            <section className="sticky top-0 z-10 rounded-2xl border border-gray-200 bg-white/95 p-4 backdrop-blur dark:border-gray-800 dark:bg-gray-900/95">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-900 dark:text-white">
                    Find the right cohort faster
                  </div>
                  <div className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    Search by cohort, model, benchmark, prompt version, creator, or description.
                  </div>
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  Showing {filteredCohorts.length} of{" "}
                  {statusFilter === "archived" ? archivedCohorts : visibleCohorts} cohorts
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <QuickFilterButton
                  label="All"
                  count={visibleCohorts}
                  active={statusFilter === "all"}
                  onClick={() => setStatusFilter("all")}
                />
                <QuickFilterButton
                  label="Needs attention"
                  count={cohortsNeedingAttention}
                  active={statusFilter === "needs-attention"}
                  onClick={() => setStatusFilter("needs-attention")}
                />
                <QuickFilterButton
                  label="Running"
                  count={runningCohorts}
                  active={statusFilter === "running"}
                  onClick={() => setStatusFilter("running")}
                />
                <QuickFilterButton
                  label="Open"
                  count={activeCohorts}
                  active={statusFilter === "active"}
                  onClick={() => setStatusFilter("active")}
                />
                <QuickFilterButton
                  label="Archived"
                  count={archivedCohorts}
                  active={statusFilter === "archived"}
                  onClick={() => setStatusFilter("archived")}
                />
              </div>

              <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.6fr)_220px_220px]">
                <SearchInput
                  value={query}
                  onChange={setQuery}
                  placeholder="Search cohorts, models, benchmarks..."
                />
                <label className="block">
                  <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Status
                  </span>
                  <select
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                  >
                    <option value="all">Visible cohorts</option>
                    <option value="active">Open only</option>
                    <option value="running">Running now</option>
                    <option value="needs-attention">Needs attention</option>
                    <option value="archived">Archived</option>
                  </select>
                </label>
                <label className="block">
                  <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Sort by
                  </span>
                  <select
                    value={sortKey}
                    onChange={(event) => setSortKey(event.target.value as SortKey)}
                    className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                  >
                    <option value="recent">Latest activity</option>
                    <option value="failure">Failure rate</option>
                    <option value="runs">Run volume</option>
                    <option value="score">Average score</option>
                    <option value="duration">Average runtime</option>
                    <option value="name">Name</option>
                  </select>
                </label>
              </div>
            </section>

            {filteredCohorts.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-gray-300 bg-white p-12 text-center dark:border-gray-700 dark:bg-gray-900">
                <h2 className="text-lg font-medium text-gray-900 dark:text-white">
                  No cohorts match these filters
                </h2>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                  Try clearing the search, changing the status filter, or sorting by a different
                  signal.
                </p>
              </div>
            ) : (
              <>
                <div className="hidden items-center gap-4 rounded-2xl border border-gray-200 bg-gray-50 px-5 py-3 text-xs font-medium uppercase tracking-wide text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400 xl:grid xl:grid-cols-[minmax(0,2.2fr)_100px_100px_100px_110px_110px_140px_160px]">
                  <div>Cohort</div>
                  <div>Runs</div>
                  <div>Running</div>
                  <div>Completed</div>
                  <div>Failure rate</div>
                  <div>Avg score</div>
                  <div>Latest activity</div>
                  <div>Actions</div>
                </div>

                {filteredCohorts.map((cohort) => (
                  <div
                    key={cohort.cohort_id}
                    className="block rounded-2xl border border-gray-200 bg-white p-5 shadow-sm transition-colors hover:border-blue-300 hover:bg-blue-50/40 dark:border-gray-800 dark:bg-gray-900 dark:hover:border-blue-700 dark:hover:bg-blue-950/20"
                    data-testid={`cohort-row-${cohort.cohort_id}`}
                  >
                    <div className="hidden items-start gap-4 xl:grid xl:grid-cols-[minmax(0,2.2fr)_100px_100px_100px_110px_110px_140px_160px]">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-3">
                          <Link
                            href={`/cohorts/${cohort.cohort_id}`}
                            className="truncate text-lg font-semibold text-gray-900 hover:text-blue-700 dark:text-white dark:hover:text-blue-300"
                          >
                            {cohort.name}
                          </Link>
                          <StatusBadge status={getCohortDisplayStatus(cohort)} size="sm" />
                          {cohort.status_counts.failed > 0 && (
                            <span className="rounded-full bg-red-100 px-2.5 py-1 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-300">
                              Needs attention
                            </span>
                          )}
                        </div>

                        {cohort.description && (
                          <p className="mt-2 line-clamp-2 max-w-3xl text-sm text-gray-500 dark:text-gray-400">
                            {cohort.description}
                          </p>
                        )}

                        <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500 dark:text-gray-400">
                          <span className="rounded-full bg-gray-100 px-2.5 py-1 dark:bg-gray-800">
                            Model: {cohort.metadata_summary.model_name ?? "—"}
                          </span>
                          <span className="rounded-full bg-gray-100 px-2.5 py-1 dark:bg-gray-800">
                            By: {cohort.created_by ?? "Unknown"}
                          </span>
                          <span className="rounded-full bg-gray-100 px-2.5 py-1 dark:bg-gray-800">
                            Avg runtime: {formatDurationMs(cohort.average_duration_ms)}
                          </span>
                        </div>

                        <div className="mt-4">
                          <ProgressBar cohort={cohort} />
                        </div>
                      </div>

                      <div className="pt-1 text-sm font-semibold text-gray-900 dark:text-white">
                        {cohort.total_runs}
                      </div>
                      <div className="pt-1 text-sm font-semibold text-gray-900 dark:text-white">
                        {cohort.status_counts.executing + cohort.status_counts.evaluating}
                      </div>
                      <div className="pt-1 text-sm font-semibold text-gray-900 dark:text-white">
                        {cohort.status_counts.completed}
                      </div>
                      <div className="pt-1 text-sm font-semibold text-gray-900 dark:text-white">
                        {formatPercent(cohort.failure_rate)}
                      </div>
                      <div className="pt-1 text-sm font-semibold text-gray-900 dark:text-white">
                        {formatPercent(cohort.average_score)}
                      </div>
                      <div className="pt-1 text-sm text-gray-500 dark:text-gray-400">
                        <div className="font-medium text-gray-900 dark:text-white">
                          {formatRelativeTime(getLatestActivityAt(cohort))}
                        </div>
                        <div className="mt-1">{new Date(cohort.created_at).toLocaleDateString()}</div>
                      </div>
                      <div className="flex flex-col items-stretch gap-2">
                        <Link
                          href={`/cohorts/${cohort.cohort_id}`}
                          className="inline-flex items-center justify-center rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 transition-colors hover:border-blue-300 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300"
                        >
                          Open
                        </Link>
                        <ArchiveActionButton
                          cohort={cohort}
                          isUpdating={updatingCohortIds.includes(cohort.cohort_id)}
                          onToggle={handleArchiveToggle}
                        />
                      </div>
                    </div>

                    <div className="flex flex-col gap-5 xl:hidden">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-3">
                          <h2 className="truncate text-lg font-semibold text-gray-900 dark:text-white">
                            {cohort.name}
                          </h2>
                          <StatusBadge status={getCohortDisplayStatus(cohort)} size="sm" />
                          {cohort.status_counts.failed > 0 && (
                            <span className="rounded-full bg-red-100 px-2.5 py-1 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-300">
                              Needs attention
                            </span>
                          )}
                        </div>

                        {cohort.description && (
                          <p className="mt-2 max-w-3xl text-sm text-gray-500 dark:text-gray-400">
                            {cohort.description}
                          </p>
                        )}

                        <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500 dark:text-gray-400">
                          <span className="rounded-full bg-gray-100 px-2.5 py-1 dark:bg-gray-800">
                            Model: {cohort.metadata_summary.model_name ?? "—"}
                          </span>
                          <span className="rounded-full bg-gray-100 px-2.5 py-1 dark:bg-gray-800">
                            Created by: {cohort.created_by ?? "Unknown"}
                          </span>
                          <span className="rounded-full bg-gray-100 px-2.5 py-1 dark:bg-gray-800">
                            Latest activity: {formatRelativeTime(getLatestActivityAt(cohort))}
                          </span>
                          <span className="rounded-full bg-gray-100 px-2.5 py-1 dark:bg-gray-800">
                            Created: {new Date(cohort.created_at).toLocaleDateString()}
                          </span>
                        </div>

                        <div className="mt-4">
                          <ProgressBar cohort={cohort} />
                        </div>
                      </div>

                      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                        <div className="rounded-xl bg-gray-50 px-3 py-3 dark:bg-gray-800/50">
                          <dt className="text-gray-500 dark:text-gray-400">Runs</dt>
                          <dd className="mt-1 font-semibold text-gray-900 dark:text-white">
                            {cohort.total_runs}
                          </dd>
                        </div>
                        <div className="rounded-xl bg-gray-50 px-3 py-3 dark:bg-gray-800/50">
                          <dt className="text-gray-500 dark:text-gray-400">Completed</dt>
                          <dd className="mt-1 font-semibold text-gray-900 dark:text-white">
                            {cohort.status_counts.completed}
                          </dd>
                        </div>
                        <div className="rounded-xl bg-gray-50 px-3 py-3 dark:bg-gray-800/50">
                          <dt className="text-gray-500 dark:text-gray-400">Running</dt>
                          <dd className="mt-1 font-semibold text-gray-900 dark:text-white">
                            {cohort.status_counts.executing + cohort.status_counts.evaluating}
                          </dd>
                        </div>
                        <div className="rounded-xl bg-gray-50 px-3 py-3 dark:bg-gray-800/50">
                          <dt className="text-gray-500 dark:text-gray-400">Failure rate</dt>
                          <dd className="mt-1 font-semibold text-gray-900 dark:text-white">
                            {formatPercent(cohort.failure_rate)}
                          </dd>
                        </div>
                        <div className="rounded-xl bg-gray-50 px-3 py-3 dark:bg-gray-800/50">
                          <dt className="text-gray-500 dark:text-gray-400">Avg score</dt>
                          <dd className="mt-1 font-semibold text-gray-900 dark:text-white">
                            {formatPercent(cohort.average_score)}
                          </dd>
                        </div>
                        <div className="rounded-xl bg-gray-50 px-3 py-3 dark:bg-gray-800/50">
                          <dt className="text-gray-500 dark:text-gray-400">Avg runtime</dt>
                          <dd className="mt-1 font-semibold text-gray-900 dark:text-white">
                            {formatDurationMs(cohort.average_duration_ms)}
                          </dd>
                        </div>
                      </dl>

                      <div className="flex flex-col gap-2 sm:flex-row">
                        <Link
                          href={`/cohorts/${cohort.cohort_id}`}
                          className="inline-flex items-center justify-center rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 transition-colors hover:border-blue-300 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300"
                        >
                          Open cohort
                        </Link>
                        <ArchiveActionButton
                          cohort={cohort}
                          isUpdating={updatingCohortIds.includes(cohort.cohort_id)}
                          onToggle={handleArchiveToggle}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
