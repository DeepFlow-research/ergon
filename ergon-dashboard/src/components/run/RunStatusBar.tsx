"use client";

/**
 * RunStatusBar — segmented bar showing the count of leaf tasks in each
 * TaskStatus. Replaces the legacy "Tasks: 52 / Failed: 1" pair of tiles,
 * which hid how much work was pending, ready, or running.
 *
 * Each segment is width-proportional to its count; clicking a segment emits
 * a filter callback so the parent can highlight matching nodes in the DAG.
 */

import { TaskStatus } from "@/lib/types";
import { STATUS_TOKENS, TASK_STATUS_ORDER } from "@/lib/statusTokens";

export interface RunStatusBarProps {
  counts: Record<TaskStatus, number>;
  total: number;
  onFilter?: (status: TaskStatus | null) => void;
  activeFilter?: TaskStatus | null;
}

export function RunStatusBar({
  counts,
  total,
  onFilter,
  activeFilter = null,
}: RunStatusBarProps) {
  const safeTotal = total > 0 ? total : 1;

  return (
    <div className="flex flex-col gap-2" data-testid="run-status-bar">
      <div className="flex h-2 overflow-hidden rounded-full border border-slate-200 dark:border-slate-700">
        {TASK_STATUS_ORDER.map((status) => {
          const tokens = STATUS_TOKENS[status];
          const count = counts[status] ?? 0;
          if (count === 0) return null;
          const widthPct = (count / safeTotal) * 100;
          return (
            <button
              key={status}
              type="button"
              onClick={() =>
                onFilter?.(activeFilter === status ? null : status)
              }
              className={`${tokens.solidBg} transition-opacity ${activeFilter && activeFilter !== status ? "opacity-30" : "opacity-100"}`}
              style={{ width: `${widthPct}%` }}
              title={`${tokens.label}: ${count}`}
              aria-label={`${tokens.label}: ${count} tasks`}
            />
          );
        })}
      </div>
      <div
        className="flex flex-wrap gap-1.5 text-[11px]"
        data-testid="run-status-counts"
      >
        {TASK_STATUS_ORDER.map((status) => {
          const tokens = STATUS_TOKENS[status];
          const count = counts[status] ?? 0;
          const isActive = activeFilter === status;
          const isDimmed = activeFilter !== null && activeFilter !== status;
          return (
            <button
              key={status}
              type="button"
              onClick={() => onFilter?.(isActive ? null : status)}
              disabled={count === 0 && !isActive}
              className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-medium transition-opacity ${tokens.border} ${isActive ? `${tokens.solidBg} ${tokens.solidText}` : `${tokens.softBg} ${tokens.softText}`} ${isDimmed ? "opacity-40" : "opacity-100"} ${count === 0 ? "opacity-50" : ""} disabled:cursor-default`}
              data-testid={`run-status-count-${status}`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${tokens.solidBg} ${tokens.animate ? "animate-pulse" : ""}`}
                aria-hidden
              />
              <span className="uppercase tracking-wide">{tokens.label}</span>
              <span className="font-mono tabular-nums">{count}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
