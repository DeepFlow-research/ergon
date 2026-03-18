"use client";

/**
 * TaskDetailPanel - Slide-out panel showing full task details.
 *
 * Triggered when clicking a task node in the DAG.
 * Contains: Header, Description, Action Stream, Resources, Sandbox, Dependencies
 */

import { useEffect, useRef } from "react";
import { useTaskDetails } from "@/hooks/useTaskDetails";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ActionStreamPanel } from "./ActionStreamPanel";
import { ResourcePanel } from "./ResourcePanel";
import { SandboxPanel } from "./SandboxPanel";
import { TaskState, TaskStatus } from "@/lib/types";

interface TaskDetailPanelProps {
  runId: string;
  taskId: string | null;
  onClose: () => void;
}

/**
 * Format relative time from a timestamp.
 */
function formatRelativeTime(timestamp: string | null): string {
  if (!timestamp) return "Not started";
  const now = new Date();
  const time = new Date(timestamp);
  const diffMs = now.getTime() - time.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);

  if (diffSeconds < 60) return "just now";
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
  return time.toLocaleDateString();
}

/**
 * Calculate duration between two timestamps.
 */
function formatDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt) return "—";
  const start = new Date(startedAt);
  const end = completedAt ? new Date(completedAt) : new Date();
  const diffMs = end.getTime() - start.getTime();
  const seconds = Math.floor(diffMs / 1000);

  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}m ${remainingSeconds}s`;
}

interface DependencyItemProps {
  task: TaskState;
}

function DependencyItem({ task }: DependencyItemProps) {
  return (
    <div className="flex items-center gap-2 px-2 py-1.5 bg-gray-50 dark:bg-gray-800/50 rounded">
      <StatusBadge status={task.status} size="sm" showLabel={false} />
      <span className="text-sm text-gray-700 dark:text-gray-300 truncate flex-1">
        {task.name}
      </span>
      <span className="text-xs text-gray-400 dark:text-gray-500">L{task.level}</span>
    </div>
  );
}

interface SectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function Section({ title, icon, children, defaultOpen = true }: SectionProps) {
  return (
    <details open={defaultOpen} className="group">
      <summary className="flex items-center gap-2 cursor-pointer py-2 text-gray-700 dark:text-gray-300 font-medium hover:text-gray-900 dark:hover:text-white">
        <svg
          className="w-4 h-4 text-gray-400 transition-transform group-open:rotate-90"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        {icon}
        <span>{title}</span>
      </summary>
      <div className="pl-6 pb-4">{children}</div>
    </details>
  );
}

export function TaskDetailPanel({ runId, taskId, onClose }: TaskDetailPanelProps) {
  const { task, actions, resources, sandbox, dependencies, isLoading, error } =
    useTaskDetails(runId, taskId);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    // Add a small delay to prevent immediate closing
    const timer = setTimeout(() => {
      window.addEventListener("mousedown", handleClickOutside);
    }, 100);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("mousedown", handleClickOutside);
    };
  }, [onClose]);

  // Don't render if no task selected
  if (!taskId) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/20 dark:bg-black/40 z-40" />

      {/* Panel */}
      <div
        ref={panelRef}
        className="fixed right-0 top-0 h-full w-full sm:max-w-lg bg-white dark:bg-gray-900 shadow-2xl z-50 flex flex-col overflow-hidden animate-slide-in-right"
      >
        {/* Header */}
        <div className="flex-shrink-0 border-b border-gray-200 dark:border-gray-700 px-4 py-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              {task ? (
                <>
                  <div className="flex items-center gap-2 mb-1">
                    <h2 className="text-lg font-semibold text-gray-900 dark:text-white truncate">
                      {task.name}
                    </h2>
                    <StatusBadge status={task.status} size="sm" />
                  </div>
                  <div className="flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
                    {task.assignedWorkerName && (
                      <span className="flex items-center gap-1">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                          />
                        </svg>
                        {task.assignedWorkerName}
                      </span>
                    )}
                    <span className="flex items-center gap-1">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                      {task.status === TaskStatus.RUNNING
                        ? formatDuration(task.startedAt, null)
                        : task.completedAt
                          ? formatDuration(task.startedAt, task.completedAt)
                          : formatRelativeTime(task.startedAt)}
                    </span>
                    <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">
                      L{task.level}
                    </span>
                  </div>
                </>
              ) : isLoading ? (
                <div className="h-12 animate-pulse bg-gray-200 dark:bg-gray-700 rounded" />
              ) : (
                <div className="text-gray-500 dark:text-gray-400">Task not found</div>
              )}
            </div>

            {/* Close button */}
            <button
              onClick={onClose}
              className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {error ? (
            <div className="text-center py-8 text-red-500 dark:text-red-400">
              <p>Error loading task details</p>
              <p className="text-sm">{error}</p>
            </div>
          ) : !task ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              {isLoading ? "Loading..." : "Task not found"}
            </div>
          ) : (
            <div className="space-y-4">
              {/* Description */}
              {task.description && (
                <Section
                  title="Description"
                  icon={
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M4 6h16M4 12h16M4 18h7"
                      />
                    </svg>
                  }
                >
                  <p className="text-sm text-gray-600 dark:text-gray-300 whitespace-pre-wrap">
                    {task.description}
                  </p>
                </Section>
              )}

              {/* Actions */}
              <Section
                title={`Actions (${actions.length})`}
                icon={
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M13 10V3L4 14h7v7l9-11h-7z"
                    />
                  </svg>
                }
              >
                <ActionStreamPanel actions={actions} maxHeight="300px" />
              </Section>

              {/* Resources */}
              <Section
                title={`Resources (${resources.length})`}
                icon={
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z"
                    />
                  </svg>
                }
                defaultOpen={resources.length > 0}
              >
                <ResourcePanel resources={resources} />
              </Section>

              {/* Sandbox */}
              <Section
                title="Sandbox"
                icon={
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                    />
                  </svg>
                }
                defaultOpen={!!sandbox}
              >
                <SandboxPanel sandbox={sandbox} />
              </Section>

              {/* Dependencies */}
              {(dependencies.waitingOn.length > 0 || dependencies.blocking.length > 0) && (
                <Section
                  title="Dependencies"
                  icon={
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M13 10V3L4 14h7v7l9-11h-7z"
                      />
                    </svg>
                  }
                  defaultOpen={false}
                >
                  <div className="space-y-4">
                    {dependencies.waitingOn.length > 0 && (
                      <div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
                          Waiting on ({dependencies.waitingOn.length})
                        </div>
                        <div className="space-y-1">
                          {dependencies.waitingOn.map((dep) => (
                            <DependencyItem key={dep.id} task={dep} />
                          ))}
                        </div>
                      </div>
                    )}

                    {dependencies.blocking.length > 0 && (
                      <div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 mb-2 uppercase tracking-wide">
                          Blocking ({dependencies.blocking.length})
                        </div>
                        <div className="space-y-1">
                          {dependencies.blocking.map((dep) => (
                            <DependencyItem key={dep.id} task={dep} />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </Section>
              )}

              {/* Task ID (for debugging) */}
              <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                <div className="text-xs text-gray-400 dark:text-gray-500 font-mono">
                  Task ID: {task.id}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

    </>
  );
}
