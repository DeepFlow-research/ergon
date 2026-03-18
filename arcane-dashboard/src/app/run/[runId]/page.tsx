"use client";

/**
 * Run Detail Page - Displays the DAG visualization for a specific workflow run.
 *
 * Path: /run/[runId]
 */

import { useState, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { DAGCanvas } from "@/components/dag/DAGCanvas";
import { TaskDetailPanel } from "@/components/panels/TaskDetailPanel";

export default function RunPage() {
  const params = useParams();
  const runId = params.runId as string;
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  // Handle task click from DAG
  const handleTaskClick = useCallback((taskId: string) => {
    setSelectedTaskId(taskId);
  }, []);

  // Handle closing the detail panel
  const handleClosePanel = useCallback(() => {
    setSelectedTaskId(null);
  }, []);

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="flex-shrink-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 py-3">
        <div className="flex items-center gap-4">
          {/* Back button */}
          <Link
            href="/"
            className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
          >
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
                d="M10 19l-7-7m0 0l7-7m-7 7h18"
              />
            </svg>
            <span>Back to Runs</span>
          </Link>

          {/* Run ID */}
          <div className="text-sm text-gray-500 dark:text-gray-400 font-mono">
            Run: {runId}
          </div>
        </div>
      </header>

      {/* DAG Canvas */}
      <main className="flex-1 overflow-hidden">
        <DAGCanvas runId={runId} onTaskClick={handleTaskClick} />
      </main>

      {/* Task Detail Panel (slide-out) */}
      <TaskDetailPanel
        runId={runId}
        taskId={selectedTaskId}
        onClose={handleClosePanel}
      />
    </div>
  );
}
