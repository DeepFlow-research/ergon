"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/common/StatusBadge";
import { formatDateTime } from "@/components/indexes/format";
import type { ExperimentSummary } from "@/lib/server-data/experiments";
import type { SampleLifecycleStatus } from "@/lib/types";

function experimentStatus(experiment: ExperimentSummary): string {
  if (experiment.samples.some((sample) => sample.status === "failed")) return "failed";
  if (experiment.samples.some((sample) => ["executing", "evaluating"].includes(sample.status))) {
    return "executing";
  }
  if (experiment.samples.length > 0 && experiment.samples.every((sample) => sample.status === "completed")) {
    return "completed";
  }
  return "pending";
}

export function ExperimentIndexTable({ experiments }: { experiments: ExperimentSummary[] }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return experiments.filter((experiment) => {
      const computedStatus = experimentStatus(experiment);
      const matchesStatus = status === "all" || computedStatus === status;
      const text = [
        experiment.name,
        experiment.description,
        experiment.environments.map((env) => env.environmentName).join(" "),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return matchesStatus && (needle.length === 0 || text.includes(needle));
    });
  }, [experiments, query, status]);

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-3 border-y border-[var(--line)] bg-[var(--paper)] py-3 sm:flex-row sm:items-center sm:justify-between">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search experiments"
          className="h-9 w-full max-w-sm rounded-md border border-[var(--line)] bg-[var(--card)] px-3 text-sm text-[var(--ink)] outline-none focus:border-[var(--ink-2)]"
        />
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="h-9 rounded-md border border-[var(--line)] bg-[var(--card)] px-3 text-sm text-[var(--ink)] outline-none focus:border-[var(--ink-2)]"
        >
          <option value="all">All statuses</option>
          <option value="pending">Pending</option>
          <option value="executing">Executing</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      <div className="overflow-x-auto border border-[var(--line)] bg-[var(--card)]">
        <table className="w-full min-w-[900px] text-left text-[13px]">
          <thead className="border-b border-[var(--line)] bg-[var(--paper-2)] text-[11px] uppercase tracking-[0.08em] text-[var(--faint)]">
            <tr>
              <th className="px-3 py-2 font-semibold">Experiment</th>
              <th className="px-3 py-2 font-semibold">Environments</th>
              <th className="px-3 py-2 text-right font-semibold">Samples</th>
              <th className="px-3 py-2 text-right font-semibold">Selected</th>
              <th className="px-3 py-2 font-semibold">Status</th>
              <th className="px-3 py-2 font-semibold">Created</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((experiment) => {
              const selectedCount = experiment.environments.reduce((sum, env) => sum + env.selectedCount, 0);
              return (
                <tr
                  key={experiment.experimentId}
                  className="border-b border-[var(--line)] last:border-0 hover:bg-[var(--paper)]"
                >
                  <td className="px-3 py-2.5">
                    <Link
                      href={`/experiments/${experiment.experimentId}`}
                      className="font-medium text-[var(--ink)] underline-offset-2 hover:underline"
                    >
                      {experiment.name}
                    </Link>
                    <div className="mt-0.5 truncate text-xs text-[var(--muted)]">
                      {experiment.description ?? experiment.experimentId}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-[var(--muted)]">
                    {experiment.environments.map((env) => env.environmentName).join(", ") || "-"}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                    {experiment.sampleCount}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                    {selectedCount}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={experimentStatus(experiment) as SampleLifecycleStatus} size="sm" />
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-[var(--muted)]">
                    {formatDateTime(experiment.createdAt)}
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-sm text-[var(--muted)]">
                  No experiments match the current filters.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
