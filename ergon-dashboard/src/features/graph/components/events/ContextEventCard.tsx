import type { ReactNode } from "react";

type Tone = "amber" | "blue" | "green" | "gray" | "indigo" | "purple" | "red";

const TONE_STYLES: Record<Tone, { border: string; bg: string; pill: string; text: string }> = {
  amber: {
    border: "border-amber-200/80",
    bg: "bg-amber-50/80",
    pill: "bg-amber-100 text-amber-800 ring-amber-200",
    text: "text-amber-800",
  },
  blue: {
    border: "border-sky-200/80",
    bg: "bg-sky-50/80",
    pill: "bg-sky-100 text-sky-800 ring-sky-200",
    text: "text-sky-800",
  },
  green: {
    border: "border-emerald-200/80",
    bg: "bg-emerald-50/80",
    pill: "bg-emerald-100 text-emerald-800 ring-emerald-200",
    text: "text-emerald-800",
  },
  gray: {
    border: "border-[var(--line)]",
    bg: "bg-[var(--paper)]",
    pill: "bg-[var(--card)] text-[var(--muted)] ring-[var(--line)]",
    text: "text-[var(--muted)]",
  },
  indigo: {
    border: "border-indigo-200/80",
    bg: "bg-indigo-50/80",
    pill: "bg-indigo-100 text-indigo-800 ring-indigo-200",
    text: "text-indigo-800",
  },
  purple: {
    border: "border-purple-200/80",
    bg: "bg-purple-50/80",
    pill: "bg-purple-100 text-purple-800 ring-purple-200",
    text: "text-purple-800",
  },
  red: {
    border: "border-red-200/80",
    bg: "bg-red-50/80",
    pill: "bg-red-100 text-red-800 ring-red-200",
    text: "text-red-800",
  },
};

export function formatDuration(startedAt: string | null, completedAt: string | null): string | null {
  if (!startedAt || !completedAt) return null;
  const durationMs = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(durationMs) || durationMs < 0) return null;
  return `${Math.round(durationMs / 100) / 10}s`;
}

export function ContextEventCard({
  tone,
  title,
  subtitle,
  badge,
  duration,
  children,
  payloadLabel,
  payload,
}: {
  tone: Tone;
  title: string;
  subtitle?: string | null;
  badge?: string | null;
  duration?: string | null;
  children?: ReactNode;
  payloadLabel?: string;
  payload?: unknown;
}) {
  const styles = TONE_STYLES[tone];

  return (
    <article
      className={`rounded-[var(--radius-sm)] border ${styles.border} ${styles.bg} p-3 shadow-sm`}
      data-testid="workspace-action-card"
    >
      <div className="flex items-start justify-between gap-3" data-testid="workspace-action-summary">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] ring-1 ${styles.pill}`}>
              {title}
            </span>
            {badge && (
              <span className="max-w-[190px] truncate font-mono text-[11px] font-semibold text-[var(--ink)]" title={badge}>
                {badge}
              </span>
            )}
          </div>
          {subtitle && (
            <div className={`mt-1 truncate text-xs font-medium ${styles.text}`} title={subtitle}>
              {subtitle}
            </div>
          )}
        </div>
        {duration && (
          <span className="shrink-0 rounded-full bg-white/70 px-2 py-0.5 font-mono text-[10px] text-[var(--muted)] ring-1 ring-black/5">
            {duration}
          </span>
        )}
      </div>

      {children && <div className="mt-2 text-sm leading-5 text-[var(--ink)]">{children}</div>}

      {payloadLabel && (
        <details
          className="mt-2 rounded-[var(--radius-sm)] border border-black/5 bg-white/60 p-2"
          data-testid="workspace-action-payload"
        >
          <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--faint)]">
            {payloadLabel}
          </summary>
          <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-[var(--muted)]">
            {typeof payload === "string" ? payload : JSON.stringify(payload, null, 2)}
          </pre>
        </details>
      )}
    </article>
  );
}
