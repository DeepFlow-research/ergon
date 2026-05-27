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
  parseSampleCommunicationMessage,
  parseSampleCommunicationThread,
  parseSampleSandbox,
  parseSampleSandboxCommand,
  parseSampleSnapshot,
  parseSampleTaskEvaluation,
  SampleCommunicationMessageSchema,
  SampleCommunicationThreadSchema,
  SampleResourceSchema,
  SampleResource,
  SampleSandbox,
  SampleSandboxCommand,
  SampleSandboxCommandSchema,
  SampleSandboxSchema,
  SampleSnapshot,
  SampleTaskEvaluation,
  SampleTaskEvaluationSchema,
  TaskStatusSchema,
} from "@/lib/contracts/rest";
import { normalizeContextEventPayload } from "@/lib/sample-state/contextEvents";

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
  sample_id: z.string().uuid(),
  definition_id: z.string().uuid(),
  workflow_name: z.string(),
  snapshot: z.unknown(),
  started_at: z.string().datetime({ offset: true }),
  total_tasks: z.number().int(),
  total_leaf_tasks: z.number().int(),
});

export const DashboardThreadMessageCreatedDataSchema = z.object({
  sample_id: z.string().uuid(),
  thread: SampleCommunicationThreadSchema,
  message: SampleCommunicationMessageSchema,
});

export const DashboardTaskEvaluationUpdatedDataSchema = z.object({
  sample_id: z.string().uuid(),
  task_id: z.string().nullable().optional(),
  evaluation: SampleTaskEvaluationSchema,
});

export const SampleListEntrySchema = z.object({
  sampleId: z.string(),
  name: z.string(),
  status: z.enum(["pending", "executing", "evaluating", "completed", "failed", "cancelled"]),
  startedAt: z.string(),
  completedAt: z.string().nullable(),
  durationSeconds: z.number().nullable(),
  finalScore: z.number().nullable(),
  error: z.string().nullable(),
});

export const SyncSamplesSchema = z.array(SampleListEntrySchema);
export const SampleCompletedSocketDataSchema = z.object({
  sampleId: z.string(),
  status: z.enum(["completed", "failed"]),
  completedAt: z.string(),
  durationSeconds: z.number(),
  finalScore: z.number().nullable(),
  error: z.string().nullable(),
});
export const TaskStatusSocketDataSchema = z.object({
  sampleId: z.string(),
  taskId: z.string(),
  status: TaskStatusSchema,
  timestamp: z.string(),
  assignedWorkerId: z.string().nullable(),
  assignedWorkerSlug: z.string().nullable(),
});
export const ResourceSocketDataSchema = z.object({
  sampleId: z.string(),
  resource: SampleResourceSchema,
});
export const SandboxCreatedSocketDataSchema = z.object({
  sampleId: z.string(),
  sandbox: SampleSandboxSchema,
});
export const SandboxCommandSocketDataSchema = z.object({
  sampleId: z.string(),
  taskId: z.string(),
  command: SampleSandboxCommandSchema,
});
export const SandboxClosedSocketDataSchema = z.object({
  sampleId: z.string(),
  taskId: z.string(),
  reason: z.string(),
  timestamp: z.string(),
});

export type TaskTrigger = z.infer<typeof TaskTriggerSchema>;
export interface DashboardWorkflowStartedData {
  sample_id: string;
  definition_id: string;
  workflow_name: string;
  snapshot: SampleSnapshot;
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
export interface DashboardThreadMessageCreatedData {
  sample_id: string;
  thread: ReturnType<typeof parseSampleCommunicationThread>;
  message: ReturnType<typeof parseSampleCommunicationMessage>;
}
export interface DashboardTaskEvaluationUpdatedData {
  sample_id: string;
  task_id: string | null;
  evaluation: SampleTaskEvaluation;
}
export type SampleListEntry = z.infer<typeof SampleListEntrySchema>;
export type SampleCompletedSocketData = z.infer<typeof SampleCompletedSocketDataSchema>;
export type TaskStatusSocketData = z.infer<typeof TaskStatusSocketDataSchema>;
export interface ResourceSocketData {
  sampleId: string;
  resource: SampleResource;
}
export interface SandboxCreatedSocketData {
  sampleId: string;
  sandbox: SampleSandbox;
}
export interface SandboxCommandSocketData {
  sampleId: string;
  taskId: string;
  command: SampleSandboxCommand;
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
    sample_id: parsed.sample_id,
    thread: parseSampleCommunicationThread(parsed.thread),
    message: parseSampleCommunicationMessage(parsed.message),
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
    sample_id: parsed.sample_id,
    task_id: parsed.task_id ?? null,
    evaluation: parseSampleTaskEvaluation(parsed.evaluation),
  };
}

export function parseDashboardWorkflowStartedData(input: unknown): DashboardWorkflowStartedData {
  const raw = z.object({ snapshot: z.unknown() }).passthrough().parse(input);
  const parsed = GeneratedDashboardWorkflowStartedEventSchema.parse({
    ...raw,
    snapshot: camelizeSnapshotKeys(raw.snapshot),
  });
  return {
    sample_id: parsed.sample_id,
    definition_id: parsed.definition_id,
    workflow_name: parsed.workflow_name,
    snapshot: parseSampleSnapshot(parsed.snapshot),
    started_at: parsed.started_at,
    total_tasks: parsed.total_tasks,
    total_leaf_tasks: parsed.total_leaf_tasks,
  };
}

export function parseSyncSamples(input: unknown): SampleListEntry[] {
  return SyncSamplesSchema.parse(input);
}

export function parseSampleCompletedSocketData(input: unknown): SampleCompletedSocketData {
  return SampleCompletedSocketDataSchema.parse(input);
}

export function parseTaskStatusSocketData(input: unknown): TaskStatusSocketData {
  return TaskStatusSocketDataSchema.parse(input);
}

export function parseResourceSocketData(input: unknown): ResourceSocketData {
  const parsed = ResourceSocketDataSchema.parse(input);
  return {
    sampleId: parsed.sampleId,
    resource: parsed.resource,
  };
}

export function parseSandboxCreatedSocketData(input: unknown): SandboxCreatedSocketData {
  const parsed = SandboxCreatedSocketDataSchema.parse(input);
  return {
    sampleId: parsed.sampleId,
    sandbox: parseSampleSandbox(parsed.sandbox),
  };
}

export function parseSandboxCommandSocketData(input: unknown): SandboxCommandSocketData {
  const parsed = SandboxCommandSocketDataSchema.parse(input);
  return {
    sampleId: parsed.sampleId,
    taskId: parsed.taskId,
    command: parseSampleSandboxCommand(parsed.command),
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
  sampleId: z.string().uuid(),
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
