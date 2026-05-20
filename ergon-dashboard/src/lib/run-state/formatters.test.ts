import assert from "node:assert/strict";
import test from "node:test";

import {
  formatCost,
  formatDuration,
  formatScore,
  formatTaskCount,
  formatTokens,
  unavailableMetric,
} from "./formatters";

test("formats unavailable metric values explicitly", () => {
  assert.deepEqual(unavailableMetric("not reported"), {
    value: "Unavailable",
    detail: "not reported",
    isUnavailable: true,
  });
  assert.equal(formatScore(null).value, "Unavailable");
  assert.equal(formatCost(null, false).detail, "cost not observed");
});

test("formats run metric values consistently", () => {
  assert.equal(formatScore(0.81234).value, "81.2%");
  assert.equal(formatCost(0.00491, true).value, "$0.0049");
  assert.equal(formatCost(12.5, true).value, "$12.50");
  assert.equal(formatTokens(15320).value, "15.3K");
  assert.equal(formatDuration(92.4).value, "1m 32s");
  assert.equal(formatTaskCount({ completed: 4, running: 1, failed: 2, total: 10 }).value, "4 / 10");
});
