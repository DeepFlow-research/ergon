/**
 * Dashboard Event Types
 *
 * TypeScript interfaces mirroring the Python event contracts in h_arcane/dashboard/events.py.
 * These types provide type safety when handling Inngest events in the dashboard.
 *
 * UUIDs are serialized as strings over the wire.
 * Timestamps are ISO 8601 strings.
 */

// =============================================================================
// Enums (mirror h_arcane/core/status.py)
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

// =============================================================================
// Task Tree Types (mirror h_arcane/core/_internal/task/schema.py)
// =============================================================================

export interface WorkerRef {
  id: string;
  name: string;
}

export interface ResourceRef {
  id: string;
  name: string;
  url?: string | null;
  mime_type?: string | null;
}

export interface EvaluatorRef {
  type: string;
  [key: string]: unknown; // Extra fields allowed
}

export interface TaskTreeNode {
  // Identity
  id: string;
  name: string;
  description: string;

  // Worker Assignment
  assigned_to: WorkerRef;
  full_team?: WorkerRef[] | null;

  // DAG Structure
  children: TaskTreeNode[];
  depends_on: string[];
  parent_id?: string | null;

  // Computed Properties
  is_leaf: boolean;

  // I/O
  resources: ResourceRef[];

  // Evaluation
  evaluator?: EvaluatorRef | null;
  evaluator_type?: string | null;
}

// =============================================================================
// Event Names
// =============================================================================

export const DashboardEventNames = {
  WORKFLOW_STARTED: "dashboard/workflow.started",
  WORKFLOW_COMPLETED: "dashboard/workflow.completed",
  TASK_STATUS_CHANGED: "dashboard/task.status_changed",
  AGENT_ACTION_STARTED: "dashboard/agent.action_started",
  AGENT_ACTION_COMPLETED: "dashboard/agent.action_completed",
  RESOURCE_PUBLISHED: "dashboard/resource.published",
  SANDBOX_CREATED: "dashboard/sandbox.created",
  SANDBOX_COMMAND: "dashboard/sandbox.command",
  SANDBOX_CLOSED: "dashboard/sandbox.closed",
} as const;

export type DashboardEventName =
  (typeof DashboardEventNames)[keyof typeof DashboardEventNames];

// =============================================================================
// Workflow Lifecycle Events
// =============================================================================

export interface DashboardWorkflowStartedData {
  run_id: string;
  experiment_id: string;
  workflow_name: string;
  task_tree: TaskTreeNode;
  started_at: string; // ISO 8601
  total_tasks: number;
  total_leaf_tasks: number;
}

export interface DashboardWorkflowCompletedData {
  run_id: string;
  status: "completed" | "failed";
  completed_at: string; // ISO 8601
  duration_seconds: number;
  final_score?: number | null;
  error?: string | null;
}

// =============================================================================
// Task Lifecycle Events
// =============================================================================

export interface DashboardTaskStatusChangedData {
  run_id: string;
  task_id: string;
  task_name: string;
  parent_task_id?: string | null;
  old_status?: TaskStatus | null;
  new_status: TaskStatus;
  triggered_by?: TaskTrigger | null;
  timestamp: string; // ISO 8601
  assigned_worker_id?: string | null;
  assigned_worker_name?: string | null;
}

// =============================================================================
// Agent Action Events
// =============================================================================

export interface DashboardAgentActionStartedData {
  run_id: string;
  task_id: string;
  action_id: string;
  worker_id: string;
  worker_name: string;
  action_type: string;
  action_input: string; // JSON string
  timestamp: string; // ISO 8601
}

export interface DashboardAgentActionCompletedData {
  run_id: string;
  task_id: string;
  action_id: string;
  worker_id: string;
  action_type: string;
  action_output?: string | null; // JSON string
  duration_ms: number;
  success: boolean;
  error?: string | null;
  timestamp: string; // ISO 8601
}

// =============================================================================
// Resource Events
// =============================================================================

export interface DashboardResourcePublishedData {
  run_id: string;
  task_id: string;
  task_execution_id: string;
  resource_id: string;
  resource_name: string;
  mime_type: string;
  size_bytes: number;
  file_path: string;
  timestamp: string; // ISO 8601
}

// =============================================================================
// Sandbox Lifecycle Events
// =============================================================================

export interface DashboardSandboxCreatedData {
  run_id: string;
  task_id: string;
  sandbox_id: string;
  template?: string | null;
  timeout_minutes: number;
  timestamp: string; // ISO 8601
}

export interface DashboardSandboxCommandData {
  task_id: string;
  sandbox_id: string;
  command: string;
  stdout?: string | null;
  stderr?: string | null;
  exit_code?: number | null;
  duration_ms?: number | null;
  timestamp: string; // ISO 8601
}

export interface DashboardSandboxClosedData {
  task_id: string;
  sandbox_id: string;
  reason: "completed" | "timeout" | "error" | "cleanup";
  timestamp: string; // ISO 8601
}

// =============================================================================
// Union Types for Inngest Event Handling
// =============================================================================

export type DashboardEventData =
  | DashboardWorkflowStartedData
  | DashboardWorkflowCompletedData
  | DashboardTaskStatusChangedData
  | DashboardAgentActionStartedData
  | DashboardAgentActionCompletedData
  | DashboardResourcePublishedData
  | DashboardSandboxCreatedData
  | DashboardSandboxCommandData
  | DashboardSandboxClosedData;

// =============================================================================
// Inngest Event Types (for type-safe event handling)
// =============================================================================

export type DashboardEvents = {
  "dashboard/workflow.started": { data: DashboardWorkflowStartedData };
  "dashboard/workflow.completed": { data: DashboardWorkflowCompletedData };
  "dashboard/task.status_changed": { data: DashboardTaskStatusChangedData };
  "dashboard/agent.action_started": { data: DashboardAgentActionStartedData };
  "dashboard/agent.action_completed": {
    data: DashboardAgentActionCompletedData;
  };
  "dashboard/resource.published": { data: DashboardResourcePublishedData };
  "dashboard/sandbox.created": { data: DashboardSandboxCreatedData };
  "dashboard/sandbox.command": { data: DashboardSandboxCommandData };
  "dashboard/sandbox.closed": { data: DashboardSandboxClosedData };
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
  status: "running" | "completed" | "failed";

  // Task DAG (flattened)
  tasks: Map<string, TaskState>;
  rootTaskId: string;

  // Actions by task (append-only)
  actionsByTask: Map<string, ActionState[]>;

  // Resources by task
  resourcesByTask: Map<string, ResourceState[]>;

  // Sandboxes by task
  sandboxesByTask: Map<string, SandboxState>;

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
  "run:started": (data: { runId: string; name: string }) => void;
  "run:completed": (data: {
    runId: string;
    status: "completed" | "failed";
    durationSeconds: number;
    finalScore: number | null;
    error: string | null;
  }) => void;
  "task:status": (data: {
    runId: string;
    taskId: string;
    status: TaskStatus;
    assignedWorkerId: string | null;
    assignedWorkerName: string | null;
  }) => void;
  "action:new": (data: { runId: string; action: ActionState }) => void;
  "action:completed": (data: { runId: string; action: ActionState }) => void;
  "resource:new": (data: { runId: string; resource: ResourceState }) => void;
  "sandbox:created": (data: { runId: string; sandbox: SandboxState }) => void;
  "sandbox:command": (data: {
    runId: string;
    taskId: string;
    command: SandboxCommandState;
  }) => void;
  "sandbox:closed": (data: {
    runId: string;
    taskId: string;
    reason: string;
  }) => void;
  // Sync event - sends all current runs to a client on request
  "sync:runs": (runs: Array<{
    runId: string;
    name: string;
    status: "running" | "completed" | "failed";
    startedAt: string;
    completedAt: string | null;
    durationSeconds: number | null;
    finalScore: number | null;
    error: string | null;
  }>) => void;
  // Sync event - sends full state for a specific run
  "sync:run": (run: SerializedWorkflowRunState | null) => void;
}

/**
 * Serialized WorkflowRunState for network transfer (Maps become arrays)
 */
export interface SerializedWorkflowRunState {
  id: string;
  experimentId: string;
  name: string;
  status: "running" | "completed" | "failed";
  tasks: Array<[string, TaskState]>;
  rootTaskId: string;
  actionsByTask: Array<[string, ActionState[]]>;
  resourcesByTask: Array<[string, ResourceState[]]>;
  sandboxesByTask: Array<[string, SandboxState]>;
  startedAt: string;
  completedAt: string | null;
  durationSeconds: number | null;
  totalTasks: number;
  totalLeafTasks: number;
  completedTasks: number;
  runningTasks: number;
  failedTasks: number;
  finalScore: number | null;
  error: string | null;
}

/**
 * Events sent from client to server via Socket.io.
 */
export interface ClientToServerEvents {
  subscribe: (runId: string) => void;
  unsubscribe: (runId: string) => void;
  "request:runs": () => void;
  "request:run": (runId: string) => void;
}
