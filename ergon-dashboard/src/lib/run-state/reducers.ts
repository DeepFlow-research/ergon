import { inferTrigger } from "@/lib/runEvents";
import {
  type SandboxCommandState,
  type SandboxState,
  TaskStatus,
  type ExecutionAttemptState,
  type TaskState,
  type TaskTransitionRecord,
  type WorkflowRunState,
} from "@/lib/types";

import { recalculateTaskMetrics } from "./metrics";

export interface TaskStatusChanged {
  runId: string;
  taskId: string;
  status: TaskStatus;
  timestamp: string;
  assignedWorkerId?: string | null;
  assignedWorkerSlug?: string | null;
}

function nextExecutionStatus(status: TaskStatus): TaskStatus {
  return status === TaskStatus.READY ? TaskStatus.PENDING : status;
}

function isTerminalStatus(status: TaskStatus): boolean {
  return (
    status === TaskStatus.COMPLETED ||
    status === TaskStatus.FAILED ||
    status === TaskStatus.CANCELLED
  );
}

function updateExecutionsForStatus(
  run: WorkflowRunState,
  task: TaskState,
  event: TaskStatusChanged,
): ExecutionAttemptState[] {
  const executions = run.executionsByTask.get(event.taskId) ?? [];
  const latestExecution = executions[executions.length - 1];

  if (event.status === TaskStatus.RUNNING) {
    if (
      !latestExecution ||
      latestExecution.status === TaskStatus.COMPLETED ||
      latestExecution.status === TaskStatus.FAILED
    ) {
      return [
        ...executions,
        {
          id: `${event.taskId}:attempt:${executions.length + 1}`,
          taskId: event.taskId,
          attemptNumber: executions.length + 1,
          status: TaskStatus.RUNNING,
          agentId: event.assignedWorkerId ?? task.assignedWorkerId,
          agentName: event.assignedWorkerSlug ?? task.assignedWorkerSlug,
          startedAt: event.timestamp,
          completedAt: null,
          finalAssistantMessage: null,
          outputResourceIds: [],
          errorMessage: null,
          score: null,
          evaluationDetails: {},
        },
      ];
    }

    return executions.map((execution, index) =>
      index === executions.length - 1
        ? {
            ...execution,
            status: TaskStatus.RUNNING,
            startedAt: execution.startedAt ?? event.timestamp,
            agentId: event.assignedWorkerId ?? execution.agentId,
            agentName: event.assignedWorkerSlug ?? execution.agentName,
          }
        : execution,
    );
  }

  if (!latestExecution) {
    return executions;
  }

  return executions.map((execution, index) =>
    index === executions.length - 1
      ? {
          ...execution,
          status: nextExecutionStatus(event.status),
          completedAt: isTerminalStatus(event.status) ? event.timestamp : execution.completedAt,
          errorMessage:
            event.status === TaskStatus.FAILED
              ? execution.errorMessage ?? "Task execution failed"
              : execution.errorMessage,
        }
      : execution,
  );
}

function updateTaskForStatus(task: TaskState, event: TaskStatusChanged): TaskState {
  const fromStatus = task.status;
  const nextTask: TaskState = {
    ...task,
    status: event.status,
    assignedWorkerId:
      event.assignedWorkerId !== undefined ? event.assignedWorkerId : task.assignedWorkerId,
    assignedWorkerSlug:
      event.assignedWorkerSlug !== undefined ? event.assignedWorkerSlug : task.assignedWorkerSlug,
    startedAt:
      event.status === TaskStatus.RUNNING && !task.startedAt ? event.timestamp : task.startedAt,
    completedAt: isTerminalStatus(event.status) ? event.timestamp : task.completedAt,
  };

  if (fromStatus === event.status) {
    return nextTask;
  }

  const trigger = inferTrigger(fromStatus, event.status);
  const record: TaskTransitionRecord = {
    from: fromStatus,
    to: event.status,
    trigger,
    at: event.timestamp,
    sequence: null,
    actor: event.assignedWorkerSlug ?? task.assignedWorkerSlug ?? null,
    reason: null,
  };

  return {
    ...nextTask,
    history: [...(task.history ?? []), record],
    lastTrigger: trigger,
  };
}

export function applyTaskStatusChanged(
  run: WorkflowRunState,
  event: TaskStatusChanged,
): WorkflowRunState {
  if (event.runId !== run.id) return run;

  const task = run.tasks.get(event.taskId);
  if (!task) return run;

  const tasks = new Map(run.tasks);
  tasks.set(event.taskId, updateTaskForStatus(task, event));

  const executionsByTask = new Map(run.executionsByTask);
  executionsByTask.set(event.taskId, updateExecutionsForStatus(run, task, event));

  return {
    ...run,
    tasks,
    executionsByTask,
    ...recalculateTaskMetrics(tasks),
  };
}

export function applySandboxCreated(
  run: WorkflowRunState,
  sandbox: SandboxState,
  pendingCommands: SandboxCommandState[] = [],
): WorkflowRunState {
  const sandboxesByTask = new Map(run.sandboxesByTask);
  const seenCommands = new Set<string>();
  const commands = [...pendingCommands, ...sandbox.commands].filter((command) => {
    const key = JSON.stringify(command);
    if (seenCommands.has(key)) return false;
    seenCommands.add(key);
    return true;
  });
  sandboxesByTask.set(sandbox.taskId, {
    ...sandbox,
    commands,
  });
  return { ...run, sandboxesByTask };
}

export function applySandboxCommand(
  run: WorkflowRunState,
  taskId: string,
  command: SandboxCommandState,
): WorkflowRunState {
  const sandbox = run.sandboxesByTask.get(taskId);
  if (!sandbox) return run;

  const sandboxesByTask = new Map(run.sandboxesByTask);
  sandboxesByTask.set(taskId, {
    ...sandbox,
    commands: [...sandbox.commands, command],
  });
  return { ...run, sandboxesByTask };
}

export function applySandboxClosed(
  run: WorkflowRunState,
  taskId: string,
  reason: string,
  timestamp: string,
): WorkflowRunState {
  const sandbox = run.sandboxesByTask.get(taskId);
  if (!sandbox) return run;

  const sandboxesByTask = new Map(run.sandboxesByTask);
  sandboxesByTask.set(taskId, {
    ...sandbox,
    status: "closed",
    closedAt: timestamp,
    closeReason: reason,
  });
  return { ...run, sandboxesByTask };
}
