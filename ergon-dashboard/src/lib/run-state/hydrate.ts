import type { RunSnapshot } from "@/lib/contracts/rest";
import { parseRunSnapshot } from "@/lib/contracts/rest";
import type {
  ContextEventState,
  ExecutionAttemptState,
  ResourceState,
  SandboxState,
  TaskEvaluationState,
  TaskState,
  TaskStatus,
  WorkflowRunState,
} from "@/lib/types";

import { compareContextEvents, contextPartToUiPayload } from "./contextEvents";

function toTaskStatus(status: string): TaskStatus {
  return status as TaskStatus;
}

function deserializeTask(task: RunSnapshot["tasks"][string]): TaskState {
  return {
    ...task,
    assignedWorkerSlug: task.assignedWorkerSlug ?? null,
    status: toTaskStatus(task.status),
    history: [],
    lastTrigger: null,
  };
}

function deserializeExecution(
  execution: RunSnapshot["executionsByTask"][string][number],
): ExecutionAttemptState {
  return {
    ...execution,
    evaluationDetails: execution.evaluationDetails ?? {},
    status: toTaskStatus(execution.status),
  };
}

function deserializeResource(resource: RunSnapshot["resourcesByTask"][string][number]): ResourceState {
  return resource;
}

function deserializeSandbox(sandbox: RunSnapshot["sandboxesByTask"][string]): SandboxState {
  return {
    ...sandbox,
    status: sandbox.status as SandboxState["status"],
    closeReason: sandbox.closeReason ?? null,
    closedAt: sandbox.closedAt ?? null,
    template: sandbox.template ?? null,
    commands: (sandbox.commands ?? []).map((command) => ({
      command: command.command,
      stdout: command.stdout ?? null,
      stderr: command.stderr ?? null,
      exitCode: command.exitCode ?? null,
      durationMs: command.durationMs ?? null,
      timestamp: command.timestamp,
    })),
  };
}

function deserializeEvaluation(evaluation: RunSnapshot["evaluationsByTask"][string]): TaskEvaluationState {
  return {
    ...evaluation,
    taskId: evaluation.taskId ?? null,
    failedGate: evaluation.failedGate ?? null,
    criterionResults: evaluation.criterionResults ?? [],
  };
}

function deserializeContextEvents(data: RunSnapshot): Map<string, ContextEventState[]> {
  const byTask = (data as unknown as Record<string, unknown>).contextEventsByTask as
    | Record<string, Array<Record<string, unknown>>>
    | undefined;
  if (!byTask) return new Map();

  return new Map(
    Object.entries(byTask).map(([taskId, events]) => [
      taskId,
      events
        .map((event) => ({
          id: String(event.id ?? ""),
          runId: String(event.runId ?? data.id),
          taskExecutionId: String(event.taskExecutionId ?? ""),
          taskId: String(event.taskId ?? taskId),
          workerBindingKey: String(event.workerBindingKey ?? ""),
          sequence: Number(event.sequence ?? 0),
          eventType: String(event.eventType ?? "") as ContextEventState["eventType"],
          payload: contextPartToUiPayload(event.payload),
          createdAt: String(event.createdAt ?? ""),
          startedAt: (event.startedAt as string | null | undefined) ?? null,
          completedAt: (event.completedAt as string | null | undefined) ?? null,
        }))
        .sort(compareContextEvents),
    ]),
  );
}

export function hydrateRunSnapshot(input: unknown): WorkflowRunState {
  const data = parseRunSnapshot(input);

  return {
    id: data.id,
    experimentId: data.experimentId,
    name: data.name,
    status: data.status as WorkflowRunState["status"],
    tasks: new Map(
      Object.entries(data.tasks ?? {}).map(([taskId, task]) => [taskId, deserializeTask(task)]),
    ),
    rootTaskId: data.rootTaskId,
    resourcesByTask: new Map(
      Object.entries(data.resourcesByTask ?? {}).map(([taskId, resources]) => [
        taskId,
        resources.map(deserializeResource),
      ]),
    ),
    executionsByTask: new Map(
      Object.entries(data.executionsByTask ?? {}).map(([taskId, executions]) => [
        taskId,
        executions.map(deserializeExecution),
      ]),
    ),
    sandboxesByTask: new Map(
      Object.entries(data.sandboxesByTask ?? {}).map(([taskId, sandbox]) => [
        taskId,
        deserializeSandbox(sandbox),
      ]),
    ),
    threads: data.threads ?? [],
    contextEventsByTask: deserializeContextEvents(data),
    evaluationsByTask: new Map(
      Object.entries(data.evaluationsByTask ?? {}).map(([taskId, evaluation]) => [
        taskId,
        deserializeEvaluation(evaluation),
      ]),
    ),
    startedAt: data.startedAt ?? new Date(0).toISOString(),
    completedAt: data.completedAt ?? null,
    durationSeconds: data.durationSeconds ?? null,
    totalTasks: data.totalTasks,
    totalLeafTasks: data.totalLeafTasks,
    completedTasks: data.completedTasks,
    runningTasks: data.runningTasks,
    failedTasks: data.failedTasks,
    cancelledTasks: data.cancelledTasks,
    finalScore: data.finalScore ?? null,
    error: data.error ?? null,
    edges: new Map(),
    annotationsByTarget: new Map(),
    unhandledMutations: [],
  };
}

export const deserializeRunState = hydrateRunSnapshot;
