"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/common/StatusBadge";
import { formatDateTime, formatDurationSeconds, formatPercent } from "@/components/indexes/format";
import type { ExperimentSummary } from "@/lib/server-data/experiments";
import type { SampleLifecycleStatus } from "@/lib/types";

export function ExperimentIndexTable({ experiments }: { experiments: ExperimentSummary[] }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return experiments.filter((experiment) => {
      const matchesStatus = status === "all" || experiment.status === status;
      const text = [
        experiment.name,
        experiment.description,
        experiment.benchmark_type,
        experiment.default_model_target,
        experiment.default_evaluator_slug,
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
          <option value="defined">Defined</option>
          <option value="executing">Executing</option>
          <option value="evaluating">Evaluating</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      <div className="overflow-x-auto border border-[var(--line)] bg-[var(--card)]">
        <table className="w-full min-w-[1040px] text-left text-[13px]">
          <thead className="border-b border-[var(--line)] bg-[var(--paper-2)] text-[11px] uppercase tracking-[0.08em] text-[var(--faint)]">
            <tr>
              <th className="px-3 py-2 font-semibold">Experiment</th>
              <th className="px-3 py-2 font-semibold">Benchmark</th>
              <th className="px-3 py-2 text-right font-semibold">Runs</th>
              <th className="px-3 py-2 text-right font-semibold">Failed</th>
              <th className="px-3 py-2 font-semibold">Status</th>
              <th className="px-3 py-2 text-right font-semibold">Score</th>
              <th className="px-3 py-2 text-right font-semibold">Duration</th>
              <th className="px-3 py-2 font-semibold">Latest</th>
              <th className="px-3 py-2 font-semibold">Model / Evaluator</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((experiment) => (
              <tr
                key={experiment.definition_id}
                className="border-b border-[var(--line)] last:border-0 hover:bg-[var(--paper)]"
              >
                <td className="px-3 py-2.5">
                  <Link
                    href={`/experiments/${experiment.definition_id}`}
                    className="font-medium text-[var(--ink)] underline-offset-2 hover:underline"
                  >
                    {experiment.name}
                  </Link>
                  <div className="mt-0.5 truncate text-xs text-[var(--muted)]">
                    {experiment.description ?? experiment.definition_id}
                  </div>
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-[var(--ink-2)]">
                  {experiment.benchmark_type}
                  <div className="mt-0.5 text-[var(--faint)]">{experiment.sample_count} samples</div>
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                  {experiment.run_count}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                  {experiment.failure_count}
                </td>
                <td className="px-3 py-2.5">
                  <StatusBadge status={experiment.status as SampleLifecycleStatus} size="sm" />
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                  {formatPercent(experiment.average_score)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                  {formatDurationSeconds(
                    experiment.average_duration_ms === null
                      ? null
                      : experiment.average_duration_ms / 1000,
                  )}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-[var(--muted)]">
                  {formatDateTime(experiment.latest_activity_at ?? experiment.created_at)}
                </td>
                <td className="px-3 py-2.5 text-xs text-[var(--muted)]">
                  <div className="truncate">{experiment.default_model_target ?? "-"}</div>
                  <div className="truncate text-[var(--faint)]">
                    {experiment.default_evaluator_slug ?? "-"}
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-sm text-[var(--muted)]">
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
