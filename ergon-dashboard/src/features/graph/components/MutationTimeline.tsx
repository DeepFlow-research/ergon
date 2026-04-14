"use client";

import { useCallback, useEffect, useRef } from "react";
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

  const maxSequence =
    mutations.length > 0 ? mutations[mutations.length - 1].sequence : 0;
  const minSequence = mutations.length > 0 ? mutations[0].sequence : 0;

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

  return (
    <div className="flex flex-col gap-3">
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
