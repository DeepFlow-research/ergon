import { z } from "zod";

import { schemas } from "@/generated/rest/contracts";

export const BenchmarkNameSchema = schemas.BenchmarkName;
export const ExperimentCohortStatusSchema = schemas.ExperimentCohortStatus;
export const RunStatusSchema = schemas.RunStatus;
export const TaskStatusSchema = schemas.TaskStatus;

export const CohortSummarySchema = schemas.CohortSummaryDto;
export const CohortDetailSchema = schemas.CohortDetailDto;
export const UpdateCohortRequestSchema = schemas.UpdateCohortRequest;

export const RunActionSchema = schemas.RunActionDto;
export const RunExecutionAttemptSchema = schemas.RunExecutionAttemptDto;
export const RunResourceSchema = schemas.RunResourceDto;
export const RunSandboxCommandSchema = schemas.RunSandboxCommandDto;
export const RunSandboxSchema = schemas.RunSandboxDto;
export const RunTaskSchema = schemas.RunTaskDto;
export const RunCommunicationMessageSchema = schemas.RunCommunicationMessageDto;
export const RunCommunicationThreadSchema = schemas.RunCommunicationThreadDto;
export const RunTaskEvaluationSchema = schemas.RunTaskEvaluationDto;
export const RunSnapshotSchema = schemas.RunSnapshotDto;

export const CohortSummaryListSchema = z.array(CohortSummarySchema);

type KnownKeys<T> = {
  [K in keyof T as string extends K ? never : number extends K ? never : symbol extends K
    ? never
    : K]: T[K];
};

export type BenchmarkName = z.infer<typeof BenchmarkNameSchema>;
export type ExperimentCohortStatusValue = z.infer<typeof ExperimentCohortStatusSchema>;
export type RunLifecycleStatus = z.infer<typeof RunStatusSchema>;
export type TaskStatusValue = z.infer<typeof TaskStatusSchema>;

type RawCohortSummary = KnownKeys<z.infer<typeof CohortSummarySchema>>;
type RawCohortDetail = KnownKeys<z.infer<typeof CohortDetailSchema>>;
type RawCohortRunRow = KnownKeys<NonNullable<RawCohortDetail["runs"]>[number]>;
type RawRunAction = KnownKeys<z.infer<typeof RunActionSchema>>;
type RawRunExecutionAttempt = KnownKeys<z.infer<typeof RunExecutionAttemptSchema>>;
type RawRunResource = KnownKeys<z.infer<typeof RunResourceSchema>>;
type RawRunSandboxCommand = KnownKeys<z.infer<typeof RunSandboxCommandSchema>>;
type RawRunSandbox = KnownKeys<z.infer<typeof RunSandboxSchema>>;
type RawRunTask = KnownKeys<z.infer<typeof RunTaskSchema>>;
type RawRunCommunicationMessage = KnownKeys<z.infer<typeof RunCommunicationMessageSchema>>;
type RawRunCommunicationThread = KnownKeys<z.infer<typeof RunCommunicationThreadSchema>>;
type RawRunTaskEvaluation = KnownKeys<z.infer<typeof RunTaskEvaluationSchema>>;
type RawRunEvaluationCriterion = KnownKeys<NonNullable<RawRunTaskEvaluation["criterionResults"]>[number]>;
type RawRunSnapshot = KnownKeys<z.infer<typeof RunSnapshotSchema>>;

export type UpdateCohortRequest = z.infer<typeof UpdateCohortRequestSchema>;
export type RawRunActionType = RawRunAction;
export type RawRunSandboxType = RawRunSandbox;
export type RawRunSandboxCommandType = RawRunSandboxCommand;

export interface CohortMetadataSummary {
  code_commit_sha: string | null;
  repo_dirty: boolean | null;
  prompt_version: string | null;
  worker_version: string | null;
  model_provider: string | null;
  model_name: string | null;
  sandbox_config: Record<string, unknown>;
  dispatch_config: Record<string, unknown>;
}

export interface CohortStatusCounts {
  pending: number;
  executing: number;
  evaluating: number;
  completed: number;
  failed: number;
}

export interface CohortStatsExtras {
  benchmark_counts?: Record<string, number>;
  latest_run_at?: string | null;
}

export interface CohortSummary
  extends Omit<
    RawCohortSummary,
    | "average_duration_ms"
    | "average_score"
    | "best_score"
    | "created_by"
    | "description"
    | "extras"
    | "metadata_summary"
    | "stats_updated_at"
    | "status_counts"
    | "total_runs"
    | "worst_score"
  > {
  average_duration_ms: number | null;
  average_score: number | null;
  best_score: number | null;
  created_by: string | null;
  description: string | null;
  extras: CohortStatsExtras;
  metadata_summary: CohortMetadataSummary;
  stats_updated_at: string | null;
  status_counts: CohortStatusCounts;
  total_runs: number;
  worst_score: number | null;
}

export interface CohortRunRow
  extends Omit<RawCohortRunRow, "completed_at" | "error_message" | "final_score" | "running_time_ms" | "started_at"> {
  completed_at: string | null;
  error_message: string | null;
  final_score: number | null;
  running_time_ms: number | null;
  started_at: string | null;
}

export interface CohortDetail {
  summary: CohortSummary;
  runs: CohortRunRow[];
}

export interface RunAction
  extends Omit<RawRunAction, "completedAt" | "durationMs" | "error" | "output" | "startedAt"> {
  completedAt: string | null;
  durationMs: number | null;
  error: string | null;
  output: string | null;
  startedAt: string;
}

export interface RunExecutionAttempt
  extends Omit<
    RawRunExecutionAttempt,
    "agentId" | "agentName" | "completedAt" | "errorMessage" | "outputResourceIds" | "outputText" | "score" | "startedAt"
  > {
  agentId: string | null;
  agentName: string | null;
  completedAt: string | null;
  errorMessage: string | null;
  outputResourceIds: string[];
  outputText: string | null;
  score: number | null;
  startedAt: string | null;
}

export type RunResource = RawRunResource;

export interface RunSandboxCommand
  extends Omit<RawRunSandboxCommand, "durationMs" | "exitCode" | "stderr" | "stdout"> {
  durationMs: number | null;
  exitCode: number | null;
  stderr: string | null;
  stdout: string | null;
}

export interface RunSandbox
  extends Omit<RawRunSandbox, "closeReason" | "closedAt" | "commands" | "template"> {
  closeReason: string | null;
  closedAt: string | null;
  commands: RunSandboxCommand[];
  template: string | null;
}

export interface RunTask
  extends Omit<
    RawRunTask,
    "assignedWorkerId" | "assignedWorkerName" | "childIds" | "completedAt" | "dependsOnIds" | "parentId" | "startedAt"
  > {
  assignedWorkerId: string | null;
  assignedWorkerName: string | null;
  childIds: string[];
  completedAt: string | null;
  dependsOnIds: string[];
  parentId: string | null;
  startedAt: string | null;
}

export interface RunCommunicationMessage extends Omit<RawRunCommunicationMessage, "taskId"> {
  taskId: string | null;
}

export interface RunCommunicationThread
  extends Omit<RawRunCommunicationThread, "messages" | "taskId"> {
  messages: RunCommunicationMessage[];
  taskId: string | null;
}

export interface RunEvaluationCriterion
  extends Omit<RawRunEvaluationCriterion, "error" | "evaluatedActionIds" | "evaluatedResourceIds"> {
  error: Record<string, unknown> | null;
  evaluatedActionIds: string[];
  evaluatedResourceIds: string[];
}

export interface RunTaskEvaluation
  extends Omit<RawRunTaskEvaluation, "criterionResults" | "failedGate" | "taskId"> {
  criterionResults: RunEvaluationCriterion[];
  failedGate: string | null;
  taskId: string | null;
}

export interface RunSnapshot
  extends Omit<
    RawRunSnapshot,
    | "actionsByTask"
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
  actionsByTask: Record<string, RunAction[]>;
  completedAt: string | null;
  durationSeconds: number | null;
  error: string | null;
  evaluationsByTask: Record<string, RunTaskEvaluation>;
  executionsByTask: Record<string, RunExecutionAttempt[]>;
  finalScore: number | null;
  resourcesByTask: Record<string, RunResource[]>;
  sandboxesByTask: Record<string, RunSandbox>;
  startedAt: string;
  tasks: Record<string, RunTask>;
  threads: RunCommunicationThread[];
}

function normalizeCohortSummary(summary: RawCohortSummary): CohortSummary {
  // extras and metadata_summary arrive via .passthrough() on the generated Zod
  // schema, so KnownKeys strips them. Cast once to access safely.
  const pt = summary as RawCohortSummary & {
    extras?: CohortStatsExtras;
    metadata_summary?: Partial<CohortMetadataSummary>;
  };
  return {
    ...summary,
    average_duration_ms: summary.average_duration_ms ?? null,
    average_score: summary.average_score ?? null,
    best_score: summary.best_score ?? null,
    created_by: summary.created_by ?? null,
    description: summary.description ?? null,
    extras: pt.extras ?? {},
    metadata_summary: {
      code_commit_sha: pt.metadata_summary?.code_commit_sha ?? null,
      repo_dirty: pt.metadata_summary?.repo_dirty ?? null,
      prompt_version: pt.metadata_summary?.prompt_version ?? null,
      worker_version: pt.metadata_summary?.worker_version ?? null,
      model_provider: pt.metadata_summary?.model_provider ?? null,
      model_name: pt.metadata_summary?.model_name ?? null,
      sandbox_config: pt.metadata_summary?.sandbox_config ?? {},
      dispatch_config: pt.metadata_summary?.dispatch_config ?? {},
    },
    stats_updated_at: summary.stats_updated_at ?? null,
    status_counts: {
      pending: summary.status_counts?.pending ?? 0,
      executing: summary.status_counts?.executing ?? 0,
      evaluating: summary.status_counts?.evaluating ?? 0,
      completed: summary.status_counts?.completed ?? 0,
      failed: summary.status_counts?.failed ?? 0,
    },
    total_runs: summary.total_runs ?? 0,
    worst_score: summary.worst_score ?? null,
  };
}

function normalizeRunAction(action: RawRunAction): RunAction {
  return {
    ...action,
    completedAt: action.completedAt ?? null,
    durationMs: action.durationMs ?? null,
    error: action.error ?? null,
    output: action.output ?? null,
    startedAt: action.startedAt ?? new Date(0).toISOString(),
  };
}

function normalizeRunExecutionAttempt(execution: RawRunExecutionAttempt): RunExecutionAttempt {
  return {
    ...execution,
    agentId: execution.agentId ?? null,
    agentName: execution.agentName ?? null,
    completedAt: execution.completedAt ?? null,
    errorMessage: execution.errorMessage ?? null,
    outputResourceIds: execution.outputResourceIds ?? [],
    outputText: execution.outputText ?? null,
    score: execution.score ?? null,
    startedAt: execution.startedAt ?? null,
  };
}

function normalizeRunSandboxCommand(command: RawRunSandboxCommand): RunSandboxCommand {
  return {
    ...command,
    durationMs: command.durationMs ?? null,
    exitCode: command.exitCode ?? null,
    stderr: command.stderr ?? null,
    stdout: command.stdout ?? null,
  };
}

function normalizeRunSandbox(sandbox: RawRunSandbox): RunSandbox {
  return {
    ...sandbox,
    closeReason: sandbox.closeReason ?? null,
    closedAt: sandbox.closedAt ?? null,
    commands: (sandbox.commands ?? []).map(normalizeRunSandboxCommand),
    template: sandbox.template ?? null,
  };
}

function normalizeRunTask(task: RawRunTask): RunTask {
  return {
    ...task,
    assignedWorkerId: task.assignedWorkerId ?? null,
    assignedWorkerName: task.assignedWorkerName ?? null,
    childIds: task.childIds ?? [],
    completedAt: task.completedAt ?? null,
    dependsOnIds: task.dependsOnIds ?? [],
    parentId: task.parentId ?? null,
    startedAt: task.startedAt ?? null,
  };
}

function normalizeRunCommunicationMessage(message: RawRunCommunicationMessage): RunCommunicationMessage {
  return {
    ...message,
    taskId: message.taskId ?? null,
  };
}

function normalizeRunCommunicationThread(thread: RawRunCommunicationThread): RunCommunicationThread {
  return {
    ...thread,
    messages: (thread.messages ?? []).map(normalizeRunCommunicationMessage),
    taskId: thread.taskId ?? null,
  };
}

function normalizeRunTaskEvaluation(evaluation: RawRunTaskEvaluation): RunTaskEvaluation {
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

export function parseCohortSummaryList(input: unknown): CohortSummary[] {
  return CohortSummaryListSchema.parse(input).map(normalizeCohortSummary);
}

export function parseCohortDetail(input: unknown): CohortDetail {
  const detail = CohortDetailSchema.parse(input);
  return {
    summary: normalizeCohortSummary(detail.summary),
    runs: (detail.runs ?? []).map((run) => ({
      ...run,
      completed_at: run.completed_at ?? null,
      error_message: run.error_message ?? null,
      final_score: run.final_score ?? null,
      running_time_ms: run.running_time_ms ?? null,
      started_at: run.started_at ?? null,
    })),
  };
}

export function parseCohortSummary(input: unknown): CohortSummary {
  return normalizeCohortSummary(CohortSummarySchema.parse(input));
}

export function parseUpdateCohortRequest(input: unknown): UpdateCohortRequest {
  return UpdateCohortRequestSchema.parse(input);
}

export function parseRunAction(input: unknown): RunAction {
  return normalizeRunAction(RunActionSchema.parse(input));
}

export function parseRunSandbox(input: unknown): RunSandbox {
  return normalizeRunSandbox(RunSandboxSchema.parse(input));
}

export function parseRunSandboxCommand(input: unknown): RunSandboxCommand {
  return normalizeRunSandboxCommand(RunSandboxCommandSchema.parse(input));
}

export function parseRunCommunicationMessage(input: unknown): RunCommunicationMessage {
  return normalizeRunCommunicationMessage(RunCommunicationMessageSchema.parse(input));
}

export function parseRunCommunicationThread(input: unknown): RunCommunicationThread {
  return normalizeRunCommunicationThread(RunCommunicationThreadSchema.parse(input));
}

export function parseRunTaskEvaluation(input: unknown): RunTaskEvaluation {
  return normalizeRunTaskEvaluation(RunTaskEvaluationSchema.parse(input));
}

export function parseRunSnapshot(input: unknown): RunSnapshot {
  const snapshot = RunSnapshotSchema.parse(input);
  return {
    ...snapshot,
    actionsByTask: Object.fromEntries(
      Object.entries(snapshot.actionsByTask ?? {}).map(([taskId, actions]) => [
        taskId,
        actions.map(normalizeRunAction),
      ]),
    ),
    completedAt: snapshot.completedAt ?? null,
    durationSeconds: snapshot.durationSeconds ?? null,
    error: snapshot.error ?? null,
    evaluationsByTask: Object.fromEntries(
      Object.entries(snapshot.evaluationsByTask ?? {}).map(([taskId, evaluation]) => [
        taskId,
        normalizeRunTaskEvaluation(evaluation),
      ]),
    ),
    executionsByTask: Object.fromEntries(
      Object.entries(snapshot.executionsByTask ?? {}).map(([taskId, executions]) => [
        taskId,
        executions.map(normalizeRunExecutionAttempt),
      ]),
    ),
    finalScore: snapshot.finalScore ?? null,
    resourcesByTask: snapshot.resourcesByTask ?? {},
    sandboxesByTask: Object.fromEntries(
      Object.entries(snapshot.sandboxesByTask ?? {}).map(([taskId, sandbox]) => [
        taskId,
        normalizeRunSandbox(sandbox),
      ]),
    ),
    startedAt: snapshot.startedAt ?? new Date(0).toISOString(),
    tasks: Object.fromEntries(
      Object.entries(snapshot.tasks ?? {}).map(([taskId, task]) => [taskId, normalizeRunTask(task)]),
    ),
    threads: (snapshot.threads ?? []).map(normalizeRunCommunicationThread),
  };
}
