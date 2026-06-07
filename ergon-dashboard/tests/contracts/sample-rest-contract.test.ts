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

const sampleId = "00000000-0000-4000-8000-000000000001";
const experimentId = "00000000-0000-4000-8000-000000000002";
const environmentId = "00000000-0000-4000-8000-000000000003";
const statusEventId = "00000000-0000-4000-8000-000000000004";
const taskEventId = "00000000-0000-4000-8000-000000000005";
const taskId = "00000000-0000-4000-8000-000000000006";

export const fixtureSampleDetail: SampleDetailView = {
  sampleId,
  experimentId,
  environmentId,
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
      eventId: statusEventId,
      sampleId,
      eventType: "sample.status_changed",
      targetType: "sample",
      targetId: sampleId,
      status: "pending",
      timestamp: "2026-05-26T00:00:00Z",
      payload: { status: "pending" },
    },
    {
      eventId: taskEventId,
      sampleId,
      eventType: "task.added",
      targetType: "task",
      targetId: taskId,
      taskSlug: "prove",
      status: "pending",
      timestamp: "2026-05-26T00:00:01Z",
      payload: { task_slug: "prove" },
    },
  ],
};

export const fixtureSampleGraph: SampleGraphView = {
  nodes: [
    {
      taskId,
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

  assert.equal(parsed.sampleId, sampleId);
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
