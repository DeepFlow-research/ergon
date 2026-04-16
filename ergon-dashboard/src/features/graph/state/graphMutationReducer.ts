import type {
  AnnotationState,
  EdgeState,
  TaskState,
  TaskTransitionRecord,
  UnhandledMutationRecord,
  WorkflowRunState,
} from "@/lib/types";
import { TaskStatus } from "@/lib/types";
import type { DashboardGraphMutationData } from "@/lib/contracts/events";
import type {
  AnnotationValue,
  EdgeAddedValue,
  EdgeStatusChangedValue,
  GraphMutationDto,
  NodeAddedValue,
  NodeFieldChangedValue,
  NodeStatusChangedValue,
} from "@/features/graph/contracts/graphMutations";
import {
  AnnotationValueSchema,
  EdgeAddedValueSchema,
  EdgeStatusChangedValueSchema,
  NodeAddedValueSchema,
  NodeFieldChangedValueSchema,
  NodeStatusChangedValueSchema,
} from "@/features/graph/contracts/graphMutations";
import { inferTrigger } from "@/lib/runEvents";

const TERMINAL_STATUSES: Set<string> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

interface MutationContext {
  /** Sequence number from the original GraphMutationDto, if available. */
  sequence: number | null;
  createdAt: string;
  mutationId: string | null;
  actor: string | null;
  reason: string | null;
}

function ctxFromMutation(mutation: DashboardGraphMutationData): MutationContext {
  const m = mutation as unknown as {
    sequence?: number | null;
    created_at?: string;
    timestamp?: string;
    id?: string;
    actor?: string;
    reason?: string | null;
  };
  return {
    sequence: m.sequence ?? null,
    createdAt: m.created_at ?? m.timestamp ?? new Date().toISOString(),
    mutationId: m.id ?? null,
    actor: m.actor ?? null,
    reason: m.reason ?? null,
  };
}

function ensureAnnotations(state: WorkflowRunState): Map<string, AnnotationState[]> {
  if (!state.annotationsByTarget) state.annotationsByTarget = new Map();
  return state.annotationsByTarget;
}

function ensureEdges(state: WorkflowRunState): Map<string, EdgeState> {
  if (!state.edges) state.edges = new Map();
  return state.edges;
}

function ensureUnhandled(state: WorkflowRunState): UnhandledMutationRecord[] {
  if (!state.unhandledMutations) state.unhandledMutations = [];
  return state.unhandledMutations;
}

function recordUnhandled(
  state: WorkflowRunState,
  mutation: DashboardGraphMutationData,
  note: string,
): void {
  const ctx = ctxFromMutation(mutation);
  ensureUnhandled(state).push({
    mutationId: ctx.mutationId ?? `${mutation.mutation_type}:${ctx.sequence ?? "?"}`,
    sequence: ctx.sequence ?? 0,
    mutationType: mutation.mutation_type,
    targetId: mutation.target_id,
    actor: ctx.actor ?? "unknown",
    createdAt: ctx.createdAt,
    note,
  });
}

function edgeId(sourceId: string, targetId: string): string {
  return `${sourceId}::${targetId}`;
}

/**
 * Apply a single graph mutation to a WorkflowRunState.
 *
 * Returns a new object reference (shallow copy) for React state updates.
 * Exhaustive on mutation_type — adding a new variant without handling
 * it here is a compile error.
 *
 * Invariant: every mutation either (a) produces a visible state delta, or
 * (b) is recorded in `unhandledMutations`. No mutation is ever silently dropped.
 */
export function applyGraphMutation(
  state: WorkflowRunState,
  mutation: DashboardGraphMutationData,
): WorkflowRunState {
  const next: WorkflowRunState = { ...state, tasks: new Map(state.tasks) };
  if (state.edges) next.edges = new Map(state.edges);
  if (state.annotationsByTarget)
    next.annotationsByTarget = new Map(state.annotationsByTarget);
  if (state.unhandledMutations)
    next.unhandledMutations = [...state.unhandledMutations];

  const ctx = ctxFromMutation(mutation);

  switch (mutation.mutation_type) {
    case "node.added":
      return applyNodeAdded(
        next,
        mutation.target_id,
        NodeAddedValueSchema.parse(mutation.new_value),
      );

    case "node.removed":
      return applyNodeStatusChange(
        next,
        mutation.target_id,
        { status: "cancelled" },
        ctx,
      );

    case "node.status_changed":
      return applyNodeStatusChange(
        next,
        mutation.target_id,
        NodeStatusChangedValueSchema.parse(mutation.new_value),
        ctx,
      );

    case "node.field_changed":
      return applyNodeFieldChange(
        next,
        mutation.target_id,
        NodeFieldChangedValueSchema.parse(mutation.new_value),
      );

    case "edge.added":
      return applyEdgeAdded(
        next,
        EdgeAddedValueSchema.parse(mutation.new_value),
        ctx,
      );

    case "edge.removed":
      return applyEdgeRemoved(next, mutation.target_id, ctx);

    case "edge.status_changed":
      return applyEdgeStatusChanged(
        next,
        mutation.target_id,
        EdgeStatusChangedValueSchema.parse(mutation.new_value),
        ctx,
      );

    case "annotation.set":
      return applyAnnotationSet(
        next,
        mutation.target_id,
        AnnotationValueSchema.parse(mutation.new_value),
        ctx,
      );

    case "annotation.deleted":
      return applyAnnotationDeleted(
        next,
        mutation.target_id,
        AnnotationValueSchema.parse(mutation.new_value),
        ctx,
      );

    default: {
      const _exhaustive: never = mutation.mutation_type;
      recordUnhandled(next, mutation, `Unknown mutation type: ${_exhaustive}`);
      return next;
    }
  }
}

function applyNodeAdded(
  state: WorkflowRunState,
  nodeId: string,
  value: NodeAddedValue,
): WorkflowRunState {
  if (state.tasks.has(nodeId)) return state;

  const task: TaskState = {
    id: nodeId,
    name: value.task_key,
    description: value.description,
    status: value.status as TaskStatus,
    parentId: null,
    childIds: [],
    dependsOnIds: [],
    assignedWorkerId: null,
    assignedWorkerName: value.assigned_worker_key,
    startedAt: null,
    completedAt: null,
    isLeaf: true,
    level: 0,
    history: [],
    lastTrigger: null,
  };

  state.tasks.set(nodeId, task);
  state.totalTasks += 1;
  state.totalLeafTasks += 1;
  return state;
}

function applyNodeStatusChange(
  state: WorkflowRunState,
  nodeId: string,
  value: NodeStatusChangedValue,
  ctx: MutationContext,
): WorkflowRunState {
  const task = state.tasks.get(nodeId);
  if (!task) return state;

  const fromStatus = task.status ?? null;
  const toStatus = value.status as TaskStatus;
  const updated: TaskState = { ...task, status: toStatus };

  if (value.status === "running" && !task.startedAt) {
    updated.startedAt = ctx.createdAt;
  }
  if (TERMINAL_STATUSES.has(value.status) && !task.completedAt) {
    updated.completedAt = ctx.createdAt;
  }

  if (fromStatus !== toStatus) {
    const trigger = inferTrigger(fromStatus ?? null, toStatus);
    const record: TaskTransitionRecord = {
      from: fromStatus ?? null,
      to: toStatus,
      trigger,
      at: ctx.createdAt,
      sequence: ctx.sequence,
      actor: ctx.actor,
      reason: ctx.reason,
    };
    updated.history = [...(task.history ?? []), record];
    updated.lastTrigger = trigger;
  }

  state.tasks.set(nodeId, updated);
  recalculateMetrics(state);
  return state;
}

function applyNodeFieldChange(
  state: WorkflowRunState,
  nodeId: string,
  value: NodeFieldChangedValue,
): WorkflowRunState {
  const task = state.tasks.get(nodeId);
  if (!task) return state;

  const updated = { ...task };
  switch (value.field) {
    case "description":
      updated.description = value.value ?? "";
      break;
    case "assigned_worker_key":
      updated.assignedWorkerName = value.value;
      break;
  }

  state.tasks.set(nodeId, updated);
  return state;
}

function applyEdgeAdded(
  state: WorkflowRunState,
  value: EdgeAddedValue,
  ctx: MutationContext,
): WorkflowRunState {
  const source = state.tasks.get(value.source_node_id);
  const target = state.tasks.get(value.target_node_id);

  const edges = ensureEdges(state);
  const id = edgeId(value.source_node_id, value.target_node_id);
  edges.set(id, {
    id,
    sourceId: value.source_node_id,
    targetId: value.target_node_id,
    status: value.status,
    createdAt: ctx.createdAt,
  });

  if (!source || !target) return state;

  const updatedTarget = { ...target };
  const updatedSource = { ...source };

  if (updatedTarget.parentId === null) {
    updatedTarget.parentId = value.source_node_id;
    updatedTarget.level = updatedSource.level + 1;
    updatedSource.childIds = [...updatedSource.childIds, value.target_node_id];
    if (updatedSource.isLeaf) {
      updatedSource.isLeaf = false;
      state.totalLeafTasks -= 1;
    }
  } else if (updatedTarget.parentId !== value.source_node_id) {
    updatedTarget.dependsOnIds = [
      ...updatedTarget.dependsOnIds,
      value.source_node_id,
    ];
  }

  state.tasks.set(value.source_node_id, updatedSource);
  state.tasks.set(value.target_node_id, updatedTarget);
  return state;
}

function applyEdgeRemoved(
  state: WorkflowRunState,
  targetEdgeId: string,
  _ctx: MutationContext,
): WorkflowRunState {
  const edges = ensureEdges(state);
  // `target_id` for edge mutations is documented as the edge id — we look it up
  // either directly or by the source::target convention.
  const match = edges.get(targetEdgeId);
  if (!match) {
    // still a valid operation; record that we observed it but the edge wasn't
    // in our local map (common when the snapshot pre-dates the edge).
    edges.set(targetEdgeId, {
      id: targetEdgeId,
      sourceId: "",
      targetId: "",
      status: "removed",
      createdAt: _ctx.createdAt,
    });
    return state;
  }
  edges.delete(match.id);

  if (match.sourceId && match.targetId) {
    const target = state.tasks.get(match.targetId);
    const source = state.tasks.get(match.sourceId);
    if (target) {
      const updated = {
        ...target,
        dependsOnIds: target.dependsOnIds.filter((d) => d !== match.sourceId),
      };
      if (updated.parentId === match.sourceId) updated.parentId = null;
      state.tasks.set(match.targetId, updated);
    }
    if (source) {
      const updatedSource = {
        ...source,
        childIds: source.childIds.filter((c) => c !== match.targetId),
      };
      state.tasks.set(match.sourceId, updatedSource);
    }
  }
  return state;
}

function applyEdgeStatusChanged(
  state: WorkflowRunState,
  targetEdgeId: string,
  value: EdgeStatusChangedValue,
  ctx: MutationContext,
): WorkflowRunState {
  const edges = ensureEdges(state);
  const existing = edges.get(targetEdgeId);
  edges.set(targetEdgeId, {
    id: targetEdgeId,
    sourceId: existing?.sourceId ?? "",
    targetId: existing?.targetId ?? "",
    status: value.status,
    createdAt: existing?.createdAt ?? ctx.createdAt,
  });
  return state;
}

function applyAnnotationSet(
  state: WorkflowRunState,
  targetId: string,
  value: AnnotationValue,
  ctx: MutationContext,
): WorkflowRunState {
  const annotations = ensureAnnotations(state);
  const existing = annotations.get(targetId) ?? [];
  const next = existing.filter((a) => a.namespace !== value.namespace);
  next.push({
    namespace: value.namespace,
    payload: value.payload,
    setAt: ctx.createdAt,
    deleted: false,
  });
  annotations.set(targetId, next);
  return state;
}

function applyAnnotationDeleted(
  state: WorkflowRunState,
  targetId: string,
  value: AnnotationValue,
  ctx: MutationContext,
): WorkflowRunState {
  const annotations = ensureAnnotations(state);
  const existing = annotations.get(targetId);
  if (!existing) return state;
  const next = existing.map((a) =>
    a.namespace === value.namespace
      ? { ...a, deleted: true, deletedAt: ctx.createdAt }
      : a,
  );
  annotations.set(targetId, next);
  return state;
}

function recalculateMetrics(state: WorkflowRunState): void {
  let completed = 0,
    running = 0,
    failed = 0;
  for (const task of state.tasks.values()) {
    if (task.status === "completed") completed++;
    else if (task.status === "running") running++;
    else if (task.status === "failed") failed++;
  }
  state.completedTasks = completed;
  state.runningTasks = running;
  state.failedTasks = failed;
}

const SNAPSHOT_INTERVAL = 50;

/**
 * Replay mutations up to a given sequence number from an initial state.
 * Used by the timeline scrubber for WAL playback.
 *
 * When a `snapshotCache` is provided, the replay starts from the nearest
 * cached snapshot before `upToSequence` and caches new snapshots at every
 * `SNAPSHOT_INTERVAL` sequences for faster scrubbing.
 */
export function replayToSequence(
  mutations: GraphMutationDto[],
  upToSequence: number,
  initialState: WorkflowRunState,
  snapshotCache?: Map<number, WorkflowRunState>,
): WorkflowRunState {
  let startSeq = -1;
  let state: WorkflowRunState = {
    ...initialState,
    tasks: new Map(initialState.tasks),
  };

  if (snapshotCache) {
    for (const [seq, snap] of snapshotCache) {
      if (seq <= upToSequence && seq > startSeq) {
        startSeq = seq;
        state = { ...snap, tasks: new Map(snap.tasks) };
      }
    }
  }

  for (const m of mutations) {
    if (m.sequence > upToSequence) break;
    if (m.sequence <= startSeq) continue;

    state = applyGraphMutation(state, {
      ...m,
      timestamp: m.created_at,
    } as DashboardGraphMutationData);

    if (snapshotCache && m.sequence % SNAPSHOT_INTERVAL === 0) {
      snapshotCache.set(m.sequence, { ...state, tasks: new Map(state.tasks) });
    }
  }

  return state;
}
