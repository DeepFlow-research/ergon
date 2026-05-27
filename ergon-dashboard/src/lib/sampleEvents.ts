/**
 * Unified run-event log.
 *
 * Multiple Inngest / Socket.io streams (`task.status_changed`, `sandbox.command`,
 * `thread.message_created`, `task.evaluation_updated`, `resource.published`,
 * `graph.mutation`, `context.event`, workflow lifecycle)
 * collectively describe what happened during a run, but each one is rendered in a
 * different panel. The `SampleEvent` union gives us one chronologically sortable
 * shape that the UnifiedEventStream and the SampleTimeline can both consume.
 *
 * Construction is **derived** on the client from the `SampleWorkspaceState` we already
 * assemble — no new backend contract is introduced.
 */

import type {
  ResourceState,
  SandboxCommandState,
  SandboxState,
  TaskState,
  TaskStatus,
  TaskTransitionRecord,
  TaskTrigger,
  UnhandledMutationRecord,
  SampleWorkspaceState,
  ContextEventState,
  TaskEvaluationState,
  CommunicationThreadState,
  CommunicationMessageState,
} from "@/lib/types";

export type SampleEventKind =
  | "workflow.started"
  | "workflow.completed"
  | "task.transition"
  | "sandbox.created"
  | "sandbox.command"
  | "sandbox.closed"
  | "thread.message"
  | "task.evaluation"
  | "resource.published"
  | "context.event"
  | "unhandled.mutation";

export const SAMPLE_EVENT_KINDS: readonly SampleEventKind[] = [
  "workflow.started",
  "workflow.completed",
  "task.transition",
  "sandbox.created",
  "sandbox.command",
  "sandbox.closed",
  "thread.message",
  "task.evaluation",
  "resource.published",
  "context.event",
  "unhandled.mutation",
] as const;

export interface SampleEventBase {
  id: string;
  at: string;
  kind: SampleEventKind;
  /** Related task id when applicable — powers the "jump to node" affordance. */
  taskId?: string | null;
  /** Related graph-mutation sequence when applicable — powers timeline jump. */
  sequence?: number | null;
}

export interface WorkflowStartedEvent extends SampleEventBase {
  kind: "workflow.started";
  sampleName: string;
}

export interface WorkflowCompletedEvent extends SampleEventBase {
  kind: "workflow.completed";
  status: string;
  finalScore: number | null;
  error: string | null;
}

export interface TaskTransitionEvent extends SampleEventBase {
  kind: "task.transition";
  taskId: string;
  taskName: string;
  from: TaskStatus | null;
  to: TaskStatus;
  trigger: TaskTrigger | "unknown";
  reason: string | null;
  actor: string | null;
}

export interface SandboxCreatedEvent extends SampleEventBase {
  kind: "sandbox.created";
  sandboxId: string;
  template: string | null;
}

export interface SandboxCommandEvent extends SampleEventBase {
  kind: "sandbox.command";
  command: string;
  exitCode: number | null;
  durationMs: number | null;
}

export interface SandboxClosedEvent extends SampleEventBase {
  kind: "sandbox.closed";
  sandboxId: string;
  closeReason: string | null;
}

export interface ThreadMessageEvent extends SampleEventBase {
  kind: "thread.message";
  threadId: string;
  authorRole: string;
  preview: string;
}

export interface TaskEvaluationEvent extends SampleEventBase {
  kind: "task.evaluation";
  score: number | null;
  passed: boolean | null;
}

export interface ResourcePublishedEvent extends SampleEventBase {
  kind: "resource.published";
  name: string;
  mimeType: string;
  sizeBytes: number;
}

export interface ContextEvent extends SampleEventBase {
  kind: "context.event";
  eventId: string;
  summary: string;
}

export interface UnhandledMutationEvent extends SampleEventBase {
  kind: "unhandled.mutation";
  mutationType: string;
  note: string;
}

export type SampleEvent =
  | WorkflowStartedEvent
  | WorkflowCompletedEvent
  | TaskTransitionEvent
  | SandboxCreatedEvent
  | SandboxCommandEvent
  | SandboxClosedEvent
  | ThreadMessageEvent
  | TaskEvaluationEvent
  | ResourcePublishedEvent
  | ContextEvent
  | UnhandledMutationEvent;

/**
 * Human-readable label for an event kind (used in filter UI + row prefixes).
 */
export const SAMPLE_EVENT_KIND_LABELS: Record<SampleEventKind, string> = {
  "workflow.started": "Workflow started",
  "workflow.completed": "Workflow completed",
  "task.transition": "Task transition",
  "sandbox.created": "Sandbox created",
  "sandbox.command": "Sandbox command",
  "sandbox.closed": "Sandbox closed",
  "thread.message": "Thread message",
  "task.evaluation": "Evaluation",
  "resource.published": "Resource",
  "context.event": "Context event",
  "unhandled.mutation": "Unhandled mutation",
};

/**
 * Tailwind color token per event kind — used for the lane indicator in the
 * timeline, the left border of a row in the stream, and the filter chip.
 */
export const SAMPLE_EVENT_KIND_COLORS: Record<SampleEventKind, string> = {
  "workflow.started": "bg-sky-500",
  "workflow.completed": "bg-emerald-500",
  "task.transition": "bg-indigo-500",
  "sandbox.created": "bg-cyan-500",
  "sandbox.command": "bg-cyan-400",
  "sandbox.closed": "bg-slate-500",
  "thread.message": "bg-amber-500",
  "task.evaluation": "bg-pink-500",
  "resource.published": "bg-lime-500",
  "context.event": "bg-zinc-400",
  "unhandled.mutation": "bg-rose-600",
};

/**
 * Infer a plausible `TaskTrigger` for a (from → to) status transition when the
 * backend did not send one. The mapping mirrors the server's state machine.
 */
export function inferTrigger(
  from: TaskStatus | null,
  to: TaskStatus,
): TaskTrigger | "unknown" {
  if (from === null && to === "pending") return "workflow_started" as TaskTrigger;
  if (from === "pending" && to === "ready")
    return "dependency_satisfied" as TaskTrigger;
  if (from === "ready" && to === "running")
    return "worker_started" as TaskTrigger;
  if (from === "running" && to === "completed")
    return "execution_succeeded" as TaskTrigger;
  if (from === "running" && to === "failed")
    return "execution_failed" as TaskTrigger;
  if (to === "completed" && from !== "running")
    return "children_completed" as TaskTrigger;
  return "unknown";
}

function messagePreview(msg: CommunicationMessageState): string {
  const candidate =
    (msg as unknown as { content?: unknown }).content ??
    (msg as unknown as { text?: unknown }).text ??
    (msg as unknown as { preview?: unknown }).preview ??
    "";
  const str = typeof candidate === "string" ? candidate : JSON.stringify(candidate);
  return str.length > 140 ? `${str.slice(0, 137)}...` : str;
}

/**
 * Build the flat, chronologically-sorted SampleEvent log from a SampleWorkspaceState.
 *
 * Consumers should treat this as a *pure derivation* of state — it is cheap
 * enough to recompute on every render of the stream, but the SampleWorkspacePage
 * memoizes it on `runState` identity.
 */
export function buildSampleEvents(run: SampleWorkspaceState | null): SampleEvent[] {
  if (!run) return [];
  const events: SampleEvent[] = [];

  events.push({
    id: `workflow.started:${run.id}`,
    kind: "workflow.started",
    at: run.startedAt,
    sampleName: run.name,
  });

  if (run.completedAt) {
    events.push({
      id: `workflow.completed:${run.id}`,
      kind: "workflow.completed",
      at: run.completedAt,
      status: run.status,
      finalScore: run.finalScore,
      error: run.error,
    });
  }

  for (const task of run.tasks.values()) {
    const history = task.history ?? [];
    for (let i = 0; i < history.length; i++) {
      const h = history[i];
      events.push(transitionToEvent(task, h, i));
    }
  }

  for (const sandbox of run.sandboxesByTask.values()) {
    events.push(sandboxCreatedEvent(sandbox));
    for (let i = 0; i < sandbox.commands.length; i++) {
      const cmd = sandbox.commands[i];
      events.push(sandboxCommandEvent(sandbox, cmd, i));
    }
    if (sandbox.status === "closed" && sandbox.closedAt) {
      events.push({
        id: `sandbox.closed:${sandbox.sandboxId}`,
        kind: "sandbox.closed",
        at: sandbox.closedAt,
        taskId: sandbox.taskId,
        sandboxId: sandbox.sandboxId,
        closeReason: sandbox.closeReason ?? null,
      });
    }
  }

  for (const thread of run.threads) {
    const messages = threadMessages(thread);
    for (const msg of messages) {
      const at =
        (msg as unknown as { createdAt?: string }).createdAt ??
        (msg as unknown as { timestamp?: string }).timestamp ??
        run.startedAt;
      const authorRole =
        (msg as unknown as { role?: string }).role ??
        (msg as unknown as { authorRole?: string }).authorRole ??
        "unknown";
      events.push({
        id: `thread.message:${thread.id}:${(msg as unknown as { id?: string }).id ?? at}`,
        kind: "thread.message",
        at,
        taskId: (thread as unknown as { taskId?: string | null }).taskId ?? null,
        threadId: thread.id,
        authorRole,
        preview: messagePreview(msg),
      });
    }
  }

  for (const [key, evaluation] of run.evaluationsByTask.entries()) {
    const e = evaluation as TaskEvaluationState & {
      createdAt?: string;
      updatedAt?: string;
      score?: number | null;
      passed?: boolean | null;
    };
    const at = e.updatedAt ?? e.createdAt ?? run.startedAt;
    events.push({
      id: `task.evaluation:${key}`,
      kind: "task.evaluation",
      at,
      taskId: key === "__run__" ? null : key,
      score: e.score ?? null,
      passed: e.passed ?? null,
    });
  }

  for (const resources of run.resourcesByTask.values()) {
    for (const r of resources) {
      events.push(resourcePublishedEvent(r));
    }
  }

  for (const [taskId, contextEvents] of run.contextEventsByTask.entries()) {
    for (const ev of contextEvents) {
      events.push(contextEventToEvent(taskId, ev));
    }
  }

  if (run.unhandledMutations) {
    for (const u of run.unhandledMutations) {
      events.push(unhandledToEvent(u));
    }
  }

  events.sort((a, b) => {
    if (a.at === b.at) {
      const sa = a.sequence ?? -1;
      const sb = b.sequence ?? -1;
      if (sa !== sb) return sa - sb;
      return a.id.localeCompare(b.id);
    }
    return a.at.localeCompare(b.at);
  });

  return events;
}

function transitionToEvent(
  task: TaskState,
  h: TaskTransitionRecord,
  idx: number,
): TaskTransitionEvent {
  return {
    id: `task.transition:${task.id}:${idx}:${h.at}`,
    kind: "task.transition",
    at: h.at,
    taskId: task.id,
    sequence: h.sequence,
    taskName: task.name,
    from: h.from,
    to: h.to,
    trigger: h.trigger,
    reason: h.reason,
    actor: h.actor,
  };
}

function sandboxCreatedEvent(sandbox: SandboxState): SandboxCreatedEvent {
  return {
    id: `sandbox.created:${sandbox.sandboxId}`,
    kind: "sandbox.created",
    at: sandbox.createdAt,
    taskId: sandbox.taskId,
    sandboxId: sandbox.sandboxId,
    template: sandbox.template,
  };
}

function sandboxCommandEvent(
  sandbox: SandboxState,
  cmd: SandboxCommandState,
  idx: number,
): SandboxCommandEvent {
  return {
    id: `sandbox.command:${sandbox.sandboxId}:${idx}`,
    kind: "sandbox.command",
    at: cmd.timestamp,
    taskId: sandbox.taskId,
    command: cmd.command,
    exitCode: cmd.exitCode,
    durationMs: cmd.durationMs,
  };
}

function resourcePublishedEvent(r: ResourceState): ResourcePublishedEvent {
  return {
    id: `resource.published:${r.id}`,
    kind: "resource.published",
    at: r.createdAt,
    taskId: r.taskId,
    name: r.name,
    mimeType: r.mimeType,
    sizeBytes: r.sizeBytes,
  };
}

function contextEventToEvent(taskId: string, ev: ContextEventState): ContextEvent {
  const e = ev as unknown as {
    id?: string;
    sequence?: number;
    createdAt?: string;
    timestamp?: string;
    eventType?: string;
    kind?: string;
    summary?: string;
    description?: string;
  };
  const at = e.createdAt ?? e.timestamp ?? "1970-01-01T00:00:00.000Z";
  const summary =
    e.summary ??
    e.description ??
    e.eventType ??
    e.kind ??
    "context event";
  return {
    id: `context.event:${taskId}:${e.id ?? e.sequence ?? at}`,
    kind: "context.event",
    at,
    taskId,
    sequence: e.sequence ?? null,
    eventId: e.id ?? `${taskId}-${e.sequence ?? at}`,
    summary: String(summary),
  };
}

function unhandledToEvent(u: UnhandledMutationRecord): UnhandledMutationEvent {
  return {
    id: `unhandled.mutation:${u.mutationId}`,
    kind: "unhandled.mutation",
    at: u.createdAt,
    taskId: u.targetId,
    sequence: u.sequence,
    mutationType: u.mutationType,
    note: u.note,
  };
}

function threadMessages(
  thread: CommunicationThreadState,
): CommunicationMessageState[] {
  const candidate = (thread as unknown as { messages?: unknown }).messages;
  if (Array.isArray(candidate)) return candidate as CommunicationMessageState[];
  return [];
}

/**
 * Convenience: count how many of each kind we have — used by filter toolbars.
 */
export function countEventsByKind(
  events: SampleEvent[],
): Record<SampleEventKind, number> {
  const counts = Object.fromEntries(
    SAMPLE_EVENT_KINDS.map((k) => [k, 0]),
  ) as Record<SampleEventKind, number>;
  for (const e of events) counts[e.kind] += 1;
  return counts;
}

/**
 * Find the closest event (by wall-clock `at`) whose `taskId` matches — used
 * when jumping from a DAG selection to the event stream.
 */
export function findNearestEventForTask(
  events: SampleEvent[],
  taskId: string,
  at: string | null,
): SampleEvent | null {
  let best: SampleEvent | null = null;
  let bestDelta = Number.POSITIVE_INFINITY;
  const target = at ? new Date(at).getTime() : null;
  for (const e of events) {
    if (e.taskId !== taskId) continue;
    if (target === null) return e;
    const delta = Math.abs(new Date(e.at).getTime() - target);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = e;
    }
  }
  return best;
}
