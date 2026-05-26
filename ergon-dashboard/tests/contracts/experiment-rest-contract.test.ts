import assert from "node:assert/strict";
import test from "node:test";

import {
  parseExperimentListState,
  parseExperimentState,
  type ExperimentDetailView,
} from "../../src/lib/contracts/rest";

const retiredIdentityPattern = new RegExp(["run" + "Id", "definitionId"].join("|"), "i");

export const fixtureExperimentDetail: ExperimentDetailView = {
  experimentId: "exp-1",
  name: "mixed-training",
  description: "mixed environment validation",
  environments: [
    {
      environmentId: "env-1",
      environmentName: "mini-validation",
      sourceMode: "materialized",
      sampleCount: 3,
      selectedCount: 2,
      sourceMetadata: { provider: "records" },
    },
  ],
  sampleCount: 3,
  samples: [
    {
      sampleId: "sample-1",
      experimentId: "exp-1",
      environmentId: "env-1",
      environmentName: "mini-validation",
      sampleKey: "problem-1",
      sampleRef: { id: "problem-1" },
      sourceMetadata: { provider: "records" },
      status: "completed",
      createdAt: "2026-05-26T00:00:00Z",
    },
  ],
  samplerInvocations: [
    {
      samplerInvocationId: "sampler-1",
      samplerName: "RandomSampler",
      requestedK: 2,
      candidatePoolSize: 3,
      selectedCount: 2,
      samplerConfig: {},
      createdAt: "2026-05-26T00:00:00Z",
    },
  ],
  metadata: {},
  createdAt: "2026-05-26T00:00:00Z",
};

test("experiment contract has environments and sample ids", () => {
  const parsed = parseExperimentState(fixtureExperimentDetail);

  assert.equal(parsed.environments[0].environmentName, "mini-validation");
  assert.equal(parsed.samples[0].sampleId, "sample-1");
  assert.doesNotMatch(JSON.stringify(parsed), retiredIdentityPattern);
});

test("experiment list contract wraps sample-centered experiment items", () => {
  const parsed = parseExperimentListState({ items: [fixtureExperimentDetail] });

  assert.equal(parsed.items[0].experimentId, "exp-1");
  assert.equal(parsed.items[0].samplerInvocations[0].selectedCount, 2);
});
