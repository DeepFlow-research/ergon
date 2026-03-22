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
  ActionSocketData,
  DashboardAgentActionCompletedData as GeneratedDashboardAgentActionCompletedData,
  DashboardAgentActionStartedData as GeneratedDashboardAgentActionStartedData,
  DashboardCohortUpdatedData as GeneratedDashboardCohortUpdatedData,
  DashboardResourcePublishedData as GeneratedDashboardResourcePublishedData,
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
  AGENT_ACTION_STARTED: "dashboard/agent.action_started",
  AGENT_ACTION_COMPLETED: "dashboard/agent.action_completed",
  RESOURCE_PUBLISHED: "dashboard/resource.published",
  SANDBOX_CREATED: "dashboard/sandbox.created",
  SANDBOX_COMMAND: "dashboard/sandbox.command",
  SANDBOX_CLOSED: "dashboard/sandbox.closed",
  THREAD_MESSAGE_CREATED: "dashboard/thread.message_created",
  TASK_EVALUATION_UPDATED: "dashboard/task.evaluation_updated",
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
export type DashboardAgentActionStartedData = GeneratedDashboardAgentActionStartedData;
export type DashboardAgentActionCompletedData = GeneratedDashboardAgentActionCompletedData;
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

// =============================================================================
// Union Types for Inngest Event Handling
// =============================================================================

export type DashboardEventData =
  | DashboardWorkflowStartedData
  | DashboardWorkflowCompletedData
  | DashboardCohortUpdatedData
  | DashboardTaskStatusChangedData
  | DashboardAgentActionStartedData
  | DashboardAgentActionCompletedData
  | DashboardResourcePublishedData
  | DashboardSandboxCreatedData
  | DashboardSandboxCommandData
  | DashboardSandboxClosedData
  | DashboardThreadMessageCreatedData
  | DashboardTaskEvaluationUpdatedData;

// =============================================================================
// Inngest Event Types (for type-safe event handling)
// =============================================================================

export type DashboardEvents = {
  "dashboard/workflow.started": { data: DashboardWorkflowStartedData };
  "dashboard/workflow.completed": { data: DashboardWorkflowCompletedData };
  "dashboard/cohort.updated": { data: DashboardCohortUpdatedData };
  "dashboard/task.status_changed": { data: DashboardTaskStatusChangedData };
  "dashboard/agent.action_started": { data: DashboardAgentActionStartedData };
  "dashboard/agent.action_completed": {
    data: DashboardAgentActionCompletedData;
  };
  "dashboard/resource.published": { data: DashboardResourcePublishedData };
  "dashboard/sandbox.created": { data: DashboardSandboxCreatedData };
  "dashboard/sandbox.command": { data: DashboardSandboxCommandData };
  "dashboard/sandbox.closed": { data: DashboardSandboxClosedData };
  "dashboard/thread.message_created": { data: DashboardThreadMessageCreatedData };
  "dashboard/task.evaluation_updated": { data: DashboardTaskEvaluationUpdatedData };
};

// =============================================================================
// State Management Types (for DashboardStore)
// =============================================================================

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
  startedAt: string | null;
  completedAt: string | null;
  isLeaf: boolean;
  level: number; // Depth in tree (root = 0)
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
 * Action state in the store.
 * Represents an agent tool call during task execution.
 */
export interface ActionState {
  id: string;
  taskId: string;
  workerId: string;
  workerName: string;
  type: string; // Tool name
  input: string; // JSON string
  output: string | null; // JSON string
  status: "started" | "completed" | "failed";
  startedAt: string;
  completedAt: string | null;
  durationMs: number | null;
  success: boolean;
  error: string | null;
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

  // Actions by task (append-only)
  actionsByTask: Map<string, ActionState[]>;

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
  "action:new": (data: ActionSocketData) => void;
  "action:completed": (data: ActionSocketData) => void;
  "resource:new": (data: ResourceSocketData) => void;
  "sandbox:created": (data: SandboxCreatedSocketData) => void;
  "sandbox:command": (data: SandboxCommandSocketData) => void;
  "sandbox:closed": (data: SandboxClosedSocketData) => void;
  "thread:message": (data: DashboardThreadMessageCreatedData) => void;
  "task:evaluation": (data: DashboardTaskEvaluationUpdatedData) => void;
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
