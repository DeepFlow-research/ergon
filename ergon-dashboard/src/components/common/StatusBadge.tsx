"use client";

/**
 * StatusBadge - Color-coded status indicator for tasks and runs.
 *
 * Displays task status with appropriate colors:
 * - pending: gray
 * - ready: blue
 * - running: yellow (with pulse animation)
 * - completed: green
 * - failed: red
 */

import { ExperimentCohortStatus, RunLifecycleStatus, TaskStatus } from "@/lib/types";

// Status type includes TaskStatus enum values and run-level status strings
// Note: TaskStatus.RUNNING = "running", TaskStatus.COMPLETED = "completed", etc.
// So "running" | "completed" | "failed" are already covered by TaskStatus
type StatusType = TaskStatus | RunLifecycleStatus | ExperimentCohortStatus;

interface StatusBadgeProps {
  status: StatusType;
  size?: "sm" | "md";
  showLabel?: boolean;
}

interface StatusConfig {
  bg: string;
  text: string;
  ring: string;
  label: string;
  animate?: boolean;
  color: string;
}

const statusConfig: Record<string, StatusConfig> = {
  [TaskStatus.PENDING]: {
    bg: "bg-gray-100 dark:bg-gray-800",
    text: "text-gray-600 dark:text-gray-400",
    ring: "ring-gray-200 dark:ring-gray-700",
    label: "Pending",
    color: "#9ca3af",
  },
  [TaskStatus.READY]: {
    bg: "bg-blue-100 dark:bg-blue-900/30",
    text: "text-blue-600 dark:text-blue-400",
    ring: "ring-blue-200 dark:ring-blue-800",
    label: "Ready",
    color: "#3b82f6",
  },
  [TaskStatus.RUNNING]: {
    bg: "bg-yellow-100 dark:bg-yellow-900/30",
    text: "text-yellow-700 dark:text-yellow-400",
    ring: "ring-yellow-200 dark:ring-yellow-800",
    label: "Running",
    animate: true,
    color: "#eab308",
  },
  [TaskStatus.COMPLETED]: {
    bg: "bg-green-100 dark:bg-green-900/30",
    text: "text-green-600 dark:text-green-400",
    ring: "ring-green-200 dark:ring-green-800",
    label: "Completed",
    color: "#22c55e",
  },
  [TaskStatus.FAILED]: {
    bg: "bg-red-100 dark:bg-red-900/30",
    text: "text-red-600 dark:text-red-400",
    ring: "ring-red-200 dark:ring-red-800",
    label: "Failed",
    color: "#ef4444",
  },
  executing: {
    bg: "bg-yellow-100 dark:bg-yellow-900/30",
    text: "text-yellow-700 dark:text-yellow-400",
    ring: "ring-yellow-200 dark:ring-yellow-800",
    label: "Executing",
    animate: true,
    color: "#eab308",
  },
  evaluating: {
    bg: "bg-violet-100 dark:bg-violet-900/30",
    text: "text-violet-700 dark:text-violet-400",
    ring: "ring-violet-200 dark:ring-violet-800",
    label: "Evaluating",
    animate: true,
    color: "#8b5cf6",
  },
  active: {
    bg: "bg-blue-100 dark:bg-blue-900/30",
    text: "text-blue-700 dark:text-blue-400",
    ring: "ring-blue-200 dark:ring-blue-800",
    label: "Active",
    color: "#3b82f6",
  },
  archived: {
    bg: "bg-gray-100 dark:bg-gray-800",
    text: "text-gray-600 dark:text-gray-400",
    ring: "ring-gray-200 dark:ring-gray-700",
    label: "Archived",
    color: "#9ca3af",
  },
};

// Default config for unknown statuses
const defaultConfig: StatusConfig = {
  bg: "bg-gray-100 dark:bg-gray-800",
  text: "text-gray-600 dark:text-gray-400",
  ring: "ring-gray-200 dark:ring-gray-700",
  label: "Unknown",
  color: "#9ca3af",
};

export function StatusBadge({
  status,
  size = "md",
  showLabel = true,
}: StatusBadgeProps) {
  const config = statusConfig[status] || defaultConfig;

  const sizeClasses = {
    sm: {
      badge: "px-1.5 py-0.5 text-xs",
      dot: "w-1.5 h-1.5",
    },
    md: {
      badge: "px-2 py-1 text-sm",
      dot: "w-2 h-2",
    },
  };

  const sizes = sizeClasses[size];

  return (
    <span
      className={`
        inline-flex items-center gap-1.5 rounded-full font-medium
        ring-1 ring-inset
        ${config.bg} ${config.text} ${config.ring}
        ${sizes.badge}
      `}
    >
      {/* Status dot */}
      <span className="relative flex">
        <span
          className={`rounded-full ${sizes.dot}`}
          style={{ backgroundColor: config.color }}
        />
        {config.animate && (
          <span
            className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
            style={{ backgroundColor: config.color }}
          />
        )}
      </span>

      {/* Label */}
      {showLabel && <span>{config.label}</span>}
    </span>
  );
}

/**
 * Compact dot-only status indicator for use in tight spaces.
 */
export function StatusDot({
  status,
  size = "md",
}: {
  status: StatusType;
  size?: "sm" | "md" | "lg";
}) {
  const config = statusConfig[status] || defaultConfig;

  const sizeClasses = {
    sm: "w-2 h-2",
    md: "w-3 h-3",
    lg: "w-4 h-4",
  };

  return (
    <span className="relative inline-flex">
      <span
        className={`rounded-full ${sizeClasses[size]}`}
        style={{ backgroundColor: config.color }}
      />
      {config.animate && (
        <span
          className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
          style={{ backgroundColor: config.color }}
        />
      )}
    </span>
  );
}
