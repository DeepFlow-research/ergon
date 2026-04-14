import type { TaskState } from "@/lib/types";
import { formatDurationMs } from "@/lib/formatDuration";

const startedAtShortFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

/** Task inspector panel: date + time including seconds (locale-aware). */
const taskInspectorWallClockFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "medium",
});

/** Localized display + ISO for `<time datetime>` (task workspace Started / Ended rows). */
export function formatTaskWallTimestamp(iso: string | null): {
  text: string;
  dateTime: string | null;
} {
  if (iso == null || iso === "") return { text: "—", dateTime: null };
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { text: "—", dateTime: null };
  return { text: taskInspectorWallClockFormatter.format(d), dateTime: iso };
}

/**
 * Primary one-line summary for graph task cards: wall duration when finished,
 * or a started timestamp while the task is in progress. Returns null when the
 * task has not started yet (no `startedAt`), matching API semantics.
 */
export function getTaskTimingPrimaryLine(
  task: Pick<TaskState, "startedAt" | "completedAt">,
): string | null {
  const { startedAt, completedAt } = task;
  if (startedAt && completedAt) {
    const a = Date.parse(startedAt);
    const b = Date.parse(completedAt);
    if (Number.isFinite(a) && Number.isFinite(b) && b >= a) {
      return formatDurationMs(b - a);
    }
  }
  if (startedAt) {
    const d = new Date(startedAt);
    if (!Number.isNaN(d.getTime())) {
      return `Started ${startedAtShortFormatter.format(d)}`;
    }
  }
  return null;
}
