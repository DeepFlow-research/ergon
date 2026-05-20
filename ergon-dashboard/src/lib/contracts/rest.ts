import { z } from "zod";

import { schemas } from "@/generated/rest/contracts";

export const BenchmarkNameSchema = z.string();
export const RunStatusSchema = z.enum(["pending", "executing", "evaluating", "completed", "failed", "cancelled"]);
export const TaskStatusSchema = z.string();

export const ExperimentDetailSchema = schemas.ExperimentDetailDto;

export const RunExecutionAttemptSchema = schemas.RunExecutionAttemptDto;
export const RunResourceSchema = schemas.RunResourceDto;
export const RunSandboxCommandSchema = schemas.RunSandboxCommandDto;
export const RunSandboxSchema = schemas.RunSandboxDto;
export const RunTaskSchema = schemas.RunTaskDto;
export const RunCommunicationMessageSchema = schemas.RunCommunicationMessageDto;
export const RunCommunicationThreadSchema = schemas.RunCommunicationThreadDto;
export const RunTaskEvaluationSchema = schemas.RunTaskEvaluationDto;
export const RunSnapshotSchema = schemas.RunSnapshotDto;

type KnownKeys<T> = {
  [K in keyof T as string extends K ? never : number extends K ? never : symbol extends K
    ? never
    : K]: T[K];
};

export type BenchmarkName = z.infer<typeof BenchmarkNameSchema>;
export type RunLifecycleStatus = z.infer<typeof RunStatusSchema>;
export type TaskStatusValue = z.infer<typeof TaskStatusSchema>;

type RawExperimentDetail = KnownKeys<z.infer<typeof ExperimentDetailSchema>>;
type RawExperimentRunRow = KnownKeys<NonNullable<RawExperimentDetail["runs"]>[number]>;
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

export type RawRunSandboxType = RawRunSandbox;
export type RawRunSandboxCommandType = RawRunSandboxCommand;

export interface ExperimentStatusCounts {
  pending: number;
  executing: number;
  evaluating: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface ExperimentRunRow
  extends Omit<
    RawExperimentRunRow,
    | "completed_at"
    | "error_message"
    | "evaluator_slug"
    | "final_score"
    | "model_target"
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
  running_time_ms: number | null;
  seed: number | null;
  started_at: string | null;
  total_cost_usd: number | null;
  total_tasks: number | null;
  worker_team: Record<string, unknown>;
}

export interface ExperimentDetail extends Omit<RawExperimentDetail, "runs" | "analytics"> {
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

export interface RunExecutionAttempt
  extends Omit<
    RawRunExecutionAttempt,
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

/**
 * Per-task row in {@link RunSnapshot.tasks} (camelCase on the wire).
 *
 * Semantics mirror the backend `RunTaskDto` field descriptions:
 * - `startedAt`: null only while the task has not actually started yet (e.g. pending / ready).
 * - `completedAt`: null until a terminal outcome; may be null together with `startedAt` if not started.
 */
export interface RunTask
  extends Omit<
    RawRunTask,
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
  evaluationsByTask: Record<string, RunTaskEvaluation>;
  executionsByTask: Record<string, RunExecutionAttempt[]>;
  finalScore: number | null;
  resourcesByTask: Record<string, RunResource[]>;
  sandboxesByTask: Record<string, RunSandbox>;
  startedAt: string;
  tasks: Record<string, RunTask>;
  threads: RunCommunicationThread[];
}

function normalizeRunExecutionAttempt(execution: RawRunExecutionAttempt): RunExecutionAttempt {
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
    assignedWorkerSlug: task.assignedWorkerSlug ?? null,
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
    summary: thread.summary ?? null,
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

export function parseExperimentDetail(input: unknown): ExperimentDetail {
  const detail = ExperimentDetailSchema.parse(input);
  return {
    ...detail,
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
    runs: (detail.runs ?? []).map((run) => ({
      ...run,
      completed_at: run.completed_at ?? null,
      error_message: run.error_message ?? null,
      evaluator_slug: run.evaluator_slug ?? null,
      final_score: run.final_score ?? null,
      model_target: run.model_target ?? null,
      running_time_ms: run.running_time_ms ?? null,
      seed: run.seed ?? null,
      started_at: run.started_at ?? null,
      total_cost_usd: run.total_cost_usd ?? null,
      total_tasks: run.total_tasks ?? null,
      worker_team: run.worker_team ?? {},
    })),
  };
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
