"use client";

/**
 * RunListPanel - Displays a list of workflow runs.
 *
 * Groups runs into "Active" (running) and "Recent" (completed/failed) sections.
 * Clicking a run navigates to the DAG view at /run/[runId].
 */

import { useRouter } from "next/navigation";
import { useRuns, RunSummary } from "@/hooks/useRuns";
import { StatusBadge } from "@/components/common/StatusBadge";

/**
 * Format duration in seconds to a human-readable string.
 */
function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";

  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);

  if (minutes < 60) {
    return remainingSeconds > 0
      ? `${minutes}m ${remainingSeconds}s`
      : `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

/**
 * Format timestamp to relative time (e.g., "2 min ago").
 */
function formatRelativeTime(timestamp: string): string {
  const now = new Date();
  const time = new Date(timestamp);
  const diffMs = now.getTime() - time.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);

  if (diffSeconds < 60) return "just now";
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
  return `${Math.floor(diffSeconds / 86400)}d ago`;
}

interface RunRowProps {
  run: RunSummary;
  onClick: () => void;
}

function RunRow({ run, onClick }: RunRowProps) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors border-b border-gray-100 dark:border-gray-800 last:border-b-0 group"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate group-hover:text-blue-600 dark:group-hover:text-blue-400">
              {run.name}
            </h3>
            <StatusBadge status={run.status} size="sm" />
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5 truncate font-mono">
            {run.id.slice(0, 8)}...
          </p>
        </div>

        <div className="flex items-center gap-6 text-sm text-gray-500 dark:text-gray-400">
          {/* Duration */}
          <div className="text-right">
            <div className="font-medium text-gray-700 dark:text-gray-300">
              {run.status === "running"
                ? "Running..."
                : formatDuration(run.durationSeconds)}
            </div>
            <div className="text-xs">
              {formatRelativeTime(run.completedAt || run.startedAt)}
            </div>
          </div>

          {/* Score (if available) */}
          {run.finalScore !== null && (
            <div className="text-right">
              <div className="font-medium text-gray-700 dark:text-gray-300">
                {(run.finalScore * 100).toFixed(1)}%
              </div>
              <div className="text-xs">score</div>
            </div>
          )}

          {/* Arrow indicator */}
          <svg
            className="w-5 h-5 text-gray-400 group-hover:text-blue-500 transition-colors"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5l7 7-7 7"
            />
          </svg>
        </div>
      </div>

      {/* Error message if failed */}
      {run.error && (
        <p className="mt-2 text-sm text-red-600 dark:text-red-400 truncate">
          {run.error}
        </p>
      )}
    </button>
  );
}

interface RunSectionProps {
  title: string;
  runs: RunSummary[];
  emptyMessage: string;
  onRunClick: (runId: string) => void;
}

function RunSection({ title, runs, emptyMessage, onRunClick }: RunSectionProps) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg shadow-sm border border-gray-200 dark:border-gray-800 overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
        <h2 className="font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
          {title}
          <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
            ({runs.length})
          </span>
        </h2>
      </div>

      {runs.length === 0 ? (
        <div className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
          {emptyMessage}
        </div>
      ) : (
        <div className="divide-y divide-gray-100 dark:divide-gray-800">
          {runs.map((run) => (
            <RunRow key={run.id} run={run} onClick={() => onRunClick(run.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

export function RunListPanel() {
  const router = useRouter();
  const { activeRuns, completedRuns, isLoading, error } = useRuns();

  const handleRunClick = (runId: string) => {
    router.push(`/run/${runId}`);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-gray-500 dark:text-gray-400">
          <svg
            className="animate-spin h-5 w-5"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span>Connecting to server...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Connection error banner */}
      {error && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg px-4 py-3 text-yellow-700 dark:text-yellow-400">
          <div className="flex items-center gap-2">
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Active Runs */}
      <RunSection
        title="Active Runs"
        runs={activeRuns}
        emptyMessage="No active runs. Start a workflow to see it here."
        onRunClick={handleRunClick}
      />

      {/* Recent Runs */}
      <RunSection
        title="Recent Runs"
        runs={completedRuns}
        emptyMessage="No completed runs yet."
        onRunClick={handleRunClick}
      />
    </div>
  );
}
