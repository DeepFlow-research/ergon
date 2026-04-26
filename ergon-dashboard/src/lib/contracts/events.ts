import { z } from "zod";

import {
  MutationTypeSchema,
  GraphTargetTypeSchema,
} from "@/features/graph/contracts/graphMutations";
import {
  DashboardResourcePublishedEvent as GeneratedDashboardResourcePublishedEvent,
  DashboardSandboxClosedEvent as GeneratedDashboardSandboxClosedEvent,
  DashboardSandboxCommandEvent as GeneratedDashboardSandboxCommandEvent,
  DashboardSandboxCreatedEvent as GeneratedDashboardSandboxCreatedEvent,
  DashboardTaskStatusChangedEvent as GeneratedDashboardTaskStatusChangedEvent,
  DashboardWorkflowCompletedEvent as GeneratedDashboardWorkflowCompletedEvent,
} from "@/generated/events";
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
  RunSandbox,
  RunSandboxCommand,
  RunSandboxCommandSchema,
  RunSandboxSchema,
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

export const DashboardCohortUpdatedDataSchema = z.object({
  cohort_id: z.string().uuid(),
  summary: CohortSummarySchema,
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

export const RunListEntrySchema = z.object({
  runId: z.string(),
  name: z.string(),
  status: z.enum(["pending", "executing", "evaluating", "completed", "failed", "cancelled"]),
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
// Migrated to generated schemas — types re-exported under the legacy `Data` suffix.
export type DashboardWorkflowCompletedData = GeneratedDashboardWorkflowCompletedEvent;
export type DashboardTaskStatusChangedData = GeneratedDashboardTaskStatusChangedEvent;
export type DashboardResourcePublishedData = GeneratedDashboardResourcePublishedEvent;
export type DashboardSandboxCreatedData = GeneratedDashboardSandboxCreatedEvent;
export type DashboardSandboxCommandData = GeneratedDashboardSandboxCommandEvent;
export type DashboardSandboxClosedData = GeneratedDashboardSandboxClosedEvent;
export interface DashboardCohortUpdatedData {
  cohort_id: string;
  summary: CohortSummary;
}
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

function camelizeKey(key: string): string {
  return key.replace(/_([a-z])/g, (_, char: string) => char.toUpperCase());
}

function camelizeObjectKeys(input: unknown): unknown {
  if (Array.isArray(input)) {
    return input.map(camelizeObjectKeys);
  }
  if (input === null || typeof input !== "object") {
    return input;
  }
  return Object.fromEntries(
    Object.entries(input as Record<string, unknown>).map(([key, value]) => [
      camelizeKey(key),
      camelizeObjectKeys(value),
    ]),
  );
}

// TODO(E2b): replace with generated once backend ``summary`` type is tightened
// (docs/bugs/open/2026-04-23-inngest-function-failures.md § E2b).
export function parseDashboardCohortUpdatedData(input: unknown): DashboardCohortUpdatedData {
  const parsed = DashboardCohortUpdatedDataSchema.parse(input);
  return {
    cohort_id: parsed.cohort_id,
    summary: parseCohortSummary(parsed.summary),
  };
}

// TODO(E2b): replace with generated once backend ``thread``/``message`` types
// are tightened (docs/bugs/open/2026-04-23-inngest-function-failures.md § E2b).
export function parseDashboardThreadMessageCreatedData(
  input: unknown,
): DashboardThreadMessageCreatedData {
  const raw = z.object({ thread: z.unknown(), message: z.unknown() }).passthrough().parse(input);
  const parsed = DashboardThreadMessageCreatedDataSchema.parse({
    ...raw,
    thread: camelizeObjectKeys(raw.thread),
    message: camelizeObjectKeys(raw.message),
  });
  return {
    run_id: parsed.run_id,
    thread: parseRunCommunicationThread(parsed.thread),
    message: parseRunCommunicationMessage(parsed.message),
  };
}

// TODO(E2b): replace with generated once backend ``evaluation`` type is
// tightened (docs/bugs/open/2026-04-23-inngest-function-failures.md § E2b).
export function parseDashboardTaskEvaluationUpdatedData(
  input: unknown,
): DashboardTaskEvaluationUpdatedData {
  const raw = z.object({ evaluation: z.unknown() }).passthrough().parse(input);
  const parsed = DashboardTaskEvaluationUpdatedDataSchema.parse({
    ...raw,
    evaluation: camelizeObjectKeys(raw.evaluation),
  });
  return {
    run_id: parsed.run_id,
    task_id: parsed.task_id ?? null,
    evaluation: parseRunTaskEvaluation(parsed.evaluation),
  };
}

export function parseDashboardWorkflowStartedData(input: unknown): DashboardWorkflowStartedData {
  // Generated schema for dashboard/workflow.started still types ``task_tree``
  // as ``z.any()`` — see docs/bugs/open/2026-04-23-inngest-function-failures.md § E3.
  // TODO(E2b): replace with DashboardWorkflowStartedEventSchema.parse(...) once
  // json-schema-to-zod handles ``$ref``/``$defs`` for recursive TaskTreeNode.
  return DashboardWorkflowStartedDataSchema.parse(input);
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
    turn_token_ids: z.array(z.number()).nullable(),
    turn_logprobs: z.array(TokenLogprobSchema).nullable(),
  }),
  z.object({
    event_type: z.literal("tool_call"),
    tool_call_id: z.string(),
    tool_name: z.string(),
    args: z.record(z.string(), z.unknown()),
    turn_id: z.string(),
    turn_token_ids: z.array(z.number()).nullable(),
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
    turn_token_ids: z.array(z.number()).nullable(),
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
