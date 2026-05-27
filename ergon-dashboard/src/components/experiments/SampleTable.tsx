import Link from "next/link";
import React from "react";

import { StatusBadge } from "@/components/common/StatusBadge";
import type { ExperimentSampleSummaryView } from "@/lib/contracts/rest";
import type { SampleLifecycleStatus } from "@/lib/types";

export function SampleTable({ samples }: { samples: ExperimentSampleSummaryView[] }) {
  return (
    <div className="overflow-hidden rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] shadow-card">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-[var(--line)] bg-[var(--paper)] text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
          <tr>
            <th className="px-3 py-2">Sample</th>
            <th className="px-3 py-2">Environment</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Created</th>
          </tr>
        </thead>
        <tbody>
          {samples.map((sample) => (
            <tr
              key={sample.sampleId}
              data-testid={`experiment-sample-row-${sample.sampleId}`}
              className="group border-b border-[var(--line)] last:border-0 hover:bg-[var(--paper)]"
            >
              <td>
                <Link
                  href={`/samples/${sample.sampleId}`}
                  className="block px-3 py-2 font-mono text-xs text-[var(--ink)] underline-offset-2 group-hover:underline"
                >
                  {sample.sampleKey}
                </Link>
                <div className="px-3 pb-2 font-mono text-[11px] text-[var(--muted)]">{sample.sampleId}</div>
              </td>
              <td className="px-3 py-2 text-[var(--muted)]">{sample.environmentName}</td>
              <td className="px-3 py-2">
                <StatusBadge status={sample.status as SampleLifecycleStatus} size="sm" />
              </td>
              <td className="px-3 py-2 font-mono text-xs text-[var(--muted)]">
                {new Date(sample.createdAt).toLocaleString()}
              </td>
            </tr>
          ))}
          {samples.length === 0 ? (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-[var(--muted)]">
                No samples have been materialized yet.
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
