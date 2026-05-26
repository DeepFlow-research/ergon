import type { SampleEventView } from "@/lib/contracts/rest";
import React from "react";

export function SampleEvents({ events }: { events: SampleEventView[] }) {
  return (
    <section className="rounded-[var(--radius)] border border-[var(--line)] bg-[var(--card)] p-4">
      <h2 className="text-sm font-semibold text-[var(--ink)]">Event Stream</h2>
      <div className="mt-3 space-y-2">
        {events.map((event) => (
          <div
            key={event.eventId}
            className="grid gap-2 border-b border-[var(--line)] pb-2 text-sm last:border-0 last:pb-0 md:grid-cols-[170px_1fr_160px]"
          >
            <span className="font-mono text-xs text-[var(--muted)]">
              {new Date(event.timestamp).toLocaleString()}
            </span>
            <span className="font-medium text-[var(--ink)]">{event.eventType}</span>
            <span className="font-mono text-xs text-[var(--muted)]">{event.targetType}</span>
          </div>
        ))}
        {events.length === 0 ? <div className="text-sm text-[var(--muted)]">No events recorded.</div> : null}
      </div>
    </section>
  );
}
