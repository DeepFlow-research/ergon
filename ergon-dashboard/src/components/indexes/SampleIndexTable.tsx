"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/common/StatusBadge";
import {
  formatDateTime,
  formatDurationSeconds,
  formatNumber,
  formatPercent,
} from "@/components/indexes/format";
import type { SampleSummary } from "@/lib/server-data/samples";
import type { SampleLifecycleStatus } from "@/lib/types";

export function SampleIndexTable({ runs }: { runs: SampleSummary[] }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return runs.filter((run) => {
      const matchesStatus = status === "all" || run.status === status;
      const text = [
        run.name,
        run.definition_name,
        run.experiment,
        run.benchmark_type,
        run.instance_key,
        run.sample_id,
        run.model_target,
        run.evaluator_slug,
        run.error_message,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return matchesStatus && (needle.length === 0 || text.includes(needle));
    });
  }, [query, runs, status]);

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-3 border-y border-[var(--line)] bg-[var(--paper)] py-3 sm:flex-row sm:items-center sm:justify-between">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search runs"
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
          <option value="evaluating">Evaluating</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      <div className="overflow-x-auto border border-[var(--line)] bg-[var(--card)]">
        <table className="w-full min-w-[1180px] text-left text-[13px]">
          <thead className="border-b border-[var(--line)] bg-[var(--paper-2)] text-[11px] uppercase tracking-[0.08em] text-[var(--faint)]">
            <tr>
              <th className="px-3 py-2 font-semibold">Run</th>
              <th className="px-3 py-2 font-semibold">Experiment</th>
              <th className="px-3 py-2 font-semibold">Benchmark / Sample</th>
              <th className="px-3 py-2 font-semibold">Status</th>
              <th className="px-3 py-2 text-right font-semibold">Tasks</th>
              <th className="px-3 py-2 text-right font-semibold">Score</th>
              <th className="px-3 py-2 text-right font-semibold">Return</th>
              <th className="px-3 py-2 text-right font-semibold">Duration</th>
              <th className="px-3 py-2 font-semibold">Latest</th>
              <th className="px-3 py-2 font-semibold">Model / Evaluator</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((run) => (
              <tr
                key={run.id}
                className="border-b border-[var(--line)] last:border-0 hover:bg-[var(--paper)]"
              >
                <td className="px-3 py-2.5">
                  <Link
                    href={`/samples/${run.id}`}
                    className="font-medium text-[var(--ink)] underline-offset-2 hover:underline"
                  >
                    {run.name}
                  </Link>
                  <div className="mt-0.5 font-mono text-xs text-[var(--faint)]">{run.id}</div>
                </td>
                <td className="px-3 py-2.5">
                  <Link
                    href={`/experiments/${run.definition_id}`}
                    className="text-[var(--ink-2)] underline-offset-2 hover:underline"
                  >
                    {run.definition_name ?? run.experiment ?? "Experiment"}
                  </Link>
                  <div className="mt-0.5 text-xs text-[var(--faint)]">
                    {run.experiment ?? run.definition_id}
                  </div>
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-[var(--ink-2)]">
                  {run.benchmark_type}
                  <div className="mt-0.5 text-[var(--faint)]">{run.sample_label}</div>
                </td>
                <td className="px-3 py-2.5">
                  <StatusBadge status={run.status as SampleLifecycleStatus} size="sm" />
                  {run.error_message ? (
                    <div className="mt-1 max-w-[160px] truncate text-xs text-[var(--status-failed)]">
                      {run.error_message}
                    </div>
                  ) : null}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                  {run.completed_tasks}/{run.total_tasks}
                  <div className="mt-0.5 text-xs text-[var(--faint)]">
                    F {run.failed_tasks} R {run.running_tasks}
                  </div>
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                  {formatPercent(run.final_score)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                  {formatNumber(run.return_value)}
                </td>
                <td className="px-3 py-2.5 text-right font-mono text-[var(--ink)]">
                  {formatDurationSeconds(run.duration_seconds)}
                </td>
                <td className="px-3 py-2.5 font-mono text-xs text-[var(--muted)]">
                  {formatDateTime(run.latest_activity_at ?? run.completed_at ?? run.started_at)}
                </td>
                <td className="px-3 py-2.5 text-xs text-[var(--muted)]">
                  <div className="truncate">{run.model_target ?? "-"}</div>
                  <div className="truncate text-[var(--faint)]">{run.evaluator_slug ?? "-"}</div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={10} className="px-3 py-8 text-center text-sm text-[var(--muted)]">
                  No runs match the current filters.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
