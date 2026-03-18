"use client";

/**
 * useTaskDetails - Convenience hook to extract task-specific data from runState.
 *
 * Provides easy access to a task's details including its actions, resources,
 * sandbox, and dependency information.
 */

import { useMemo } from "react";
import { useRunState } from "@/hooks/useRunState";
import {
  TaskState,
  ActionState,
  ResourceState,
  SandboxState,
} from "@/lib/types";

export interface TaskDependencies {
  /** Tasks this task depends on (waiting for) */
  waitingOn: TaskState[];
  /** Tasks that depend on this task (blocking) */
  blocking: TaskState[];
}

export interface UseTaskDetailsResult {
  /** The task state, or null if not found */
  task: TaskState | null;
  /** Actions performed by this task's worker */
  actions: ActionState[];
  /** Resources produced by this task */
  resources: ResourceState[];
  /** Sandbox associated with this task (if any) */
  sandbox: SandboxState | undefined;
  /** Dependency information */
  dependencies: TaskDependencies;
  /** Whether the run state is still loading */
  isLoading: boolean;
  /** Any error from the run state */
  error: string | null;
}

/**
 * Hook to get detailed information about a specific task within a run.
 *
 * @param runId - The workflow run ID
 * @param taskId - The task ID (null means no task selected)
 */
export function useTaskDetails(
  runId: string,
  taskId: string | null
): UseTaskDetailsResult {
  const { runState, isLoading, error } = useRunState(runId);

  // Extract task
  const task = useMemo(() => {
    if (!runState || !taskId) return null;
    return runState.tasks.get(taskId) ?? null;
  }, [runState, taskId]);

  // Extract actions for this task
  const actions = useMemo(() => {
    if (!runState || !taskId) return [];
    return runState.actionsByTask.get(taskId) ?? [];
  }, [runState, taskId]);

  // Extract resources for this task
  const resources = useMemo(() => {
    if (!runState || !taskId) return [];
    return runState.resourcesByTask.get(taskId) ?? [];
  }, [runState, taskId]);

  // Extract sandbox for this task
  const sandbox = useMemo(() => {
    if (!runState || !taskId) return undefined;
    return runState.sandboxesByTask.get(taskId);
  }, [runState, taskId]);

  // Calculate dependencies
  const dependencies = useMemo((): TaskDependencies => {
    if (!runState || !task) {
      return { waitingOn: [], blocking: [] };
    }

    // Tasks this task depends on (waiting for)
    const waitingOn: TaskState[] = [];
    for (const depId of task.dependsOnIds) {
      const depTask = runState.tasks.get(depId);
      if (depTask) {
        waitingOn.push(depTask);
      }
    }

    // Tasks that depend on this task (blocking)
    const blocking: TaskState[] = [];
    for (const t of Array.from(runState.tasks.values())) {
      if (t.dependsOnIds.includes(task.id)) {
        blocking.push(t);
      }
    }

    return { waitingOn, blocking };
  }, [runState, task]);

  return {
    task,
    actions,
    resources,
    sandbox,
    dependencies,
    isLoading,
    error,
  };
}
