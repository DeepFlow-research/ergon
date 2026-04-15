import { z } from "zod";

import {
  MutationTypeSchema,
  GraphTargetTypeSchema,
} from "@/features/graph/contracts/graphMutations";
import {
  CohortSummary,
  CohortSummarySchema,
  parseCohortSummary,
  parseRunCommunicationMessage,
  parseRunCommunicationThread,
  parseRunSandbox,
  parseRunSandboxCommand,
  parseRunTaskEvaluation,
  RunCommunicationMessageSchema,
  RunCommunicationThreadSchema,
  RunResourceSchema,
  RunResource,
  RunSandboxCommandSchema,
  RunSandboxSchema,
  RunSandbox,
  RunSandboxCommand,
  RunTaskEvaluation,
  RunTaskEvaluationSchema,
  TaskStatusSchema,
} from "@/lib/contracts/rest";

export const TaskTriggerSchema = z.enum([
  "workflow_started",
  "dependency_satisfied",
  "worker_started",
  "execution_succeeded",
  "execution_failed",
  "children_completed",
]);

export const WorkerRefSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  type: z.string(),
});

export const ResourceRefSchema = z.object({
  path: z.string().nullable().optional(),
  name: z.string(),
  content: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  mime_type: z.string().nullable().optional(),
});

export const EvaluatorRefSchema = z.object({ type: z.string() }).passthrough();

export type WorkerRef = z.infer<typeof WorkerRefSchema>;
export type ResourceRef = z.infer<typeof ResourceRefSchema>;
export type EvaluatorRef = z.infer<typeof EvaluatorRefSchema>;
export type TaskTreeNode = {
  id: string;
  name: string;
  description: string;
  assigned_to: WorkerRef;
  full_team?: WorkerRef[] | null;
  children: TaskTreeNode[];
  depends_on: string[];
  parent_id?: string | null;
  is_leaf: boolean;
  resources: ResourceRef[];
  evaluator?: EvaluatorRef | null;
  evaluator_type?: string | null;
};

export const TaskTreeNodeSchema: z.ZodType<{
  id: string;
  name: string;
  description: string;
  assigned_to: WorkerRef;
  full_team?: WorkerRef[] | null;
  children: TaskTreeNode[];
  depends_on: string[];
  parent_id?: string | null;
  is_leaf: boolean;
  resources: ResourceRef[];
  evaluator?: EvaluatorRef | null;
  evaluator_type?: string | null;
}> = z.lazy(() =>
  z.object({
    id: z.string().uuid(),
    name: z.string(),
    description: z.string(),
    assigned_to: WorkerRefSchema,
    full_team: z.array(WorkerRefSchema).nullable().optional(),
    children: z.array(TaskTreeNodeSchema),
    depends_on: z.array(z.string().uuid()),
    parent_id: z.string().uuid().nullable().optional(),
    is_leaf: z.boolean(),
    resources: z.array(ResourceRefSchema),
    evaluator: EvaluatorRefSchema.nullable().optional(),
    evaluator_type: z.string().nullable().optional(),
  }),
);

export const DashboardWorkflowStartedDataSchema = z.object({
  run_id: z.string().uuid(),
  experiment_id: z.string().uuid(),
  workflow_name: z.string(),
  task_tree: TaskTreeNodeSchema,
  started_at: z.string().datetime({ offset: true }),
  total_tasks: z.number().int(),
  total_leaf_tasks: z.number().int(),
});

export const DashboardWorkflowCompletedDataSchema = z.object({
  run_id: z.string().uuid(),
  status: z.enum(["completed", "failed"]),
  completed_at: z.string().datetime({ offset: true }),
  duration_seconds: z.number(),
  final_score: z.number().nullable().optional(),
  error: z.string().nullable().optional(),
});

export const DashboardCohortUpdatedDataSchema = z.object({
  cohort_id: z.string().uuid(),
  summary: CohortSummarySchema,
});

export const DashboardTaskStatusChangedDataSchema = z.object({
  run_id: z.string().uuid(),
  task_id: z.string().uuid(),
  task_name: z.string(),
  parent_task_id: z.string().uuid().nullable().optional(),
  old_status: TaskStatusSchema.nullable().optional(),
  new_status: TaskStatusSchema,
  triggered_by: TaskTriggerSchema.nullable().optional(),
  timestamp: z.string().datetime({ offset: true }),
  assigned_worker_id: z.string().uuid().nullable().optional(),
  assigned_worker_name: z.string().nullable().optional(),
});

export const DashboardResourcePublishedDataSchema = z.object({
  run_id: z.string().uuid(),
  task_id: z.string().uuid(),
  task_execution_id: z.string().uuid(),
  resource_id: z.string().uuid(),
  resource_name: z.string(),
  mime_type: z.string(),
  size_bytes: z.number().int(),
  file_path: z.string(),
  timestamp: z.string().datetime({ offset: true }),
});

export const DashboardSandboxCreatedDataSchema = z.object({
  run_id: z.string().uuid(),
  task_id: z.string().uuid(),
  sandbox_id: z.string(),
  template: z.string().nullable().optional(),
  timeout_minutes: z.number().int(),
  timestamp: z.string().datetime({ offset: true }),
});

export const DashboardSandboxCommandDataSchema = z.object({
  task_id: z.string().uuid(),
  sandbox_id: z.string(),
  command: z.string(),
  stdout: z.string().nullable().optional(),
  stderr: z.string().nullable().optional(),
  exit_code: z.number().int().nullable().optional(),
  duration_ms: z.number().int().nullable().optional(),
  timestamp: z.string().datetime({ offset: true }),
});

export const DashboardSandboxClosedDataSchema = z.object({
  task_id: z.string().uuid(),
  sandbox_id: z.string(),
  reason: z.string(),
  timestamp: z.string().datetime({ offset: true }),
});

export const DashboardThreadMessageCreatedDataSchema = z.object({
  run_id: z.string().uuid(),
  thread: RunCommunicationThreadSchema,
  message: RunCommunicationMessageSchema,
});

export const DashboardTaskEvaluationUpdatedDataSchema = z.object({
  run_id: z.string().uuid(),
  task_id: z.string().nullable().optional(),
  evaluation: RunTaskEvaluationSchema,
});

export const DashboardGenerationTurnCompletedDataSchema = z.object({
  run_id: z.string().uuid(),
  task_execution_id: z.string().uuid(),
  worker_binding_key: z.string(),
  worker_name: z.string(),
  turn_index: z.number().int(),
  response_text: z.string().nullable().optional(),
  tool_calls: z.array(z.record(z.string(), z.unknown())).nullable().optional(),
  policy_version: z.string().nullable().optional(),
});

export const RunListEntrySchema = z.object({
  runId: z.string(),
  name: z.string(),
  status: z.enum(["pending", "executing", "evaluating", "completed", "failed"]),
  startedAt: z.string(),
  completedAt: z.string().nullable(),
  durationSeconds: z.number().nullable(),
  finalScore: z.number().nullable(),
  error: z.string().nullable(),
});

export const SyncRunsSchema = z.array(RunListEntrySchema);
export const RunCompletedSocketDataSchema = z.object({
  runId: z.string(),
  status: z.enum(["completed", "failed"]),
  completedAt: z.string(),
  durationSeconds: z.number(),
  finalScore: z.number().nullable(),
  error: z.string().nullable(),
});
export const TaskStatusSocketDataSchema = z.object({
  runId: z.string(),
  taskId: z.string(),
  status: TaskStatusSchema,
  timestamp: z.string(),
  assignedWorkerId: z.string().nullable(),
  assignedWorkerName: z.string().nullable(),
});
export const ResourceSocketDataSchema = z.object({
  runId: z.string(),
  resource: RunResourceSchema,
});
export const SandboxCreatedSocketDataSchema = z.object({
  runId: z.string(),
  sandbox: RunSandboxSchema,
});
export const SandboxCommandSocketDataSchema = z.object({
  runId: z.string(),
  taskId: z.string(),
  command: RunSandboxCommandSchema,
});
export const SandboxClosedSocketDataSchema = z.object({
  runId: z.string(),
  taskId: z.string(),
  reason: z.string(),
});

export type TaskTrigger = z.infer<typeof TaskTriggerSchema>;
export type DashboardWorkflowStartedData = z.infer<typeof DashboardWorkflowStartedDataSchema>;
export type DashboardWorkflowCompletedData = z.infer<typeof DashboardWorkflowCompletedDataSchema>;
export interface DashboardCohortUpdatedData {
  cohort_id: string;
  summary: CohortSummary;
}
export type DashboardTaskStatusChangedData = z.infer<typeof DashboardTaskStatusChangedDataSchema>;
export type DashboardResourcePublishedData = z.infer<typeof DashboardResourcePublishedDataSchema>;
export type DashboardSandboxCreatedData = z.infer<typeof DashboardSandboxCreatedDataSchema>;
export type DashboardSandboxCommandData = z.infer<typeof DashboardSandboxCommandDataSchema>;
export type DashboardSandboxClosedData = z.infer<typeof DashboardSandboxClosedDataSchema>;
export interface DashboardThreadMessageCreatedData {
  run_id: string;
  thread: ReturnType<typeof parseRunCommunicationThread>;
  message: ReturnType<typeof parseRunCommunicationMessage>;
}
export interface DashboardTaskEvaluationUpdatedData {
  run_id: string;
  task_id: string | null;
  evaluation: RunTaskEvaluation;
}
export type DashboardGenerationTurnCompletedData = z.infer<
  typeof DashboardGenerationTurnCompletedDataSchema
>;
export type RunListEntry = z.infer<typeof RunListEntrySchema>;
export type RunCompletedSocketData = z.infer<typeof RunCompletedSocketDataSchema>;
export type TaskStatusSocketData = z.infer<typeof TaskStatusSocketDataSchema>;
export interface ResourceSocketData {
  runId: string;
  resource: RunResource;
}
export interface SandboxCreatedSocketData {
  runId: string;
  sandbox: RunSandbox;
}
export interface SandboxCommandSocketData {
  runId: string;
  taskId: string;
  command: RunSandboxCommand;
}
export type SandboxClosedSocketData = z.infer<typeof SandboxClosedSocketDataSchema>;

export function parseDashboardCohortUpdatedData(input: unknown): DashboardCohortUpdatedData {
  const parsed = DashboardCohortUpdatedDataSchema.parse(input);
  return {
    cohort_id: parsed.cohort_id,
    summary: parseCohortSummary(parsed.summary),
  };
}

export function parseDashboardThreadMessageCreatedData(
  input: unknown,
): DashboardThreadMessageCreatedData {
  const parsed = DashboardThreadMessageCreatedDataSchema.parse(input);
  return {
    run_id: parsed.run_id,
    thread: parseRunCommunicationThread(parsed.thread),
    message: parseRunCommunicationMessage(parsed.message),
  };
}

export function parseDashboardTaskEvaluationUpdatedData(
  input: unknown,
): DashboardTaskEvaluationUpdatedData {
  const parsed = DashboardTaskEvaluationUpdatedDataSchema.parse(input);
  return {
    run_id: parsed.run_id,
    task_id: parsed.task_id ?? null,
    evaluation: parseRunTaskEvaluation(parsed.evaluation),
  };
}

export function parseDashboardWorkflowStartedData(input: unknown): DashboardWorkflowStartedData {
  return DashboardWorkflowStartedDataSchema.parse(input);
}

export function parseDashboardWorkflowCompletedData(
  input: unknown,
): DashboardWorkflowCompletedData {
  return DashboardWorkflowCompletedDataSchema.parse(input);
}

export function parseDashboardTaskStatusChangedData(
  input: unknown,
): DashboardTaskStatusChangedData {
  return DashboardTaskStatusChangedDataSchema.parse(input);
}

export function parseDashboardResourcePublishedData(
  input: unknown,
): DashboardResourcePublishedData {
  return DashboardResourcePublishedDataSchema.parse(input);
}

export function parseDashboardSandboxCreatedData(input: unknown): DashboardSandboxCreatedData {
  return DashboardSandboxCreatedDataSchema.parse(input);
}

export function parseDashboardSandboxCommandData(input: unknown): DashboardSandboxCommandData {
  return DashboardSandboxCommandDataSchema.parse(input);
}

export function parseDashboardSandboxClosedData(input: unknown): DashboardSandboxClosedData {
  return DashboardSandboxClosedDataSchema.parse(input);
}

export function parseSyncRuns(input: unknown): RunListEntry[] {
  return SyncRunsSchema.parse(input);
}

export function parseRunCompletedSocketData(input: unknown): RunCompletedSocketData {
  return RunCompletedSocketDataSchema.parse(input);
}

export function parseTaskStatusSocketData(input: unknown): TaskStatusSocketData {
  return TaskStatusSocketDataSchema.parse(input);
}

export function parseResourceSocketData(input: unknown): ResourceSocketData {
  const parsed = ResourceSocketDataSchema.parse(input);
  return {
    runId: parsed.runId,
    resource: parsed.resource,
  };
}

export function parseSandboxCreatedSocketData(input: unknown): SandboxCreatedSocketData {
  const parsed = SandboxCreatedSocketDataSchema.parse(input);
  return {
    runId: parsed.runId,
    sandbox: parseRunSandbox(parsed.sandbox),
  };
}

export function parseSandboxCommandSocketData(input: unknown): SandboxCommandSocketData {
  const parsed = SandboxCommandSocketDataSchema.parse(input);
  return {
    runId: parsed.runId,
    taskId: parsed.taskId,
    command: parseRunSandboxCommand(parsed.command),
  };
}

export function parseSandboxClosedSocketData(input: unknown): SandboxClosedSocketData {
  return SandboxClosedSocketDataSchema.parse(input);
}

export function parseDashboardGenerationTurnCompletedData(
  input: unknown,
): DashboardGenerationTurnCompletedData {
  return DashboardGenerationTurnCompletedDataSchema.parse(input);
}

// =============================================================================
// Graph Mutation Events
// =============================================================================

export const DashboardGraphMutationDataSchema = z.object({
  run_id: z.string().uuid(),
  sequence: z.number().int().nonnegative(),
  mutation_type: MutationTypeSchema,
  target_type: GraphTargetTypeSchema,
  target_id: z.string().uuid(),
  actor: z.string().min(1),
  new_value: z.record(z.string(), z.unknown()),
  old_value: z.record(z.string(), z.unknown()).nullable().optional(),
  reason: z.string().nullable().optional(),
  timestamp: z.string().datetime({ offset: true }),
});

export type DashboardGraphMutationData = z.infer<typeof DashboardGraphMutationDataSchema>;

export function parseDashboardGraphMutationData(input: unknown): DashboardGraphMutationData {
  return DashboardGraphMutationDataSchema.parse(input);
}

export const GraphMutationSocketDataSchema = z.object({
  runId: z.string().uuid(),
  mutation: DashboardGraphMutationDataSchema,
});
export type GraphMutationSocketData = z.infer<typeof GraphMutationSocketDataSchema>;

// =============================================================================
// Context Event Events
// =============================================================================

const TokenLogprobSchema = z.object({
  token: z.string(),
  logprob: z.number(),
});

const ContextEventPayloadSchema = z.discriminatedUnion("event_type", [
  z.object({ event_type: z.literal("system_prompt"), text: z.string() }),
  z.object({
    event_type: z.literal("user_message"),
    text: z.string(),
    from_worker_key: z.string().nullable(),
  }),
  z.object({
    event_type: z.literal("assistant_text"),
    text: z.string(),
    turn_id: z.string(),
    turn_logprobs: z.array(TokenLogprobSchema).nullable(),
  }),
  z.object({
    event_type: z.literal("tool_call"),
    tool_call_id: z.string(),
    tool_name: z.string(),
    args: z.record(z.string(), z.unknown()),
    turn_id: z.string(),
    turn_logprobs: z.array(TokenLogprobSchema).nullable(),
  }),
  z.object({
    event_type: z.literal("tool_result"),
    tool_call_id: z.string(),
    tool_name: z.string(),
    result: z.unknown(),
    is_error: z.boolean(),
  }),
  z.object({
    event_type: z.literal("thinking"),
    text: z.string(),
    turn_id: z.string(),
    turn_logprobs: z.array(TokenLogprobSchema).nullable(),
  }),
]);

export const DashboardContextEventEventSchema = z.object({
  id: z.string(),
  run_id: z.string(),
  task_execution_id: z.string(),
  task_node_id: z.string(),
  worker_binding_key: z.string(),
  sequence: z.number(),
  event_type: z.string(),
  payload: ContextEventPayloadSchema,
  created_at: z.string(),
  started_at: z.string().nullable(),
  completed_at: z.string().nullable(),
});

export type DashboardContextEventEventData = z.infer<typeof DashboardContextEventEventSchema>;

export function parseDashboardContextEventData(data: unknown): DashboardContextEventEventData {
  return DashboardContextEventEventSchema.parse(data);
}
