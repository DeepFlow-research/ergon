import Link from "next/link";
import React from "react";

import { SampleTable } from "@/components/experiments/SampleTable";
import type { ExperimentDashboardState } from "@/lib/sample-state/dashboard";

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

export function ExperimentDetail({ state }: { state: ExperimentDashboardState }) {
  const selectedCount = state.environments.reduce((sum, env) => sum + env.selectedCount, 0);

  return (
    <main className="mx-auto w-full max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <Link href="/experiments" className="text-sm text-[var(--muted)] hover:text-[var(--ink)]">
            Experiments
          </Link>
          <h1 className="mt-2 text-3xl font-semibold text-[var(--ink)]">{state.name}</h1>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {state.environments.length} environments · {state.sampleCount} samples · {selectedCount} selected · created{" "}
            {formatDate(state.createdAt)}
          </p>
        </div>
      </div>

      <section className="mb-6 grid gap-3 md:grid-cols-3">
        {state.environments.map((environment) => (
          <div
            key={environment.environmentId}
            className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4"
          >
            <div className="text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
              Environment
            </div>
            <div className="mt-1 text-sm font-medium text-[var(--ink)]">
              {environment.environmentName}
            </div>
            <div className="mt-2 text-xs text-[var(--muted)]">
              {environment.sampleCount} samples · {environment.selectedCount} selected · {environment.sourceMode}
            </div>
          </div>
        ))}
        {state.environments.length === 0 ? (
          <div className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4 text-sm text-[var(--muted)]">
            No environments recorded yet.
          </div>
        ) : null}
      </section>

      <section className="mb-6 rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
        <div className="mb-3 text-xs uppercase tracking-[0.08em] text-[var(--faint)]">
          Sampler Invocations
        </div>
        <div className="space-y-2">
          {state.samplerInvocations.map((invocation) => (
            <div
              key={invocation.samplerInvocationId}
              className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--line)] pb-2 text-sm last:border-0 last:pb-0"
            >
              <span className="font-medium text-[var(--ink)]">{invocation.samplerName}</span>
              <span className="font-mono text-xs text-[var(--muted)]">
                requested {invocation.requestedK} · pool {invocation.candidatePoolSize} · selected{" "}
                {invocation.selectedCount}
              </span>
            </div>
          ))}
          {state.samplerInvocations.length === 0 ? (
            <div className="text-sm text-[var(--muted)]">No sampler invocations recorded yet.</div>
          ) : null}
        </div>
      </section>

      <SampleTable samples={state.samples} />
    </main>
  );
}
