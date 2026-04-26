/**
 * Contract test: every MutationType variant must have a matching case arm in
 * applyGraphMutation, i.e. the mutation must not appear in unhandledMutations
 * after being applied to an empty state.
 *
 * See docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { MutationTypeSchema } from "./graphMutations";
import { applyGraphMutation, createReplayInitialState, replayToSequence } from "../state/graphMutationReducer";
import type { WorkflowRunState } from "@/lib/types";
import { TaskStatus } from "@/lib/types";
import type { DashboardGraphMutationData } from "@/lib/contracts/events";
import type { GraphMutationDto } from "./graphMutations";

function emptyState(): WorkflowRunState {
  return {
    id: "run-test",
    experimentId: "00000000-0000-0000-0000-000000000000",
    name: "test",
    status: "executing",
    tasks: new Map(),
    rootTaskId: "11111111-1111-4111-8111-111111111111",
    resourcesByTask: new Map(),
    executionsByTask: new Map(),
    sandboxesByTask: new Map(),
    threads: [],
    contextEventsByTask: new Map(),
    evaluationsByTask: new Map(),
    startedAt: new Date().toISOString(),
    completedAt: null,
    durationSeconds: null,
    totalTasks: 0,
    totalLeafTasks: 0,
    completedTasks: 0,
    runningTasks: 0,
    failedTasks: 0,
    finalScore: null,
    error: null,
    edges: new Map(),
    annotationsByTarget: new Map(),
    unhandledMutations: [],
  };
}

/**
 * Build a minimal synthetic mutation for a given mutation_type.
 * new_value contents must satisfy the schema for that type.
 */
function syntheticMutation(
  mutationType: string,
): DashboardGraphMutationData {
  const nodeId = "11111111-1111-4111-8111-111111111111";
  const newValueByType: Record<string, Record<string, unknown>> = {
    "node.added": {
      mutation_type: "node.added",
      task_slug: "test-task",
      instance_key: "inst-1",
      description: "test",
      status: "pending",
      assigned_worker_slug: null,
    },
    "node.removed": { mutation_type: "node.removed", status: "cancelled" },
    "node.status_changed": {
      mutation_type: "node.status_changed",
      status: "running",
    },
    "node.field_changed": {
      mutation_type: "node.field_changed",
      field: "description",
      value: "updated",
    },
    "edge.added": {
      mutation_type: "edge.added",
      source_node_id: nodeId,
      target_node_id: "22222222-2222-4222-8222-222222222222",
      status: "pending",
    },
    "edge.removed": { mutation_type: "edge.removed" },
    "edge.status_changed": {
      mutation_type: "edge.status_changed",
      status: "satisfied",
    },
    "annotation.set": {
      mutation_type: "annotation.set",
      namespace: "test",
      payload: {},
    },
    "annotation.deleted": {
      mutation_type: "annotation.deleted",
      namespace: "test",
      payload: {},
    },
  };

  return {
    run_id: "00000000-0000-0000-0000-000000000000",
    sequence: 1,
    mutation_type: mutationType as DashboardGraphMutationData["mutation_type"],
    target_type: "node",
    target_id: nodeId,
    actor: "test",
    new_value: newValueByType[mutationType] ?? {},
    old_value: null,
    reason: null,
    timestamp: new Date().toISOString(),
  };
}

const ALL_MUTATION_TYPES = MutationTypeSchema.options;

for (const mutationType of ALL_MUTATION_TYPES) {
  test(
    `mutation_type '${mutationType}' is handled (does not fall through to unhandledMutations)`,
    () => {
      const state = emptyState();
      const mutation = syntheticMutation(mutationType);
      const next = applyGraphMutation(state, mutation);
      const unhandled = next.unhandledMutations ?? [];
      const fell = unhandled.some((u) => u.mutationType === mutationType);
      assert.equal(fell, false);
    },
  );
}

test("ALL_MUTATION_TYPES matches MutationTypeSchema.options (no stale snapshot)", () => {
  assert.deepEqual(ALL_MUTATION_TYPES, MutationTypeSchema.options);
});

test("replay base preserves snapshot hierarchy while dependency edges remain dependencies", () => {
  const runState = emptyState();
  runState.tasks = new Map([
    [
      "11111111-1111-4111-8111-111111111111",
      {
        id: "11111111-1111-4111-8111-111111111111",
        name: "root",
        description: "root",
        status: TaskStatus.RUNNING,
        parentId: null,
        childIds: [
          "22222222-2222-4222-8222-222222222222",
          "33333333-3333-4333-8333-333333333333",
        ],
        dependsOnIds: [],
        assignedWorkerId: null,
        assignedWorkerName: "parent",
        startedAt: "2026-04-26T12:00:00.000Z",
        completedAt: null,
        isLeaf: false,
        level: 0,
      },
    ],
    [
      "22222222-2222-4222-8222-222222222222",
      {
        id: "22222222-2222-4222-8222-222222222222",
        name: "dependency",
        description: "dependency",
        status: TaskStatus.COMPLETED,
        parentId: "11111111-1111-4111-8111-111111111111",
        childIds: [],
        dependsOnIds: [],
        assignedWorkerId: null,
        assignedWorkerName: "worker-a",
        startedAt: "2026-04-26T12:00:01.000Z",
        completedAt: "2026-04-26T12:00:05.000Z",
        isLeaf: true,
        level: 1,
      },
    ],
    [
      "33333333-3333-4333-8333-333333333333",
      {
        id: "33333333-3333-4333-8333-333333333333",
        name: "dependent",
        description: "dependent",
        status: TaskStatus.RUNNING,
        parentId: "11111111-1111-4111-8111-111111111111",
        childIds: [],
        dependsOnIds: ["22222222-2222-4222-8222-222222222222"],
        assignedWorkerId: "future-agent-id",
        assignedWorkerName: "worker-b",
        startedAt: "2026-04-26T12:00:06.000Z",
        completedAt: null,
        isLeaf: true,
        level: 1,
      },
    ],
  ]);

  const mutations: GraphMutationDto[] = [
    graphNodeAdded(0, "11111111-1111-4111-8111-111111111111", "root"),
    graphNodeAdded(1, "22222222-2222-4222-8222-222222222222", "dependency"),
    graphNodeAdded(2, "33333333-3333-4333-8333-333333333333", "dependent"),
    {
      id: "44444444-4444-4444-8444-444444444444",
      run_id: "00000000-0000-0000-0000-000000000000",
      sequence: 3,
      mutation_type: "edge.added",
      target_type: "edge",
      target_id: "44444444-4444-4444-8444-444444444444",
      actor: "manager",
      old_value: null,
      new_value: {
        source_node_id: "22222222-2222-4222-8222-222222222222",
        target_node_id: "33333333-3333-4333-8333-333333333333",
        status: "pending",
      },
      reason: "manager_decision",
      created_at: "2026-04-26T12:00:03.000Z",
    },
  ];

  const base = createReplayInitialState(runState, mutations, 3);
  const replayed = mutations.reduce(
    (state, mutation) =>
      applyGraphMutation(state, { ...mutation, timestamp: mutation.created_at }),
    base,
  );

  const dependent = replayed.tasks.get("33333333-3333-4333-8333-333333333333");
  assert.equal(dependent?.parentId, "11111111-1111-4111-8111-111111111111");
  assert.deepEqual(dependent?.dependsOnIds, ["22222222-2222-4222-8222-222222222222"]);
  assert.equal(dependent?.level, 1);
});

test("replay base does not leak future dependency edges or node field changes", () => {
  const runState = emptyState();
  runState.tasks = new Map([
    [
      "11111111-1111-4111-8111-111111111111",
      {
        id: "11111111-1111-4111-8111-111111111111",
        name: "root",
        description: "root",
        status: TaskStatus.RUNNING,
        parentId: null,
        childIds: [
          "22222222-2222-4222-8222-222222222222",
          "33333333-3333-4333-8333-333333333333",
        ],
        dependsOnIds: [],
        assignedWorkerId: null,
        assignedWorkerName: "parent",
        startedAt: "2026-04-26T12:00:00.000Z",
        completedAt: null,
        isLeaf: false,
        level: 0,
      },
    ],
    [
      "22222222-2222-4222-8222-222222222222",
      {
        id: "22222222-2222-4222-8222-222222222222",
        name: "source",
        description: "source updated",
        status: TaskStatus.COMPLETED,
        parentId: "11111111-1111-4111-8111-111111111111",
        childIds: [],
        dependsOnIds: [],
        assignedWorkerId: "future-agent-id",
        assignedWorkerName: "future-worker",
        startedAt: null,
        completedAt: null,
        isLeaf: true,
        level: 1,
      },
    ],
    [
      "33333333-3333-4333-8333-333333333333",
      {
        id: "33333333-3333-4333-8333-333333333333",
        name: "target",
        description: "target",
        status: TaskStatus.PENDING,
        parentId: "11111111-1111-4111-8111-111111111111",
        childIds: [],
        dependsOnIds: ["22222222-2222-4222-8222-222222222222"],
        assignedWorkerId: null,
        assignedWorkerName: "worker-b",
        startedAt: null,
        completedAt: null,
        isLeaf: true,
        level: 1,
      },
    ],
  ]);

  const mutations: GraphMutationDto[] = [
    graphNodeAdded(0, "11111111-1111-4111-8111-111111111111", "root"),
    graphNodeAdded(1, "22222222-2222-4222-8222-222222222222", "source"),
    graphNodeAdded(2, "33333333-3333-4333-8333-333333333333", "target"),
    {
      id: "66666666-6666-4666-8666-666666666666",
      run_id: "00000000-0000-0000-0000-000000000000",
      sequence: 3,
      mutation_type: "node.field_changed",
      target_type: "node",
      target_id: "22222222-2222-4222-8222-222222222222",
      actor: "manager",
      old_value: { description: "source" },
      new_value: { field: "description", value: "source updated" },
      reason: "update later",
      created_at: "2026-04-26T12:00:03.000Z",
    },
    {
      id: "77777777-7777-4777-8777-777777777777",
      run_id: "00000000-0000-0000-0000-000000000000",
      sequence: 4,
      mutation_type: "edge.added",
      target_type: "edge",
      target_id: "77777777-7777-4777-8777-777777777777",
      actor: "manager",
      old_value: null,
      new_value: {
        source_node_id: "22222222-2222-4222-8222-222222222222",
        target_node_id: "33333333-3333-4333-8333-333333333333",
        status: "pending",
      },
      reason: "manager_decision",
      created_at: "2026-04-26T12:00:04.000Z",
    },
  ];

  const replayed = replayToSequence(
    mutations,
    2,
    createReplayInitialState(runState, mutations, 2),
  );

  const source = replayed.tasks.get("22222222-2222-4222-8222-222222222222");
  const target = replayed.tasks.get("33333333-3333-4333-8333-333333333333");
  assert.equal(source?.description, "source");
  assert.equal(source?.assignedWorkerId, null);
  assert.equal(source?.assignedWorkerName, "worker");
  assert.deepEqual(target?.dependsOnIds, []);
});

test("dependency edges between root-level tasks do not become containment", () => {
  const runState = emptyState();
  runState.tasks = new Map([
    [
      "22222222-2222-4222-8222-222222222222",
      {
        id: "22222222-2222-4222-8222-222222222222",
        name: "source",
        description: "source",
        status: TaskStatus.COMPLETED,
        parentId: null,
        childIds: [],
        dependsOnIds: [],
        assignedWorkerId: null,
        assignedWorkerName: "worker-a",
        startedAt: null,
        completedAt: null,
        isLeaf: true,
        level: 0,
      },
    ],
    [
      "33333333-3333-4333-8333-333333333333",
      {
        id: "33333333-3333-4333-8333-333333333333",
        name: "target",
        description: "target",
        status: TaskStatus.PENDING,
        parentId: null,
        childIds: [],
        dependsOnIds: ["22222222-2222-4222-8222-222222222222"],
        assignedWorkerId: null,
        assignedWorkerName: "worker-b",
        startedAt: null,
        completedAt: null,
        isLeaf: true,
        level: 0,
      },
    ],
  ]);
  const mutations: GraphMutationDto[] = [
    graphNodeAdded(0, "22222222-2222-4222-8222-222222222222", "source"),
    graphNodeAdded(1, "33333333-3333-4333-8333-333333333333", "target"),
    {
      id: "88888888-8888-4888-8888-888888888888",
      run_id: "00000000-0000-0000-0000-000000000000",
      sequence: 2,
      mutation_type: "edge.added",
      target_type: "edge",
      target_id: "88888888-8888-4888-8888-888888888888",
      actor: "manager",
      old_value: null,
      new_value: {
        source_node_id: "22222222-2222-4222-8222-222222222222",
        target_node_id: "33333333-3333-4333-8333-333333333333",
        status: "pending",
      },
      reason: "manager_decision",
      created_at: "2026-04-26T12:00:02.000Z",
    },
  ];

  const replayed = replayToSequence(
    mutations,
    2,
    createReplayInitialState(runState, mutations, 2),
  );
  const target = replayed.tasks.get("33333333-3333-4333-8333-333333333333");
  assert.equal(target?.parentId, null);
  assert.equal(target?.level, 0);
  assert.deepEqual(target?.dependsOnIds, ["22222222-2222-4222-8222-222222222222"]);
});

function graphNodeAdded(
  sequence: number,
  targetId: string,
  slug: string,
): GraphMutationDto {
  return {
    id: `55555555-5555-4555-8555-55555555555${sequence}`,
    run_id: "00000000-0000-0000-0000-000000000000",
    sequence,
    mutation_type: "node.added",
    target_type: "node",
    target_id: targetId,
    actor: "manager",
    old_value: null,
    new_value: {
      task_slug: slug,
      instance_key: "default",
      description: slug,
      status: "pending",
      assigned_worker_slug: "worker",
    },
    reason: "manager_decision",
    created_at: `2026-04-26T12:00:0${sequence}.000Z`,
  };
}
