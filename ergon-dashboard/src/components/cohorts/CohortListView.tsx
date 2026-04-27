"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useCohorts } from "@/hooks/useCohorts";
import { StatusBadge } from "@/components/common/StatusBadge";
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

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { key: T; label: string; count?: number }[];
  value: T;
  onChange: (key: T) => void;
}) {
  return (
    <div className="inline-flex rounded-[7px] border border-[var(--line)] bg-[var(--paper)] p-0.5 text-xs">
      {options.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key)}
          className={`inline-flex items-center gap-1.5 rounded-[5px] px-2.5 py-1 font-medium transition-colors ${
            value === opt.key
              ? "bg-[var(--card)] text-[var(--ink)] shadow-card"
              : "text-[var(--muted)] hover:text-[var(--ink)]"
          }`}
        >
          <span>{opt.label}</span>
          {opt.count != null && (
            <span className="text-[var(--faint)]">· {opt.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

function failureColor(rate: number): string {
  if (rate > 0.30) return "oklch(0.50 0.16 22)";
  if (rate > 0.15) return "oklch(0.50 0.10 80)";
  return "var(--muted)";
}

function formatTimeHHMMSS(): string {
  const now = new Date();
  return [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
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

  // Suppress unused-var lint — archive toggle is still wired but hidden in the new grid rows
  void updatingCohortIds;
  void handleArchiveToggle;

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-sm text-[var(--muted)]">
        Loading cohorts...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--paper)]">
      <header
        className="border-b border-[var(--line)] bg-[var(--card)]"
        data-testid="cohort-index-header"
      >
        <div className="mx-auto max-w-7xl px-6 py-6">
          <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
            Workspace <span aria-hidden>◆</span>
          </span>
          <h1 className="mt-1 text-[26px] font-semibold leading-tight text-[var(--ink)]">
            Cohorts
          </h1>
          <p className="mt-1.5 text-[13px] text-[var(--muted)]">
            Monitor cohorts first, then drill into runs and task workspaces from the same
            operator surface.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        {error && (
          <div
            className="mb-6 rounded-[var(--radius)] border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
            data-testid="cohort-index-error"
          >
            {error}
          </div>
        )}

        {cohorts.length === 0 ? (
          <div
            className="rounded-[var(--radius)] border border-dashed border-[var(--line-strong)] bg-[var(--paper)] p-12 text-center"
            data-testid="cohort-index-empty"
          >
            <h2 className="text-lg font-medium text-[var(--ink)]">
              No cohorts yet
            </h2>
            <p className="mt-2 text-sm text-[var(--muted)]">
              Define an experiment with an optional cohort name to create the first cohort.
            </p>
          </div>
        ) : (
          <div className="space-y-4" data-testid="cohort-index-list">
            {/* Filter + search row */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter cohorts…"
                  className="w-[220px] rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-xs text-[var(--ink)] placeholder:text-[var(--faint)] focus:border-[var(--accent)] focus:outline-none"
                  data-testid="cohort-search-input"
                />
              </div>
              <SegmentedControl<StatusFilter>
                value={statusFilter}
                onChange={setStatusFilter}
                options={[
                  { key: "all", label: "All", count: visibleCohorts },
                  { key: "active", label: "Active", count: activeCohorts },
                  { key: "running", label: "Running", count: runningCohorts },
                  { key: "needs-attention", label: "Needs attention", count: cohortsNeedingAttention },
                  { key: "archived", label: "Archived", count: archivedCohorts },
                ]}
              />
              <SegmentedControl<SortKey>
                value={sortKey}
                onChange={setSortKey}
                options={[
                  { key: "recent", label: "Recent" },
                  { key: "score", label: "Score" },
                  { key: "failure", label: "Failure rate" },
                  { key: "runs", label: "Runs" },
                ]}
              />
            </div>

            {filteredCohorts.length === 0 ? (
              <div className="rounded-[var(--radius)] border border-dashed border-[var(--line-strong)] bg-[var(--paper)] p-12 text-center">
                <h2 className="text-lg font-medium text-[var(--ink)]">
                  No cohorts match these filters
                </h2>
                <p className="mt-2 text-sm text-[var(--muted)]">
                  Try clearing the search, changing the status filter, or sorting by a different
                  signal.
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-card">
                {/* Table header */}
                <div
                  className="grid border-b border-[var(--line)] px-5 py-3"
                  style={{ gridTemplateColumns: "2.6fr 1fr 1fr 1fr 1.4fr 1fr 0.8fr" }}
                >
                  {["Cohort", "Runs", "Avg score", "Failure", "Runtime", "Status", ""].map(
                    (col) => (
                      <div
                        key={col || "__chevron"}
                        className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]"
                      >
                        {col}
                      </div>
                    ),
                  )}
                </div>

                {/* Table rows */}
                {filteredCohorts.map((cohort) => (
                  <Link
                    key={cohort.cohort_id}
                    href={`/cohorts/${cohort.cohort_id}`}
                    className="grid items-center border-b border-[var(--line)] px-5 text-[13px] transition-colors hover:bg-[var(--paper)] last:border-b-0"
                    style={{
                      gridTemplateColumns: "2.6fr 1fr 1fr 1fr 1.4fr 1fr 0.8fr",
                      padding: "14px 20px",
                    }}
                    data-testid={`cohort-row-${cohort.cohort_id}`}
                  >
                    {/* Cohort name + sub ID */}
                    <div className="min-w-0 pr-4">
                      <div className="truncate font-semibold text-[var(--ink)]">
                        {cohort.name}
                      </div>
                      <div className="mt-0.5 truncate font-mono text-[11px] text-[var(--faint)]">
                        {cohort.cohort_id.slice(0, 12)}
                      </div>
                    </div>

                    {/* Runs */}
                    <div className="font-mono text-[var(--ink)]">
                      {cohort.total_runs}
                    </div>

                    {/* Avg score */}
                    <div className="font-mono text-[var(--ink)]">
                      {formatPercent(cohort.average_score)}
                    </div>

                    {/* Failure rate */}
                    <div
                      className="font-mono"
                      style={{ color: failureColor(cohort.failure_rate) }}
                    >
                      {formatPercent(cohort.failure_rate)}
                    </div>

                    {/* Runtime · last activity */}
                    <div className="text-[var(--ink)]">
                      <span>{formatDurationMs(cohort.average_duration_ms)}</span>
                      <span className="ml-1 text-[var(--faint)]">
                        · {formatRelativeTime(getLatestActivityAt(cohort))}
                      </span>
                    </div>

                    {/* Status */}
                    <div>
                      <StatusBadge
                        status={getCohortDisplayStatus(cohort)}
                        variant="solid"
                        size="sm"
                      />
                    </div>

                    {/* Chevron */}
                    <div className="text-right text-[var(--faint)]">›</div>
                  </Link>
                ))}

                {/* Footer */}
                <div className="flex items-center justify-between border-t border-[var(--line)] px-5 py-3 text-[12px] text-[var(--muted)]">
                  <span>
                    Showing {filteredCohorts.length} of{" "}
                    {statusFilter === "archived" ? archivedCohorts : visibleCohorts} cohorts
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    Updated {formatTimeHHMMSS()} · live
                    <span
                      className="inline-block size-1.5 rounded-full"
                      style={{ backgroundColor: "oklch(0.70 0.13 155)" }}
                    />
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
