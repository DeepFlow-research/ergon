"use client";

import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { TaskState, TaskStatus } from "@/lib/types";
import type { EvaluationRollup } from "@/features/evaluation/contracts";

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
  evaluationRollup?: EvaluationRollup | null;
  evaluationLensActive?: boolean;
}

function ContainerNodeComponent(props: ContainerNodeProps) {
  const {
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
    evaluationRollup = null,
  } = props;
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onClick?.(task.id);
  };

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggleExpand(task.id);
  };

  const targetPos = layoutDirection === "LR" ? Position.Left : Position.Top;
  const sourcePos = layoutDirection === "LR" ? Position.Right : Position.Bottom;

  const isRunning = task.status === ("running" as TaskStatus);
  const borderColor = isRunning ? "var(--status-running)" : "#cdd3dc";

  return (
    <div
      onClick={handleClick}
      data-testid={`graph-container-${task.id}`}
      className={`
        relative transition-all duration-200
        ${dimmed ? "opacity-30" : ""}
      `}
      style={{
        width: containerWidth,
        height: containerHeight,
        borderRadius: 8,
        border: `1px dashed ${borderColor}`,
        backgroundColor: "rgba(255,255,255,0.55)",
        ...(selected
          ? { outline: "2px solid var(--accent)", outlineOffset: 2 }
          : highlighted
            ? { outline: "2px solid var(--accent)", outlineOffset: 2 }
            : {}),
      }}
    >
      <Handle
        type="target"
        position={targetPos}
        className="!h-3 !w-3 !border-2 !border-white !bg-gray-400"
      />

      {/* Header row */}
      <div
        className="flex items-center justify-between px-2.5"
        style={{
          height: 32,
          borderBottom: `1px dashed ${borderColor}`,
        }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="truncate font-semibold"
            style={{ fontSize: 12, color: "var(--ink)" }}
          >
            {task.name}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span
            className="whitespace-nowrap font-mono"
            style={{ fontSize: 10, color: "var(--faint)" }}
          >
            {task.childIds.length} subtask{task.childIds.length !== 1 ? "s" : ""}
          </span>
          {evaluationRollup && (
            <span
              className="rounded-full bg-[var(--ink)] px-1.5 py-0.5 text-[9px] font-semibold uppercase leading-none text-[var(--card)]"
              data-testid={`graph-rubric-glyph-${task.id}`}
              title={`${evaluationRollup.status}: ${evaluationRollup.totalCriteria} criteria`}
            >
              R
            </span>
          )}

          <button
            onClick={handleToggle}
            className="shrink-0 rounded p-0.5 transition-colors hover:bg-black/10"
            aria-label={isExpanded ? "Collapse container" : "Expand container"}
          >
            <svg
              className={`h-4 w-4 transition-transform ${isExpanded ? "rotate-180" : ""}`}
              style={{ color: "var(--muted)" }}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>

      <Handle
        type="source"
        position={sourcePos}
        className="!h-3 !w-3 !border-2 !border-white !bg-gray-400"
      />

      {isRunning && !dimmed && (
        <div
          className="pointer-events-none absolute inset-0 animate-pulse opacity-40"
          style={{
            borderRadius: 8,
            border: "2px dashed var(--status-running)",
          }}
        />
      )}
    </div>
  );
}

export const ContainerNode = memo(ContainerNodeComponent);
