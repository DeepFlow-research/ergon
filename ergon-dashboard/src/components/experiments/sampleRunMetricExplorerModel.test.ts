import assert from "node:assert/strict";
import test from "node:test";

import type { ExperimentRunRow } from "@/lib/contracts/rest";

import {
  formatRunMetricValue,
  metricDescriptor,
  normalizeRunMetricPoint,
  selectSampleRunMetricExplorerView,
  type RunMetricPoint,
} from "./sampleRunMetricExplorerModel";

const definitionId = "11111111-1111-4111-8111-111111111111";
const defaultSampleId = "22222222-2222-4222-8222-222222222222";

function metrics(overrides: Partial<ExperimentRunRow["metrics"]> = {}): ExperimentRunRow["metrics"] {
  return {
    sample_id: defaultSampleId,
    status: "completed",
    instance_key: "sample-a",
    tool_call_count: 0,
    cost_observed: false,
    ...overrides,
  };
}

function runRow(overrides: Partial<ExperimentRunRow> = {}): ExperimentRunRow {
  return {
    sample_id: defaultSampleId,
    definition_id: definitionId,
    benchmark_type: "minif2f",
    instance_key: "sample-a",
    status: "completed",
    created_at: "2026-03-18T11:59:30.000Z",
    started_at: "2026-03-18T12:00:00.000Z",
    completed_at: "2026-03-18T12:00:24.000Z",
    evaluator_slug: "lean-evaluator",
    model_target: "openai:gpt-5",
    worker_team: {},
    seed: null,
    running_time_ms: 24_000,
    final_score: 0.75,
    total_tasks: 10,
    total_cost_usd: 0.12,
    error_message: null,
    metrics: metrics(),
    ...overrides,
  };
}

function point(index: number): RunMetricPoint {
  return normalizeRunMetricPoint(
    runRow({
      sample_id: `${String(index).padStart(8, "0")}-2222-4222-8222-222222222222`,
      instance_key: `sample-${index}`,
      final_score: index / 10,
      running_time_ms: index * 1000,
    }),
  );
}

test("normalizes row metrics once for cards, table, and explorer", () => {
  const normalized = normalizeRunMetricPoint(
    runRow({
      metrics: {
        ...metrics(),
        run_name: "run-alpha",
        sample_label: "friendly sample",
        score: 0.9,
        duration_ms: 15_000,
        total_tasks: 12,
        tool_call_count: 7,
      },
    }),
  );

  assert.equal(normalized.runName, "run-alpha");
  assert.equal(normalized.sampleLabel, "friendly sample");
  assert.deepEqual(normalized.metrics.score, { value: 0.9, available: true });
  assert.deepEqual(normalized.metrics.duration_ms, { value: 15_000, available: true });
  assert.deepEqual(normalized.metrics.total_tasks, { value: 12, available: true });
  assert.deepEqual(normalized.metrics.tool_call_count, { value: 7, available: true });
});

test("does not treat historical cost defaults as observed cost", () => {
  const normalized = normalizeRunMetricPoint(runRow({ total_cost_usd: 0.12 }));

  assert.equal(normalized.metrics.total_cost_usd.available, false);
  assert.equal(normalized.metrics.total_cost_usd.value, null);
  assert.equal(formatRunMetricValue(metricDescriptor("total_cost_usd"), normalized.metrics.total_cost_usd), "Observed cost unavailable");
});

test("uses explicit observed token and cost instrumentation when present", () => {
  const normalized = normalizeRunMetricPoint(
    runRow({
      metrics: {
        ...metrics(),
        total_tokens: 1234,
        token_breakdown: { prompt: 700, assistant_text: 534 },
        total_cost_usd: 0.0345,
        cost_observed: true,
      },
    }),
  );

  assert.deepEqual(normalized.metrics.total_tokens, { value: 1234, available: true });
  assert.deepEqual(normalized.tokenBreakdown, { prompt: 700, assistant_text: 534 });
  assert.deepEqual(normalized.metrics.total_cost_usd, { value: 0.0345, available: true });
});

test("selects small-n explorer views by mode and numeric threshold", () => {
  assert.equal(selectSampleRunMetricExplorerView("1d", [point(1), point(2), point(3), point(4)], "score"), "ranked-list");
  assert.equal(selectSampleRunMetricExplorerView("1d", Array.from({ length: 5 }, (_, index) => point(index + 1)), "score"), "strip");
  assert.equal(selectSampleRunMetricExplorerView("1d", Array.from({ length: 20 }, (_, index) => point(index + 1)), "score"), "histogram");
  assert.equal(selectSampleRunMetricExplorerView("2d", [point(1), point(2)], "score", "duration_ms"), "too-few-points");
  assert.equal(selectSampleRunMetricExplorerView("2d", [point(1), point(2), point(3)], "score", "duration_ms"), "scatter");
});

test("formats available and unavailable metric states", () => {
  assert.equal(formatRunMetricValue(metricDescriptor("duration_ms"), { value: 1500, available: true }), "1.5s");
  assert.equal(formatRunMetricValue(metricDescriptor("score"), { value: 0.875, available: true }), "0.88");
  assert.equal(formatRunMetricValue(metricDescriptor("total_tokens"), { value: null, available: false }), "Token usage not instrumented");
});
