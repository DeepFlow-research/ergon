import { z } from "zod";

import { schemas } from "@/generated/rest/contracts";

export const BenchmarkNameSchema = z.string();
export const SampleStatusSchema = z.enum(["pending", "executing", "evaluating", "completed", "failed", "cancelled"]);
export const TaskStatusSchema = z.string();

const restSchemas = schemas as typeof schemas & {
  ExperimentDetailDto?: z.ZodTypeAny;
};

export const ExperimentDetailSchema = restSchemas.ExperimentDetailDto ?? schemas.ExperimentDetailView;
export const SampleRuntimeEventViewSchema = schemas.SampleRuntimeEventView;
const JsonRecordSchema = z.record(z.string(), z.unknown());

export const SamplerInvocationViewSchema = z.object({
  samplerInvocationId: z.string(),
  samplerName: z.string(),
  requestedK: z.number(),
  candidatePoolSize: z.number(),
  selectedCount: z.number(),
  samplerConfig: JsonRecordSchema.default({}),
  createdAt: z.string(),
});

export const EnvironmentContributionViewSchema = z.object({
  environmentId: z.string(),
  environmentName: z.string(),
  sourceMode: z.string(),
  sampleCount: z.number(),
  selectedCount: z.number(),
  sourceMetadata: JsonRecordSchema.default({}),
});

export const ExperimentSampleSummaryViewSchema = z.object({
  sampleId: z.string(),
  experimentId: z.string(),
  environmentId: z.string(),
  environmentName: z.string(),
  sampleKey: z.string(),
  sampleRef: JsonRecordSchema.default({}),
  sourceMetadata: JsonRecordSchema.default({}),
  status: z.string(),
  createdAt: z.string(),
});

export const ExperimentDetailViewSchema = z.object({
  experimentId: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  environments: z.array(EnvironmentContributionViewSchema).default([]),
  sampleCount: z.number(),
  samples: z.array(ExperimentSampleSummaryViewSchema).default([]),
  samplerInvocations: z.array(SamplerInvocationViewSchema).default([]),
  metadata: JsonRecordSchema.default({}),
  createdAt: z.string(),
});

export const ExperimentListViewSchema = z.object({
  items: z.array(ExperimentDetailViewSchema).default([]),
});

export const SampleDetailViewSchema = z.object({
  sampleId: z.string(),
  experimentId: z.string(),
  environmentId: z.string(),
  environmentName: z.string(),
  sampleKey: z.string(),
  sampleRef: JsonRecordSchema.default({}),
  sourceMetadata: JsonRecordSchema.default({}),
  status: z.string(),
  createdAt: z.string(),
  startedAt: z.string().nullable().optional(),
  completedAt: z.string().nullable().optional(),
});

export const SampleEventViewSchema = SampleRuntimeEventViewSchema;

export const SampleGraphNodeViewSchema = z.object({
  taskId: z.string(),
  taskSlug: z.string(),
  description: z.string(),
  status: z.string(),
  parentTaskId: z.string().nullable().optional(),
  level: z.number().default(0),
  assignedWorkerSlug: z.string().nullable().optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export const SampleGraphEdgeViewSchema = z.object({
  edgeId: z.string(),
  sourceTaskId: z.string(),
  targetTaskId: z.string(),
  status: z.string(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export const SampleGraphViewSchema = z.object({
  nodes: z.array(SampleGraphNodeViewSchema).default([]),
  edges: z.array(SampleGraphEdgeViewSchema).default([]),
});

export const SampleEventsViewSchema = z.object({
  items: z.array(SampleEventViewSchema).default([]),
});

export const SampleStateViewSchema = z.object({
  sampleId: z.string(),
  experimentId: z.string(),
  environmentId: z.string(),
  environmentName: z.string(),
  detail: SampleDetailViewSchema,
  events: z.array(SampleEventViewSchema).default([]),
  graph: SampleGraphViewSchema.default({ nodes: [], edges: [] }),
});

export const SampleExecutionAttemptSchema = schemas.SampleExecutionAttemptDto;
export const SampleResourceSchema = schemas.SampleResourceDto;
export const SampleSandboxCommandSchema = schemas.SampleSandboxCommandDto;
export const SampleSandboxSchema = schemas.SampleSandboxDto;
export const SampleTaskSchema = schemas.SampleTaskDto;
export const SampleCommunicationMessageSchema = schemas.SampleCommunicationMessageDto;
export const SampleCommunicationThreadSchema = schemas.SampleCommunicationThreadDto;
export const SampleTaskEvaluationSchema = schemas.SampleTaskEvaluationDto;
export const SampleSnapshotSchema = schemas.SampleSnapshotDto;

type KnownKeys<T> = {
  [K in keyof T as string extends K ? never : number extends K ? never : symbol extends K
    ? never
    : K]: T[K];
};

export type BenchmarkName = z.infer<typeof BenchmarkNameSchema>;
export type SampleLifecycleStatus = z.infer<typeof SampleStatusSchema>;
export type TaskStatusValue = z.infer<typeof TaskStatusSchema>;

type RawExperimentDetail = Record<string, any>;
type RawExperimentRunRow = Record<string, any>;
type RawExperimentSummary = Record<string, any>;
type RawSampleExecutionAttempt = KnownKeys<z.infer<typeof SampleExecutionAttemptSchema>>;
type RawSampleResource = KnownKeys<z.infer<typeof SampleResourceSchema>>;
type RawSampleSandboxCommand = KnownKeys<z.infer<typeof SampleSandboxCommandSchema>>;
type RawSampleSandbox = KnownKeys<z.infer<typeof SampleSandboxSchema>>;
type RawSampleTask = KnownKeys<z.infer<typeof SampleTaskSchema>>;
type RawSampleCommunicationMessage = KnownKeys<z.infer<typeof SampleCommunicationMessageSchema>>;
type RawSampleCommunicationThread = KnownKeys<z.infer<typeof SampleCommunicationThreadSchema>>;
type RawSampleTaskEvaluation = KnownKeys<z.infer<typeof SampleTaskEvaluationSchema>>;
type RawSampleEvaluationCriterion = KnownKeys<NonNullable<RawSampleTaskEvaluation["criterionResults"]>[number]>;
type RawSampleSnapshot = KnownKeys<z.infer<typeof SampleSnapshotSchema>>;
type RawSampleSnapshotMetrics = KnownKeys<NonNullable<RawSampleSnapshot["metrics"]>>;

export type RawSampleSandboxType = RawSampleSandbox;
export type RawSampleSandboxCommandType = RawSampleSandboxCommand;

export type SampleSnapshotMetrics = RawSampleSnapshotMetrics;
export type SampleRuntimeEventView = z.infer<typeof SampleRuntimeEventViewSchema>;

export type SamplerInvocationView = z.infer<typeof SamplerInvocationViewSchema>;
export type EnvironmentContributionView = z.infer<typeof EnvironmentContributionViewSchema>;
export type ExperimentSampleSummaryView = z.infer<typeof ExperimentSampleSummaryViewSchema>;
export type ExperimentDetailView = z.infer<typeof ExperimentDetailViewSchema>;
export type ExperimentListView = z.infer<typeof ExperimentListViewSchema>;
export type SampleDetailView = z.infer<typeof SampleDetailViewSchema>;
export type SampleEventView = z.infer<typeof SampleEventViewSchema>;
export type SampleGraphNodeView = z.infer<typeof SampleGraphNodeViewSchema>;
export type SampleGraphEdgeView = z.infer<typeof SampleGraphEdgeViewSchema>;
export type SampleGraphView = z.infer<typeof SampleGraphViewSchema>;
export type SampleEventsView = z.infer<typeof SampleEventsViewSchema>;
export type SampleStateView = z.infer<typeof SampleStateViewSchema>;

export interface ExperimentStatusCounts {
  pending: number;
  executing: number;
  evaluating: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface ExperimentRunMetrics {
  sample_id: string;
  run_name?: string | null;
  status: string;
  sample_label?: string | null;
  instance_key: string;
  score?: number | null;
  return_value?: number | null;
  duration_ms?: number | null;
  total_tasks?: number | null;
  tool_call_count: number;
  total_cost_usd?: number | null;
  cost_observed: boolean;
  total_tokens?: number | null;
  tokens_observed?: boolean;
  token_breakdown?: Record<string, number>;
  model_target?: string | null;
  evaluator_slug?: string | null;
  error_summary?: string | null;
}

export interface ExperimentSummaryDetail
  extends Omit<
    RawExperimentSummary,
    | "average_duration_ms"
    | "average_score"
    | "average_tasks"
    | "default_evaluator_slug"
    | "default_model_target"
    | "description"
    | "failure_count"
    | "latest_activity_at"
    | "status_counts"
    | "total_cost_usd"
  > {
  average_duration_ms?: number | null;
  average_score?: number | null;
  average_tasks?: number | null;
  default_evaluator_slug?: string | null;
  default_model_target?: string | null;
  description?: string | null;
  failure_count?: number;
  latest_activity_at?: string | null;
  status_counts?: Partial<ExperimentStatusCounts>;
  total_cost_usd?: number | null;
}

export interface ExperimentRunRow
  extends Omit<
    RawExperimentRunRow,
    | "completed_at"
    | "error_message"
    | "evaluator_slug"
    | "final_score"
    | "model_target"
    | "metrics"
    | "running_time_ms"
    | "seed"
    | "started_at"
    | "total_cost_usd"
    | "total_tasks"
    | "worker_team"
  > {
  completed_at: string | null;
  error_message: string | null;
  evaluator_slug: string | null;
  final_score: number | null;
  model_target: string | null;
  metrics: ExperimentRunMetrics;
  running_time_ms: number | null;
  seed: number | null;
  started_at: string | null;
  total_cost_usd: number | null;
  total_tasks: number | null;
  worker_team: Record<string, unknown>;
}

export interface ExperimentDetail extends Omit<RawExperimentDetail, "analytics" | "experiment" | "runs"> {
  experiment: ExperimentSummaryDetail;
  runs: ExperimentRunRow[];
  analytics: {
    total_runs: number;
    status_counts: ExperimentStatusCounts;
    average_score: number | null;
    average_duration_ms: number | null;
    average_tasks: number | null;
    total_cost_usd: number | null;
    latest_activity_at: string | null;
    error_count: number;
  };
}

export interface SampleExecutionAttempt
  extends Omit<
    RawSampleExecutionAttempt,
    "agentId" | "agentName" | "completedAt" | "errorMessage" | "finalAssistantMessage" | "outputResourceIds" | "score" | "startedAt"
  > {
  agentId: string | null;
  agentName: string | null;
  completedAt: string | null;
  errorMessage: string | null;
  finalAssistantMessage: string | null;
  outputResourceIds: string[];
  score: number | null;
  startedAt: string | null;
}

export type SampleResource = RawSampleResource;

export interface SampleSandboxCommand
  extends Omit<RawSampleSandboxCommand, "durationMs" | "exitCode" | "stderr" | "stdout"> {
  durationMs: number | null;
  exitCode: number | null;
  stderr: string | null;
  stdout: string | null;
}

export interface SampleSandbox
  extends Omit<RawSampleSandbox, "closeReason" | "closedAt" | "commands" | "template"> {
  closeReason: string | null;
  closedAt: string | null;
  commands: SampleSandboxCommand[];
  template: string | null;
}

/**
 * Per-task row in {@link SampleSnapshot.tasks} (camelCase on the wire).
 *
 * Semantics mirror the backend `SampleTaskDto` field descriptions:
 * - `startedAt`: null only while the task has not actually started yet (e.g. pending / ready).
 * - `completedAt`: null until a terminal outcome; may be null together with `startedAt` if not started.
 */
export interface SampleTask
  extends Omit<
    RawSampleTask,
    "assignedWorkerId" | "assignedWorkerSlug" | "childIds" | "completedAt" | "dependsOnIds" | "parentId" | "startedAt"
  > {
  assignedWorkerId: string | null;
  assignedWorkerSlug: string | null;
  childIds: string[];
  /** Terminal wall time when set; null until finished or if the task never started. */
  completedAt: string | null;
  dependsOnIds: string[];
  parentId: string | null;
  /** First meaningful execution start; null only before the task has actually started. */
  startedAt: string | null;
}

export interface SampleCommunicationMessage extends Omit<RawSampleCommunicationMessage, "taskId"> {
  taskId: string | null;
}

export interface SampleCommunicationThread
  extends Omit<RawSampleCommunicationThread, "messages" | "taskId"> {
  messages: SampleCommunicationMessage[];
  taskId: string | null;
}

export interface SampleEvaluationCriterion
  extends Omit<RawSampleEvaluationCriterion, "error" | "evaluatedActionIds" | "evaluatedResourceIds"> {
  error: Record<string, unknown> | null;
  evaluatedActionIds: string[];
  evaluatedResourceIds: string[];
}

export interface SampleTaskEvaluation
  extends Omit<RawSampleTaskEvaluation, "criterionResults" | "failedGate" | "taskId"> {
  criterionResults: SampleEvaluationCriterion[];
  failedGate: string | null;
  taskId: string | null;
}

export interface SampleSnapshot
  extends Omit<
    RawSampleSnapshot,
    | "completedAt"
    | "durationSeconds"
    | "error"
    | "evaluationsByTask"
    | "executionsByTask"
    | "finalScore"
    | "resourcesByTask"
    | "sandboxesByTask"
    | "startedAt"
    | "tasks"
    | "threads"
  > {
  completedAt: string | null;
  durationSeconds: number | null;
  error: string | null;
  evaluationsByTask: Record<string, SampleTaskEvaluation>;
  executionsByTask: Record<string, SampleExecutionAttempt[]>;
  finalScore: number | null;
  resourcesByTask: Record<string, SampleResource[]>;
  sandboxesByTask: Record<string, SampleSandbox>;
  startedAt: string;
  tasks: Record<string, SampleTask>;
  threads: SampleCommunicationThread[];
}

function normalizeSampleExecutionAttempt(execution: RawSampleExecutionAttempt): SampleExecutionAttempt {
  return {
    ...execution,
    agentId: execution.agentId ?? null,
    agentName: execution.agentName ?? null,
    completedAt: execution.completedAt ?? null,
    errorMessage: execution.errorMessage ?? null,
    outputResourceIds: execution.outputResourceIds ?? [],
    finalAssistantMessage: execution.finalAssistantMessage ?? null,
    score: execution.score ?? null,
    startedAt: execution.startedAt ?? null,
  };
}

function normalizeSampleSandboxCommand(command: RawSampleSandboxCommand): SampleSandboxCommand {
  return {
    ...command,
    durationMs: command.durationMs ?? null,
    exitCode: command.exitCode ?? null,
    stderr: command.stderr ?? null,
    stdout: command.stdout ?? null,
  };
}

function normalizeSampleSandbox(sandbox: RawSampleSandbox): SampleSandbox {
  return {
    ...sandbox,
    closeReason: sandbox.closeReason ?? null,
    closedAt: sandbox.closedAt ?? null,
    commands: (sandbox.commands ?? []).map(normalizeSampleSandboxCommand),
    template: sandbox.template ?? null,
  };
}

function normalizeSampleTask(task: RawSampleTask): SampleTask {
  return {
    ...task,
    assignedWorkerId: task.assignedWorkerId ?? null,
    assignedWorkerSlug: task.assignedWorkerSlug ?? null,
    childIds: task.childIds ?? [],
    completedAt: task.completedAt ?? null,
    dependsOnIds: task.dependsOnIds ?? [],
    parentId: task.parentId ?? null,
    startedAt: task.startedAt ?? null,
  };
}

function normalizeSampleCommunicationMessage(message: RawSampleCommunicationMessage): SampleCommunicationMessage {
  return {
    ...message,
    taskId: message.taskId ?? null,
  };
}

function normalizeSampleCommunicationThread(thread: RawSampleCommunicationThread): SampleCommunicationThread {
  return {
    ...thread,
    messages: (thread.messages ?? []).map(normalizeSampleCommunicationMessage),
    taskId: thread.taskId ?? null,
    summary: thread.summary ?? null,
  };
}

function normalizeSampleTaskEvaluation(evaluation: RawSampleTaskEvaluation): SampleTaskEvaluation {
  return {
    ...evaluation,
    criterionResults: (evaluation.criterionResults ?? []).map((criterion) => ({
      ...criterion,
      error: criterion.error ?? null,
      evaluatedActionIds: criterion.evaluatedActionIds ?? [],
      evaluatedResourceIds: criterion.evaluatedResourceIds ?? [],
    })),
    failedGate: evaluation.failedGate ?? null,
    taskId: evaluation.taskId ?? null,
  };
}

export function parseExperimentDetail(input: unknown): ExperimentDetail {
  const detail = ExperimentDetailSchema.parse(input) as RawExperimentDetail;
  return {
    ...detail,
    experiment: detail.experiment ?? {},
    analytics: {
      total_runs: detail.analytics?.total_runs ?? 0,
      average_duration_ms: detail.analytics?.average_duration_ms ?? null,
      average_score: detail.analytics?.average_score ?? null,
      average_tasks: detail.analytics?.average_tasks ?? null,
      error_count: detail.analytics?.error_count ?? 0,
      latest_activity_at: detail.analytics?.latest_activity_at ?? null,
      status_counts: {
        pending: detail.analytics?.status_counts?.pending ?? 0,
        executing: detail.analytics?.status_counts?.executing ?? 0,
        evaluating: detail.analytics?.status_counts?.evaluating ?? 0,
        completed: detail.analytics?.status_counts?.completed ?? 0,
        failed: detail.analytics?.status_counts?.failed ?? 0,
        cancelled: detail.analytics?.status_counts?.cancelled ?? 0,
      },
      total_cost_usd: detail.analytics?.total_cost_usd ?? null,
    },
    runs: ((detail.runs ?? []) as RawExperimentRunRow[]).map((run) => ({
      ...run,
      completed_at: run.completed_at ?? null,
      error_message: run.error_message ?? null,
      evaluator_slug: run.evaluator_slug ?? null,
      final_score: run.final_score ?? null,
      model_target: run.model_target ?? null,
      metrics: run.metrics ?? {},
      running_time_ms: run.running_time_ms ?? null,
      seed: run.seed ?? null,
      started_at: run.started_at ?? null,
      total_cost_usd: run.total_cost_usd ?? null,
      total_tasks: run.total_tasks ?? null,
      worker_team: run.worker_team ?? {},
    })),
  };
}

export function parseExperimentState(input: unknown): ExperimentDetailView {
  return ExperimentDetailViewSchema.parse(input);
}

export function parseExperimentListState(input: unknown): ExperimentListView {
  return ExperimentListViewSchema.parse(input);
}

export function parseSampleDetail(input: unknown): SampleDetailView {
  return SampleDetailViewSchema.parse(input);
}

export function parseSampleEvents(input: unknown): SampleEventsView {
  return SampleEventsViewSchema.parse(input);
}

export function parseSampleGraph(input: unknown): SampleGraphView {
  return SampleGraphViewSchema.parse(input);
}

export function parseSampleState(input: unknown): SampleStateView {
  return SampleStateViewSchema.parse(input);
}

export function parseSampleSandbox(input: unknown): SampleSandbox {
  return normalizeSampleSandbox(SampleSandboxSchema.parse(input));
}

export function parseSampleSandboxCommand(input: unknown): SampleSandboxCommand {
  return normalizeSampleSandboxCommand(SampleSandboxCommandSchema.parse(input));
}

export function parseSampleCommunicationMessage(input: unknown): SampleCommunicationMessage {
  return normalizeSampleCommunicationMessage(SampleCommunicationMessageSchema.parse(input));
}

export function parseSampleCommunicationThread(input: unknown): SampleCommunicationThread {
  return normalizeSampleCommunicationThread(SampleCommunicationThreadSchema.parse(input));
}

export function parseSampleRuntimeEvents(input: unknown): SampleRuntimeEventView[] {
  return z.array(SampleRuntimeEventViewSchema).parse(input);
}

export function parseSampleTaskEvaluation(input: unknown): SampleTaskEvaluation {
  return normalizeSampleTaskEvaluation(SampleTaskEvaluationSchema.parse(input));
}

export function parseSampleSnapshot(input: unknown): SampleSnapshot {
  const snapshot = SampleSnapshotSchema.parse(input);
  return {
    ...snapshot,
    completedAt: snapshot.completedAt ?? null,
    durationSeconds: snapshot.durationSeconds ?? null,
    error: snapshot.error ?? null,
    evaluationsByTask: Object.fromEntries(
      Object.entries(snapshot.evaluationsByTask ?? {}).map(([taskId, evaluation]) => [
        taskId,
        normalizeSampleTaskEvaluation(evaluation),
      ]),
    ),
    executionsByTask: Object.fromEntries(
      Object.entries(snapshot.executionsByTask ?? {}).map(([taskId, executions]) => [
        taskId,
        executions.map(normalizeSampleExecutionAttempt),
      ]),
    ),
    finalScore: snapshot.finalScore ?? null,
    resourcesByTask: snapshot.resourcesByTask ?? {},
    sandboxesByTask: Object.fromEntries(
      Object.entries(snapshot.sandboxesByTask ?? {}).map(([taskId, sandbox]) => [
        taskId,
        normalizeSampleSandbox(sandbox),
      ]),
    ),
    startedAt: snapshot.startedAt ?? new Date(0).toISOString(),
    tasks: Object.fromEntries(
      Object.entries(snapshot.tasks ?? {}).map(([taskId, task]) => [taskId, normalizeSampleTask(task)]),
    ),
    threads: (snapshot.threads ?? []).map(normalizeSampleCommunicationThread),
  };
}
