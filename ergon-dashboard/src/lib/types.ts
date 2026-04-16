import type { ContextEventState } from "./contracts/contextEvents";
export type { ContextEventState };

import type {
  BenchmarkName as RestBenchmarkName,
  CohortDetail as RestCohortDetail,
  CohortSummary as RestCohortSummary,
  ExperimentCohortStatusValue,
  RunCommunicationMessage as RestRunCommunicationMessage,
  RunCommunicationThread as RestRunCommunicationThread,
  RunLifecycleStatus as RestRunLifecycleStatus,
  RunSnapshot,
  RunTaskEvaluation as RestRunTaskEvaluation,
} from "@/lib/contracts/rest";
import type {
  DashboardCohortUpdatedData as GeneratedDashboardCohortUpdatedData,
  DashboardGraphMutationData as GeneratedDashboardGraphMutationData,
  DashboardResourcePublishedData as GeneratedDashboardResourcePublishedData,
  GraphMutationSocketData as GeneratedGraphMutationSocketData,
  ResourceSocketData,
  RunCompletedSocketData,
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
  RunListEntry,
  TaskStatusSocketData,
  TaskTreeNode,
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
export type RunLifecycleStatus = RestRunLifecycleStatus;
export type ExperimentCohortStatus = ExperimentCohortStatusValue;
export type { TaskTreeNode };

// =============================================================================
// Event Names
// =============================================================================

export const DashboardEventNames = {
  WORKFLOW_STARTED: "dashboard/workflow.started",
  WORKFLOW_COMPLETED: "dashboard/workflow.completed",
  COHORT_UPDATED: "dashboard/cohort.updated",
  TASK_STATUS_CHANGED: "dashboard/task.status_changed",
  RESOURCE_PUBLISHED: "dashboard/resource.published",
  SANDBOX_CREATED: "dashboard/sandbox.created",
  SANDBOX_COMMAND: "dashboard/sandbox.command",
  SANDBOX_CLOSED: "dashboard/sandbox.closed",
  THREAD_MESSAGE_CREATED: "dashboard/thread.message_created",
  TASK_EVALUATION_UPDATED: "dashboard/task.evaluation_updated",
  GENERATION_TURN_COMPLETED: "dashboard/generation.turn_completed",
  GRAPH_MUTATION: "dashboard/graph.mutation",
  CONTEXT_EVENT: "dashboard/context.event",
} as const;

export type DashboardEventName =
  (typeof DashboardEventNames)[keyof typeof DashboardEventNames];

// =============================================================================
// Workflow Lifecycle Events
// =============================================================================

export type DashboardWorkflowStartedData = GeneratedDashboardWorkflowStartedData;
export type DashboardWorkflowCompletedData = GeneratedDashboardWorkflowCompletedData;
export type CohortSummary = RestCohortSummary;
export type CohortRunRow = NonNullable<RestCohortDetail["runs"]>[number];
export type CohortDetail = RestCohortDetail;
export type DashboardCohortUpdatedData = GeneratedDashboardCohortUpdatedData;
export type DashboardTaskStatusChangedData = GeneratedDashboardTaskStatusChangedData;
export type DashboardResourcePublishedData = GeneratedDashboardResourcePublishedData;
export type DashboardSandboxCreatedData = GeneratedDashboardSandboxCreatedData;
export type DashboardSandboxCommandData = GeneratedDashboardSandboxCommandData;
export type DashboardSandboxClosedData = GeneratedDashboardSandboxClosedData;
export type CommunicationMessageState = RestRunCommunicationMessage;
export type CommunicationThreadState = RestRunCommunicationThread;
export type EvaluationCriterionState = NonNullable<RestRunTaskEvaluation["criterionResults"]>[number];
export type TaskEvaluationState = RestRunTaskEvaluation;
export type DashboardThreadMessageCreatedData = GeneratedDashboardThreadMessageCreatedData;
export type DashboardTaskEvaluationUpdatedData = GeneratedDashboardTaskEvaluationUpdatedData;

import type { DashboardGenerationTurnCompletedData as _GeneratedDashboardGenerationTurnCompletedData, DashboardContextEventEventData as _GeneratedDashboardContextEventEventData } from "@/lib/contracts/events";
export type DashboardGenerationTurnCompletedData = _GeneratedDashboardGenerationTurnCompletedData;
export type DashboardContextEventEventData = _GeneratedDashboardContextEventEventData;

export type DashboardGraphMutationData = GeneratedDashboardGraphMutationData;
export type GraphMutationSocketData = GeneratedGraphMutationSocketData;

// =============================================================================
// Union Types for Inngest Event Handling
// =============================================================================

export type DashboardEventData =
  | DashboardWorkflowStartedData
  | DashboardWorkflowCompletedData
  | DashboardCohortUpdatedData
  | DashboardTaskStatusChangedData
  | DashboardResourcePublishedData
  | DashboardSandboxCreatedData
  | DashboardSandboxCommandData
  | DashboardSandboxClosedData
  | DashboardThreadMessageCreatedData
  | DashboardTaskEvaluationUpdatedData
  | DashboardGenerationTurnCompletedData
  | DashboardGraphMutationData
  | DashboardContextEventEventData;

// =============================================================================
// Inngest Event Types (for type-safe event handling)
// =============================================================================

export type DashboardEvents = {
  "dashboard/workflow.started": { data: DashboardWorkflowStartedData };
  "dashboard/workflow.completed": { data: DashboardWorkflowCompletedData };
  "dashboard/cohort.updated": { data: DashboardCohortUpdatedData };
  "dashboard/task.status_changed": { data: DashboardTaskStatusChangedData };
  "dashboard/resource.published": { data: DashboardResourcePublishedData };
  "dashboard/sandbox.created": { data: DashboardSandboxCreatedData };
  "dashboard/sandbox.command": { data: DashboardSandboxCommandData };
  "dashboard/sandbox.closed": { data: DashboardSandboxClosedData };
  "dashboard/thread.message_created": { data: DashboardThreadMessageCreatedData };
  "dashboard/task.evaluation_updated": { data: DashboardTaskEvaluationUpdatedData };
  "dashboard/generation.turn_completed": { data: DashboardGenerationTurnCompletedData };
  "dashboard/graph.mutation": { data: DashboardGraphMutationData };
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
 * Task state in the store (flattened from TaskTreeNode).
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
  assignedWorkerName: string | null;
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
  outputText: string | null;
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
  taskExecutionId: string;
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

export interface GenerationTurnState {
  taskExecutionId: string;
  workerBindingKey: string;
  workerName: string;
  turnIndex: number;
  responseText: string | null;
  toolCalls: Array<{ tool_call_id: string; tool_name: string; args: unknown }> | null;
  policyVersion: string | null;
  /** ISO timestamp of when this turn completed, if available. Used for timeline correlation. */
  at?: string | null;
  /** Task node this turn belongs to (for cross-linking from timeline/stream). */
  taskId?: string | null;
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
export interface WorkflowRunState {
  id: string;
  experimentId: string;
  name: string;
  status: RunLifecycleStatus;

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

  // Generation turns (RL observability) — append-only, keyed by task execution
  generationTurns: GenerationTurnState[];

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
  "cohort:updated": (data: DashboardCohortUpdatedData) => void;
  "run:started": (data: { runId: string; name: string }) => void;
  "run:completed": (data: RunCompletedSocketData) => void;
  "task:status": (data: TaskStatusSocketData) => void;
  "resource:new": (data: ResourceSocketData) => void;
  "sandbox:created": (data: SandboxCreatedSocketData) => void;
  "sandbox:command": (data: SandboxCommandSocketData) => void;
  "sandbox:closed": (data: SandboxClosedSocketData) => void;
  "thread:message": (data: DashboardThreadMessageCreatedData) => void;
  "task:evaluation": (data: DashboardTaskEvaluationUpdatedData) => void;
  "generation:turn": (data: { runId: string; turn: GenerationTurnState }) => void;
  "graph:mutation": (data: GraphMutationSocketData) => void;
  "context:event": (data: { runId: string; taskNodeId: string; event: ContextEventState }) => void;
  // Sync event - sends all current runs to a client on request
  "sync:runs": (runs: RunListEntry[]) => void;
  // Sync event - sends full state for a specific run
  "sync:run": (run: SerializedWorkflowRunState | null) => void;
}

/**
 * Validated run snapshot payload used over REST and Socket.io sync.
 */
export type SerializedWorkflowRunState = RunSnapshot;

/**
 * Events sent from client to server via Socket.io.
 */
export interface ClientToServerEvents {
  subscribe: (runId: string) => void;
  unsubscribe: (runId: string) => void;
  "request:runs": () => void;
  "request:run": (runId: string) => void;
}
