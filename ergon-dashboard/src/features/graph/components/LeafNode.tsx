"use client";

import { memo, useEffect, useState } from "react";
import type { TaskState, TaskStatus } from "@/lib/types";
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

const STATUS_STYLES: Record<
  string,
  { bg: string; border: string; text: string }
> = {
  completed: {
    bg: "oklch(0.96 0.04 155)",
    border: "oklch(0.85 0.10 155)",
    text: "oklch(0.40 0.12 155)",
  },
  running: {
    bg: "oklch(0.97 0.04 80)",
    border: "oklch(0.85 0.10 80)",
    text: "oklch(0.42 0.12 65)",
  },
  ready: {
    bg: "oklch(0.97 0.03 240)",
    border: "oklch(0.86 0.08 240)",
    text: "oklch(0.40 0.12 240)",
  },
  pending: {
    bg: "#ffffff",
    border: "#e2e6ec",
    text: "#98a2b1",
  },
  failed: {
    bg: "oklch(0.97 0.04 22)",
    border: "oklch(0.85 0.10 22)",
    text: "oklch(0.40 0.16 22)",
  },
};

const FALLBACK_STYLE = STATUS_STYLES.pending;

function getStatusStyle(status: string) {
  return STATUS_STYLES[status] ?? FALLBACK_STYLE;
}

function StatusDot({ status }: { status: string }) {
  const style = getStatusStyle(status);
  const isRunning = status === "running";
  return (
    <span
      className={isRunning ? "animate-status-pulse" : ""}
      style={{
        position: "absolute",
        top: 6,
        right: 6,
        width: 7,
        height: 7,
        borderRadius: "50%",
        backgroundColor: style.text,
      }}
    />
  );
}

function LeafNodeComponent(props: LeafNodeProps) {
  const {
    task,
    onClick,
    selected = false,
    dimmed = false,
    highlighted = false,
    layoutDirection = "LR",
  } = props;
  const [isAnimating, setIsAnimating] = useState(false);
  const [prevStatus, setPrevStatus] = useState(task.status);

  const targetPos = layoutDirection === "LR" ? Position.Left : Position.Top;
  const sourcePos = layoutDirection === "LR" ? Position.Right : Position.Bottom;

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

  const ss = getStatusStyle(task.status);

  const statusLabel =
    task.status === ("running" as TaskStatus)
      ? `running${task.assignedWorkerName ? ` · ${task.assignedWorkerName}` : ""}`
      : task.status;

  return (
    <div
      onClick={handleClick}
      data-testid={`graph-node-${task.id}`}
      data-task-status={task.status}
      className={`
        relative cursor-pointer
        transition-all duration-200
        hover:shadow-md
        ${dimmed ? "opacity-30" : ""}
        ${isAnimating ? "scale-[1.02]" : ""}
      `}
      style={{
        minWidth: 130,
        maxWidth: 200,
        padding: "8px 28px 8px 10px",
        borderRadius: 6,
        border: `1px solid ${ss.border}`,
        backgroundColor: ss.bg,
        ...(selected
          ? {
              outline: `2px solid var(--accent)`,
              outlineOffset: 2,
            }
          : highlighted
            ? {
                outline: `2px solid var(--accent)`,
                outlineOffset: 2,
              }
            : {}),
      }}
    >
      <StatusDot status={task.status} />

      <Handle
        type="target"
        position={targetPos}
        className="!h-2 !w-2 !border-2 !border-white !bg-gray-400"
      />

      <div
        className="truncate font-semibold leading-tight"
        style={{ fontSize: 13, color: "var(--ink)" }}
      >
        {task.name}
      </div>

      <div
        className="truncate font-mono"
        style={{ fontSize: 10, marginTop: 2, color: ss.text }}
      >
        {statusLabel}
      </div>

      <Handle
        type="source"
        position={sourcePos}
        className="!h-2 !w-2 !border-2 !border-white !bg-gray-400"
      />
    </div>
  );
}

export const LeafNode = memo(LeafNodeComponent);
