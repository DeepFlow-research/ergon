import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import type {
  ContextEventState,
  ExecutionAttemptState,
  SandboxCommandState,
  WorkflowRunState,
} from "@/lib/types";
import type { RunEvent } from "@/lib/runEvents";
import type { RunActivity } from "./types";

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

function executionLabel(execution: ExecutionAttemptState, run: WorkflowRunState): string {
  const task = run.tasks.get(execution.taskId);
  return task?.name ?? `Attempt ${execution.attemptNumber}`;
}

function truncate(value: string, length = 64): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function addMs(timestamp: string, durationMs: number | null): string | null {
  if (durationMs === null || durationMs <= 0) return null;
  const startMs = Date.parse(timestamp);
  if (!Number.isFinite(startMs)) return null;
  return new Date(startMs + durationMs).toISOString();
}

function executionActivities(
  run: WorkflowRunState,
): RunActivity[] {
  const activities: RunActivity[] = [];
  for (const executions of run.executionsByTask.values()) {
    for (const execution of executions) {
      if (!isFiniteTime(execution.startedAt)) continue;
      const endAt = execution.completedAt;
      activities.push({
        id: `execution:${execution.id}`,
        kind: "execution",
        band: "work",
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
          openEnded: endAt === null,
        },
        lineage: {
          taskId: execution.taskId,
          taskExecutionId: execution.id,
          agentId: execution.agentId,
        },
        debug: {
          source: "execution.span",
          payload: execution,
        },
      });
    }
  }
  return activities;
}

function sandboxCommandLabel(command: SandboxCommandState): string {
  return `cmd: ${truncate(command.command)}`;
}

function sandboxActivities(
  run: WorkflowRunState,
): RunActivity[] {
  const activities: RunActivity[] = [];
  for (const sandbox of run.sandboxesByTask.values()) {
    if (isFiniteTime(sandbox.createdAt)) {
      const endAt = sandbox.closedAt;
      activities.push({
        id: `sandbox:${sandbox.sandboxId}`,
        kind: "sandbox",
        band: "work",
        label: `sandbox: ${sandbox.template ?? sandbox.sandboxId}`,
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
          openEnded: endAt === null,
        },
        lineage: {
          taskId: sandbox.taskId,
          sandboxId: sandbox.sandboxId,
        },
        debug: {
          source: "sandbox.span",
          payload: {
            ...sandbox,
            commands: undefined,
          },
        },
      });
    }

    for (let i = 0; i < sandbox.commands.length; i++) {
      const command = sandbox.commands[i];
      if (!isFiniteTime(command.timestamp)) continue;
      const endAt = addMs(command.timestamp, command.durationMs);
      activities.push({
        id: `sandbox.command:${sandbox.sandboxId}:${i}`,
        kind: "sandbox",
        band: "tools",
        label: sandboxCommandLabel(command),
        taskId: sandbox.taskId,
        sequence: null,
        startAt: command.timestamp,
        endAt,
        isInstant: !endAt || endAt === command.timestamp,
        actor: null,
        sourceKind: "sandbox.command",
        metadata: {
          sandboxId: sandbox.sandboxId,
          exitCode: command.exitCode,
          durationMs: command.durationMs,
        },
        lineage: {
          taskId: sandbox.taskId,
          sandboxId: sandbox.sandboxId,
        },
        debug: {
          source: "sandbox.command",
          payload: command,
        },
      });
    }
  }
  return activities;
}

function contextLabel(event: ContextEventState): string {
  const payloadType =
    typeof event.payload === "object" &&
    event.payload !== null &&
    "event_type" in event.payload
      ? String((event.payload as { event_type?: unknown }).event_type)
      : null;
  return payloadType ?? event.eventType;
}

function contextActivities(run: WorkflowRunState): RunActivity[] {
  const activities: RunActivity[] = [];
  for (const [taskId, events] of run.contextEventsByTask.entries()) {
    for (const event of events) {
      const startAt = event.startedAt ?? event.createdAt;
      if (!isFiniteTime(startAt)) continue;
      const endAt = event.completedAt;
      activities.push({
        id: `context:${event.id}`,
        kind: "context",
        band: "tools",
        label: contextLabel(event),
        taskId,
        sequence: null,
        startAt,
        endAt,
        isInstant: !endAt || endAt === startAt,
        actor: event.workerBindingKey ?? null,
        sourceKind: endAt ? "context.span" : "context.event",
        metadata: {
          eventId: event.id,
          eventType: event.eventType,
          contextSequence: event.sequence ?? null,
          taskExecutionId: event.taskExecutionId,
        },
        lineage: {
          taskId,
          taskExecutionId: event.taskExecutionId,
          workerBindingKey: event.workerBindingKey,
        },
        debug: {
          source: "context.event",
          payload: event,
        },
      });
    }
  }
  return activities;
}

function eventMarkerActivities(events: RunEvent[]): RunActivity[] {
  return events.flatMap((event): RunActivity[] => {
    switch (event.kind) {
      case "thread.message":
        return [
          {
            id: `message:${event.id}`,
            kind: "message",
            band: "communication",
            label: truncate(event.preview),
            taskId: event.taskId ?? null,
            sequence: event.sequence ?? null,
            startAt: event.at,
            endAt: null,
            isInstant: true,
            actor: event.authorRole,
            sourceKind: event.kind,
            metadata: {
              threadId: event.threadId,
            },
            lineage: {
              taskId: event.taskId ?? null,
              threadId: event.threadId,
            },
            debug: {
              source: event.kind,
              payload: event,
            },
          },
        ];
      case "resource.published":
        return [
          {
            id: `artifact:${event.id}`,
            kind: "artifact",
            band: "outputs",
            label: `artifact: ${event.name}`,
            taskId: event.taskId ?? null,
            sequence: event.sequence ?? null,
            startAt: event.at,
            endAt: null,
            isInstant: true,
            actor: null,
            sourceKind: event.kind,
            metadata: {
              mimeType: event.mimeType,
              sizeBytes: event.sizeBytes,
            },
            lineage: {
              taskId: event.taskId ?? null,
            },
            debug: {
              source: event.kind,
              payload: event,
            },
          },
        ];
      case "task.evaluation":
        return [
          {
            id: `evaluation:${event.id}`,
            kind: "evaluation",
            band: "outputs",
            label: `Evaluation ${event.passed === null ? "updated" : event.passed ? "passed" : "failed"}`,
            taskId: event.taskId ?? null,
            sequence: event.sequence ?? null,
            startAt: event.at,
            endAt: null,
            isInstant: true,
            actor: null,
            sourceKind: event.kind,
            metadata: {
              score: event.score,
              passed: event.passed,
            },
            lineage: {
              taskId: event.taskId ?? null,
            },
            debug: {
              source: event.kind,
              payload: event,
            },
          },
        ];
      default:
        return [];
    }
  });
}

function graphMutationActivities(mutations: GraphMutationDto[]): RunActivity[] {
  return mutations.map((mutation) => ({
    id: `graph:${mutation.id}`,
    kind: "graph",
    band: "graph",
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
    lineage: {
      taskId: mutation.target_type === "node" ? mutation.target_id : null,
    },
    debug: {
      source: "graph.mutation",
      payload: mutation,
    },
  }));
}

export function buildRunActivities(input: BuildRunActivitiesInput): RunActivity[] {
  if (!input.runState) return [];
  return [
    ...executionActivities(input.runState),
    ...sandboxActivities(input.runState),
    ...contextActivities(input.runState),
    ...eventMarkerActivities(input.events),
    ...graphMutationActivities(input.mutations),
  ].sort(compareActivity);
}
