import assert from "node:assert/strict";
import test from "node:test";

import fixture from "../../../tests/fixtures/mas-runs/concurrent-mas-run.json";
import { parseGraphMutationDtoArray } from "@/features/graph/contracts/graphMutations";
import { replayToSequence } from "@/features/graph/state/graphMutationReducer";
import { buildRunEvents } from "@/lib/runEvents";
import { deserializeRunState } from "@/lib/runState";
import type { WorkflowRunState } from "@/lib/types";
import { buildRunActivities } from "./buildRunActivities";
import { stackActivities } from "./stackLayout";

function emptyRunStateFrom(runState: WorkflowRunState): WorkflowRunState {
  return {
    ...runState,
    tasks: new Map(),
    resourcesByTask: new Map(),
    executionsByTask: new Map(),
    sandboxesByTask: new Map(),
    threads: [],
    contextEventsByTask: new Map(),
    evaluationsByTask: new Map(),
    totalTasks: 0,
    totalLeafTasks: 0,
    completedTasks: 0,
    runningTasks: 0,
    failedTasks: 0,
    edges: new Map(),
    annotationsByTarget: new Map(),
    unhandledMutations: [],
  };
}

test("golden concurrent fixture replays the whole graph at selected sequence and stacks overlapping activity", () => {
  const runState = deserializeRunState(fixture.runState);
  const mutations = parseGraphMutationDtoArray(fixture.mutations);
  const checkpoint = fixture.checkpoints.find((entry) => entry.sequence === 14);
  assert.ok(checkpoint);

  const displayState = replayToSequence(
    mutations,
    checkpoint.sequence,
    emptyRunStateFrom(runState),
    new Map(),
  );
  const activities = buildRunActivities({
    runState,
    events: buildRunEvents(runState),
    mutations,
    currentSequence: checkpoint.sequence,
  });
  const stack = stackActivities(activities);

  assert.deepEqual(
    new Set(displayState.tasks.keys()),
    new Set(checkpoint.expectedTaskIds),
  );
  assert.equal(stack.maxConcurrency, checkpoint.expectedMaxConcurrency);
});
