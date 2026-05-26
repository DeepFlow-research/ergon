import assert from "node:assert/strict";
import test from "node:test";

import { buildSampleState } from "../../src/lib/sample-state/dashboard";
import { fixtureSampleDetail, fixtureSampleEvents, fixtureSampleGraph } from "../contracts/sample-rest-contract.test";

const retiredIdentityPattern = new RegExp(["GraphMutation", "run" + "Id", "definitionId"].join("|"), "i");

test("sample state stores typed WAL events and graph projection", () => {
  const state = buildSampleState({
    detail: fixtureSampleDetail,
    events: fixtureSampleEvents.items,
    graph: fixtureSampleGraph,
  });

  assert.deepEqual(
    state.events.map((event) => event.eventType),
    ["sample.status_changed", "task.added"],
  );
  assert.equal(state.graph.nodes[0].taskSlug, "prove");
  assert.doesNotMatch(JSON.stringify(state), retiredIdentityPattern);
});
