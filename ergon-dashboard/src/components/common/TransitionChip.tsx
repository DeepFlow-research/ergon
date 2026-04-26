"use client";

/**
 * TransitionChip — the visual primitive for a status transition.
 *
 * Shape: `PENDING ──dependency_satisfied──▶ READY  12:04:07.142`
 *
 * This is how the run workspace answers the question "why did this task
 * change state?". The `from` dot uses its status tokens, the `to` dot uses
 * its status tokens, the trigger label sits on the arrow, and the timestamp
 * anchors the transition to wall-clock time.
 */

import { TaskStatus, TaskTrigger } from "@/lib/types";
import { tokensFor } from "@/lib/statusTokens";
import { formatClockTimeMs } from "@/lib/timeFormat";

const TRIGGER_LABELS: Record<string, string> = {
  [TaskTrigger.WORKFLOW_STARTED]: "workflow started",
  [TaskTrigger.DEPENDENCY_SATISFIED]: "deps satisfied",
  [TaskTrigger.WORKER_STARTED]: "worker started",
  [TaskTrigger.EXECUTION_SUCCEEDED]: "execution succeeded",
  [TaskTrigger.EXECUTION_FAILED]: "execution failed",
  [TaskTrigger.CHILDREN_COMPLETED]: "children completed",
  unknown: "unknown trigger",
};

function formatTimeMs(iso: string | null): string {
  if (!iso) return "—";
  const label = formatClockTimeMs(iso);
  return label === "—" ? iso : label;
}

interface TransitionChipProps {
  from: TaskStatus | null;
  to: TaskStatus;
  trigger: TaskTrigger | "unknown";
  at?: string | null;
  reason?: string | null;
  compact?: boolean;
  /** Override; defaults to wall-clock derived from `at`. */
  children?: React.ReactNode;
}

export function TransitionChip({
  from,
  to,
  trigger,
  at,
  reason,
  compact,
}: TransitionChipProps) {
  const fromTokens = from ? tokensFor(from) : null;
  const toTokens = tokensFor(to);
  const triggerLabel = TRIGGER_LABELS[trigger] ?? String(trigger);
  const isUnknown = trigger === "unknown";

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full border ${toTokens.border} ${toTokens.softBg} ${compact ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs"}`}
      data-testid="transition-chip"
      title={reason ?? undefined}
    >
      {fromTokens ? (
        <span
          className={`${fromTokens.solidBg} h-2 w-2 rounded-full`}
          aria-hidden
        />
      ) : (
        <span className="h-2 w-2 rounded-full border border-dashed border-slate-400" aria-hidden />
      )}
      <span className={`font-medium uppercase tracking-wide ${fromTokens?.softText ?? "text-slate-500"}`}>
        {from ?? "init"}
      </span>
      <span className="flex items-center gap-1 text-slate-400 dark:text-slate-500">
        <span className="hidden h-px w-3 bg-current sm:inline-block" />
        <span
          className={`font-mono ${isUnknown ? "italic text-rose-500" : ""}`}
          aria-label={`trigger: ${triggerLabel}`}
        >
          {triggerLabel}
        </span>
        <svg
          viewBox="0 0 12 8"
          className="h-2 w-3 fill-current"
          aria-hidden
        >
          <path d="M0 4h9M7 1l4 3-4 3" stroke="currentColor" fill="none" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span
        className={`${toTokens.solidBg} h-2 w-2 rounded-full ${toTokens.animate ? "animate-pulse" : ""}`}
        aria-hidden
      />
      <span className={`font-semibold uppercase tracking-wide ${toTokens.softText}`}>
        {to}
      </span>
      {at && !compact && (
        <span className="font-mono text-[10px] tabular-nums text-slate-400 dark:text-slate-500">
          {formatTimeMs(at)}
        </span>
      )}
    </div>
  );
}
