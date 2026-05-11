import assert from "node:assert/strict";
import test from "node:test";

import { getHarnessExperiment, resetDashboardHarness } from "../../src/lib/testing/dashboardHarness";

test("harness miss for experiment is represented as null, not notFound policy", () => {
  resetDashboardHarness();
  assert.equal(getHarnessExperiment("missing-experiment"), null);
});
