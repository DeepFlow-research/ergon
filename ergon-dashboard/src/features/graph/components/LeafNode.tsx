"use client";

import { memo, useEffect, useState } from "react";
import type { TaskState, TaskStatus } from "@/lib/types";
import { TaskGraphStatusIcon } from "@/components/dag/TaskGraphStatusIcon";
import { getLevelColor } from "@/features/graph/theme/levelColors";
import { getTaskTimingPrimaryLine } from "@/features/graph/utils/taskTiming";
import { tokensFor } from "@/lib/statusTokens";
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

/**
 * CornerBadge — slot-1-style corner status indicator. A solid circular badge
 * ringed with white (or dark ring on dark mode) that overlaps the node's
 * top-right corner; pulses on RUNNING. This replaces the floating
 * `TaskGraphStatusIcon` which read as just another icon, not a status.
 */
function CornerBadge({ status }: { status: TaskStatus }) {
  const tokens = tokensFor(status);
  return (
    <div
      className={`absolute -right-1 -top-1 z-30 flex size-[19px] items-center justify-center rounded-full border border-white shadow-sm ${tokens.solidBg} ${tokens.animate ? "animate-pulse" : ""}`}
      aria-label={`Status: ${tokens.label}`}
      title={tokens.label}
    >
      <TaskGraphStatusIcon status={status} />
    </div>
  );
}

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

  const tokens = tokensFor(task.status);
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
          rounded-[8px] border shadow-sm
          transition-all duration-200
          hover:shadow-md hover:scale-[1.01]
          px-2 py-1.5 flex items-center gap-1.5
          border-[#d7dce4] bg-white
          ${isAnimating ? "ring-2 ring-blue-400" : ""}
          ${selected ? "ring-2 ring-indigo-500" : ""}
          ${dimmed ? "opacity-30" : ""}
          ${highlighted ? "ring-2 ring-blue-500" : ""}
        `}
        style={{ borderLeft: `3px solid ${levelHex}` }}
      >
        <CornerBadge status={task.status} />
        <Handle
          type="target"
          position={targetPos}
          className="!h-2 !w-2 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
        />
        <span className="truncate pr-5 text-[11px] font-semibold text-[#0c1118]">
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
          relative cursor-pointer min-w-[148px] max-w-[174px]
          rounded-[9px] border shadow-sm
          transition-all duration-200
          hover:shadow-md hover:scale-[1.01]
          border-[#d7dce4] bg-white
          ${isAnimating ? "ring-2 ring-blue-400" : ""}
          ${task.status === ("running" as TaskStatus) ? "shadow-yellow-200" : ""}
          ${selected ? "ring-2 ring-indigo-500" : ""}
          ${dimmed ? "opacity-30" : ""}
          ${highlighted ? "ring-2 ring-blue-500" : ""}
        `}
        style={{ borderLeft: `3px solid ${levelHex}` }}
      >
        <CornerBadge status={task.status} />
        <Handle
          type="target"
          position={targetPos}
          className="!h-3 !w-3 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
        />

        <div className="p-2 pr-7">
          <div className="mb-1 flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#64707f]">
              {task.status}
            </span>
          </div>

          <h3 className="truncate text-xs font-semibold leading-tight text-[#0c1118]">
            {task.name}
          </h3>

          {task.assignedWorkerName && (
            <div className="mt-1 flex items-center gap-1 text-[11px] text-[#64707f]">
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
            <p className="mt-1 text-[10px] tabular-nums text-[#64707f]">{timingLine}</p>
          )}
        </div>

        <Handle
          type="source"
          position={sourcePos}
          className="!h-3 !w-3 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
        />

        {task.status === ("running" as TaskStatus) && !dimmed && (
          <div className="pointer-events-none absolute inset-0 rounded-[9px] border border-yellow-400 opacity-50 animate-pulse" />
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
        relative cursor-pointer min-w-[168px] max-w-[198px]
        rounded-[10px] border shadow-sm
        transition-all duration-200
        hover:shadow-md hover:scale-[1.01]
        border-[#d7dce4] bg-white
        ${isAnimating ? "ring-2 ring-blue-400" : ""}
        ${task.status === ("running" as TaskStatus) ? "shadow-yellow-200" : ""}
        ${selected ? "ring-2 ring-indigo-500" : ""}
        ${dimmed ? "opacity-30" : ""}
        ${highlighted ? "ring-2 ring-blue-500" : ""}
      `}
      style={{ borderLeft: `3px solid ${levelHex}` }}
    >
      <CornerBadge status={task.status} />
      <Handle
        type="target"
        position={targetPos}
        className="!h-3 !w-3 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
      />

      <div className="p-2.5 pr-8">
        {/* Header: Status + Level */}
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#64707f]">
              {task.status}
            </span>
          </div>
          <span className="font-mono text-[10px] text-[#98a2b1]">
            L{task.level}
          </span>
        </div>

        {/* Task Name */}
        <h3 className="truncate text-sm font-semibold leading-tight text-[#0c1118]">
          {task.name}
        </h3>

        {/* Description */}
        {task.description && task.description.length < 60 && (
          <p className="mt-1 line-clamp-2 text-[11px] text-[#64707f]">
            {task.description}
          </p>
        )}

        {/* Worker Assignment */}
        {task.assignedWorkerName && (
          <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-[#64707f]">
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
          <p className="mt-1.5 text-[10px] tabular-nums text-[#64707f]">{timingLine}</p>
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
