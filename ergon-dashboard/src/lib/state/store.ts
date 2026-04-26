/**
 * DashboardStore - In-memory state management for active workflow runs.
 *
 * This is intentionally simple - the dashboard is a diagnostic tool,
 * not a database of record. The Python backend + PostgreSQL is the source of truth.
 *
 * The store holds the current state of all active runs for quick access.
 * State is populated from Inngest events and broadcast to clients via Socket.io.
 * 
 * NOTE: Uses global singleton pattern to ensure the same store instance is used
 * across all module imports (important for Next.js API routes / Inngest functions).
 */

import { config } from "../config";
import {
  ContextEventState,
  ExecutionAttemptState,
  TaskStatus,
  TaskTreeNode,
  TaskState,
  CommunicationThreadState,
  ResourceState,
  SandboxState,
  SandboxCommandState,
  TaskEvaluationState,
  WorkflowRunState,
} from "../types";
import { applyGraphMutation as reduceGraphMutation } from "@/features/graph/state/graphMutationReducer";
import { inferTrigger } from "@/lib/runEvents";
import type { DashboardGraphMutationData } from "@/lib/contracts/events";
import type { TaskTransitionRecord } from "@/lib/types";

// Extend global to store DashboardStore instance across module loads
declare global {
  // eslint-disable-next-line no-var
  var __dashboardStore: DashboardStore | undefined;
}

class DashboardStore {
  private runs: Map<string, WorkflowRunState> = new Map();
  private pendingSandboxCommands: Map<string, Map<string, SandboxCommandState[]>> =
    new Map();

  // ==========================================================================
  // Queries
  // ==========================================================================

  getRun(runId: string): WorkflowRunState | undefined {
    return this.runs.get(runId);
  }

  getAllRuns(): WorkflowRunState[] {
    return Array.from(this.runs.values());
  }

  getActiveRuns(): WorkflowRunState[] {
    return this.getAllRuns().filter(
      (r) => r.status === "pending" || r.status === "executing" || r.status === "evaluating",
    );
  }

  getRecentRuns(limit: number = 10): WorkflowRunState[] {
    return this.getAllRuns()
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt))
      .slice(0, limit);
  }

  getTask(runId: string, taskId: string): TaskState | undefined {
    return this.runs.get(runId)?.tasks.get(taskId);
  }

  getTasksAtLevel(runId: string, level: number): TaskState[] {
    const run = this.runs.get(runId);
    if (!run) return [];
    return Array.from(run.tasks.values()).filter((t) => t.level === level);
  }

  getResourcesForTask(runId: string, taskId: string): ResourceState[] {
    return this.runs.get(runId)?.resourcesByTask.get(taskId) ?? [];
  }

  getSandboxForTask(runId: string, taskId: string): SandboxState | undefined {
    return this.runs.get(runId)?.sandboxesByTask.get(taskId);
  }

  reset(): void {
    this.runs.clear();
    this.pendingSandboxCommands.clear();
  }

  seedRun(run: WorkflowRunState): void {
    this.runs.set(run.id, run);
  }

  // ==========================================================================
  // Mutations (called by Inngest event handlers)
  // ==========================================================================

  /**
   * Initialize a new workflow run from a workflow.started event.
   */
  initializeRun(
    runId: string,
    experimentId: string,
    name: string,
    taskTree: TaskTreeNode,
    startedAt: string,
    totalTasks: number,
    totalLeafTasks: number
  ): WorkflowRunState {
    const tasks = this.parseTaskTree(taskTree);
    const rootTaskId = taskTree.id;

    const run: WorkflowRunState = {
      id: runId,
      experimentId,
      name,
      status: "executing",
      tasks,
      rootTaskId,
      resourcesByTask: new Map(),
      executionsByTask: new Map(),
      sandboxesByTask: new Map(),
      threads: [],
      evaluationsByTask: new Map(),
      contextEventsByTask: new Map(),
      startedAt,
      completedAt: null,
      durationSeconds: null,
      totalTasks,
      totalLeafTasks,
      completedTasks: 0,
      runningTasks: 0,
      failedTasks: 0,
      cancelledTasks: 0,
      finalScore: null,
      error: null,
      edges: new Map(),
      annotationsByTarget: new Map(),
      unhandledMutations: [],
    };

    this.runs.set(runId, run);
    return run;
  }

  /**
   * Mark a workflow run as completed or failed.
   */
  completeRun(
    runId: string,
    status: "completed" | "failed",
    completedAt: string,
    durationSeconds: number,
    finalScore: number | null,
    error: string | null
  ): void {
    const run = this.runs.get(runId);
    if (!run) return;

    run.status = status;
    run.completedAt = completedAt;
    run.durationSeconds = durationSeconds;
    run.finalScore = finalScore;
    run.error = error;
  }

  /**
   * Update a task's status from a task.status_changed event.
   */
  updateTaskStatus(
    runId: string,
    taskId: string,
    newStatus: TaskStatus,
    timestamp: string,
    assignedWorkerId?: string | null,
    assignedWorkerName?: string | null
  ): void {
    const run = this.runs.get(runId);
    const task = run?.tasks.get(taskId);
    if (!run || !task) return;

    const nextExecutionStatus =
      newStatus === TaskStatus.READY ? TaskStatus.PENDING : newStatus;
    const executions = run.executionsByTask.get(taskId) ?? [];
    const latestExecution = executions[executions.length - 1];

    if (newStatus === TaskStatus.RUNNING) {
      if (
        !latestExecution ||
        latestExecution.status === TaskStatus.COMPLETED ||
        latestExecution.status === TaskStatus.FAILED
      ) {
        const nextExecution: ExecutionAttemptState = {
          id: `${taskId}:attempt:${executions.length + 1}`,
          taskId,
          attemptNumber: executions.length + 1,
          status: TaskStatus.RUNNING,
          agentId: assignedWorkerId ?? task.assignedWorkerId,
          agentName: assignedWorkerName ?? task.assignedWorkerName,
          startedAt: timestamp,
          completedAt: null,
          finalAssistantMessage: null,
          outputResourceIds: [],
          errorMessage: null,
          score: null,
          evaluationDetails: {},
        };
        run.executionsByTask.set(taskId, [...executions, nextExecution]);
      } else {
        latestExecution.status = TaskStatus.RUNNING;
        latestExecution.startedAt = latestExecution.startedAt ?? timestamp;
        latestExecution.agentId = assignedWorkerId ?? latestExecution.agentId;
        latestExecution.agentName = assignedWorkerName ?? latestExecution.agentName;
      }
    } else if (latestExecution) {
      latestExecution.status = nextExecutionStatus;
      if (newStatus === TaskStatus.COMPLETED || newStatus === TaskStatus.FAILED) {
        latestExecution.completedAt = timestamp;
        if (newStatus === TaskStatus.FAILED && latestExecution.errorMessage === null) {
          latestExecution.errorMessage = "Task execution failed";
        }
      }
    }

    const fromStatus = task.status;
    task.status = newStatus;

    if (fromStatus !== newStatus) {
      const trigger = inferTrigger(fromStatus, newStatus);
      const record: TaskTransitionRecord = {
        from: fromStatus,
        to: newStatus,
        trigger,
        at: timestamp,
        sequence: null,
        actor: assignedWorkerName ?? task.assignedWorkerName ?? null,
        reason: null,
      };
      task.history = [...(task.history ?? []), record];
      task.lastTrigger = trigger;
    }

    if (assignedWorkerId !== undefined) {
      task.assignedWorkerId = assignedWorkerId;
    }
    if (assignedWorkerName !== undefined) {
      task.assignedWorkerName = assignedWorkerName;
    }

    // Update timestamps
    if (newStatus === TaskStatus.RUNNING && !task.startedAt) {
      task.startedAt = timestamp;
    }
    if (
      newStatus === TaskStatus.COMPLETED ||
      newStatus === TaskStatus.FAILED
    ) {
      task.completedAt = timestamp;
    }

    // Update run metrics
    this.recalculateRunMetrics(run);
  }

  /**
   * Add a resource from a resource.published event.
   */
  addResource(runId: string, resource: ResourceState): void {
    const run = this.runs.get(runId);
    if (!run) return;

    const taskResources = run.resourcesByTask.get(resource.taskId) ?? [];
    taskResources.push(resource);
    run.resourcesByTask.set(resource.taskId, taskResources);
  }

  upsertThread(runId: string, thread: CommunicationThreadState): void {
    const run = this.runs.get(runId);
    if (!run) return;

    const existingIndex = run.threads.findIndex((candidate) => candidate.id === thread.id);
    if (existingIndex >= 0) {
      run.threads[existingIndex] = thread;
    } else {
      run.threads.push(thread);
    }
  }

  addContextEvent(runId: string, taskNodeId: string, event: ContextEventState): void {
    const run = this.runs.get(runId);
    if (!run) return;
    const existing = run.contextEventsByTask.get(taskNodeId) ?? [];
    if (existing.some((e) => e.id === event.id)) return; // deduplicate
    run.contextEventsByTask.set(
      taskNodeId,
      [...existing, event].sort((a, b) => a.sequence - b.sequence),
    );
  }

  upsertEvaluation(runId: string, taskId: string | null, evaluation: TaskEvaluationState): void {
    const run = this.runs.get(runId);
    if (!run) return;

    run.evaluationsByTask.set(taskId ?? "__run__", evaluation);
  }

  /**
   * Create or update a sandbox from sandbox.created event.
   */
  createSandbox(
    runId: string,
    taskId: string,
    sandboxId: string,
    template: string | null,
    timeoutMinutes: number,
    timestamp: string
  ): void {
    const run = this.runs.get(runId);
    if (!run) return;

    const pendingCommands =
      this.pendingSandboxCommands.get(runId)?.get(taskId) ?? [];

    const sandbox: SandboxState = {
      sandboxId,
      taskId,
      template,
      timeoutMinutes,
      status: "active",
      createdAt: timestamp,
      closedAt: null,
      closeReason: null,
      commands: pendingCommands,
    };

    run.sandboxesByTask.set(taskId, sandbox);

    const pendingByTask = this.pendingSandboxCommands.get(runId);
    if (pendingByTask) {
      pendingByTask.delete(taskId);
      if (pendingByTask.size === 0) {
        this.pendingSandboxCommands.delete(runId);
      }
    }
  }

  /**
   * Add a command to a sandbox from sandbox.command event.
   */
  addSandboxCommand(
    runId: string,
    taskId: string,
    command: SandboxCommandState
  ): void {
    const run = this.runs.get(runId);
    const sandbox = run?.sandboxesByTask.get(taskId);
    if (!run) return;

    if (!sandbox) {
      const pendingByTask =
        this.pendingSandboxCommands.get(runId) ?? new Map();
      const pendingCommands = pendingByTask.get(taskId) ?? [];
      pendingCommands.push(command);
      pendingByTask.set(taskId, pendingCommands);
      this.pendingSandboxCommands.set(runId, pendingByTask);
      return;
    }

    sandbox.commands.push(command);
  }

  /**
   * Close a sandbox from sandbox.closed event.
   */
  closeSandbox(
    runId: string,
    taskId: string,
    reason: string,
    timestamp: string
  ): void {
    const run = this.runs.get(runId);
    const sandbox = run?.sandboxesByTask.get(taskId);
    if (!sandbox) return;

    sandbox.status = "closed";
    sandbox.closedAt = timestamp;
    sandbox.closeReason = reason;
  }

  applyGraphMutation(runId: string, mutation: DashboardGraphMutationData): void {
    const run = this.runs.get(runId);
    if (!run) return;
    const updated = reduceGraphMutation(run, mutation);
    this.runs.set(runId, updated);
  }

  /**
   * Remove old completed runs to prevent memory growth.
   * Keeps the most recent N runs.
   */
  pruneOldRuns(keepCount: number = config.maxRunsToKeep): void {
    const runs = this.getAllRuns();
    if (runs.length <= keepCount) return;

    // Sort by startedAt descending, keep the newest
    const sorted = runs.sort((a, b) => b.startedAt.localeCompare(a.startedAt));
    const toRemove = sorted.slice(keepCount);

    for (const run of toRemove) {
      // Only remove completed/failed runs
      if (run.status === "completed" || run.status === "failed") {
        this.runs.delete(run.id);
      }
    }
  }

  // ==========================================================================
  // Private Helpers
  // ==========================================================================

  /**
   * Parse a TaskTreeNode into a flat Map<taskId, TaskState>.
   * Computes level (depth) for each task.
   */
  private parseTaskTree(
    tree: TaskTreeNode,
    level: number = 0,
    parentId: string | null = null
  ): Map<string, TaskState> {
    const tasks = new Map<string, TaskState>();

    const taskState: TaskState = {
      id: tree.id,
      name: tree.name,
      description: tree.description,
      status: TaskStatus.PENDING,
      parentId,
      childIds: tree.children.map((c) => c.id),
      dependsOnIds: tree.depends_on,
      assignedWorkerId: tree.assigned_to?.id ?? null,
      assignedWorkerName: tree.assigned_to?.name ?? null,
      startedAt: null,
      completedAt: null,
      isLeaf: tree.is_leaf,
      level,
    };

    tasks.set(tree.id, taskState);

    // Recursively parse children
    for (const child of tree.children) {
      const childTasks = this.parseTaskTree(child, level + 1, tree.id);
      for (const [id, state] of Array.from(childTasks.entries())) {
        tasks.set(id, state);
      }
    }

    return tasks;
  }

  /**
   * Recalculate run metrics based on current task states.
   */
  private recalculateRunMetrics(run: WorkflowRunState): void {
    let completed = 0;
    let running = 0;
    let failed = 0;

    for (const task of Array.from(run.tasks.values())) {
      // Only count leaf tasks for metrics
      if (!task.isLeaf) continue;

      switch (task.status) {
        case TaskStatus.COMPLETED:
          completed++;
          break;
        case TaskStatus.RUNNING:
          running++;
          break;
        case TaskStatus.FAILED:
          failed++;
          break;
      }
    }

    run.completedTasks = completed;
    run.runningTasks = running;
    run.failedTasks = failed;
  }
}

// Export singleton instance using global to persist across module reloads
// This ensures the same store instance is used by Inngest functions and Socket.io handlers
function getStore(): DashboardStore {
  if (!global.__dashboardStore) {
    console.log("[DashboardStore] Creating new global store instance");
    global.__dashboardStore = new DashboardStore();
  }
  return global.__dashboardStore;
}

export const store = getStore();
