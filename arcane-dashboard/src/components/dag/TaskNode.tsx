"use client";

/**
 * TaskNode - Custom react-flow node component for tasks.
 *
 * Displays a task node in the DAG with:
 * - Task name
 * - Status badge
 * - Assigned worker
 * - Subtle animation on status change
 * - Dim/highlight support for search
 */

import { memo, useEffect, useState } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { TaskState, TaskStatus } from "@/lib/types";
import { StatusDot } from "@/components/common/StatusBadge";

// Define the data structure for task nodes
export type TaskNodeData = {
  task: TaskState;
  onClick?: (taskId: string) => void;
  dimmed?: boolean;
  highlighted?: boolean;
};

// Define the full node type for react-flow
export type TaskNodeType = Node<TaskNodeData, "taskNode">;

const statusBorderColors: Record<TaskStatus, string> = {
  [TaskStatus.PENDING]: "border-gray-300 dark:border-gray-600",
  [TaskStatus.READY]: "border-blue-400 dark:border-blue-500",
  [TaskStatus.RUNNING]: "border-yellow-400 dark:border-yellow-500",
  [TaskStatus.COMPLETED]: "border-green-400 dark:border-green-500",
  [TaskStatus.FAILED]: "border-red-400 dark:border-red-500",
};

const statusBgColors: Record<TaskStatus, string> = {
  [TaskStatus.PENDING]: "bg-gray-50 dark:bg-gray-800",
  [TaskStatus.READY]: "bg-blue-50 dark:bg-blue-900/20",
  [TaskStatus.RUNNING]: "bg-yellow-50 dark:bg-yellow-900/20",
  [TaskStatus.COMPLETED]: "bg-green-50 dark:bg-green-900/20",
  [TaskStatus.FAILED]: "bg-red-50 dark:bg-red-900/20",
};

function TaskNodeComponent({ data }: NodeProps<TaskNodeType>) {
  const { task, onClick, dimmed = false, highlighted = false } = data;
  const [isAnimating, setIsAnimating] = useState(false);
  const [prevStatus, setPrevStatus] = useState(task.status);

  // Animate on status change
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

  const borderColor = statusBorderColors[task.status];
  const bgColor = statusBgColors[task.status];

  return (
    <div
      onClick={handleClick}
      className={`
        relative cursor-pointer min-w-[180px] max-w-[280px]
        rounded-lg border-2 shadow-sm
        transition-all duration-200
        hover:shadow-md hover:scale-[1.02]
        ${borderColor} ${bgColor}
        ${isAnimating ? "ring-2 ring-offset-2 ring-blue-400 dark:ring-blue-500" : ""}
        ${task.status === TaskStatus.RUNNING ? "shadow-yellow-200 dark:shadow-yellow-900" : ""}
        ${dimmed ? "opacity-30" : ""}
        ${highlighted ? "ring-2 ring-blue-500 ring-offset-2" : ""}
      `}
    >
      {/* Input Handle (top) */}
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-gray-400 dark:!bg-gray-500 !w-3 !h-3 !border-2 !border-white dark:!border-gray-900"
      />

      {/* Content */}
      <div className="p-3">
        {/* Header: Status + Level */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <StatusDot status={task.status} size="md" />
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
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

        {/* Description (if short enough) */}
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

        {/* Leaf indicator */}
        {task.isLeaf && (
          <div className="absolute top-2 right-2">
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

        {/* Children count indicator */}
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

      {/* Output Handle (bottom) */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!bg-gray-400 dark:!bg-gray-500 !w-3 !h-3 !border-2 !border-white dark:!border-gray-900"
      />

      {/* Running animation pulse ring */}
      {task.status === TaskStatus.RUNNING && !dimmed && (
        <div className="absolute inset-0 rounded-lg border-2 border-yellow-400 animate-pulse opacity-50 pointer-events-none" />
      )}
    </div>
  );
}

// Memoize to prevent unnecessary re-renders
export const TaskNode = memo(TaskNodeComponent);

// Register the node type for react-flow
export const nodeTypes = {
  taskNode: TaskNode,
};
