import Link from "next/link";
import React from "react";

import { StatusBadge } from "@/components/common/StatusBadge";
import { SampleEvents } from "@/components/samples/SampleEvents";
import type { SampleDashboardState } from "@/lib/sample-state/dashboard";
import type { SampleLifecycleStatus } from "@/lib/types";

function JsonBlock({ value }: { value: Record<string, unknown> }) {
  const entries = Object.entries(value);
  if (entries.length === 0) return <span className="text-[var(--muted)]">-</span>;
  return <pre className="overflow-auto text-xs text-[var(--muted)]">{JSON.stringify(value, null, 2)}</pre>;
}

export function SampleDetail({ state }: { state: SampleDashboardState }) {
  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <Link
            href={`/experiments/${state.experimentId}`}
            className="text-sm text-[var(--muted)] hover:text-[var(--ink)]"
          >
            Experiment
          </Link>
          <h1 className="mt-2 font-mono text-2xl font-semibold text-[var(--ink)]">{state.sampleKey}</h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {state.environmentName} · {state.sampleId}
          </p>
        </div>
        <StatusBadge status={state.status as SampleLifecycleStatus} />
      </div>

      <section className="mb-6 grid gap-3 md:grid-cols-3">
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Environment</div>
          <div className="mt-1 text-sm text-[var(--ink)]">{state.environmentName}</div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Tasks</div>
          <div className="mt-1 text-sm text-[var(--ink)]">
            {state.graph.nodes.length} nodes · {state.graph.edges.length} edges
          </div>
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Events</div>
          <div className="mt-1 text-sm text-[var(--ink)]">{state.events.length}</div>
        </div>
      </section>

      <section className="mb-6 grid gap-4 md:grid-cols-2">
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="mb-2 text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Source</div>
          <JsonBlock value={state.sourceMetadata} />
        </div>
        <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
          <div className="mb-2 text-xs uppercase tracking-[0.08em] text-[var(--faint)]">Sample Ref</div>
          <JsonBlock value={state.sampleRef} />
        </div>
      </section>

      <section className="mb-6 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
        <h2 className="text-sm font-semibold text-[var(--ink)]">Graph Projection</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
              <tr>
                <th className="py-2">Task</th>
                <th className="py-2">Status</th>
                <th className="py-2">Worker</th>
              </tr>
            </thead>
            <tbody>
              {state.graph.nodes.map((node) => (
                <tr key={node.taskId} className="border-t border-[var(--line)]">
                  <td className="py-2 font-mono text-xs text-[var(--ink)]">{node.taskSlug}</td>
                  <td className="py-2"><StatusBadge status={node.status as SampleLifecycleStatus} size="sm" /></td>
                  <td className="py-2 text-xs text-[var(--muted)]">{node.assignedWorkerSlug ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <SampleEvents events={state.events} />
    </main>
  );
}
