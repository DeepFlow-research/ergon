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
  TaskStatus,
  TaskState,
  CommunicationThreadState,
  ResourceState,
  SandboxState,
  SandboxCommandState,
  TaskEvaluationState,
  SampleWorkspaceState,
} from "../types";
import { applyGraphMutation as reduceGraphMutation } from "@/features/graph/state/graphMutationReducer";
import type { DashboardGraphMutationData } from "@/lib/contracts/events";
import type { RunSnapshot } from "@/lib/contracts/rest";
import { hydrateRunSnapshot } from "@/lib/sample-state/hydrate";
import {
  applySandboxClosed,
  applySandboxCommand,
  applySandboxCreated,
  applyTaskStatusChanged,
} from "@/lib/sample-state/reducers";

// Extend global to store DashboardStore instance across module loads
declare global {
  // eslint-disable-next-line no-var
  var __dashboardStore: DashboardStore | undefined;
}

class DashboardStore {
  private runs: Map<string, SampleWorkspaceState> = new Map();
  private pendingSandboxCommands: Map<string, Map<string, SandboxCommandState[]>> =
    new Map();

  // ==========================================================================
  // Queries
  // ==========================================================================

  getRun(sampleId: string): SampleWorkspaceState | undefined {
    return this.runs.get(sampleId);
  }

  getAllRuns(): SampleWorkspaceState[] {
    return Array.from(this.runs.values());
  }

  getActiveRuns(): SampleWorkspaceState[] {
    return this.getAllRuns().filter(
      (r) => r.status === "pending" || r.status === "executing" || r.status === "evaluating",
    );
  }

  getRecentRuns(limit: number = 10): SampleWorkspaceState[] {
    return this.getAllRuns()
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt))
      .slice(0, limit);
  }

  getTask(sampleId: string, taskId: string): TaskState | undefined {
    return this.runs.get(sampleId)?.tasks.get(taskId);
  }

  getTasksAtLevel(sampleId: string, level: number): TaskState[] {
    const run = this.runs.get(sampleId);
    if (!run) return [];
    return Array.from(run.tasks.values()).filter((t) => t.level === level);
  }

  getResourcesForTask(sampleId: string, taskId: string): ResourceState[] {
    return this.runs.get(sampleId)?.resourcesByTask.get(taskId) ?? [];
  }

  getSandboxForTask(sampleId: string, taskId: string): SandboxState | undefined {
    return this.runs.get(sampleId)?.sandboxesByTask.get(taskId);
  }

  reset(): void {
    this.runs.clear();
    this.pendingSandboxCommands.clear();
  }

  seedRun(run: SampleWorkspaceState): void {
    this.runs.set(run.id, run);
  }

  // ==========================================================================
  // Mutations (called by Inngest event handlers)
  // ==========================================================================

  /**
   * Initialize a new workflow run from a workflow.started event.
   */
  initializeRun(
    sampleId: string,
    definitionId: string,
    name: string,
    snapshot: RunSnapshot,
    startedAt: string,
    totalTasks: number,
    totalLeafTasks: number
  ): SampleWorkspaceState {
    const hydrated = hydrateRunSnapshot({
      ...snapshot,
      id: sampleId,
      definitionId,
      name,
      status: "executing",
      startedAt,
      totalTasks,
      totalLeafTasks,
    });
    const run: SampleWorkspaceState = {
      ...hydrated,
      status: "executing",
      completedAt: null,
      durationSeconds: null,
      finalScore: null,
      error: null,
    };

    this.runs.set(sampleId, run);
    return run;
  }

  /**
   * Mark a workflow run as completed or failed.
   */
  completeRun(
    sampleId: string,
    status: "completed" | "failed",
    completedAt: string,
    durationSeconds: number,
    finalScore: number | null,
    error: string | null
  ): void {
    const run = this.runs.get(sampleId);
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
    sampleId: string,
    taskId: string,
    newStatus: TaskStatus,
    timestamp: string,
    assignedWorkerId?: string | null,
    assignedWorkerSlug?: string | null
  ): void {
    const run = this.runs.get(sampleId);
    if (!run) return;

    this.runs.set(
      sampleId,
      applyTaskStatusChanged(run, {
        sampleId,
        taskId,
        status: newStatus,
        timestamp,
        assignedWorkerId,
        assignedWorkerSlug,
      }),
    );
  }

  /**
   * Add a resource from a resource.published event.
   */
  addResource(sampleId: string, resource: ResourceState): void {
    const run = this.runs.get(sampleId);
    if (!run) return;

    const taskResources = run.resourcesByTask.get(resource.taskId) ?? [];
    taskResources.push(resource);
    run.resourcesByTask.set(resource.taskId, taskResources);
  }

  upsertThread(sampleId: string, thread: CommunicationThreadState): void {
    const run = this.runs.get(sampleId);
    if (!run) return;

    const existingIndex = run.threads.findIndex((candidate) => candidate.id === thread.id);
    if (existingIndex >= 0) {
      run.threads[existingIndex] = thread;
    } else {
      run.threads.push(thread);
    }
  }

  addContextEvent(sampleId: string, taskId: string, event: ContextEventState): void {
    const run = this.runs.get(sampleId);
    if (!run) return;
    const existing = run.contextEventsByTask.get(taskId) ?? [];
    if (existing.some((e) => e.id === event.id)) return; // deduplicate
    run.contextEventsByTask.set(
      taskId,
      [...existing, event].sort((a, b) => a.sequence - b.sequence),
    );
  }

  upsertEvaluation(sampleId: string, taskId: string | null, evaluation: TaskEvaluationState): void {
    const run = this.runs.get(sampleId);
    if (!run) return;

    run.evaluationsByTask.set(taskId ?? "__run__", evaluation);
  }

  /**
   * Create or update a sandbox from sandbox.created event.
   */
  createSandbox(
    sampleId: string,
    taskId: string,
    sandboxId: string,
    template: string | null,
    timeoutMinutes: number,
    timestamp: string
  ): void {
    const run = this.runs.get(sampleId);
    if (!run) return;

    const pendingCommands =
      this.pendingSandboxCommands.get(sampleId)?.get(taskId) ?? [];

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

    this.runs.set(sampleId, applySandboxCreated(run, sandbox));

    const pendingByTask = this.pendingSandboxCommands.get(sampleId);
    if (pendingByTask) {
      pendingByTask.delete(taskId);
      if (pendingByTask.size === 0) {
        this.pendingSandboxCommands.delete(sampleId);
      }
    }
  }

  /**
   * Add a command to a sandbox from sandbox.command event.
   */
  addSandboxCommand(
    sampleId: string,
    taskId: string,
    command: SandboxCommandState
  ): void {
    const run = this.runs.get(sampleId);
    const sandbox = run?.sandboxesByTask.get(taskId);
    if (!run) return;

    if (!sandbox) {
      const pendingByTask =
        this.pendingSandboxCommands.get(sampleId) ?? new Map();
      const pendingCommands = pendingByTask.get(taskId) ?? [];
      pendingCommands.push(command);
      pendingByTask.set(taskId, pendingCommands);
      this.pendingSandboxCommands.set(sampleId, pendingByTask);
      return;
    }

    this.runs.set(sampleId, applySandboxCommand(run, taskId, command));
  }

  /**
   * Close a sandbox from sandbox.closed event.
   */
  closeSandbox(
    sampleId: string,
    taskId: string,
    reason: string,
    timestamp: string
  ): void {
    const run = this.runs.get(sampleId);
    if (!run) return;

    this.runs.set(sampleId, applySandboxClosed(run, taskId, reason, timestamp));
  }

  applyGraphMutation(sampleId: string, mutation: DashboardGraphMutationData): void {
    const run = this.runs.get(sampleId);
    if (!run) return;
    const updated = reduceGraphMutation(run, mutation);
    this.runs.set(sampleId, updated);
  }

  /**
   * Remove old completed runs to prevent memory growth.
   * Keeps the most recent N runs.
   */
  pruneOldSamples(keepCount: number = config.maxSamplesToKeep): void {
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
