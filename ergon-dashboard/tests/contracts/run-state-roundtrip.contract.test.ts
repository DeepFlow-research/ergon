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

test("run snapshot hydration preserves nested run metrics for header display", () => {
  const run = createDashboardSeed().runs?.[0];
  assert.ok(run);

  const state = hydrateRunSnapshot({
    ...run,
    metrics: {
      runId: FIXTURE_IDS.runId,
      status: "failed",
      durationMs: 9000,
      totalTasks: 3,
      toolCallCount: 2,
      totalTokens: 1234,
      tokenBreakdown: { prompt: 1000, assistant_text: 234 },
      totalCostUsd: 0.42,
      costObserved: true,
    },
  }) as ReturnType<typeof hydrateRunSnapshot> & {
    metrics?: {
      totalTokens: number | null;
      totalCostUsd: number | null;
      costObserved: boolean;
    };
  };

  assert.equal(state.metrics?.totalTokens, 1234);
  assert.equal(state.metrics?.totalCostUsd, 0.42);
  assert.equal(state.metrics?.costObserved, true);
});
