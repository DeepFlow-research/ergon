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
  TaskStatus,
  TaskTreeNode,
  TaskState,
  ActionState,
  ResourceState,
  SandboxState,
  SandboxCommandState,
  WorkflowRunState,
} from "../types";

// Extend global to store DashboardStore instance across module loads
declare global {
  // eslint-disable-next-line no-var
  var __dashboardStore: DashboardStore | undefined;
}

class DashboardStore {
  private runs: Map<string, WorkflowRunState> = new Map();

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
    return this.getAllRuns().filter((r) => r.status === "running");
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

  getActionsForTask(runId: string, taskId: string): ActionState[] {
    return this.runs.get(runId)?.actionsByTask.get(taskId) ?? [];
  }

  getResourcesForTask(runId: string, taskId: string): ResourceState[] {
    return this.runs.get(runId)?.resourcesByTask.get(taskId) ?? [];
  }

  getSandboxForTask(runId: string, taskId: string): SandboxState | undefined {
    return this.runs.get(runId)?.sandboxesByTask.get(taskId);
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
      status: "running",
      tasks,
      rootTaskId,
      actionsByTask: new Map(),
      resourcesByTask: new Map(),
      sandboxesByTask: new Map(),
      startedAt,
      completedAt: null,
      durationSeconds: null,
      totalTasks,
      totalLeafTasks,
      completedTasks: 0,
      runningTasks: 0,
      failedTasks: 0,
      finalScore: null,
      error: null,
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

    task.status = newStatus;

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
   * Add or update an action from agent.action_started or agent.action_completed events.
   */
  addAction(runId: string, action: ActionState): void {
    const run = this.runs.get(runId);
    if (!run) return;

    const taskActions = run.actionsByTask.get(action.taskId) ?? [];

    // Check if this action already exists (update case)
    const existingIndex = taskActions.findIndex((a) => a.id === action.id);
    if (existingIndex >= 0) {
      taskActions[existingIndex] = action;
    } else {
      taskActions.push(action);
    }

    run.actionsByTask.set(action.taskId, taskActions);
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

    const sandbox: SandboxState = {
      sandboxId,
      taskId,
      template,
      timeoutMinutes,
      status: "active",
      createdAt: timestamp,
      closedAt: null,
      closeReason: null,
      commands: [],
    };

    run.sandboxesByTask.set(taskId, sandbox);
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
    if (!sandbox) return;

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
      if (run.status !== "running") {
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
