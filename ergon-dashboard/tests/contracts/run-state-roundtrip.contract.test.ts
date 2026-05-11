import assert from "node:assert/strict";
import test from "node:test";

import { parseRunSnapshot } from "../../src/lib/contracts/rest";
import { hydrateRunSnapshot, serializeRunSnapshot } from "../../src/lib/run-state";
import { createDashboardSeed, FIXTURE_IDS } from "../helpers/dashboardFixtures";

test("run state serializes back into a valid wire run snapshot", () => {
  const run = createDashboardSeed().runs?.[0];
  assert.ok(run);

  const state = hydrateRunSnapshot(run);
  const wire = serializeRunSnapshot(state);
  const reparsed = parseRunSnapshot(wire);

  assert.equal(reparsed.id, FIXTURE_IDS.runId);
  assert.equal(reparsed.tasks[FIXTURE_IDS.solveTaskId]?.id, FIXTURE_IDS.solveTaskId);
});
