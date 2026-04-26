import type { ActivityBand, ActivityStackLayout, RunActivity } from "./types";

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
const DEFAULT_MIN_MARKER_WIDTH_PCT = 1.6;
const ROW_GUTTER_PCT = 0.15;
export const ACTIVITY_BAND_ORDER: ActivityBand[] = [
  "work",
  "graph",
  "tools",
  "communication",
  "outputs",
];

function firstFreeRow(rowEnds: number[], start: number): number {
  const row = rowEnds.findIndex((end) => end <= start);
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
  const minMarkerWidthPct = options.minMarkerWidthPct ?? DEFAULT_MIN_MARKER_WIDTH_PCT;
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
    return { items: [], bands: [], rowCount: 0, startMs: 0, endMs: 0, maxConcurrency: 0 };
  }

  const startMs = Math.min(...timed.map((item) => item.startMs));
  const endMs = Math.max(...timed.map((item) => item.endMs));
  const spanMs = Math.max(1, endMs - startMs);
  const items = [];
  const bands = [];

  for (const band of ACTIVITY_BAND_ORDER) {
    const bandTimed = timed.filter((item) => item.activity.band === band);
    if (bandTimed.length === 0) continue;

    const rowEnds: number[] = [];
    const bandItems = bandTimed.map(({ activity, startMs: itemStartMs, endMs: itemEndMs }) => {
      const leftPct = ((itemStartMs - startMs) / spanMs) * 100;
      const rawWidthPct = ((itemEndMs - itemStartMs) / spanMs) * 100;
      const widthPct = Math.max(
        activity.isInstant ? minMarkerWidthPct : minSpanWidthPct,
        rawWidthPct,
      );
      const row = firstFreeRow(rowEnds, leftPct);
      rowEnds[row] = leftPct + widthPct + ROW_GUTTER_PCT;

      return { activity, row, leftPct, widthPct };
    });

    const rowCount = Math.max(1, rowEnds.length);
    bands.push({ band, rowCount });
    items.push(...bandItems);
  }

  const maxConcurrency = computeMaxSpanConcurrency(timed);
  const rowCount = bands.reduce((sum, band) => sum + band.rowCount, 0);

  return {
    items: items.sort(
      (a, b) =>
        ACTIVITY_BAND_ORDER.indexOf(a.activity.band) -
          ACTIVITY_BAND_ORDER.indexOf(b.activity.band) ||
        a.activity.startAt.localeCompare(b.activity.startAt) ||
        Number(a.activity.isInstant) - Number(b.activity.isInstant) ||
        a.activity.id.localeCompare(b.activity.id),
    ),
    bands,
    rowCount,
    startMs,
    endMs,
    maxConcurrency,
  };
}
