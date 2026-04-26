import type { RunActivity } from "./types";

function parseTime(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

export function resolveCurrentActivityId(
  activities: RunActivity[],
  currentTimestamp: string | null,
  currentSequence: number | null = null,
): string | null {
  if (!currentTimestamp) return null;
  const currentMs = Date.parse(currentTimestamp);
  if (!Number.isFinite(currentMs)) return null;

  let selected: RunActivity | null = null;
  let selectedMs = Number.NEGATIVE_INFINITY;
  for (const activity of activities) {
    const activityMs = parseTime(activity.startAt);
    if (activityMs > currentMs) continue;
    if (
      currentSequence !== null &&
      activity.sequence !== null &&
      activity.sequence > currentSequence
    ) {
      continue;
    }
    if (
      activityMs > selectedMs ||
      (activityMs === selectedMs &&
        (activity.sequence ?? Number.NEGATIVE_INFINITY) >
          (selected?.sequence ?? Number.NEGATIVE_INFINITY)) ||
      (activityMs === selectedMs &&
        (activity.sequence ?? Number.NEGATIVE_INFINITY) ===
          (selected?.sequence ?? Number.NEGATIVE_INFINITY) &&
        (!selected || activity.id > selected.id))
    ) {
      selected = activity;
      selectedMs = activityMs;
    }
  }

  return selected?.id ?? null;
}
