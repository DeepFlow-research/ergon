import type { ContextEventState } from "./contracts/contextEvents";
export type { ContextEventState };

import type {
  BenchmarkName as RestBenchmarkName,
  ExperimentDetail as RestExperimentDetail,
  SampleCommunicationMessage as RestSampleCommunicationMessage,
  SampleCommunicationThread as RestSampleCommunicationThread,
  SampleLifecycleStatus as RestSampleLifecycleStatus,
  SampleSnapshot,
  SampleSnapshotMetrics,
  SampleTaskEvaluation as RestSampleTaskEvaluation,
} from "@/lib/contracts/rest";
export type { SampleDashboardState } from "@/lib/sample-state/dashboard";
import type {
  DashboardSampleRuntimeEventData as GeneratedDashboardSampleRuntimeEventData,
  DashboardResourcePublishedData as GeneratedDashboardResourcePublishedData,
  SampleRuntimeEventSocketData as GeneratedSampleRuntimeEventSocketData,
  ResourceSocketData,
  SampleCompletedSocketData,
  DashboardSandboxClosedData as GeneratedDashboardSandboxClosedData,
  SandboxClosedSocketData,
  SandboxCommandSocketData,
  SandboxCreatedSocketData,
  DashboardSandboxCommandData as GeneratedDashboardSandboxCommandData,
  DashboardSandboxCreatedData as GeneratedDashboardSandboxCreatedData,
  DashboardTaskEvaluationUpdatedData as GeneratedDashboardTaskEvaluationUpdatedData,
  DashboardTaskStatusChangedData as GeneratedDashboardTaskStatusChangedData,
  DashboardThreadMessageCreatedData as GeneratedDashboardThreadMessageCreatedData,
  DashboardWorkflowCompletedData as GeneratedDashboardWorkflowCompletedData,
  DashboardWorkflowStartedData as GeneratedDashboardWorkflowStartedData,
  SampleListEntry,
  TaskStatusSocketData,
} from "@/lib/contracts/events";

// =============================================================================
// Internal enums mirrored from backend wire values
// =============================================================================

export enum TaskStatus {
  PENDING = "pending",
  READY = "ready",
  RUNNING = "running",
  COMPLETED = "completed",
  FAILED = "failed",
  CANCELLED = "cancelled",
}

export enum TaskTrigger {
  WORKFLOW_STARTED = "workflow_started",
  DEPENDENCY_SATISFIED = "dependency_satisfied",
  WORKER_STARTED = "worker_started",
  EXECUTION_SUCCEEDED = "execution_succeeded",
  EXECUTION_FAILED = "execution_failed",
  CHILDREN_COMPLETED = "children_completed",
}

export type BenchmarkName = RestBenchmarkName;
export type SampleLifecycleStatus = RestSampleLifecycleStatus;

// =============================================================================
// Event Names
// =============================================================================

export const DashboardEventNames = {
  WORKFLOW_STARTED: "dashboard/workflow.started",
  WORKFLOW_COMPLETED: "dashboard/workflow.completed",
  TASK_STATUS_CHANGED: "dashboard/task.status_changed",
  RESOURCE_PUBLISHED: "dashboard/resource.published",
  SANDBOX_CREATED: "dashboard/sandbox.created",
  SANDBOX_COMMAND: "dashboard/sandbox.command",
  SANDBOX_CLOSED: "dashboard/sandbox.closed",
  THREAD_MESSAGE_CREATED: "dashboard/thread.message_created",
  TASK_EVALUATION_UPDATED: "dashboard/task.evaluation_updated",
  GRAPH_MUTATION: "dashboard/sample.runtime_event",
  CONTEXT_EVENT: "dashboard/context.event",
} as const;

export type DashboardEventName =
  (typeof DashboardEventNames)[keyof typeof DashboardEventNames];

// =============================================================================
// Workflow Lifecycle Events
// =============================================================================

export type DashboardWorkflowStartedData = GeneratedDashboardWorkflowStartedData;
export type DashboardWorkflowCompletedData = GeneratedDashboardWorkflowCompletedData;
export type ExperimentDetail = RestExperimentDetail;
export type DashboardTaskStatusChangedData = GeneratedDashboardTaskStatusChangedData;
export type DashboardResourcePublishedData = GeneratedDashboardResourcePublishedData;
export type DashboardSandboxCreatedData = GeneratedDashboardSandboxCreatedData;
export type DashboardSandboxCommandData = GeneratedDashboardSandboxCommandData;
export type DashboardSandboxClosedData = GeneratedDashboardSandboxClosedData;
export type CommunicationMessageState = RestSampleCommunicationMessage;
export type CommunicationThreadState = RestSampleCommunicationThread;
export type EvaluationCriterionState = NonNullable<RestSampleTaskEvaluation["criterionResults"]>[number];
export type TaskEvaluationState = RestSampleTaskEvaluation;
export type DashboardThreadMessageCreatedData = GeneratedDashboardThreadMessageCreatedData;
export type DashboardTaskEvaluationUpdatedData = GeneratedDashboardTaskEvaluationUpdatedData;

import type { DashboardContextEventEventData as _GeneratedDashboardContextEventEventData } from "@/lib/contracts/events";
export type DashboardContextEventEventData = _GeneratedDashboardContextEventEventData;

export type DashboardSampleRuntimeEventData = GeneratedDashboardSampleRuntimeEventData;
export type SampleRuntimeEventSocketData = GeneratedSampleRuntimeEventSocketData;

// =============================================================================
// Union Types for Inngest Event Handling
// =============================================================================

export type DashboardEventData =
  | DashboardWorkflowStartedData
  | DashboardWorkflowCompletedData
  | DashboardTaskStatusChangedData
  | DashboardResourcePublishedData
  | DashboardSandboxCreatedData
  | DashboardSandboxCommandData
  | DashboardSandboxClosedData
  | DashboardThreadMessageCreatedData
  | DashboardTaskEvaluationUpdatedData
  | DashboardSampleRuntimeEventData
  | DashboardContextEventEventData;

// =============================================================================
// Inngest Event Types (for type-safe event handling)
// =============================================================================

export type DashboardEvents = {
  "dashboard/workflow.started": { data: DashboardWorkflowStartedData };
  "dashboard/workflow.completed": { data: DashboardWorkflowCompletedData };
  "dashboard/task.status_changed": { data: DashboardTaskStatusChangedData };
  "dashboard/resource.published": { data: DashboardResourcePublishedData };
  "dashboard/sandbox.created": { data: DashboardSandboxCreatedData };
  "dashboard/sandbox.command": { data: DashboardSandboxCommandData };
  "dashboard/sandbox.closed": { data: DashboardSandboxClosedData };
  "dashboard/thread.message_created": { data: DashboardThreadMessageCreatedData };
  "dashboard/task.evaluation_updated": { data: DashboardTaskEvaluationUpdatedData };
  "dashboard/sample.runtime_event": { data: DashboardSampleRuntimeEventData };
  "dashboard/context.event": { data: DashboardContextEventEventData };
};

// =============================================================================
// State Management Types (for DashboardStore)
// =============================================================================

/**
 * One transition in a task's lifecycle (pending→ready→running→completed, etc).
 *
 * Created by the graph mutation reducer on every `node.status_changed` event
 * and surfaced in the per-task transition log and the unified event stream.
 */
export interface TaskTransitionRecord {
  from: TaskStatus | null;
  to: TaskStatus;
  /** Best-effort trigger. When the backend does not include one we infer from (from → to). */
  trigger: TaskTrigger | "unknown";
  at: string;
  /** The graph-mutation sequence number that produced this transition, if known. */
  sequence: number | null;
  actor: string | null;
  reason: string | null;
}

/**
 * Task state in the store (flattened from the run snapshot task map).
 * Represents the current state of a task during execution.
 */
export interface TaskState {
  id: string;
  name: string;
  description: string;
  status: TaskStatus;
  parentId: string | null;
  childIds: string[];
  dependsOnIds: string[];
  assignedWorkerId: string | null;
  assignedWorkerSlug: string | null;
  /** From run snapshot `startedAt`: null only before the task has actually started. */
  startedAt: string | null;
  /** From run snapshot `completedAt`: null until the task finishes (or never started). */
  completedAt: string | null;
  isLeaf: boolean;
  level: number; // Depth in tree (root = 0)
  /** Chronological history of status transitions for this task. */
  history?: TaskTransitionRecord[];
  /** Most recent transition trigger (shortcut for UI without walking history). */
  lastTrigger?: TaskTrigger | "unknown" | null;
}

export interface ExecutionAttemptState {
  id: string;
  taskId: string;
  attemptNumber: number;
  status: TaskStatus;
  agentId: string | null;
  agentName: string | null;
  startedAt: string | null;
  completedAt: string | null;
  finalAssistantMessage: string | null;
  outputResourceIds: string[];
  errorMessage: string | null;
  score: number | null;
  evaluationDetails: Record<string, unknown>;
}

/**
 * Resource state in the store.
 * Represents an output file produced by a task.
 */
export interface ResourceState {
  id: string;
  taskId: string;
  taskAttemptId: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
  filePath: string;
  createdAt: string;
}

/**
 * Sandbox state in the store.
 * Represents an E2B sandbox for a task.
 */
export interface SandboxState {
  sandboxId: string;
  taskId: string;
  template: string | null;
  timeoutMinutes: number;
  status: "active" | "closed";
  createdAt: string;
  closedAt: string | null;
  closeReason: string | null;
  commands: SandboxCommandState[];
}

/**
 * Command executed in a sandbox.
 */
export interface SandboxCommandState {
  command: string;
  stdout: string | null;
  stderr: string | null;
  exitCode: number | null;
  durationMs: number | null;
  timestamp: string;
}

/**
 * A DAG edge tracked independently of node parent/child structure, so we can
 * respond to edge.removed / edge.status_changed mutations instead of silently
 * dropping them.
 */
export interface EdgeState {
  id: string;
  sourceId: string;
  targetId: string;
  status: string;
  createdAt: string;
}

/**
 * An annotation applied to a node or edge. Kept as a lossless append-only
 * list per target so `annotation.set` / `annotation.deleted` never vanish.
 */
export interface AnnotationState {
  namespace: string;
  payload: Record<string, unknown>;
  setAt: string;
  /** True when an annotation.deleted mutation retired this record. */
  deleted?: boolean;
  deletedAt?: string | null;
}

/**
 * Record of a graph mutation the reducer could not fully apply. Surfaced in
 * the timeline as a ⚠ marker so users notice dropped updates instead of them
 * silently disappearing.
 */
export interface UnhandledMutationRecord {
  mutationId: string;
  sequence: number;
  mutationType: string;
  targetId: string;
  actor: string;
  createdAt: string;
  note: string;
}

/**
 * Complete workflow run state.
 * This is the top-level state object held in the DashboardStore.
 */
export interface SampleWorkspaceState {
  id: string;
  experimentId: string | null;
  name: string;
  status: SampleLifecycleStatus;

  // Task DAG (flattened)
  tasks: Map<string, TaskState>;
  rootTaskId: string;

  // Resources by task
  resourcesByTask: Map<string, ResourceState[]>;

  // Execution attempts by task
  executionsByTask: Map<string, ExecutionAttemptState[]>;

  // Sandboxes by task
  sandboxesByTask: Map<string, SandboxState>;

  // Communication threads scoped to the run, optionally linked to a task
  threads: CommunicationThreadState[];

  // Task evaluation snapshots keyed by task ID or "__run__" for run-scoped judgments
  evaluationsByTask: Map<string, TaskEvaluationState>;

  // Context events (lossless per-event records) keyed by task node ID
  contextEventsByTask: Map<string, ContextEventState[]>;

  // Timing
  startedAt: string;
  completedAt: string | null;
  durationSeconds: number | null;

  // Metrics
  totalTasks: number;
  totalLeafTasks: number;
  completedTasks: number;
  runningTasks: number;
  failedTasks: number;
  cancelledTasks: number;
  metrics?: SampleSnapshotMetrics | null;

  // Result
  finalScore: number | null;
  error: string | null;

  /** Edges tracked independently so edge-level mutations are visible. */
  edges?: Map<string, EdgeState>;

  /** Annotations by target (node or edge) id. */
  annotationsByTarget?: Map<string, AnnotationState[]>;

  /** Graph mutations the reducer could not apply (never silently dropped). */
  unhandledMutations?: UnhandledMutationRecord[];
}

// =============================================================================
// Socket.io Event Types
// =============================================================================

/**
 * Events sent from server to client via Socket.io.
 */
export interface ServerToClientEvents {
  "sample:started": (data: { sampleId: string; name: string }) => void;
  "sample:completed": (data: SampleCompletedSocketData) => void;
  "task:status": (data: TaskStatusSocketData) => void;
  "resource:new": (data: ResourceSocketData) => void;
  "sandbox:created": (data: SandboxCreatedSocketData) => void;
  "sandbox:command": (data: SandboxCommandSocketData) => void;
  "sandbox:closed": (data: SandboxClosedSocketData) => void;
  "thread:message": (data: DashboardThreadMessageCreatedData) => void;
  "task:evaluation": (data: DashboardTaskEvaluationUpdatedData) => void;
  "sample:runtime-event": (data: SampleRuntimeEventSocketData) => void;
  "context:event": (data: { sampleId: string; taskId: string; event: ContextEventState }) => void;
  // Sync event - sends all current runs to a client on request
  "sync:samples": (runs: SampleListEntry[]) => void;
  // Sync event - sends full state for a specific sample
  "sync:sample": (run: SerializedSampleWorkspaceState | null) => void;
}

/**
 * Validated run snapshot payload used over REST and Socket.io sync.
 */
export type SerializedSampleWorkspaceState = SampleSnapshot;

/**
 * Events sent from client to server via Socket.io.
 */
export interface ClientToServerEvents {
  subscribe: (sampleId: string) => void;
  unsubscribe: (sampleId: string) => void;
  "request:samples": () => void;
  "request:sample": (sampleId: string) => void;
}
