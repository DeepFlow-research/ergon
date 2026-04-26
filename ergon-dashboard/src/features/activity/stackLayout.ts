import type { ActivityStackLayout, RunActivity } from "./types";

export interface StackActivityOptions {
  minMarkerWidthPct?: number;
  minSpanWidthPct?: number;
  markerDurationMs?: number;
}

interface TimedActivity {
  activity: RunActivity;
  startMs: number;
  endMs: number;
}

const DEFAULT_MARKER_DURATION_MS = 250;

function firstFreeRow(rowEnds: number[], startMs: number): number {
  const row = rowEnds.findIndex((endMs) => endMs <= startMs);
  return row === -1 ? rowEnds.length : row;
}

function parseTime(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function toTimedActivity(
  activity: RunActivity,
  markerDurationMs: number,
): TimedActivity {
  const startMs = parseTime(activity.startAt);
  const rawEndMs = activity.endAt ? parseTime(activity.endAt) : startMs;
  const endMs =
    activity.isInstant || rawEndMs <= startMs
      ? startMs + markerDurationMs
      : rawEndMs;
  return { activity, startMs, endMs };
}

function computeMaxSpanConcurrency(timed: TimedActivity[]): number {
  const events = timed
    .filter((item) => !item.activity.isInstant)
    .flatMap((item) => [
      { at: item.startMs, delta: 1 },
      { at: item.endMs, delta: -1 },
    ])
    .sort((a, b) => a.at - b.at || a.delta - b.delta);
  if (events.length === 0) return 0;
  let max = 0;
  let active = 0;
  for (const event of events) {
    active += event.delta;
    max = Math.max(max, active);
  }
  return max;
}

export function stackActivities(
  activities: RunActivity[],
  options: StackActivityOptions = {},
): ActivityStackLayout {
  const minMarkerWidthPct = options.minMarkerWidthPct ?? 0.35;
  const minSpanWidthPct = options.minSpanWidthPct ?? 0.75;
  const markerDurationMs = options.markerDurationMs ?? DEFAULT_MARKER_DURATION_MS;
  const timed = activities
    .map((activity) => toTimedActivity(activity, markerDurationMs))
    .sort(
      (a, b) =>
        a.startMs - b.startMs ||
        a.endMs - b.endMs ||
        a.activity.id.localeCompare(b.activity.id),
    );

  if (timed.length === 0) {
    return { items: [], rowCount: 0, startMs: 0, endMs: 0, maxConcurrency: 0 };
  }

  const startMs = Math.min(...timed.map((item) => item.startMs));
  const endMs = Math.max(...timed.map((item) => item.endMs));
  const spanMs = Math.max(1, endMs - startMs);
  const rowEnds: number[] = [];

  const items = timed.map(({ activity, startMs: itemStartMs, endMs: itemEndMs }) => {
    const row = firstFreeRow(rowEnds, itemStartMs);
    rowEnds[row] = itemEndMs;

    const leftPct = ((itemStartMs - startMs) / spanMs) * 100;
    const rawWidthPct = ((itemEndMs - itemStartMs) / spanMs) * 100;
    const widthPct = activity.isInstant
      ? Math.max(minMarkerWidthPct, rawWidthPct)
      : Math.max(minSpanWidthPct, rawWidthPct);

    return { activity, row, leftPct, widthPct };
  });

  const maxConcurrency = computeMaxSpanConcurrency(timed);

  return { items, rowCount: rowEnds.length, startMs, endMs, maxConcurrency };
}
