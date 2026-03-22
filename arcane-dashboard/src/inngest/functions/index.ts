/**
 * Inngest Functions for Dashboard Event Handling
 *
 * These functions receive events from the Python backend via Inngest,
 * update the DashboardStore, and broadcast changes to connected clients via Socket.io.
 */

import { inngest } from "../client";
import { store } from "@/lib/state/store";
import {
  broadcastRunStarted,
  broadcastCohortUpdated,
  broadcastRunCompleted,
  broadcastTaskEvaluation,
  broadcastTaskStatus,
  broadcastThreadMessage,
  broadcastActionNew,
  broadcastActionCompleted,
  broadcastResourceNew,
  broadcastSandboxCreated,
  broadcastSandboxCommand,
  broadcastSandboxClosed,
} from "@/lib/socket/server";
import {
  parseDashboardAgentActionCompletedData,
  parseDashboardAgentActionStartedData,
  parseDashboardCohortUpdatedData,
  parseDashboardResourcePublishedData,
  parseDashboardSandboxClosedData,
  parseDashboardSandboxCommandData,
  parseDashboardSandboxCreatedData,
  parseDashboardTaskEvaluationUpdatedData,
  parseDashboardTaskStatusChangedData,
  parseDashboardThreadMessageCreatedData,
  parseDashboardWorkflowCompletedData,
  parseDashboardWorkflowStartedData,
} from "@/lib/contracts/events";
import {
  ActionState,
  ResourceState,
  SandboxCommandState,
  TaskStatus,
} from "@/lib/types";

// =============================================================================
// Workflow Lifecycle Events
// =============================================================================

const onWorkflowStarted = inngest.createFunction(
  { id: "dashboard-workflow-started" },
  { event: "dashboard/workflow.started" },
  async ({ event }) => {
    const payload = parseDashboardWorkflowStartedData(event.data);
    const {
      run_id,
      experiment_id,
      workflow_name,
      task_tree,
      started_at,
      total_tasks,
      total_leaf_tasks,
    } = payload;

    console.log("[Dashboard] Workflow started - INNGEST FUNCTION TRIGGERED:", {
      run_id,
      workflow_name,
      total_tasks,
    });

    // Update store
    store.initializeRun(
      run_id,
      experiment_id,
      workflow_name,
      task_tree,
      started_at,
      total_tasks,
      total_leaf_tasks
    );
    
    // Log store state after initialization
    const allRuns = store.getAllRuns();
    console.log(`[Dashboard] Store now has ${allRuns.length} runs:`, allRuns.map(r => ({ id: r.id, name: r.name, status: r.status })));

    // Broadcast to all clients (new run appeared)
    console.log("[Dashboard] About to call broadcastRunStarted...");
    broadcastRunStarted(run_id, workflow_name);
    console.log("[Dashboard] broadcastRunStarted completed");

    // Prune old runs to prevent memory growth
    store.pruneOldRuns();

    return { success: true };
  }
);

const onWorkflowCompleted = inngest.createFunction(
  { id: "dashboard-workflow-completed" },
  { event: "dashboard/workflow.completed" },
  async ({ event }) => {
    const payload = parseDashboardWorkflowCompletedData(event.data);
    const {
      run_id,
      status,
      completed_at,
      duration_seconds,
      final_score,
      error,
    } = payload;

    console.log("[Dashboard] Workflow completed:", {
      run_id,
      status,
      duration_seconds,
    });

    // Update store
    store.completeRun(
      run_id,
      status,
      completed_at,
      duration_seconds,
      final_score ?? null,
      error ?? null
    );

    // Broadcast to run subscribers
    broadcastRunCompleted(
      run_id,
      status,
      completed_at,
      duration_seconds,
      final_score ?? null,
      error ?? null
    );

    return { success: true };
  }
);

const onCohortUpdated = inngest.createFunction(
  { id: "dashboard-cohort-updated" },
  { event: "dashboard/cohort.updated" },
  async ({ event }) => {
    const payload = parseDashboardCohortUpdatedData(event.data);
    console.log("[Dashboard] Cohort updated:", {
      cohort_id: payload.cohort_id,
      total_runs: payload.summary.total_runs,
    });
    broadcastCohortUpdated(payload);
    return { success: true };
  },
);

const onThreadMessageCreated = inngest.createFunction(
  { id: "dashboard-thread-message-created" },
  { event: "dashboard/thread.message_created" },
  async ({ event }) => {
    const payload = parseDashboardThreadMessageCreatedData(event.data);
    store.upsertThread(payload.run_id, payload.thread);
    broadcastThreadMessage(payload);
    return { success: true };
  },
);

const onTaskEvaluationUpdated = inngest.createFunction(
  { id: "dashboard-task-evaluation-updated" },
  { event: "dashboard/task.evaluation_updated" },
  async ({ event }) => {
    const payload = parseDashboardTaskEvaluationUpdatedData(event.data);
    store.upsertEvaluation(payload.run_id, payload.task_id, payload.evaluation);
    broadcastTaskEvaluation(payload);
    return { success: true };
  },
);

// =============================================================================
// Task Lifecycle Events
// =============================================================================

const onTaskStatusChanged = inngest.createFunction(
  { id: "dashboard-task-status-changed" },
  { event: "dashboard/task.status_changed" },
  async ({ event }) => {
    const payload = parseDashboardTaskStatusChangedData(event.data);
    const {
      run_id,
      task_id,
      task_name,
      new_status,
      timestamp,
      assigned_worker_id,
      assigned_worker_name,
    } = payload;

    console.log("[Dashboard] Task status changed:", {
      run_id,
      task_id,
      task_name,
      new_status,
    });

    // Update store
    store.updateTaskStatus(
      run_id,
      task_id,
      new_status as TaskStatus,
      timestamp,
      assigned_worker_id ?? null,
      assigned_worker_name ?? null
    );

    // Broadcast to run subscribers
    broadcastTaskStatus(
      run_id,
      task_id,
      new_status as TaskStatus,
      timestamp,
      assigned_worker_id ?? null,
      assigned_worker_name ?? null
    );

    return { success: true };
  }
);

// =============================================================================
// Agent Action Events
// =============================================================================

const onAgentActionStarted = inngest.createFunction(
  { id: "dashboard-agent-action-started" },
  { event: "dashboard/agent.action_started" },
  async ({ event }) => {
    const payload = parseDashboardAgentActionStartedData(event.data);
    const {
      run_id,
      task_id,
      action_id,
      worker_id,
      worker_name,
      action_type,
      action_input,
      timestamp,
    } = payload;

    console.log("[Dashboard] Agent action started:", {
      run_id,
      task_id,
      action_type,
      worker_name,
    });

    // Create action state
    const action: ActionState = {
      id: action_id,
      taskId: task_id,
      workerId: worker_id,
      workerName: worker_name,
      type: action_type,
      input: action_input,
      output: null,
      status: "started",
      startedAt: timestamp,
      completedAt: null,
      durationMs: null,
      success: false,
      error: null,
    };

    // Update store
    store.addAction(run_id, action);

    // Broadcast to run subscribers
    broadcastActionNew(run_id, action);

    return { success: true };
  }
);

const onAgentActionCompleted = inngest.createFunction(
  { id: "dashboard-agent-action-completed" },
  { event: "dashboard/agent.action_completed" },
  async ({ event }) => {
    const payload = parseDashboardAgentActionCompletedData(event.data);
    const {
      run_id,
      task_id,
      action_id,
      worker_id,
      action_type,
      action_output,
      duration_ms,
      success,
      error,
      timestamp,
    } = payload;

    console.log("[Dashboard] Agent action completed:", {
      run_id,
      task_id,
      action_type,
      success,
      duration_ms,
    });

    // Get existing action to preserve input and worker_name
    const existingActions = store.getActionsForTask(run_id, task_id);
    const existingAction = existingActions.find((a) => a.id === action_id);

    // Create/update action state
    const action: ActionState = {
      id: action_id,
      taskId: task_id,
      workerId: worker_id,
      workerName: existingAction?.workerName ?? "",
      type: action_type,
      input: existingAction?.input ?? "",
      output: action_output ?? null,
      status: success ? "completed" : "failed",
      startedAt: existingAction?.startedAt ?? timestamp,
      completedAt: timestamp,
      durationMs: duration_ms ?? null,
      success,
      error: error ?? null,
    };

    // Update store
    store.addAction(run_id, action);

    // Broadcast to run subscribers
    broadcastActionCompleted(run_id, action);

    return { success: true };
  }
);

// =============================================================================
// Resource Events
// =============================================================================

const onResourcePublished = inngest.createFunction(
  { id: "dashboard-resource-published" },
  { event: "dashboard/resource.published" },
  async ({ event }) => {
    const payload = parseDashboardResourcePublishedData(event.data);
    const {
      run_id,
      task_id,
      task_execution_id,
      resource_id,
      resource_name,
      mime_type,
      size_bytes,
      file_path,
      timestamp,
    } = payload;

    console.log("[Dashboard] Resource published:", {
      run_id,
      task_id,
      resource_name,
      mime_type,
      size_bytes,
    });

    // Create resource state
    const resource: ResourceState = {
      id: resource_id,
      taskId: task_id,
      taskExecutionId: task_execution_id,
      name: resource_name,
      mimeType: mime_type,
      sizeBytes: size_bytes,
      filePath: file_path,
      createdAt: timestamp,
    };

    // Update store
    store.addResource(run_id, resource);

    // Broadcast to run subscribers
    broadcastResourceNew(run_id, resource);

    return { success: true };
  }
);

// =============================================================================
// Sandbox Lifecycle Events
// =============================================================================

const onSandboxCreated = inngest.createFunction(
  { id: "dashboard-sandbox-created" },
  { event: "dashboard/sandbox.created" },
  async ({ event }) => {
    const payload = parseDashboardSandboxCreatedData(event.data);
    const { run_id, task_id, sandbox_id, template, timeout_minutes, timestamp } =
      payload;

    console.log("[Dashboard] Sandbox created:", {
      run_id,
      task_id,
      sandbox_id,
      template,
    });

    const runId = run_id;

    // Update store
    store.createSandbox(
      runId,
      task_id,
      sandbox_id,
      template ?? null,
      timeout_minutes,
      timestamp
    );

    // Broadcast to run subscribers
    const sandbox = store.getSandboxForTask(runId, task_id);
    if (sandbox) {
      broadcastSandboxCreated(runId, sandbox);
    }

    return { success: true };
  }
);

const onSandboxCommand = inngest.createFunction(
  { id: "dashboard-sandbox-command" },
  { event: "dashboard/sandbox.command" },
  async ({ event }) => {
    const payload = parseDashboardSandboxCommandData(event.data);
    const {
      task_id,
      sandbox_id,
      command,
      stdout,
      stderr,
      exit_code,
      duration_ms,
      timestamp,
    } = payload;

    console.log("[Dashboard] Sandbox command:", {
      task_id,
      sandbox_id,
      command,
      exit_code,
    });

    // Find the run_id for this task
    const runs = store.getAllRuns();
    let runId: string | null = null;

    for (const run of runs) {
      if (run.tasks.has(task_id)) {
        runId = run.id;
        break;
      }
    }

    if (!runId) {
      console.warn(
        `[Dashboard] Could not find run for task ${task_id} in sandbox.command`
      );
      return { success: false, error: "Run not found" };
    }

    // Create command state
    const commandState: SandboxCommandState = {
      command,
      stdout: stdout ?? null,
      stderr: stderr ?? null,
      exitCode: exit_code ?? null,
      durationMs: duration_ms ?? null,
      timestamp,
    };

    // Update store
    store.addSandboxCommand(runId, task_id, commandState);

    // Broadcast to run subscribers
    broadcastSandboxCommand(runId, task_id, commandState);

    return { success: true };
  }
);

const onSandboxClosed = inngest.createFunction(
  { id: "dashboard-sandbox-closed" },
  { event: "dashboard/sandbox.closed" },
  async ({ event }) => {
    const { task_id, sandbox_id, reason, timestamp } = parseDashboardSandboxClosedData(
      event.data,
    );

    console.log("[Dashboard] Sandbox closed:", {
      task_id,
      sandbox_id,
      reason,
    });

    // Find the run_id for this task
    const runs = store.getAllRuns();
    let runId: string | null = null;

    for (const run of runs) {
      if (run.tasks.has(task_id)) {
        runId = run.id;
        break;
      }
    }

    if (!runId) {
      console.warn(
        `[Dashboard] Could not find run for task ${task_id} in sandbox.closed`
      );
      return { success: false, error: "Run not found" };
    }

    // Update store
    store.closeSandbox(runId, task_id, reason, timestamp);

    // Broadcast to run subscribers
    broadcastSandboxClosed(runId, task_id, reason);

    return { success: true };
  }
);

// =============================================================================
// Export all functions
// =============================================================================

export const functions = [
  onWorkflowStarted,
  onWorkflowCompleted,
  onCohortUpdated,
  onThreadMessageCreated,
  onTaskEvaluationUpdated,
  onTaskStatusChanged,
  onAgentActionStarted,
  onAgentActionCompleted,
  onResourcePublished,
  onSandboxCreated,
  onSandboxCommand,
  onSandboxClosed,
];
