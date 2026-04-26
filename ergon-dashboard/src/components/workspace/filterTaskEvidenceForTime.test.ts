import assert from "node:assert/strict";
import test from "node:test";

import fixture from "../../../tests/fixtures/mas-runs/concurrent-mas-run.json";
import { deserializeRunState } from "@/lib/runState";
import { filterTaskEvidenceForTime } from "./filterTaskEvidenceForTime";

const searchTaskId = "10000000-0000-4000-8000-000000000002";

test("filterTaskEvidenceForTime hides task evidence created after the selected timeline time", () => {
  const runState = deserializeRunState(fixture.runState);
  const filtered = filterTaskEvidenceForTime({
    resources: runState.resourcesByTask.get(searchTaskId) ?? [],
    executions: runState.executionsByTask.get(searchTaskId) ?? [],
    sandbox: runState.sandboxesByTask.get(searchTaskId),
    threads: runState.threads,
    evaluation: runState.evaluationsByTask.get(searchTaskId) ?? null,
    contextEvents: runState.contextEventsByTask.get(searchTaskId) ?? [],
    selectedTime: "2026-04-26T12:00:10.000Z",
  });

  assert.equal(filtered.resources.length, 0);
  assert.equal(filtered.executions.length, 1);
  assert.equal(filtered.sandbox?.commands.length, 0);
  assert.equal(filtered.contextEvents.length, 1);
});

test("filterTaskEvidenceForTime returns unfiltered task evidence in live mode", () => {
  const runState = deserializeRunState(fixture.runState);
  const filtered = filterTaskEvidenceForTime({
    resources: runState.resourcesByTask.get(searchTaskId) ?? [],
    executions: runState.executionsByTask.get(searchTaskId) ?? [],
    sandbox: runState.sandboxesByTask.get(searchTaskId),
    threads: runState.threads,
    evaluation: runState.evaluationsByTask.get(searchTaskId) ?? null,
    contextEvents: runState.contextEventsByTask.get(searchTaskId) ?? [],
    selectedTime: null,
  });

  assert.equal(filtered.resources.length, 1);
  assert.equal(filtered.sandbox?.commands.length, 1);
});
