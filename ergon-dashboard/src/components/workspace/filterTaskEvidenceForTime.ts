import type {
  CommunicationThreadState,
  ContextEventState,
  ExecutionAttemptState,
  ResourceState,
  SandboxState,
  TaskEvaluationState,
} from "@/lib/types";

export interface TaskEvidence {
  resources: ResourceState[];
  executions: ExecutionAttemptState[];
  sandbox: SandboxState | undefined;
  threads: CommunicationThreadState[];
  evaluation: TaskEvaluationState | null;
  contextEvents: ContextEventState[];
}

export interface FilterTaskEvidenceForTimeInput extends TaskEvidence {
  selectedTime: string | null;
}

function atOrBefore(value: string | null | undefined, selectedMs: number): boolean {
  if (!value) return false;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) && parsed <= selectedMs;
}

export function filterTaskEvidenceForTime({
  resources,
  executions,
  sandbox,
  threads,
  evaluation,
  contextEvents,
  selectedTime,
}: FilterTaskEvidenceForTimeInput): TaskEvidence {
  if (!selectedTime) {
    return { resources, executions, sandbox, threads, evaluation, contextEvents };
  }

  const selectedMs = Date.parse(selectedTime);
  if (!Number.isFinite(selectedMs)) {
    return { resources, executions, sandbox, threads, evaluation, contextEvents };
  }

  const filteredSandbox = sandbox
    ? {
        ...sandbox,
        commands: sandbox.commands.filter((command) =>
          atOrBefore(command.timestamp, selectedMs),
        ),
      }
    : undefined;

  return {
    resources: resources.filter((resource) => atOrBefore(resource.createdAt, selectedMs)),
    executions: executions.filter((execution) =>
      atOrBefore(execution.startedAt, selectedMs),
    ),
    sandbox: filteredSandbox,
    threads: threads
      .map((thread) => ({
        ...thread,
        messages: (thread.messages ?? []).filter((message) =>
          atOrBefore(message.createdAt, selectedMs),
        ),
      }))
      .filter((thread) => atOrBefore(thread.createdAt, selectedMs) || (thread.messages ?? []).length > 0),
    evaluation:
      evaluation && atOrBefore(evaluation.createdAt, selectedMs) ? evaluation : null,
    contextEvents: contextEvents.filter((event) =>
      atOrBefore(event.createdAt, selectedMs),
    ),
  };
}
