/** Formats a duration in milliseconds for compact UI (run runtime, task wall time). */
export function formatDurationMs(durationMs: number | null | undefined): string {
  if (durationMs == null) return "—";
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;
  if (durationMs < 60_000) return `${(durationMs / 1000).toFixed(1)}s`;
  return `${(durationMs / 60_000).toFixed(1)}m`;
}
