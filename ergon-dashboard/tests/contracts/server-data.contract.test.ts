import assert from "node:assert/strict";
import test from "node:test";

import { loadExperimentList } from "../../src/lib/server-data/experiments";
import { loadRunList } from "../../src/lib/server-data/samples";
import { getHarnessExperiment, resetDashboardHarness } from "../../src/lib/testing/dashboardHarness";

test("harness miss for experiment is represented as null, not notFound policy", () => {
  resetDashboardHarness();
  assert.equal(getHarnessExperiment("missing-experiment"), null);
});

test("experiment list server data keeps operational analytics fields", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify([
        {
          definition_id: "11111111-1111-1111-1111-111111111111",
          name: "MiniWob comparison",
          benchmark_type: "miniwob",
          sample_count: 12,
          status: "running",
          default_model_target: "openai:gpt-4.1",
          default_evaluator_slug: "judge-v1",
          created_at: "2026-05-20T12:00:00Z",
          run_count: 3,
          failure_count: 1,
          latest_activity_at: "2026-05-20T12:30:00Z",
          average_score: 0.82,
          average_duration_ms: 1234,
        },
      ]),
      { status: 200, headers: { "content-type": "application/json" } },
    );

  try {
    const result = await loadExperimentList();

    assert.equal(result.ok, true);
    assert.equal(result.ok && result.data[0].failure_count, 1);
    assert.equal(result.ok && result.data[0].latest_activity_at, "2026-05-20T12:30:00Z");
    assert.equal(result.ok && result.data[0].average_score, 0.82);
    assert.equal(result.ok && result.data[0].average_duration_ms, 1234);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("run list server data applies list filters and parses index summary fields", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(
      JSON.stringify([
        {
          id: "22222222-2222-2222-2222-222222222222",
          name: "alpha task 1",
          status: "completed",
          created_at: "2026-05-20T12:00:00Z",
          completed_at: "2026-05-20T12:10:00Z",
          latest_activity_at: "2026-05-20T12:10:00Z",
          duration_seconds: 600,
          definition_id: "11111111-1111-1111-1111-111111111111",
          definition_name: "MiniWob comparison",
          experiment: "alpha",
          benchmark_type: "miniwob",
          instance_key: "task-1",
          sample_id: "sample-1",
          sample_label: "task-1",
          evaluator_slug: "judge-v1",
          model_target: "openai:gpt-4.1",
          final_score: 0.88,
          return_value: 12.5,
          total_tasks: 3,
          completed_tasks: 2,
          failed_tasks: 1,
          running_tasks: 0,
          metrics: { pass_rate: 0.9 },
        },
      ]),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  };

  try {
    const result = await loadRunList({
      limit: 25,
      offset: 50,
      status: "completed",
      definitionId: "11111111-1111-1111-1111-111111111111",
      experiment: "alpha",
    });

    assert.match(requestedUrl, /\/samples\?/);
    assert.match(requestedUrl, /limit=25/);
    assert.match(requestedUrl, /offset=50/);
    assert.match(requestedUrl, /status=completed/);
    assert.match(requestedUrl, /definition_id=11111111-1111-1111-1111-111111111111/);
    assert.match(requestedUrl, /experiment=alpha/);
    assert.equal(result.ok, true);
    assert.equal(result.ok && result.data[0].name, "alpha task 1");
    assert.equal(result.ok && result.data[0].definition_name, "MiniWob comparison");
    assert.equal(result.ok && result.data[0].total_tasks, 3);
    assert.deepEqual(result.ok && result.data[0].metrics, { pass_rate: 0.9 });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
