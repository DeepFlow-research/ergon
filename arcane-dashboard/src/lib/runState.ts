import type { RunSnapshot } from "@/lib/contracts/rest";
import { parseRunSnapshot } from "@/lib/contracts/rest";
import type {
  ActionState,
  ExecutionAttemptState,
  ResourceState,
  SandboxState,
  SerializedWorkflowRunState,
  TaskState,
  TaskStatus,
  TaskEvaluationState,
  WorkflowRunState,
} from "@/lib/types";

function toTaskStatus(status: string): TaskStatus {
  return status as TaskStatus;
}

function deserializeTask(task: RunSnapshot["tasks"][string]): TaskState {
  return {
    ...task,
    status: toTaskStatus(task.status),
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

function deserializeAction(action: RunSnapshot["actionsByTask"][string][number]): ActionState {
  return {
    ...action,
    status: action.status as ActionState["status"],
    startedAt: action.startedAt ?? new Date(0).toISOString(),
    completedAt: action.completedAt ?? null,
    durationMs: action.durationMs ?? null,
    error: action.error ?? null,
    output: action.output ?? null,
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

export function deserializeRunState(input: unknown): WorkflowRunState {
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
    actionsByTask: new Map(
      Object.entries(data.actionsByTask ?? {}).map(([taskId, actions]) => [
        taskId,
        actions.map(deserializeAction),
      ]),
    ),
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
    finalScore: data.finalScore ?? null,
    error: data.error ?? null,
  };
}

export function serializeRunState(run: WorkflowRunState): SerializedWorkflowRunState {
  return {
    ...run,
    tasks: Object.fromEntries(run.tasks.entries()),
    actionsByTask: Object.fromEntries(run.actionsByTask.entries()),
    resourcesByTask: Object.fromEntries(run.resourcesByTask.entries()),
    executionsByTask: Object.fromEntries(run.executionsByTask.entries()),
    sandboxesByTask: Object.fromEntries(run.sandboxesByTask.entries()),
    evaluationsByTask: Object.fromEntries(run.evaluationsByTask.entries()),
  };
}
