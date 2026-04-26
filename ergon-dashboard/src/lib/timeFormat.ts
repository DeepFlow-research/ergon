export function formatClockTime(value: string | number | Date): string {
  return formatDateTime(value, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatClockTimeMs(value: string | number | Date): string {
  return formatDateTime(value, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  });
}

export function formatClockTimeSeconds(value: string | number | Date): string {
  return formatDateTime(value, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatDate(value: string | number | Date): string {
  return formatDateTime(value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function formatDateTime(value: string | number | Date, options: Intl.DateTimeFormatOptions): string {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";

  return new Intl.DateTimeFormat("en-GB", {
    ...options,
    hour12: false,
    timeZone: "UTC",
  }).format(date);
}
