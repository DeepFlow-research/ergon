import assert from "node:assert/strict";
import test from "node:test";

import fixture from "../../../tests/fixtures/mas-runs/concurrent-mas-run.json";
import { parseGraphMutationDtoArray } from "@/features/graph/contracts/graphMutations";
import { buildRunEvents } from "@/lib/runEvents";
import { deserializeRunState } from "@/lib/runState";
import { buildRunActivities } from "./buildRunActivities";

test("buildRunActivities derives spans and markers without creating agent lanes", () => {
  const runState = deserializeRunState(fixture.runState);
  const mutations = parseGraphMutationDtoArray(fixture.mutations);
  const events = buildRunEvents(runState);

  const activities = buildRunActivities({
    runState,
    events,
    mutations,
    currentSequence: 14,
  });

  assert.ok(
    activities.some(
      (activity) =>
        activity.kind === "execution" &&
        activity.taskId === "10000000-0000-4000-8000-000000000002" &&
        activity.isInstant === false,
    ),
  );
  assert.ok(
    activities.some(
      (activity) =>
        activity.kind === "graph" &&
        activity.sequence === 10 &&
        activity.taskId === "10000000-0000-4000-8000-000000000003",
    ),
  );
  assert.ok(activities.some((activity) => activity.kind === "artifact"));
  assert.ok(activities.some((activity) => activity.kind === "evaluation"));
  assert.equal(
    activities.some((activity) => "laneId" in activity.metadata),
    false,
  );
});
