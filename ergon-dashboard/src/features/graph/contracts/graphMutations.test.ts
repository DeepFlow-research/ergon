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
import { applyGraphMutation } from "../state/graphMutationReducer";
import type { WorkflowRunState } from "@/lib/types";
import type { DashboardGraphMutationData } from "@/lib/contracts/events";

function emptyState(): WorkflowRunState {
  return {
    id: "run-test",
    experimentId: "00000000-0000-0000-0000-000000000000",
    name: "test",
    status: "executing",
    tasks: new Map(),
    rootTaskId: "00000000-0000-0000-0000-000000000001",
    resourcesByTask: new Map(),
    executionsByTask: new Map(),
    sandboxesByTask: new Map(),
    threads: [],
    generationTurns: [],
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
  const nodeId = "00000000-0000-0000-0000-000000000001";
  const newValueByType: Record<string, Record<string, unknown>> = {
    "node.added": {
      mutation_type: "node.added",
      task_key: "test-task",
      instance_key: "inst-1",
      description: "test",
      status: "pending",
      assigned_worker_key: null,
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
      target_node_id: "00000000-0000-0000-0000-000000000002",
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
