export interface MetricDisplay {
  value: string;
  detail: string | null;
  isUnavailable: boolean;
}

export function unavailableMetric(detail: string): MetricDisplay {
  return {
    value: "Unavailable",
    detail,
    isUnavailable: true,
  };
}

function availableMetric(value: string, detail: string | null = null): MetricDisplay {
  return {
    value,
    detail,
    isUnavailable: false,
  };
}

export function formatScore(value: number | null | undefined): MetricDisplay {
  if (value == null) return unavailableMetric("score not reported");
  return availableMetric(`${(value * 100).toFixed(1)}%`);
}

export function formatCost(
  value: number | null | undefined,
  observed: boolean | null | undefined,
): MetricDisplay {
  if (!observed || value == null) return unavailableMetric("provider did not report cost");
  if (value > 0 && value < 1) return availableMetric(`$${value.toFixed(4)}`);
  return availableMetric(
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value),
  );
}

export function formatTokens(value: number | null | undefined): MetricDisplay {
  if (value == null) return unavailableMetric("provider did not report tokens");
  if (value < 1000) return availableMetric(String(value));
  if (value < 1_000_000) return availableMetric(`${(value / 1000).toFixed(1)}K`);
  return availableMetric(`${(value / 1_000_000).toFixed(1)}M`);
}

export function formatDuration(value: number | null | undefined): MetricDisplay {
  if (value == null) return unavailableMetric("duration not reported");
  if (value < 60) return availableMetric(`${Math.max(0, value).toFixed(1)}s`);
  const totalSeconds = Math.round(value);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return availableMetric(`${minutes}m ${seconds}s`);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return availableMetric(`${hours}h ${remainingMinutes}m`);
}

export function formatTaskCount({
  completed,
  running,
  failed,
  total,
}: {
  completed: number;
  running: number;
  failed: number;
  total: number;
}): MetricDisplay {
  if (total <= 0) return unavailableMetric("tasks not reported");
  const detailParts = [
    running > 0 ? `${running} running` : null,
    failed > 0 ? `${failed} failed` : null,
  ].filter((part): part is string => part !== null);
  return availableMetric(`${completed} / ${total}`, detailParts.join(" · ") || "completed tasks");
}
