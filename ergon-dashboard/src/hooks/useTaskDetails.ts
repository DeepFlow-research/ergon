"use client";

/**
 * useTaskDetails - Convenience hook to extract task-specific data from runState.
 *
 * Provides easy access to a task's details including its actions, resources,
 * sandbox, and dependency information.
 */

import { useMemo } from "react";
import {
  ExecutionAttemptState,
  TaskState,
  CommunicationThreadState,
  ResourceState,
  SandboxState,
  TaskEvaluationState,
  WorkflowRunState,
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
  /** Resources produced by this task */
  resources: ResourceState[];
  /** Execution attempts for this task */
  executions: ExecutionAttemptState[];
  /** Sandbox associated with this task (if any) */
  sandbox: SandboxState | undefined;
  /** Communication threads relevant to this task or run */
  threads: CommunicationThreadState[];
  /** Evaluation snapshot at task scope, or run scope if only that exists */
  evaluation: TaskEvaluationState | null;
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
  runState: WorkflowRunState | null,
  taskId: string | null
): UseTaskDetailsResult {
  // Extract task
  const task = useMemo(() => {
    if (!runState || !taskId) return null;
    return runState.tasks.get(taskId) ?? null;
  }, [runState, taskId]);

  // Extract resources for this task
  const resources = useMemo(() => {
    if (!runState || !taskId) return [];
    return runState.resourcesByTask.get(taskId) ?? [];
  }, [runState, taskId]);

  const executions = useMemo(() => {
    if (!runState || !taskId) return [];
    return runState.executionsByTask.get(taskId) ?? [];
  }, [runState, taskId]);

  // Extract sandbox for this task
  const sandbox = useMemo(() => {
    if (!runState || !taskId) return undefined;
    return runState.sandboxesByTask.get(taskId);
  }, [runState, taskId]);

  const threads = useMemo(() => {
    if (!runState || !taskId) return [];
    return runState.threads.filter((thread) => thread.taskId === null || thread.taskId === taskId);
  }, [runState, taskId]);

  const evaluation = useMemo(() => {
    if (!runState || !taskId) return null;
    return runState.evaluationsByTask.get(taskId) ?? runState.evaluationsByTask.get("__run__") ?? null;
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
    resources,
    executions,
    sandbox,
    threads,
    evaluation,
    dependencies,
    isLoading: runState === null,
    error: null,
  };
}
