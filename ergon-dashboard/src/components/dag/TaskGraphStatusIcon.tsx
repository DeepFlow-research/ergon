"use client";

import { memo } from "react";
import { TaskStatus } from "@/lib/types";

function labelFor(status: TaskStatus): string {
  switch (status) {
    case TaskStatus.PENDING:
      return "Pending task";
    case TaskStatus.READY:
      return "Ready to run";
    case TaskStatus.RUNNING:
      return "Running";
    case TaskStatus.COMPLETED:
      return "Completed";
    case TaskStatus.FAILED:
      return "Failed";
    case TaskStatus.CANCELLED:
      return "Cancelled";
    default:
      return "Task";
  }
}

/** Compact corner icon for graph cards (distinct from inline StatusDot). */
export const TaskGraphStatusIcon = memo(function TaskGraphStatusIcon({
  status,
}: {
  status: TaskStatus;
}) {
  const base =
    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-white bg-white/95 text-[11px] font-bold shadow-sm dark:border-gray-900 dark:bg-gray-900/95";

  if (status === TaskStatus.COMPLETED) {
    return (
      <span className={`${base} text-green-600 dark:text-green-400`} aria-label={labelFor(status)}>
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.2}>
          <path d="M3 8l3 3 7-7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    );
  }
  if (status === TaskStatus.FAILED) {
    return (
      <span className={`${base} text-red-600 dark:text-red-400`} aria-label={labelFor(status)}>
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.2}>
          <path d="M4 4l8 8M12 4l-8 8" strokeLinecap="round" />
        </svg>
      </span>
    );
  }
  if (status === TaskStatus.RUNNING) {
    return (
      <span className={`${base} text-amber-600 dark:text-amber-400`} aria-label={labelFor(status)}>
        <span className="flex gap-0.5">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.2s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.1s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
        </span>
      </span>
    );
  }
  if (status === TaskStatus.READY) {
    return (
      <span className={`${base} text-blue-600 dark:text-blue-400`} aria-label={labelFor(status)}>
        <svg viewBox="0 0 16 16" className="ml-0.5 h-3.5 w-3.5" fill="currentColor">
          <path d="M5 4l8 4-8 4V4z" />
        </svg>
      </span>
    );
  }
  if (status === TaskStatus.CANCELLED) {
    return (
      <span className={`${base} text-gray-500 dark:text-gray-400`} aria-label={labelFor(status)}>
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2}>
          <path d="M4 8h8" strokeLinecap="round" />
        </svg>
      </span>
    );
  }
  /* pending and unknown */
  return (
    <span className={`${base} text-gray-500 dark:text-gray-400`} aria-label={labelFor(status)}>
      <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={1.8}>
        <circle cx="8" cy="8" r="5.5" />
      </svg>
    </span>
  );
});
