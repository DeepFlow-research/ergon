/**
 * Inngest Functions for Dashboard Event Handling
 *
 * These functions receive events from the Python backend via Inngest,
 * update the DashboardStore, and broadcast changes to connected clients via Socket.io.
 */

import { inngest } from "../client";
import { store } from "@/lib/state/store";
import {
  broadcastSampleStarted,
  broadcastSampleCompleted,
  broadcastGraphMutation,
  broadcastTaskEvaluation,
  broadcastTaskStatus,
  broadcastThreadMessage,
  broadcastResourceNew,
  broadcastSandboxCreated,
  broadcastSandboxCommand,
  broadcastSandboxClosed,
} from "@/lib/socket/server";
import {
  isDashboardSampleRuntimeGraphEvent,
  parseDashboardSampleRuntimeEventData,
  parseDashboardTaskEvaluationUpdatedData,
  parseDashboardThreadMessageCreatedData,
  parseDashboardWorkflowStartedData,
} from "@/lib/contracts/events";
import {
  DashboardResourcePublishedEventSchema,
  DashboardSandboxClosedEventSchema,
  DashboardSandboxCommandEventSchema,
  DashboardSandboxCreatedEventSchema,
  DashboardTaskStatusChangedEventSchema,
  DashboardWorkflowCompletedEventSchema,
} from "@/generated/events";
import {
  ResourceState,
  SandboxCommandState,
  TaskStatus,
} from "@/lib/types";
import { onContextEvent } from "./onContextEvent";

// =============================================================================
// Workflow Lifecycle Events
// =============================================================================

const onWorkflowStarted = inngest.createFunction(
  { id: "dashboard-workflow-started" },
  { event: "dashboard/workflow.started" },
  async ({ event }) => {
    const payload = parseDashboardWorkflowStartedData(event.data);
    const {
      sample_id,
      workflow_name,
      snapshot,
      started_at,
      total_tasks,
      total_leaf_tasks,
    } = payload;

    console.log("[Dashboard] Workflow started - INNGEST FUNCTION TRIGGERED:", {
      sample_id,
      workflow_name,
      total_tasks,
    });

    // Update store
    store.initializeSample(
      sample_id,
      workflow_name,
      snapshot,
      started_at,
      total_tasks,
      total_leaf_tasks
    );
    
    // Log store state after initialization
    const allRuns = store.getAllSamples();
    console.log(`[Dashboard] Store now has ${allRuns.length} runs:`, allRuns.map(r => ({ id: r.id, name: r.name, status: r.status })));

    // Broadcast to all clients (new run appeared)
    console.log("[Dashboard] About to call broadcastSampleStarted...");
    broadcastSampleStarted(sample_id, workflow_name);
    console.log("[Dashboard] broadcastSampleStarted completed");

    // Prune old runs to prevent memory growth
    store.pruneOldSamples();

    return { success: true };
  }
);

const onWorkflowCompleted = inngest.createFunction(
  { id: "dashboard-workflow-completed" },
  { event: "dashboard/workflow.completed" },
  async ({ event }) => {
    const payload = DashboardWorkflowCompletedEventSchema.parse(event.data);
    const {
      sample_id,
      status,
      completed_at,
      duration_seconds,
      final_score,
      error,
    } = payload;
    // Generated schema types ``status`` as ``string``; the store/socket
    // layer narrows to the wire-level literal union.
    const narrowedStatus = status as "completed" | "failed";

    console.log("[Dashboard] Workflow completed:", {
      sample_id,
      status,
      duration_seconds,
    });

    // Update store
    store.completeSample(
      sample_id,
      narrowedStatus,
      completed_at,
      duration_seconds,
      final_score ?? null,
      error ?? null
    );

    // Broadcast to run subscribers
    broadcastSampleCompleted(
      sample_id,
      narrowedStatus,
      completed_at,
      duration_seconds,
      final_score ?? null,
      error ?? null
    );

    return { success: true };
  }
);

const onThreadMessageCreated = inngest.createFunction(
  { id: "dashboard-thread-message-created" },
  { event: "dashboard/thread.message_created" },
  async ({ event }) => {
    const payload = parseDashboardThreadMessageCreatedData(event.data);
    store.upsertThread(payload.sample_id, payload.thread);
    broadcastThreadMessage(payload);
    return { success: true };
  },
);

const onTaskEvaluationUpdated = inngest.createFunction(
  { id: "dashboard-task-evaluation-updated" },
  { event: "dashboard/task.evaluation_updated" },
  async ({ event }) => {
    const payload = parseDashboardTaskEvaluationUpdatedData(event.data);
    store.upsertEvaluation(payload.sample_id, payload.task_id, payload.evaluation);
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
    const payload = DashboardTaskStatusChangedEventSchema.parse(event.data);
    const {
      sample_id,
      task_id,
      task_name,
      new_status,
      timestamp,
      assigned_worker_id,
      assigned_worker_slug,
    } = payload;

    console.log("[Dashboard] Task status changed:", {
      sample_id,
      task_id,
      task_name,
      new_status,
    });

    // Update store
    store.updateTaskStatus(
      sample_id,
      task_id,
      new_status as TaskStatus,
      timestamp,
      assigned_worker_id ?? null,
      assigned_worker_slug ?? null
    );

    // Broadcast to run subscribers
    broadcastTaskStatus(
      sample_id,
      task_id,
      new_status as TaskStatus,
      timestamp,
      assigned_worker_id ?? null,
      assigned_worker_slug ?? null
    );

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
    const payload = DashboardResourcePublishedEventSchema.parse(event.data);
    const {
      sample_id,
      task_id,
      task_attempt_id,
      resource_id,
      resource_name,
      mime_type,
      size_bytes,
      file_path,
      timestamp,
    } = payload;

    console.log("[Dashboard] Resource published:", {
      sample_id,
      task_id,
      resource_name,
      mime_type,
      size_bytes,
    });

    // Create resource state
    const resource: ResourceState = {
      id: resource_id,
      taskId: task_id,
      taskAttemptId: task_attempt_id,
      name: resource_name,
      mimeType: mime_type,
      sizeBytes: size_bytes,
      filePath: file_path,
      createdAt: timestamp,
    };

    // Update store
    store.addResource(sample_id, resource);

    // Broadcast to run subscribers
    broadcastResourceNew(sample_id, resource);

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
    const payload = DashboardSandboxCreatedEventSchema.parse(event.data);
    const { sample_id, task_id, sandbox_id, template, timeout_minutes, timestamp } =
      payload;

    console.log("[Dashboard] Sandbox created:", {
      sample_id,
      task_id,
      sandbox_id,
      template,
    });

    const sampleId = sample_id;

    // Update store
    store.createSandbox(
      sampleId,
      task_id,
      sandbox_id,
      template ?? null,
      timeout_minutes,
      timestamp
    );

    // Broadcast to run subscribers
    const sandbox = store.getSandboxForTask(sampleId, task_id);
    if (sandbox) {
      broadcastSandboxCreated(sampleId, sandbox);
    }

    return { success: true };
  }
);

const onSandboxCommand = inngest.createFunction(
  { id: "dashboard-sandbox-command" },
  { event: "dashboard/sandbox.command" },
  async ({ event }) => {
    const payload = DashboardSandboxCommandEventSchema.parse(event.data);
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

    // Find the sample_id for this task
    const runs = store.getAllSamples();
    let sampleId: string | null = null;

    for (const run of runs) {
      if (run.tasks.has(task_id)) {
        sampleId = run.id;
        break;
      }
    }

    if (!sampleId) {
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
    store.addSandboxCommand(sampleId, task_id, commandState);

    // Broadcast to run subscribers
    broadcastSandboxCommand(sampleId, task_id, commandState);

    return { success: true };
  }
);

const onSandboxClosed = inngest.createFunction(
  { id: "dashboard-sandbox-closed" },
  { event: "dashboard/sandbox.closed" },
  async ({ event }) => {
    const { task_id, sandbox_id, reason, timestamp } =
      DashboardSandboxClosedEventSchema.parse(event.data);

    console.log("[Dashboard] Sandbox closed:", {
      task_id,
      sandbox_id,
      reason,
    });

    // Find the sample_id for this task
    const runs = store.getAllSamples();
    let sampleId: string | null = null;

    for (const run of runs) {
      if (run.tasks.has(task_id)) {
        sampleId = run.id;
        break;
      }
    }

    if (!sampleId) {
      console.warn(
        `[Dashboard] Could not find run for task ${task_id} in sandbox.closed`
      );
      return { success: false, error: "Run not found" };
    }

    // Update store
    store.closeSandbox(sampleId, task_id, reason, timestamp);

    // Broadcast to run subscribers
    broadcastSandboxClosed(sampleId, task_id, reason, timestamp);

    return { success: true };
  }
);

// =============================================================================
// Graph Mutation Events
// =============================================================================

const onGraphMutation = inngest.createFunction(
  { id: "handle-sample-runtime-event", name: "Handle Sample Runtime Event" },
  { event: "dashboard/sample.runtime_event" },
  async ({ event }) => {
    if (!isDashboardSampleRuntimeGraphEvent(event.data)) {
      return { success: true, ignored: true };
    }
    const mutation = parseDashboardSampleRuntimeEventData(event.data);
    store.applyGraphMutation(mutation.sample_id, mutation);
    broadcastGraphMutation(mutation.sample_id, mutation);
    return { success: true };
  },
);

// =============================================================================
// Export all functions
// =============================================================================

export const functions = [
  onWorkflowStarted,
  onWorkflowCompleted,
  onThreadMessageCreated,
  onTaskEvaluationUpdated,
  onTaskStatusChanged,
  onResourcePublished,
  onSandboxCreated,
  onSandboxCommand,
  onSandboxClosed,
  onGraphMutation,
  onContextEvent,
];
