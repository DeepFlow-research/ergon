"use client";

import { useMemo } from "react";
import { TaskState, TaskStatus } from "@/lib/types";

interface DepthSelectorProps {
  tasks: Map<string, TaskState>;
  currentDepth: number | "all";
  onDepthChange: (depth: number | "all") => void;
  maxAvailableDepth: number;
}

interface DepthInfo {
  depth: number;
  /** Total nodes visible at this depth level (cumulative from 0 to depth). */
  visibleCount: number;
  runningCount: number;
  failedCount: number;
}

export function DepthSelector({
  tasks,
  currentDepth,
  onDepthChange,
  maxAvailableDepth,
}: DepthSelectorProps) {
  const depthInfos = useMemo(() => {
    const tasksByLevel = new Map<number, TaskState[]>();
    for (const task of tasks.values()) {
      const existing = tasksByLevel.get(task.level) ?? [];
      existing.push(task);
      tasksByLevel.set(task.level, existing);
    }

    const infos: DepthInfo[] = [];
    let cumulativeVisible = 0;
    let cumulativeRunning = 0;
    let cumulativeFailed = 0;

    for (let d = 0; d <= maxAvailableDepth; d++) {
      const tasksAtLevel = tasksByLevel.get(d) ?? [];
      cumulativeVisible += tasksAtLevel.length;
      cumulativeRunning += tasksAtLevel.filter(
        (t) => t.status === TaskStatus.RUNNING,
      ).length;
      cumulativeFailed += tasksAtLevel.filter(
        (t) => t.status === TaskStatus.FAILED,
      ).length;

      infos.push({
        depth: d,
        visibleCount: cumulativeVisible,
        runningCount: cumulativeRunning,
        failedCount: cumulativeFailed,
      });
    }

    return infos;
  }, [tasks, maxAvailableDepth]);

  const totalInfo = useMemo(() => {
    let completed = 0;
    let total = 0;
    let running = 0;
    for (const task of tasks.values()) {
      total++;
      if (task.status === TaskStatus.COMPLETED) completed++;
      if (task.status === TaskStatus.RUNNING) running++;
    }
    return { completed, total, running };
  }, [tasks]);

  const isAllSelected = currentDepth === "all";

  return (
    <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
      {/* Depth buttons */}
      {depthInfos.map((info) => {
        const isSelected =
          currentDepth !== "all" && currentDepth === info.depth;
        const hasRunning = info.runningCount > 0;
        const hasFailed = info.failedCount > 0;

        return (
          <button
            key={info.depth}
            onClick={() => onDepthChange(info.depth)}
            className={`
              relative px-3 py-1.5 text-sm font-medium rounded-md transition-all
              ${
                isSelected
                  ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                  : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200/50 dark:hover:bg-gray-700/50"
              }
            `}
          >
            <span>{info.depth}</span>
            <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-400">
              {info.visibleCount}
            </span>

            {hasRunning && (
              <span className="absolute -top-1 -right-1 flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-yellow-500" />
              </span>
            )}
            {!hasRunning && hasFailed && (
              <span className="absolute -top-1 -right-1 flex h-2 w-2">
                <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500" />
              </span>
            )}
          </button>
        );
      })}

      {/* "All" button */}
      <button
        onClick={() => onDepthChange("all")}
        className={`
          relative px-3 py-1.5 text-sm font-medium rounded-md transition-all
          ${
            isAllSelected
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
              : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200/50 dark:hover:bg-gray-700/50"
          }
        `}
      >
        <span>All</span>
        <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-400">
          {totalInfo.total}
        </span>
        {totalInfo.running > 0 && (
          <span className="absolute -top-1 -right-1 flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-yellow-500" />
          </span>
        )}
      </button>

      {/* Completion progress bar */}
      <div className="ml-3 flex items-center gap-2">
        <div className="w-24 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 transition-all duration-300"
            style={{
              width: `${totalInfo.total > 0 ? (totalInfo.completed / totalInfo.total) * 100 : 0}%`,
            }}
          />
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {totalInfo.completed}/{totalInfo.total}
        </span>
      </div>
    </div>
  );
}
