import type { TaskState, WorkflowRunState } from "@/lib/types";
import { TaskStatus } from "@/lib/types";
import type { DashboardGraphMutationData } from "@/lib/contracts/events";
import type {
  NodeAddedValue,
  NodeStatusChangedValue,
  NodeFieldChangedValue,
  EdgeAddedValue,
  GraphMutationDto,
} from "@/features/graph/contracts/graphMutations";
import {
  NodeAddedValueSchema,
  NodeStatusChangedValueSchema,
  NodeFieldChangedValueSchema,
  EdgeAddedValueSchema,
} from "@/features/graph/contracts/graphMutations";

const TERMINAL_STATUSES: Set<string> = new Set([
  "completed",
  "failed",
  "abandoned",
]);

/**
 * Apply a single graph mutation to a WorkflowRunState.
 *
 * Returns a new object reference (shallow copy) for React state updates.
 * Exhaustive on mutation_type — adding a new variant without handling
 * it here is a compile error.
 */
export function applyGraphMutation(
  state: WorkflowRunState,
  mutation: DashboardGraphMutationData,
): WorkflowRunState {
  const next = { ...state, tasks: new Map(state.tasks) };

  switch (mutation.mutation_type) {
    case "node.added":
      return applyNodeAdded(
        next,
        mutation.target_id,
        NodeAddedValueSchema.parse(mutation.new_value),
      );

    case "node.removed":
      return applyNodeStatusChange(next, mutation.target_id, {
        status: "removed",
      });

    case "node.status_changed":
      return applyNodeStatusChange(
        next,
        mutation.target_id,
        NodeStatusChangedValueSchema.parse(mutation.new_value),
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
      );

    case "edge.removed":
      return next;

    case "edge.status_changed":
      return next;

    case "annotation.set":
    case "annotation.deleted":
      return next;

    default: {
      const _exhaustive: never = mutation.mutation_type;
      console.warn(`Unhandled mutation type: ${_exhaustive}`);
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
): WorkflowRunState {
  const task = state.tasks.get(nodeId);
  if (!task) return state;

  const updated = { ...task, status: value.status as TaskStatus };

  if (value.status === "running" && !task.startedAt) {
    updated.startedAt = new Date().toISOString();
  }
  if (TERMINAL_STATUSES.has(value.status) && !task.completedAt) {
    updated.completedAt = new Date().toISOString();
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
): WorkflowRunState {
  const source = state.tasks.get(value.source_node_id);
  const target = state.tasks.get(value.target_node_id);
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
  let state = { ...initialState, tasks: new Map(initialState.tasks) };

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
