/**
 * Centralized Tailwind + hex color tokens for TaskStatus values.
 *
 * Motivation: prior to this module, node components, status badges, and
 * timeline chips all hand-picked their own `bg-yellow-xxx` / `border-red-xxx`
 * combinations, which drifted over time. The tokens below are the single
 * source of truth — every surface that renders a status should pull from here.
 */

import { TaskStatus } from "@/lib/types";

export interface StatusTokens {
  label: string;
  /** Saturated hex (used for SVG fills and inline styles). */
  hex: string;
  /** Tailwind bg for light contexts (e.g. row chips, surface tiles). */
  softBg: string;
  /** Tailwind bg for emphatic / inverted treatments (e.g. corner badge fill). */
  solidBg: string;
  /** Text color that reads well on the soft bg. */
  softText: string;
  /** Text color that reads well on the solid bg. */
  solidText: string;
  /** Tailwind border matching the family. */
  border: string;
  /** Tailwind ring used for focus / selected halos. */
  ring: string;
  /** True when a pulse animation should indicate "actively changing". */
  animate: boolean;
}

export const STATUS_TOKENS: Record<TaskStatus, StatusTokens> = {
  [TaskStatus.PENDING]: {
    label: "Pending",
    hex: "#94a3b8", // slate-400
    softBg: "bg-slate-100 dark:bg-slate-800/70",
    solidBg: "bg-slate-400 dark:bg-slate-500",
    softText: "text-slate-600 dark:text-slate-300",
    solidText: "text-white",
    border: "border-slate-300 dark:border-slate-600",
    ring: "ring-slate-300 dark:ring-slate-600",
    animate: false,
  },
  [TaskStatus.READY]: {
    label: "Ready",
    hex: "#0ea5e9", // sky-500
    softBg: "bg-sky-50 dark:bg-sky-900/30",
    solidBg: "bg-sky-500 dark:bg-sky-400",
    softText: "text-sky-700 dark:text-sky-300",
    solidText: "text-white",
    border: "border-sky-300 dark:border-sky-500",
    ring: "ring-sky-300 dark:ring-sky-500",
    animate: false,
  },
  [TaskStatus.RUNNING]: {
    label: "Running",
    hex: "#f59e0b", // amber-500
    softBg: "bg-amber-50 dark:bg-amber-900/30",
    solidBg: "bg-amber-500 dark:bg-amber-400",
    softText: "text-amber-700 dark:text-amber-300",
    solidText: "text-white",
    border: "border-amber-400 dark:border-amber-500",
    ring: "ring-amber-400 dark:ring-amber-500",
    animate: true,
  },
  [TaskStatus.COMPLETED]: {
    label: "Completed",
    hex: "#10b981", // emerald-500
    softBg: "bg-emerald-50 dark:bg-emerald-900/30",
    solidBg: "bg-emerald-500 dark:bg-emerald-400",
    softText: "text-emerald-700 dark:text-emerald-300",
    solidText: "text-white",
    border: "border-emerald-400 dark:border-emerald-500",
    ring: "ring-emerald-400 dark:ring-emerald-500",
    animate: false,
  },
  [TaskStatus.FAILED]: {
    label: "Failed",
    hex: "#e11d48", // rose-600
    softBg: "bg-rose-50 dark:bg-rose-900/30",
    solidBg: "bg-rose-600 dark:bg-rose-500",
    softText: "text-rose-700 dark:text-rose-300",
    solidText: "text-white",
    border: "border-rose-400 dark:border-rose-500",
    ring: "ring-rose-400 dark:ring-rose-500",
    animate: false,
  },
  [TaskStatus.ABANDONED]: {
    label: "Abandoned",
    hex: "#71717a", // zinc-500
    softBg: "bg-zinc-100 dark:bg-zinc-800/70",
    solidBg: "bg-zinc-500 dark:bg-zinc-400",
    softText: "text-zinc-600 dark:text-zinc-300",
    solidText: "text-white",
    border: "border-zinc-300 dark:border-zinc-600",
    ring: "ring-zinc-300 dark:ring-zinc-600",
    animate: false,
  },
};

/** Canonical order for status chips/bars (lifecycle-ordered). */
export const TASK_STATUS_ORDER: TaskStatus[] = [
  TaskStatus.PENDING,
  TaskStatus.READY,
  TaskStatus.RUNNING,
  TaskStatus.COMPLETED,
  TaskStatus.FAILED,
  TaskStatus.ABANDONED,
];

export function tokensFor(status: TaskStatus | string): StatusTokens {
  return (
    STATUS_TOKENS[status as TaskStatus] ??
    STATUS_TOKENS[TaskStatus.PENDING]
  );
}
