import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import type {
  ContextEventState,
  ExecutionAttemptState,
  SandboxCommandState,
  SandboxState,
  WorkflowRunState,
} from "@/lib/types";
import type { RunEvent } from "@/lib/runEvents";
import type { ActivityKind, RunActivity } from "./types";

export interface BuildRunActivitiesInput {
  runState: WorkflowRunState | null;
  events: RunEvent[];
  mutations: GraphMutationDto[];
  currentSequence: number | null;
}

function isFiniteTime(value: string | null | undefined): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

function compareActivity(a: RunActivity, b: RunActivity): number {
  if (a.startAt !== b.startAt) return a.startAt.localeCompare(b.startAt);
  const aSeq = a.sequence ?? -1;
  const bSeq = b.sequence ?? -1;
  if (aSeq !== bSeq) return aSeq - bSeq;
  return a.id.localeCompare(b.id);
}

function capEndAt(endAt: string | null, selectedTime: string | null): string | null {
  if (!selectedTime || !endAt) return endAt;
  return Date.parse(endAt) > Date.parse(selectedTime) ? selectedTime : endAt;
}

function executionLabel(execution: ExecutionAttemptState, run: WorkflowRunState): string {
  const task = run.tasks.get(execution.taskId);
  return task?.name ?? `Attempt ${execution.attemptNumber}`;
}

function executionActivities(
  run: WorkflowRunState,
  selectedTime: string | null,
): RunActivity[] {
  const activities: RunActivity[] = [];
  for (const executions of run.executionsByTask.values()) {
    for (const execution of executions) {
      if (!isFiniteTime(execution.startedAt)) continue;
      const endAt = capEndAt(execution.completedAt, selectedTime) ?? selectedTime;
      activities.push({
        id: `execution:${execution.id}`,
        kind: "execution",
        label: executionLabel(execution, run),
        taskId: execution.taskId,
        sequence: null,
        startAt: execution.startedAt,
        endAt,
        isInstant: !endAt || endAt === execution.startedAt,
        actor: execution.agentName,
        sourceKind: "execution.span",
        metadata: {
          attemptNumber: execution.attemptNumber,
          status: execution.status,
          agentId: execution.agentId,
        },
      });
    }
  }
  return activities;
}

function sandboxActivities(
  run: WorkflowRunState,
  selectedTime: string | null,
): RunActivity[] {
  const activities: RunActivity[] = [];
  for (const sandbox of run.sandboxesByTask.values()) {
    activities.push(sandboxSpanActivity(sandbox, selectedTime));
    for (let i = 0; i < sandbox.commands.length; i++) {
      activities.push(commandActivity(sandbox, sandbox.commands[i], i));
    }
  }
  return activities;
}

function sandboxSpanActivity(sandbox: SandboxState, selectedTime: string | null): RunActivity {
  const endAt = capEndAt(sandbox.closedAt, selectedTime) ?? selectedTime;
  return {
    id: `sandbox:${sandbox.sandboxId}`,
    kind: "sandbox",
    label: sandbox.template ?? sandbox.sandboxId,
    taskId: sandbox.taskId,
    sequence: null,
    startAt: sandbox.createdAt,
    endAt,
    isInstant: !endAt || endAt === sandbox.createdAt,
    actor: null,
    sourceKind: "sandbox.span",
    metadata: {
      sandboxId: sandbox.sandboxId,
      status: sandbox.status,
      closeReason: sandbox.closeReason,
    },
  };
}

function commandActivity(
  sandbox: SandboxState,
  command: SandboxCommandState,
  index: number,
): RunActivity {
  const startMs = Date.parse(command.timestamp);
  const endAt =
    command.durationMs != null && Number.isFinite(startMs)
      ? new Date(startMs + command.durationMs).toISOString()
      : null;
  return {
    id: `sandbox.command:${sandbox.sandboxId}:${index}`,
    kind: "sandbox",
    label: command.command,
    taskId: sandbox.taskId,
    sequence: null,
    startAt: command.timestamp,
    endAt,
    isInstant: !endAt,
    actor: null,
    sourceKind: "sandbox.command",
    metadata: {
      exitCode: command.exitCode,
      durationMs: command.durationMs,
    },
  };
}

function contextActivities(run: WorkflowRunState): RunActivity[] {
  const activities: RunActivity[] = [];
  for (const [taskId, contextEvents] of run.contextEventsByTask.entries()) {
    for (const event of contextEvents) {
      activities.push(contextActivity(taskId, event));
    }
  }
  return activities;
}

function contextActivity(taskId: string, event: ContextEventState): RunActivity {
  const label =
    typeof event.payload === "object" &&
    event.payload &&
    "tool_name" in event.payload
      ? String((event.payload as { tool_name?: unknown }).tool_name)
      : event.eventType;
  return {
    id: `context:${event.id}`,
    kind: "context",
    label,
    taskId,
    sequence: event.sequence,
    startAt: event.startedAt ?? event.createdAt,
    endAt: event.completedAt,
    isInstant: !event.startedAt || !event.completedAt,
    actor: event.workerBindingKey,
    sourceKind: "context.event",
    metadata: {
      eventType: event.eventType,
      taskExecutionId: event.taskExecutionId,
    },
  };
}

function eventKindToActivityKind(event: RunEvent): ActivityKind | null {
  switch (event.kind) {
    case "thread.message":
      return "message";
    case "task.evaluation":
      return "evaluation";
    case "resource.published":
      return "artifact";
    case "workflow.started":
    case "workflow.completed":
    case "task.transition":
    case "unhandled.mutation":
      return "graph";
    case "sandbox.created":
    case "sandbox.command":
    case "sandbox.closed":
    case "context.event":
      return null;
  }
}

function eventLabel(event: RunEvent): string {
  switch (event.kind) {
    case "thread.message":
      return event.preview;
    case "task.evaluation":
      return "Evaluation";
    case "resource.published":
      return event.name;
    case "workflow.started":
      return "Workflow started";
    case "workflow.completed":
      return `Workflow ${event.status}`;
    case "task.transition":
      return `${event.taskName}: ${event.to}`;
    case "unhandled.mutation":
      return event.mutationType;
    default:
      return event.kind;
  }
}

function eventMarkerActivities(events: RunEvent[]): RunActivity[] {
  return events.flatMap((event) => {
    const kind = eventKindToActivityKind(event);
    if (!kind) return [];
    return [
      {
        id: `event:${event.id}`,
        kind,
        label: eventLabel(event),
        taskId: event.taskId ?? null,
        sequence: event.sequence ?? null,
        startAt: event.at,
        endAt: null,
        isInstant: true,
        actor: "actor" in event && typeof event.actor === "string" ? event.actor : null,
        sourceKind: event.kind,
        metadata: { eventKind: event.kind },
      },
    ];
  });
}

function graphMutationActivities(mutations: GraphMutationDto[]): RunActivity[] {
  return mutations.map((mutation) => ({
    id: `graph:${mutation.id}`,
    kind: "graph",
    label: mutation.mutation_type,
    taskId: mutation.target_type === "node" ? mutation.target_id : null,
    sequence: mutation.sequence,
    startAt: mutation.created_at,
    endAt: null,
    isInstant: true,
    actor: mutation.actor,
    sourceKind: "graph.mutation",
    metadata: {
      mutationType: mutation.mutation_type,
      targetType: mutation.target_type,
      reason: mutation.reason,
    },
  }));
}

export function buildRunActivities(input: BuildRunActivitiesInput): RunActivity[] {
  if (!input.runState) return [];
  const selectedMutation =
    input.currentSequence == null
      ? null
      : input.mutations.find((mutation) => mutation.sequence === input.currentSequence);
  const selectedTime = selectedMutation?.created_at ?? null;
  return [
    ...executionActivities(input.runState, selectedTime),
    ...sandboxActivities(input.runState, selectedTime),
    ...contextActivities(input.runState),
    ...eventMarkerActivities(input.events),
    ...graphMutationActivities(input.mutations),
  ].sort(compareActivity);
}
