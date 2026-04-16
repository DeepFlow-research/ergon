"use client";

/**
 * UnifiedEventStream — a single chronological feed of every RunEvent the run
 * produced, with per-kind filtering and click-to-focus interactions.
 *
 * Prior to this component, the dashboard rendered task transitions, generation
 * turns, sandbox commands, thread messages, evaluations, and resources in six
 * different panels with six different layouts, and there was no single place to
 * answer "what happened and in what order?". The stream is a derivation of the
 * `WorkflowRunState` we already have — no new backend wiring required.
 */

import { useMemo, useState } from "react";

import {
  RUN_EVENT_KINDS,
  RUN_EVENT_KIND_COLORS,
  RUN_EVENT_KIND_LABELS,
  countEventsByKind,
  type RunEvent,
  type RunEventKind,
} from "@/lib/runEvents";
import { TransitionChip } from "@/components/common/TransitionChip";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      fractionalSecondDigits: 3,
    });
  } catch {
    return iso;
  }
}

function formatRelative(iso: string, anchorMs: number | null): string {
  if (anchorMs === null) return "";
  const t = new Date(iso).getTime();
  const delta = t - anchorMs;
  const sign = delta < 0 ? "-" : "+";
  const abs = Math.abs(delta);
  if (abs < 1000) return `${sign}${abs}ms`;
  if (abs < 60_000) return `${sign}${(abs / 1000).toFixed(2)}s`;
  return `${sign}${(abs / 60_000).toFixed(2)}m`;
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return `${s.slice(0, n - 1)}…`;
}

interface EventRowProps {
  event: RunEvent;
  anchorMs: number | null;
  isHighlighted: boolean;
  onTaskClick?: (taskId: string) => void;
  onSequenceClick?: (sequence: number) => void;
}

function EventRow({
  event,
  anchorMs,
  isHighlighted,
  onTaskClick,
  onSequenceClick,
}: EventRowProps) {
  const laneColor = RUN_EVENT_KIND_COLORS[event.kind];
  const label = RUN_EVENT_KIND_LABELS[event.kind];
  return (
    <li
      className={`group relative flex gap-3 rounded-lg border border-transparent px-2 py-1.5 transition-colors hover:border-slate-200 hover:bg-slate-50 dark:hover:border-slate-700 dark:hover:bg-slate-800/60 ${isHighlighted ? "border-indigo-300 bg-indigo-50/60 dark:border-indigo-500 dark:bg-indigo-500/10" : ""}`}
      data-testid={`event-row-${event.kind}`}
    >
      <span
        className={`mt-1 h-4 w-1 shrink-0 rounded-full ${laneColor}`}
        aria-hidden
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
          <span className="font-mono tabular-nums text-slate-600 dark:text-slate-300">
            {formatTime(event.at)}
          </span>
          {anchorMs !== null && (
            <span className="font-mono tabular-nums text-slate-400">
              {formatRelative(event.at, anchorMs)}
            </span>
          )}
          <span className="rounded-full border border-slate-200 bg-white px-1.5 py-0.5 font-medium uppercase tracking-wide text-[9px] text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
            {label}
          </span>
          {event.taskId && onTaskClick && (
            <button
              type="button"
              onClick={() => onTaskClick(event.taskId!)}
              className="rounded-full border border-slate-200 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 hover:border-indigo-300 hover:text-indigo-600 dark:border-slate-700 dark:text-slate-400"
              title="Focus this task in the graph"
            >
              task {event.taskId.slice(0, 8)}
            </button>
          )}
          {event.sequence !== null && event.sequence !== undefined && onSequenceClick && (
            <button
              type="button"
              onClick={() => onSequenceClick(event.sequence!)}
              className="rounded-full border border-slate-200 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 hover:border-indigo-300 hover:text-indigo-600 dark:border-slate-700 dark:text-slate-400"
              title="Jump to this sequence in the timeline"
            >
              seq {event.sequence}
            </button>
          )}
        </div>
        <EventBody event={event} />
      </div>
    </li>
  );
}

function EventBody({ event }: { event: RunEvent }) {
  switch (event.kind) {
    case "workflow.started":
      return (
        <div className="text-xs text-slate-600 dark:text-slate-300">
          Workflow <span className="font-semibold">{event.runName}</span> started.
        </div>
      );
    case "workflow.completed":
      return (
        <div className="text-xs text-slate-600 dark:text-slate-300">
          Workflow ended in <span className="font-semibold">{event.status}</span>
          {event.finalScore !== null && (
            <> with score <span className="font-mono">{event.finalScore.toFixed(3)}</span></>
          )}
          {event.error && <> — {truncate(event.error, 120)}</>}.
        </div>
      );
    case "task.transition":
      return (
        <div className="flex flex-wrap items-center gap-2">
          <TransitionChip
            compact
            from={event.from}
            to={event.to}
            trigger={event.trigger}
            reason={event.reason}
          />
          <span className="truncate text-xs text-slate-600 dark:text-slate-300">
            {event.taskName}
          </span>
        </div>
      );
    case "generation.turn":
      return (
        <div className="text-xs text-slate-600 dark:text-slate-300">
          Turn <span className="font-mono">{event.turnIndex}</span> on{" "}
          <span className="font-semibold">{event.workerName}</span>
          {event.toolCallCount > 0 && (
            <> — {event.toolCallCount} tool call{event.toolCallCount !== 1 ? "s" : ""}</>
          )}
          {event.toolNames.length > 0 && (
            <span className="ml-1 font-mono text-slate-500">
              [{event.toolNames.slice(0, 4).join(", ")}
              {event.toolNames.length > 4 && `, +${event.toolNames.length - 4}`}]
            </span>
          )}
        </div>
      );
    case "sandbox.created":
      return (
        <div className="text-xs text-slate-600 dark:text-slate-300">
          Sandbox <span className="font-mono">{event.sandboxId.slice(0, 8)}</span> created
          {event.template && <> from template <span className="font-mono">{event.template}</span></>}.
        </div>
      );
    case "sandbox.command":
      return (
        <div className="flex items-baseline gap-2 text-xs text-slate-600 dark:text-slate-300">
          <code className="truncate rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-200">
            $ {truncate(event.command, 160)}
          </code>
          {event.exitCode !== null && (
            <span className={`font-mono text-[10px] ${event.exitCode === 0 ? "text-emerald-600" : "text-rose-600"}`}>
              exit {event.exitCode}
            </span>
          )}
          {event.durationMs !== null && (
            <span className="font-mono text-[10px] text-slate-400">
              {event.durationMs}ms
            </span>
          )}
        </div>
      );
    case "sandbox.closed":
      return (
        <div className="text-xs text-slate-600 dark:text-slate-300">
          Sandbox <span className="font-mono">{event.sandboxId.slice(0, 8)}</span> closed
          {event.closeReason && <> ({event.closeReason})</>}.
        </div>
      );
    case "thread.message":
      return (
        <div className="text-xs text-slate-600 dark:text-slate-300">
          <span className="font-semibold uppercase tracking-wide text-[10px] text-slate-500">
            {event.authorRole}
          </span>{" "}
          {truncate(event.preview, 160)}
        </div>
      );
    case "task.evaluation":
      return (
        <div className="text-xs text-slate-600 dark:text-slate-300">
          Evaluation{" "}
          {event.passed === null ? (
            "recorded"
          ) : event.passed ? (
            <span className="text-emerald-600 dark:text-emerald-400">passed</span>
          ) : (
            <span className="text-rose-600 dark:text-rose-400">failed</span>
          )}
          {event.score !== null && (
            <> — score <span className="font-mono">{event.score.toFixed(3)}</span></>
          )}
          .
        </div>
      );
    case "resource.published":
      return (
        <div className="text-xs text-slate-600 dark:text-slate-300">
          Resource <span className="font-semibold">{event.name}</span>{" "}
          <span className="font-mono text-slate-500">({event.mimeType}, {event.sizeBytes}B)</span>
        </div>
      );
    case "context.event":
      return (
        <div className="text-xs text-slate-600 dark:text-slate-300">
          {truncate(event.summary, 160)}
        </div>
      );
    case "unhandled.mutation":
      return (
        <div className="text-xs text-rose-600 dark:text-rose-400">
          Dropped <span className="font-mono">{event.mutationType}</span> — {event.note}
        </div>
      );
  }
}

export interface UnifiedEventStreamProps {
  events: RunEvent[];
  /** Anchor used for relative offsets; defaults to first event's wall-clock. */
  anchor?: string | null;
  /** When set, rows for this task are highlighted. */
  highlightedTaskId?: string | null;
  onTaskClick?: (taskId: string) => void;
  onSequenceClick?: (sequence: number) => void;
  /** Initial per-kind filter; absent kinds default to enabled. */
  initialEnabledKinds?: Partial<Record<RunEventKind, boolean>>;
  /** Cap rows rendered at once; oldest truncated with a "show more" toggle. */
  maxRows?: number;
}

export function UnifiedEventStream({
  events,
  anchor,
  highlightedTaskId,
  onTaskClick,
  onSequenceClick,
  initialEnabledKinds,
  maxRows = 500,
}: UnifiedEventStreamProps) {
  const [enabledKinds, setEnabledKinds] = useState<Record<RunEventKind, boolean>>(
    () =>
      Object.fromEntries(
        RUN_EVENT_KINDS.map((k) => [k, initialEnabledKinds?.[k] ?? true]),
      ) as Record<RunEventKind, boolean>,
  );
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);

  const counts = useMemo(() => countEventsByKind(events), [events]);
  const anchorMs = useMemo(() => {
    if (anchor) return new Date(anchor).getTime();
    if (events.length === 0) return null;
    return new Date(events[0].at).getTime();
  }, [anchor, events]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return events.filter((e) => {
      if (!enabledKinds[e.kind]) return false;
      if (!q) return true;
      // cheap full-text: label + JSON of event fields
      const hay = `${RUN_EVENT_KIND_LABELS[e.kind]} ${JSON.stringify(e)}`.toLowerCase();
      return hay.includes(q);
    });
  }, [events, enabledKinds, query]);

  const visible = showAll ? filtered : filtered.slice(-maxRows);
  const hiddenCount = filtered.length - visible.length;

  return (
    <div
      className="flex min-h-0 flex-col gap-3 rounded-3xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
      data-testid="unified-event-stream"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Event stream
        </h2>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {filtered.length} / {events.length}
        </span>
        <div className="flex-1" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter events…"
          className="w-48 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          data-testid="event-stream-search"
        />
      </div>

      <div className="flex flex-wrap gap-1.5" data-testid="event-stream-filters">
        {RUN_EVENT_KINDS.map((kind) => {
          const on = enabledKinds[kind];
          const count = counts[kind];
          const tone = RUN_EVENT_KIND_COLORS[kind];
          return (
            <button
              key={kind}
              type="button"
              onClick={() =>
                setEnabledKinds((prev) => ({ ...prev, [kind]: !prev[kind] }))
              }
              disabled={count === 0}
              className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-opacity ${on ? "border-slate-300 bg-white text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200" : "border-slate-200 bg-slate-50 text-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-500"} ${count === 0 ? "opacity-40" : ""} disabled:cursor-default`}
              data-testid={`event-stream-filter-${kind}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${tone}`} aria-hidden />
              <span className="uppercase tracking-wide">
                {RUN_EVENT_KIND_LABELS[kind]}
              </span>
              <span className="font-mono tabular-nums text-slate-500">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-auto pr-1">
        {visible.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-6 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-400">
            No events match the current filter.
          </div>
        ) : (
          <>
            {hiddenCount > 0 && (
              <div className="mb-2 flex items-center justify-between rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-1.5 text-[11px] text-slate-500 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-400">
                <span>
                  {hiddenCount} earlier event{hiddenCount !== 1 ? "s" : ""} hidden
                </span>
                <button
                  type="button"
                  className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                  onClick={() => setShowAll(true)}
                >
                  Show all
                </button>
              </div>
            )}
            <ol className="space-y-1" data-testid="event-stream-list">
              {visible.map((event) => (
                <EventRow
                  key={event.id}
                  event={event}
                  anchorMs={anchorMs}
                  isHighlighted={
                    !!highlightedTaskId && event.taskId === highlightedTaskId
                  }
                  onTaskClick={onTaskClick}
                  onSequenceClick={onSequenceClick}
                />
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  );
}
