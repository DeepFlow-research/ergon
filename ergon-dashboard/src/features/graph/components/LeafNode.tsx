"use client";

import { memo, useEffect, useState } from "react";
import type { TaskState, TaskStatus } from "@/lib/types";
import { TaskGraphStatusIcon } from "@/components/dag/TaskGraphStatusIcon";
import { getLevelColor } from "@/features/graph/theme/levelColors";
import { getTaskTimingPrimaryLine } from "@/features/graph/utils/taskTiming";
import { Handle, Position } from "@xyflow/react";

interface LeafNodeProps {
  task: TaskState;
  variant: "full" | "standard" | "compact";
  onClick?: (taskId: string) => void;
  selected?: boolean;
  dimmed?: boolean;
  highlighted?: boolean;
  layoutDirection?: "TB" | "LR";
  maxGraphDepth?: number;
}

const statusBorderColors: Record<string, string> = {
  pending: "border-gray-300 dark:border-gray-600",
  ready: "border-blue-400 dark:border-blue-500",
  running: "border-yellow-400 dark:border-yellow-500",
  completed: "border-green-400 dark:border-green-500",
  failed: "border-red-400 dark:border-red-500",
  cancelled: "border-gray-400 dark:border-gray-500",
};

const statusBgColors: Record<string, string> = {
  pending: "bg-gray-50 dark:bg-gray-800",
  ready: "bg-blue-50 dark:bg-blue-900/20",
  running: "bg-yellow-50 dark:bg-yellow-900/20",
  completed: "bg-green-50 dark:bg-green-900/20",
  failed: "bg-red-50 dark:bg-red-900/20",
  cancelled: "bg-gray-100 dark:bg-gray-800/50",
};

function LeafNodeComponent({
  task,
  variant,
  onClick,
  selected = false,
  dimmed = false,
  highlighted = false,
  layoutDirection = "LR",
  maxGraphDepth,
}: LeafNodeProps) {
  const [isAnimating, setIsAnimating] = useState(false);
  const [prevStatus, setPrevStatus] = useState(task.status);

  const targetPos = layoutDirection === "LR" ? Position.Left : Position.Top;
  const sourcePos = layoutDirection === "LR" ? Position.Right : Position.Bottom;
  const depthForPalette = Math.max(maxGraphDepth ?? task.level, task.level);
  const levelHex = getLevelColor(task.level, depthForPalette);

  useEffect(() => {
    if (task.status !== prevStatus) {
      setIsAnimating(true);
      setPrevStatus(task.status);
      const timer = setTimeout(() => setIsAnimating(false), 500);
      return () => clearTimeout(timer);
    }
  }, [task.status, prevStatus]);

  const handleClick = () => {
    onClick?.(task.id);
  };

  const borderColor =
    statusBorderColors[task.status] ?? statusBorderColors.pending;
  const bgColor = statusBgColors[task.status] ?? statusBgColors.pending;
  const timingLine = getTaskTimingPrimaryLine(task);

  if (variant === "compact") {
    const timingHint = timingLine ? `\n${timingLine}` : "";
    return (
      <div
        onClick={handleClick}
        data-testid={`graph-node-${task.id}`}
        title={`${task.name}\n${task.status}${task.assignedWorkerName ? `\nWorker: ${task.assignedWorkerName}` : ""}${task.description ? `\n${task.description}` : ""}${timingHint}`}
        className={`
          relative cursor-pointer
          rounded-md border shadow-sm
          transition-all duration-200
          hover:shadow-md hover:scale-[1.02]
          px-2 py-1.5 flex items-center gap-1.5
          ${borderColor} ${bgColor}
          ${isAnimating ? "ring-2 ring-offset-1 ring-blue-400 dark:ring-blue-500" : ""}
          ${selected ? "ring-2 ring-offset-1 ring-indigo-500 dark:ring-indigo-400" : ""}
          ${dimmed ? "opacity-30" : ""}
          ${highlighted ? "ring-2 ring-blue-500 ring-offset-1" : ""}
        `}
        style={{ borderLeft: `3px solid ${levelHex}` }}
      >
        <div className="absolute right-1 top-1 z-10 scale-90">
          <TaskGraphStatusIcon status={task.status} />
        </div>
        <Handle
          type="target"
          position={targetPos}
          className="!h-2 !w-2 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
        />
        <span className="truncate pr-8 text-xs font-medium text-gray-900 dark:text-white">
          {task.name}
        </span>
        <Handle
          type="source"
          position={sourcePos}
          className="!h-2 !w-2 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
        />
      </div>
    );
  }

  if (variant === "standard") {
    return (
      <div
        onClick={handleClick}
        data-testid={`graph-node-${task.id}`}
        className={`
          relative cursor-pointer min-w-[160px] max-w-[200px]
          rounded-lg border-2 shadow-sm
          transition-all duration-200
          hover:shadow-md hover:scale-[1.02]
          ${borderColor} ${bgColor}
          ${isAnimating ? "ring-2 ring-offset-2 ring-blue-400 dark:ring-blue-500" : ""}
          ${task.status === ("running" as TaskStatus) ? "shadow-yellow-200 dark:shadow-yellow-900" : ""}
          ${selected ? "ring-2 ring-offset-2 ring-indigo-500 dark:ring-indigo-400" : ""}
          ${dimmed ? "opacity-30" : ""}
          ${highlighted ? "ring-2 ring-blue-500 ring-offset-2" : ""}
        `}
        style={{ borderLeft: `3px solid ${levelHex}` }}
      >
        <div className="absolute right-1.5 top-1.5 z-10">
          <TaskGraphStatusIcon status={task.status} />
        </div>
        <Handle
          type="target"
          position={targetPos}
          className="!h-3 !w-3 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
        />

        <div className="p-2.5 pr-10">
          <div className="mb-1.5 flex items-center gap-2">
            <span className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
              {task.status}
            </span>
          </div>

          <h3 className="font-semibold text-gray-900 dark:text-white text-sm leading-tight truncate">
            {task.name}
          </h3>

          {task.assignedWorkerName && (
            <div className="flex items-center gap-1 mt-1.5 text-xs text-gray-500 dark:text-gray-400">
              <svg
                className="w-3 h-3"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                />
              </svg>
              <span className="truncate">{task.assignedWorkerName}</span>
            </div>
          )}
          {timingLine && (
            <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400 tabular-nums">{timingLine}</p>
          )}
        </div>

        <Handle
          type="source"
          position={sourcePos}
          className="!h-3 !w-3 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
        />

        {task.status === ("running" as TaskStatus) && !dimmed && (
          <div className="pointer-events-none absolute inset-0 rounded-lg border-2 border-yellow-400 opacity-50 animate-pulse" />
        )}
      </div>
    );
  }

  // Full variant — matches original TaskNode rendering
  return (
    <div
      onClick={handleClick}
      data-testid={`graph-node-${task.id}`}
      className={`
        relative cursor-pointer min-w-[180px] max-w-[280px]
        rounded-lg border-2 shadow-sm
        transition-all duration-200
        hover:shadow-md hover:scale-[1.02]
        ${borderColor} ${bgColor}
        ${isAnimating ? "ring-2 ring-offset-2 ring-blue-400 dark:ring-blue-500" : ""}
        ${task.status === ("running" as TaskStatus) ? "shadow-yellow-200 dark:shadow-yellow-900" : ""}
        ${selected ? "ring-2 ring-offset-2 ring-indigo-500 dark:ring-indigo-400" : ""}
        ${dimmed ? "opacity-30" : ""}
        ${highlighted ? "ring-2 ring-blue-500 ring-offset-2" : ""}
      `}
      style={{ borderLeft: `3px solid ${levelHex}` }}
    >
      <div className="absolute right-2 top-2 z-10">
        <TaskGraphStatusIcon status={task.status} />
      </div>
      <Handle
        type="target"
        position={targetPos}
        className="!h-3 !w-3 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
      />

      <div className="p-3 pr-11">
        {/* Header: Status + Level */}
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
              {task.status}
            </span>
          </div>
          <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">
            L{task.level}
          </span>
        </div>

        {/* Task Name */}
        <h3 className="font-semibold text-gray-900 dark:text-white text-sm leading-tight truncate">
          {task.name}
        </h3>

        {/* Description */}
        {task.description && task.description.length < 60 && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
            {task.description}
          </p>
        )}

        {/* Worker Assignment */}
        {task.assignedWorkerName && (
          <div className="flex items-center gap-1.5 mt-2 text-xs text-gray-500 dark:text-gray-400">
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
            <span className="truncate">{task.assignedWorkerName}</span>
          </div>
        )}
        {timingLine && (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400 tabular-nums">{timingLine}</p>
        )}

        {/* Leaf indicator */}
        {task.isLeaf && (
          <div className="absolute right-2 top-10">
            <svg
              className="w-4 h-4 text-gray-400 dark:text-gray-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-label="Leaf task (no children)"
            >
              <title>Leaf task (no children)</title>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
        )}

        {/* Children count indicator (collapsed container) */}
        {!task.isLeaf && task.childIds.length > 0 && (
          <div className="flex items-center gap-1 mt-2 text-xs text-gray-400 dark:text-gray-500">
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16m-7 6h7"
              />
            </svg>
            <span>{task.childIds.length} subtasks</span>
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={sourcePos}
        className="!h-3 !w-3 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
      />

      {/* Running pulse ring */}
      {task.status === ("running" as TaskStatus) && !dimmed && (
        <div className="pointer-events-none absolute inset-0 rounded-lg border-2 border-yellow-400 opacity-50 animate-pulse" />
      )}
    </div>
  );
}

export const LeafNode = memo(LeafNodeComponent);
