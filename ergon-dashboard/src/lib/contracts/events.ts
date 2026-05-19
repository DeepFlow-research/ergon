import { z } from "zod";

import { GraphMutationDtoSchema } from "@/features/graph/contracts/graphMutations";
import {
  dashboardEventSchemas,
  DashboardContextEventEventSchema as GeneratedDashboardContextEventEventSchema,
  DashboardGraphMutationEventSchema as GeneratedDashboardGraphMutationEventSchema,
  DashboardResourcePublishedEvent as GeneratedDashboardResourcePublishedEvent,
  DashboardSandboxClosedEvent as GeneratedDashboardSandboxClosedEvent,
  DashboardSandboxCommandEvent as GeneratedDashboardSandboxCommandEvent,
  DashboardSandboxCreatedEvent as GeneratedDashboardSandboxCreatedEvent,
  DashboardTaskStatusChangedEvent as GeneratedDashboardTaskStatusChangedEvent,
  DashboardWorkflowCompletedEvent as GeneratedDashboardWorkflowCompletedEvent,
  DashboardWorkflowStartedEventSchema as GeneratedDashboardWorkflowStartedEventSchema,
} from "@/generated/events";
import {
  CohortSummary,
  CohortSummarySchema,
  parseCohortSummary,
  parseRunCommunicationMessage,
  parseRunCommunicationThread,
  parseRunSandbox,
  parseRunSandboxCommand,
  parseRunSnapshot,
  parseRunTaskEvaluation,
  RunCommunicationMessageSchema,
  RunCommunicationThreadSchema,
  RunResourceSchema,
  RunResource,
  RunSandbox,
  RunSandboxCommand,
  RunSandboxCommandSchema,
  RunSandboxSchema,
  RunSnapshot,
  RunTaskEvaluation,
  RunTaskEvaluationSchema,
  TaskStatusSchema,
} from "@/lib/contracts/rest";
import { normalizeContextEventPayload } from "@/lib/run-state/contextEvents";

export { dashboardEventSchemas };

export const TaskTriggerSchema = z.enum([
  "workflow_started",
  "dependency_satisfied",
  "worker_started",
  "execution_succeeded",
  "execution_failed",
  "children_completed",
]);

export const ResourceRefSchema = z.object({
  path: z.string().nullable().optional(),
  name: z.string(),
  content: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  mime_type: z.string().nullable().optional(),
});

export const EvaluatorRefSchema = z.object({ type: z.string() }).passthrough();

export type ResourceRef = z.infer<typeof ResourceRefSchema>;
export type EvaluatorRef = z.infer<typeof EvaluatorRefSchema>;

export const DashboardWorkflowStartedDataSchema = z.object({
  run_id: z.string().uuid(),
  definition_id: z.string().uuid(),
  workflow_name: z.string(),
  snapshot: z.unknown(),
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
  assignedWorkerSlug: z.string().nullable(),
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
  timestamp: z.string(),
});

export type TaskTrigger = z.infer<typeof TaskTriggerSchema>;
export interface DashboardWorkflowStartedData {
  run_id: string;
  definition_id: string;
  workflow_name: string;
  snapshot: RunSnapshot;
  started_at: string;
  total_tasks: number;
  total_leaf_tasks: number;
}
// Migrated to generated schemas; existing type names are re-exported for callers.
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

function camelizeSnapshotKeys(input: unknown): unknown {
  if (Array.isArray(input)) {
    return input.map(camelizeSnapshotKeys);
  }
  if (input === null || typeof input !== "object") {
    return input;
  }
  return Object.fromEntries(
    Object.entries(input as Record<string, unknown>).map(([key, value]) => [
      camelizeKey(key),
      key === "payload" ? value : camelizeSnapshotKeys(value),
    ]),
  );
}

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
  const raw = z.object({ snapshot: z.unknown() }).passthrough().parse(input);
  const parsed = GeneratedDashboardWorkflowStartedEventSchema.parse({
    ...raw,
    snapshot: camelizeSnapshotKeys(raw.snapshot),
  });
  return {
    run_id: parsed.run_id,
    definition_id: parsed.definition_id,
    workflow_name: parsed.workflow_name,
    snapshot: parseRunSnapshot(parsed.snapshot),
    started_at: parsed.started_at,
    total_tasks: parsed.total_tasks,
    total_leaf_tasks: parsed.total_leaf_tasks,
  };
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

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

export const DashboardGraphMutationDataSchema = z.preprocess((input) => {
  const outer = asRecord(input);
  return outer.mutation === undefined ? input : GeneratedDashboardGraphMutationEventSchema.parse(input).mutation;
}, GraphMutationDtoSchema);

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

export const DashboardContextEventEventSchema = z.object({
  ...GeneratedDashboardContextEventEventSchema.shape,
  payload: z.unknown().transform(normalizeContextEventPayload),
});

export type DashboardContextEventEventData = z.infer<typeof DashboardContextEventEventSchema>;

export function parseDashboardContextEventData(data: unknown): DashboardContextEventEventData {
  return DashboardContextEventEventSchema.parse(data);
}
