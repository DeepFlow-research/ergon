import assert from "node:assert/strict";
import test from "node:test";

import type { GraphMutationDto } from "@/features/graph/contracts/graphMutations";
import { resolveReplayStep } from "./replayNavigation";

function mutation(sequence: number, id = `mutation-${sequence}`): GraphMutationDto {
  return {
    id,
    sample_id: "run-1",
    sequence,
    mutation_type: "node.status_changed",
    target_type: "node",
    target_id: "task-1",
    actor: "test",
    old_value: null,
    new_value: { mutation_type: "node.status_changed", status: "running" },
    reason: "test",
    created_at: new Date(1_700_000_000_000 + sequence).toISOString(),
  };
}

test("replay arrow navigation can enter replay mode when timeline is collapsed", () => {
  const mutations = [mutation(10), mutation(20), mutation(30)];

  assert.equal(resolveReplayStep(mutations, null, "next"), 10);
  assert.equal(resolveReplayStep(mutations, null, "previous"), 30);
});

test("replay arrow navigation steps through existing snapshot sequences", () => {
  const mutations = [mutation(10), mutation(20), mutation(30)];

  assert.equal(resolveReplayStep(mutations, 20, "previous"), 10);
  assert.equal(resolveReplayStep(mutations, 20, "next"), 30);
  assert.equal(resolveReplayStep(mutations, 10, "previous"), 10);
  assert.equal(resolveReplayStep(mutations, 30, "next"), 30);
});

test("replay arrow navigation skips duplicate mutation sequence numbers", () => {
  const mutations = [
    mutation(6),
    mutation(7, "mutation-7a"),
    mutation(7, "mutation-7b"),
    mutation(8),
  ];

  assert.equal(resolveReplayStep(mutations, 7, "next"), 8);
  assert.equal(resolveReplayStep(mutations, 7, "previous"), 6);
});
