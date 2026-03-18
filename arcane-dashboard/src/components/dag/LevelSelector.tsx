"use client";

/**
 * LevelSelector - Tab-style buttons for DAG level filtering.
 *
 * Allows users to view tasks at different levels of the DAG hierarchy:
 * - L0: Root task
 * - L1: Direct children
 * - L2: Grandchildren
 * - etc.
 *
 * Also supports an "All" option to view all levels.
 */

import { useMemo } from "react";
import { TaskState, TaskStatus } from "@/lib/types";

interface LevelSelectorProps {
  tasks: Map<string, TaskState>;
  selectedLevel: number | null; // null = all levels
  onChange: (level: number | null) => void;
}

interface LevelInfo {
  level: number;
  taskCount: number;
  completedCount: number;
  runningCount: number;
  failedCount: number;
}

export function LevelSelector({
  tasks,
  selectedLevel,
  onChange,
}: LevelSelectorProps) {
  // Calculate level information
  const levelInfos = useMemo(() => {
    const levels = new Map<number, LevelInfo>();

    for (const task of Array.from(tasks.values())) {
      const existing = levels.get(task.level);
      if (existing) {
        existing.taskCount++;
        if (task.status === TaskStatus.COMPLETED) existing.completedCount++;
        if (task.status === TaskStatus.RUNNING) existing.runningCount++;
        if (task.status === TaskStatus.FAILED) existing.failedCount++;
      } else {
        levels.set(task.level, {
          level: task.level,
          taskCount: 1,
          completedCount: task.status === TaskStatus.COMPLETED ? 1 : 0,
          runningCount: task.status === TaskStatus.RUNNING ? 1 : 0,
          failedCount: task.status === TaskStatus.FAILED ? 1 : 0,
        });
      }
    }

    return Array.from(levels.values()).sort((a, b) => a.level - b.level);
  }, [tasks]);

  // Total counts for "All" tab
  const totalInfo = useMemo(() => {
    let taskCount = 0;
    let completedCount = 0;
    let runningCount = 0;
    let failedCount = 0;

    for (const info of levelInfos) {
      taskCount += info.taskCount;
      completedCount += info.completedCount;
      runningCount += info.runningCount;
      failedCount += info.failedCount;
    }

    return { taskCount, completedCount, runningCount, failedCount };
  }, [levelInfos]);

  const isAllSelected = selectedLevel === null;

  return (
    <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
      {/* All levels tab */}
      <button
        onClick={() => onChange(null)}
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
          {totalInfo.taskCount}
        </span>
        {/* Progress indicator */}
        {totalInfo.runningCount > 0 && (
          <span className="absolute -top-1 -right-1 flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-yellow-500" />
          </span>
        )}
      </button>

      {/* Level tabs */}
      {levelInfos.map((info) => {
        const isSelected = selectedLevel === info.level;
        const hasRunning = info.runningCount > 0;
        const hasFailed = info.failedCount > 0;

        return (
          <button
            key={info.level}
            onClick={() => onChange(info.level)}
            className={`
              relative px-3 py-1.5 text-sm font-medium rounded-md transition-all
              ${
                isSelected
                  ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                  : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200/50 dark:hover:bg-gray-700/50"
              }
            `}
          >
            <span>L{info.level}</span>
            <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-400">
              {info.taskCount}
            </span>

            {/* Status indicators */}
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

      {/* Completion progress bar */}
      <div className="ml-3 flex items-center gap-2">
        <div className="w-24 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 transition-all duration-300"
            style={{
              width: `${totalInfo.taskCount > 0 ? (totalInfo.completedCount / totalInfo.taskCount) * 100 : 0}%`,
            }}
          />
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {totalInfo.completedCount}/{totalInfo.taskCount}
        </span>
      </div>
    </div>
  );
}
