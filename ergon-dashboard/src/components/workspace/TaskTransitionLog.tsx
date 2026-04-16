"use client";

/**
 * TaskTransitionLog — chronological list of every status change for the
 * selected task, with triggers and inter-transition gap timing.
 *
 * This replaces the old situation where the TaskWorkspace only exposed
 * `startedAt` and `completedAt` — no visibility into pending→ready, the dwell
 * time in READY, or which transitions happened in which order on retries.
 */

import type { TaskState } from "@/lib/types";
import { TransitionChip } from "@/components/common/TransitionChip";

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)}s`;
  return `${(ms / 60_000).toFixed(2)}m`;
}

export function TaskTransitionLog({
  task,
  onJumpToSequence,
}: {
  task: TaskState;
  onJumpToSequence?: (sequence: number) => void;
}) {
  const history = task.history ?? [];
  if (history.length === 0) {
    return (
      <div
        className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-center text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-400"
        data-testid="task-transitions-empty"
      >
        No transitions recorded yet. This task has not changed state since it
        was observed.
      </div>
    );
  }

  return (
    <ol
      className="space-y-2"
      data-testid="task-transition-log"
    >
      {history.map((h, i) => {
        const prev = history[i - 1];
        const gapMs = prev
          ? new Date(h.at).getTime() - new Date(prev.at).getTime()
          : null;
        return (
          <li
            key={`${h.at}-${i}`}
            className="flex flex-wrap items-center gap-2"
          >
            <span className="w-5 text-right font-mono text-[10px] text-slate-400">
              {i + 1}.
            </span>
            <TransitionChip
              from={h.from}
              to={h.to}
              trigger={h.trigger}
              at={h.at}
              reason={h.reason}
            />
            {gapMs !== null && gapMs > 0 && (
              <span className="font-mono text-[10px] text-slate-400 dark:text-slate-500">
                held {formatDuration(gapMs)}
              </span>
            )}
            {h.actor && (
              <span className="text-[10px] text-slate-500 dark:text-slate-400">
                by {h.actor}
              </span>
            )}
            {h.sequence !== null && onJumpToSequence && (
              <button
                type="button"
                onClick={() => onJumpToSequence(h.sequence!)}
                className="rounded-full border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-500 transition-colors hover:border-indigo-300 hover:text-indigo-600 dark:border-slate-700 dark:text-slate-400 dark:hover:border-indigo-500 dark:hover:text-indigo-300"
                title={`Jump to mutation ${h.sequence} in the timeline`}
              >
                seq {h.sequence}
              </button>
            )}
          </li>
        );
      })}
    </ol>
  );
}
