import React from "react";

import {
  formatCost,
  formatScore,
  formatTaskCount,
  formatTokens,
  type MetricDisplay,
} from "@/lib/run-state/formatters";

export interface RunHeaderMetricValues {
  tasks: {
    completed: number;
    running: number;
    failed: number;
    total: number;
  };
  tokens: number | null;
  costUsd: number | null;
  costObserved: boolean;
  score: number | null;
}

function MetricTile({
  label,
  metric,
  testId,
}: {
  label: string;
  metric: MetricDisplay;
  testId: string;
}) {
  return (
    <div
      className={`min-w-[112px] rounded-[7px] border px-3 py-2 ${
        metric.isUnavailable
          ? "border-dashed border-[var(--line)] bg-[var(--paper)]"
          : "border-[var(--line)] bg-[var(--card)] shadow-card"
      }`}
      data-testid={`${testId}-tile`}
    >
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
        {label}
      </div>
      <div
        className={`mt-1 font-mono text-base font-semibold leading-none tabular-nums ${
          metric.isUnavailable ? "text-[var(--muted)]" : "text-[var(--ink)]"
        }`}
        data-testid={testId}
      >
        {metric.value}
      </div>
      {metric.detail && (
        <div className="mt-1 truncate text-[10px] text-[var(--muted)]" title={metric.detail}>
          {metric.detail}
        </div>
      )}
    </div>
  );
}

export function RunHeaderMetrics({ metrics }: { metrics: RunHeaderMetricValues }) {
  return (
    <div className="hidden items-stretch gap-2 border-r border-[var(--line)] pr-3 xl:flex">
      <MetricTile
        label="Tasks"
        testId="stat-tasks"
        metric={formatTaskCount(metrics.tasks)}
      />
      <MetricTile
        label="Tokens"
        testId="stat-tokens"
        metric={formatTokens(metrics.tokens)}
      />
      <MetricTile
        label="Cost"
        testId="stat-cost"
        metric={formatCost(metrics.costUsd, metrics.costObserved)}
      />
      <MetricTile
        label="Score"
        testId="stat-score"
        metric={formatScore(metrics.score)}
      />
    </div>
  );
}
