"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";

interface MutationTimelineProps {
  mutations: GraphMutationDto[];
  currentSequence: number;
  onSequenceChange: (sequence: number) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  speed: number;
  onSpeedChange: (speed: number) => void;
}

/**
 * Tailwind background token per mutation type. We expose this alongside the
 * slider so the user can see the *distribution* of mutations (adds vs status
 * changes vs removals) at a glance, not just the current sequence.
 */
const MUTATION_TYPE_COLORS: Record<string, string> = {
  "node.added": "bg-sky-500",
  "node.removed": "bg-rose-500",
  "node.status_changed": "bg-indigo-500",
  "node.field_changed": "bg-purple-500",
  "edge.added": "bg-emerald-500",
  "edge.removed": "bg-rose-400",
  "edge.status_changed": "bg-emerald-400",
  "annotation.set": "bg-amber-500",
  "annotation.deleted": "bg-amber-300",
};

function colorFor(mutationType: string): string {
  return MUTATION_TYPE_COLORS[mutationType] ?? "bg-slate-400";
}

const SPEED_OPTIONS = [1, 2, 5, 10] as const;
const MIN_DELAY_MS = 50;
const MAX_DELAY_MS = 2000;

export function MutationTimeline({
  mutations,
  currentSequence,
  onSequenceChange,
  isPlaying,
  onTogglePlay,
  speed,
  onSpeedChange,
}: MutationTimelineProps) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentSequenceRef = useRef(currentSequence);
  currentSequenceRef.current = currentSequence;
  const [hoverInfo, setHoverInfo] = useState<{
    sequence: number;
    type: string;
    actor: string;
    reason: string | null;
  } | null>(null);

  const maxSequence =
    mutations.length > 0 ? mutations[mutations.length - 1].sequence : 0;
  const minSequence = mutations.length > 0 ? mutations[0].sequence : 0;

  // Per-type counts so the user can see what kind of activity dominated.
  const typeCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const m of mutations) c[m.mutation_type] = (c[m.mutation_type] ?? 0) + 1;
    return c;
  }, [mutations]);

  const currentIndex = mutations.findIndex(
    (m) => m.sequence === currentSequence,
  );
  const currentMutation = currentIndex >= 0 ? mutations[currentIndex] : null;

  const stepForward = useCallback(() => {
    const idx = mutations.findIndex(
      (m) => m.sequence === currentSequenceRef.current,
    );
    if (idx < mutations.length - 1) {
      onSequenceChange(mutations[idx + 1].sequence);
    }
  }, [mutations, onSequenceChange]);

  const stepBack = useCallback(() => {
    const idx = mutations.findIndex(
      (m) => m.sequence === currentSequenceRef.current,
    );
    if (idx > 0) {
      onSequenceChange(mutations[idx - 1].sequence);
    }
  }, [mutations, onSequenceChange]);

  // Auto-play with wall-clock proportional timing
  useEffect(() => {
    if (!isPlaying || mutations.length === 0) return;

    function scheduleNext() {
      const idx = mutations.findIndex(
        (m) => m.sequence === currentSequenceRef.current,
      );
      if (idx < 0 || idx >= mutations.length - 1) {
        onTogglePlay();
        return;
      }

      const currentTime = new Date(mutations[idx].created_at).getTime();
      const nextTime = new Date(mutations[idx + 1].created_at).getTime();
      const rawDelay = (nextTime - currentTime) / speed;
      const delayMs = Math.max(
        MIN_DELAY_MS,
        Math.min(MAX_DELAY_MS, rawDelay),
      );

      timerRef.current = setTimeout(() => {
        onSequenceChange(mutations[idx + 1].sequence);
        scheduleNext();
      }, delayMs);
    }

    scheduleNext();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [isPlaying, mutations, speed, onSequenceChange, onTogglePlay]);

  if (mutations.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-gray-400 dark:text-gray-500">
        No mutations recorded for this run.
      </div>
    );
  }

  const formattedTime = currentMutation
    ? new Date(currentMutation.created_at).toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        fractionalSecondDigits: 3,
      })
    : "—";

  const seqSpan = Math.max(1, maxSequence - minSequence);

  return (
    <div className="flex flex-col gap-3">
      {/* Lane strip: one tick per mutation, colored by kind. Clicking jumps
          to that sequence, making the strip a direct nav control. */}
      <div
        className="relative h-4 w-full overflow-hidden rounded-md bg-slate-100 dark:bg-slate-800"
        data-testid="mutation-lane-strip"
      >
        {mutations.map((m) => {
          const leftPct = ((m.sequence - minSequence) / seqSpan) * 100;
          const active = m.sequence === currentSequence;
          return (
            <button
              key={m.sequence}
              type="button"
              onClick={() => onSequenceChange(m.sequence)}
              onMouseEnter={() =>
                setHoverInfo({
                  sequence: m.sequence,
                  type: m.mutation_type,
                  actor: m.actor,
                  reason: m.reason,
                })
              }
              onMouseLeave={() => setHoverInfo(null)}
              className={`absolute top-0 h-full w-[2px] ${colorFor(m.mutation_type)} ${active ? "ring-2 ring-indigo-500" : "opacity-70 hover:opacity-100"}`}
              style={{ left: `${leftPct}%` }}
              title={`seq ${m.sequence} — ${m.mutation_type}`}
              aria-label={`Jump to sequence ${m.sequence} (${m.mutation_type})`}
            />
          );
        })}
      </div>

      {/* Legend: how many of each kind are in this run. */}
      <div className="flex flex-wrap gap-1.5 text-[10px]">
        {Object.entries(typeCounts).map(([type, count]) => (
          <span
            key={type}
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-1.5 py-0.5 font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300"
          >
            <span className={`h-1.5 w-1.5 rounded-full ${colorFor(type)}`} aria-hidden />
            <span className="font-mono uppercase tracking-wide">{type}</span>
            <span className="font-mono tabular-nums text-slate-400">{count}</span>
          </span>
        ))}
      </div>

      {hoverInfo && (
        <div className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
          seq {hoverInfo.sequence} · <span className="font-semibold">{hoverInfo.type}</span> · {hoverInfo.actor}
          {hoverInfo.reason ? ` — ${hoverInfo.reason}` : ""}
        </div>
      )}

      {/* Slider */}
      <div className="flex items-center gap-3">
        <span className="min-w-[4rem] text-right font-mono text-xs text-gray-500 dark:text-gray-400">
          seq {currentMutation?.sequence ?? 0}
        </span>
        <input
          type="range"
          min={minSequence}
          max={maxSequence}
          value={currentSequence}
          onChange={(e) => onSequenceChange(Number(e.target.value))}
          className="h-2 flex-1 cursor-pointer appearance-none rounded-lg bg-gray-200 accent-blue-600 dark:bg-gray-700 dark:accent-blue-400"
        />
        <span className="min-w-[4rem] font-mono text-xs text-gray-500 dark:text-gray-400">
          / {maxSequence}
        </span>
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Step back */}
        <button
          onClick={stepBack}
          disabled={currentSequence <= minSequence}
          className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          title="Step back"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {/* Play/Pause */}
        <button
          onClick={onTogglePlay}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          title={isPlaying ? "Pause" : "Play"}
        >
          {isPlaying ? (
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="4" width="4" height="16" rx="1" />
              <rect x="14" y="4" width="4" height="16" rx="1" />
            </svg>
          ) : (
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>

        {/* Step forward */}
        <button
          onClick={stepForward}
          disabled={currentSequence >= maxSequence}
          className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          title="Step forward"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>

        {/* Divider */}
        <div className="h-6 w-px bg-gray-200 dark:bg-gray-700" />

        {/* Speed selector */}
        <div className="flex items-center gap-1">
          {SPEED_OPTIONS.map((s) => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={`rounded-md px-2 py-1 text-xs font-medium transition-colors ${
                speed === s
                  ? "bg-blue-600 text-white dark:bg-blue-500"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        {/* Divider */}
        <div className="h-6 w-px bg-gray-200 dark:bg-gray-700" />

        {/* Jump to end */}
        <button
          onClick={() => onSequenceChange(maxSequence)}
          className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
          title="Jump to end"
        >
          Jump to end
        </button>

        {/* Timestamp */}
        <span className="ml-auto font-mono text-xs text-gray-500 dark:text-gray-400">
          {formattedTime}
        </span>
      </div>

      {/* Current mutation detail */}
      {currentMutation && (
        <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 font-mono text-xs text-gray-600 dark:border-gray-800 dark:bg-gray-800/50 dark:text-gray-400">
          <span className="font-semibold text-gray-900 dark:text-gray-200">
            [{currentMutation.mutation_type}]
          </span>{" "}
          actor:{" "}
          <span className="text-blue-600 dark:text-blue-400">
            {currentMutation.actor}
          </span>
          {currentMutation.reason && (
            <>
              {" "}
              &mdash; &ldquo;
              <span className="italic">{currentMutation.reason}</span>&rdquo;
            </>
          )}
          {" "}&mdash; target:{" "}
          <span className="text-purple-600 dark:text-purple-400">
            {currentMutation.target_id.slice(0, 8)}
          </span>
        </div>
      )}
    </div>
  );
}
