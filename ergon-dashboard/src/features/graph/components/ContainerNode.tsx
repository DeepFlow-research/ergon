"use client";

import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { TaskState, TaskStatus } from "@/lib/types";
import { TaskGraphStatusIcon } from "@/components/dag/TaskGraphStatusIcon";
import { getLevelColor } from "@/features/graph/theme/levelColors";
import { getTaskTimingPrimaryLine } from "@/features/graph/utils/taskTiming";
import { tokensFor } from "@/lib/statusTokens";

interface ContainerNodeProps {
  task: TaskState;
  isExpanded: boolean;
  onToggleExpand: (taskId: string) => void;
  onClick?: (taskId: string) => void;
  selected?: boolean;
  dimmed?: boolean;
  highlighted?: boolean;
  containerWidth: number;
  containerHeight: number;
  layoutDirection?: "TB" | "LR";
  maxGraphDepth?: number;
}

function ContainerNodeComponent({
  task,
  isExpanded,
  onToggleExpand,
  onClick,
  selected = false,
  dimmed = false,
  highlighted = false,
  containerWidth,
  containerHeight,
  layoutDirection = "LR",
  maxGraphDepth,
}: ContainerNodeProps) {
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onClick?.(task.id);
  };

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleExpand(task.id);
  };

  const tokens = tokensFor(task.status);

  const depthForPalette = Math.max(maxGraphDepth ?? task.level, task.level);
  const levelHex = getLevelColor(task.level, depthForPalette);

  const targetPos = layoutDirection === "LR" ? Position.Left : Position.Top;
  const sourcePos = layoutDirection === "LR" ? Position.Right : Position.Bottom;
  const timingLine = getTaskTimingPrimaryLine(task);

  return (
    <div
      onClick={handleClick}
      data-testid={`graph-container-${task.id}`}
      className={`
        relative rounded-[10px] border border-dashed
        transition-all duration-200
        bg-[#f8fafc]/70
        border-[#cdd3dc]
        ${selected ? "ring-2 ring-indigo-500" : ""}
        ${highlighted ? "ring-2 ring-blue-500" : ""}
        ${dimmed ? "opacity-30" : ""}
        ${task.status === ("cancelled" as TaskStatus) ? "bg-gray-50/50" : ""}
      `}
      style={{
        width: containerWidth,
        height: containerHeight,
        borderLeft: `3px solid ${levelHex}`,
      }}
    >
      <Handle
        type="target"
        position={targetPos}
        className="!h-3 !w-3 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
      />

      <div className="flex h-8 items-center gap-2 rounded-t-[10px] border-b border-dashed border-[#d7dce4] bg-white/80 px-2.5">
        <div
          className={`flex size-[18px] shrink-0 items-center justify-center rounded-full border border-white shadow-sm ${tokens.solidBg} ${tokens.animate ? "animate-pulse" : ""}`}
          title={tokens.label}
          aria-label={`Status: ${tokens.label}`}
        >
          <TaskGraphStatusIcon status={task.status} />
        </div>
        <span className="truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-[#64707f]">
          {tokens.label}
        </span>
        <h3 className="min-w-0 flex-1 truncate text-xs font-semibold leading-tight text-[#0c1118]">
          {task.name}
        </h3>

        {task.assignedWorkerName && (
          <span className="flex max-w-[100px] shrink-0 items-center gap-1 truncate text-[11px] text-[#64707f]">
            <svg className="h-3 w-3 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
            <span className="truncate">{task.assignedWorkerName}</span>
          </span>
        )}

        <span className="shrink-0 whitespace-nowrap font-mono text-[10px] text-[#64707f]">
          {task.childIds.length} subtask{task.childIds.length !== 1 ? "s" : ""}
        </span>

        {timingLine && (
          <span
            className="max-w-[140px] shrink-0 truncate whitespace-nowrap font-mono text-[10px] text-[#64707f]"
            title={timingLine}
          >
            {timingLine}
          </span>
        )}

        <button
          onClick={handleToggle}
          className="shrink-0 rounded p-0.5 transition-colors hover:bg-black/10"
          aria-label={isExpanded ? "Collapse container" : "Expand container"}
        >
          <svg
            className={`h-4 w-4 text-[#64707f] transition-transform ${
              isExpanded ? "rotate-180" : ""
            }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      <Handle
        type="source"
        position={sourcePos}
        className="!h-3 !w-3 !border-2 !border-white !bg-gray-400 dark:!border-gray-900 dark:!bg-gray-500"
      />

      {task.status === ("running" as TaskStatus) && !dimmed && (
        <div className="pointer-events-none absolute inset-0 rounded-lg border-2 border-dashed border-yellow-400 opacity-50 animate-pulse" />
      )}
    </div>
  );
}

export const ContainerNode = memo(ContainerNodeComponent);
