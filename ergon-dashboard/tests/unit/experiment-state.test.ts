import assert from "node:assert/strict";
import test from "node:test";

import { buildExperimentState } from "../../src/lib/sample-state/dashboard";
import { fixtureExperimentDetail } from "../contracts/experiment-rest-contract.test";

test("experiment state exposes environments and samples without run vocabulary", () => {
  const state = buildExperimentState(fixtureExperimentDetail);

  assert.equal(state.environments[0].environmentName, "mini-validation");
  assert.equal(state.samples[0].sampleId, "sample-1");
  assert.doesNotMatch(JSON.stringify(state), /runId|definitionId|mutation/i);
});
