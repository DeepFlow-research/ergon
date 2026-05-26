import assert from "node:assert/strict";
import test from "node:test";

import {
  parseSampleDetail,
  parseSampleEvents,
  parseSampleGraph,
  type SampleDetailView,
  type SampleEventsView,
  type SampleGraphView,
} from "../../src/lib/contracts/rest";

const retiredSamplePattern = new RegExp(["run" + "Id", "definitionId"].join("|"), "i");
const retiredEventPattern = new RegExp(["GraphMutation", "mutation", "run" + "Id"].join("|"), "i");

export const fixtureSampleDetail: SampleDetailView = {
  sampleId: "sample-1",
  experimentId: "exp-1",
  environmentId: "env-1",
  environmentName: "mini-validation",
  sampleKey: "problem-1",
  sampleRef: { id: "problem-1" },
  sourceMetadata: { provider: "records" },
  status: "completed",
  createdAt: "2026-05-26T00:00:00Z",
  startedAt: "2026-05-26T00:00:01Z",
  completedAt: "2026-05-26T00:00:05Z",
};

export const fixtureSampleEvents: SampleEventsView = {
  items: [
    {
      eventId: "event-1",
      sampleId: "sample-1",
      eventType: "sample.status_changed",
      targetType: "sample",
      targetId: null,
      timestamp: "2026-05-26T00:00:00Z",
      payload: { status: "pending" },
    },
    {
      eventId: "event-2",
      sampleId: "sample-1",
      eventType: "task.added",
      targetType: "task",
      targetId: "task-1",
      timestamp: "2026-05-26T00:00:01Z",
      payload: { task_slug: "prove" },
    },
  ],
};

export const fixtureSampleGraph: SampleGraphView = {
  nodes: [
    {
      taskId: "task-1",
      taskSlug: "prove",
      description: "Prove the theorem",
      status: "pending",
      parentTaskId: null,
      level: 0,
      assignedWorkerSlug: "lean-worker",
      createdAt: "2026-05-26T00:00:00Z",
      updatedAt: "2026-05-26T00:00:01Z",
    },
  ],
  edges: [],
};

test("sample detail contract exposes provenance", () => {
  const parsed = parseSampleDetail(fixtureSampleDetail);

  assert.equal(parsed.sampleId, "sample-1");
  assert.equal(parsed.environmentName, "mini-validation");
  assert.doesNotMatch(JSON.stringify(parsed), retiredSamplePattern);
});

test("sample contract has events not mutations", () => {
  const parsed = parseSampleEvents(fixtureSampleEvents);

  assert.equal(parsed.items[0].eventType, "sample.status_changed");
  assert.equal(parsed.items[1].eventType, "task.added");
  assert.doesNotMatch(JSON.stringify(parsed), retiredEventPattern);
});

test("sample graph contract exposes projected tasks", () => {
  const parsed = parseSampleGraph(fixtureSampleGraph);

  assert.equal(parsed.nodes[0].taskSlug, "prove");
  assert.equal(parsed.edges.length, 0);
});
