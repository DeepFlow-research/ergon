"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";

import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import { stackActivities } from "@/features/activity/stackLayout";
import type { ActivityKind, RunActivity } from "@/features/activity/types";
import { ActivityBar, activityKindLabel } from "./ActivityBar";

interface ActivityStackTimelineProps {
  activities: RunActivity[];
  mutations: GraphMutationDto[];
  currentSequence: number;
  selectedTaskId: string | null;
  selectedActivityId: string | null;
  isPlaying: boolean;
  speed: number;
  onSequenceChange: (sequence: number) => void;
  onTogglePlay: () => void;
  onSpeedChange: (speed: number) => void;
  onActivityClick: (activity: RunActivity) => void;
}

const SPEED_OPTIONS = [1, 2, 5, 10] as const;
const MIN_DELAY_MS = 50;
const MAX_DELAY_MS = 2000;
const ROW_HEIGHT = 31;

function formatTime(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  return new Date(ms).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function countByKind(activities: RunActivity[]): Record<ActivityKind, number> {
  const counts = {
    execution: 0,
    graph: 0,
    message: 0,
    artifact: 0,
    evaluation: 0,
    context: 0,
    sandbox: 0,
  } satisfies Record<ActivityKind, number>;
  for (const activity of activities) counts[activity.kind] += 1;
  return counts;
}

export function ActivityStackTimeline({
  activities,
  mutations,
  currentSequence,
  selectedTaskId,
  selectedActivityId,
  isPlaying,
  speed,
  onSequenceChange,
  onTogglePlay,
  onSpeedChange,
  onActivityClick,
}: ActivityStackTimelineProps) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentSequenceRef = useRef(currentSequence);
  currentSequenceRef.current = currentSequence;

  const layout = useMemo(() => stackActivities(activities), [activities]);
  const counts = useMemo(() => countByKind(activities), [activities]);
  const maxSequence = mutations.length > 0 ? mutations[mutations.length - 1].sequence : 0;
  const minSequence = mutations.length > 0 ? mutations[0].sequence : 0;
  const currentMutation = mutations.find((mutation) => mutation.sequence === currentSequence);

  const stepForward = useCallback(() => {
    const idx = mutations.findIndex((mutation) => mutation.sequence === currentSequenceRef.current);
    if (idx >= 0 && idx < mutations.length - 1) {
      onSequenceChange(mutations[idx + 1].sequence);
    }
  }, [mutations, onSequenceChange]);

  const stepBack = useCallback(() => {
    const idx = mutations.findIndex((mutation) => mutation.sequence === currentSequenceRef.current);
    if (idx > 0) {
      onSequenceChange(mutations[idx - 1].sequence);
    }
  }, [mutations, onSequenceChange]);

  useEffect(() => {
    if (!isPlaying || mutations.length === 0) return;

    const scheduleNext = () => {
      const idx = mutations.findIndex((mutation) => mutation.sequence === currentSequenceRef.current);
      if (idx < 0 || idx >= mutations.length - 1) {
        onTogglePlay();
        return;
      }
      const currentTime = Date.parse(mutations[idx].created_at);
      const nextTime = Date.parse(mutations[idx + 1].created_at);
      const rawDelay = (nextTime - currentTime) / speed;
      const delayMs = Math.max(MIN_DELAY_MS, Math.min(MAX_DELAY_MS, rawDelay));
      timerRef.current = setTimeout(() => {
        onSequenceChange(mutations[idx + 1].sequence);
        scheduleNext();
      }, delayMs);
    };

    scheduleNext();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [isPlaying, mutations, onSequenceChange, onTogglePlay, speed]);

  if (activities.length === 0) {
    return (
      <div
        className="flex h-[236px] items-center justify-center bg-[#070b12] text-sm text-slate-400"
        data-testid="activity-stack-region"
      >
        No activity has been recorded for this run yet.
      </div>
    );
  }

  return (
    <div className="relative h-[236px] bg-[#070b12] text-slate-200" data-testid="activity-stack-region">
      <div className="flex h-11 items-center justify-between border-b border-white/10 px-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">
            Activity stack <span className="ml-2 font-normal normal-case tracking-normal text-slate-500">rows are overlap layers, not fixed lanes</span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-3 font-mono text-[10px] text-slate-500">
            <span data-testid="activity-current-sequence">
              seq {currentMutation?.sequence ?? currentSequence}
            </span>
            <span>{formatTime(layout.startMs)} - {formatTime(layout.endMs)}</span>
            <span>max concurrency {layout.maxConcurrency}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={stepBack}
            disabled={currentSequence <= minSequence}
            className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-white/10 disabled:opacity-35"
            data-testid="activity-step-back"
          >
            Back
          </button>
          <button
            type="button"
            onClick={onTogglePlay}
            className="rounded-md bg-white px-3 py-1 text-xs font-semibold text-[#070b12] hover:bg-slate-200"
            data-testid="activity-play-toggle"
            aria-label={isPlaying ? "Pause timeline" : "Play timeline"}
          >
            {isPlaying ? "Pause" : "Play"}
          </button>
          <button
            type="button"
            onClick={stepForward}
            disabled={currentSequence >= maxSequence}
            className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-white/10 disabled:opacity-35"
            data-testid="activity-step-forward"
          >
            Next
          </button>
          <select
            value={speed}
            onChange={(event) => onSpeedChange(Number(event.target.value))}
            className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-300"
            data-testid="activity-speed-control"
            aria-label="Timeline playback speed"
          >
            {SPEED_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}x
              </option>
            ))}
          </select>
        </div>
      </div>

      {mutations.length > 0 && (
        <input
          type="range"
          min={minSequence}
          max={maxSequence}
          value={currentSequence}
          onChange={(event) => onSequenceChange(Number(event.target.value))}
          className="mx-4 mt-2 h-1.5 w-[calc(100%-2rem)] cursor-pointer appearance-none rounded-full bg-white/10 accent-indigo-400"
          aria-label="Run timeline sequence"
        />
      )}

      <div className="absolute bottom-4 left-28 right-[430px] z-10 flex flex-wrap gap-2 text-[10px]">
        {(Object.keys(counts) as ActivityKind[]).map((kind) => (
          <span
            key={kind}
            className="rounded-full border border-white/10 bg-white/5 px-2 py-1 font-semibold uppercase tracking-wide text-slate-400"
          >
            {activityKindLabel(kind)} {counts[kind]}
          </span>
        ))}
      </div>

      <div className="relative mx-4 mt-3 h-[148px] overflow-hidden border-y border-white/10 bg-[radial-gradient(circle,rgb(148_163_184/0.08)_1px,transparent_1px)] [background-size:20px_20px]">
        <div className="absolute left-0 top-2 w-24 text-[11px] font-semibold leading-snug text-slate-400">
          Concurrent activity<br />
          <span className="font-normal text-slate-600">Bars stack only when they overlap</span>
        </div>
        <div
          className="relative ml-28 min-w-[720px]"
          style={{ height: Math.max(1, layout.rowCount) * ROW_HEIGHT }}
        >
          {Array.from({ length: layout.rowCount }).map((_, row) => (
            <div
              key={row}
              className="absolute left-0 right-0 border-t border-white/10"
              style={{ top: row * ROW_HEIGHT }}
              data-testid="activity-stack-row"
            />
          ))}
          {layout.items.map((item) => (
            <div
              key={item.activity.id}
              className="absolute left-0 right-0"
              style={{ top: item.row * ROW_HEIGHT }}
            >
              <ActivityBar
                item={item}
                selected={item.activity.id === selectedActivityId}
                highlighted={Boolean(selectedTaskId && item.activity.taskId === selectedTaskId)}
                onClick={onActivityClick}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
